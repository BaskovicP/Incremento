"""
web_dock.py — Web browsing dock (QWebEngineView with persistent profile).

Displays web pages in a right-side dock that persists across card reviews.
The last-visited URL is saved when the page finishes loading.

Public API:
    show_web_in_dock(card_id, home_url, last_url)
    open_web_location(card_id, target_url)
    on_web_question_shown(card)
    on_web_reviewer_will_end()
    on_add_cards_did_add_note(note)
    sync_web_note_type()
    add_web_function()
"""

import json
import math
import os
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from html import escape
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from aqt import mw
from aqt.utils import showInfo, tooltip
from aqt.qt import (
    QApplication,
    QCheckBox,
    QDialog,
    QDockWidget,
    QEvent,
    QFrame,
    QHBoxLayout,
    QGridLayout,
    QInputDialog,
    QLabel,
    QObject,
    QPoint,
    QPushButton,
    QRect,
    QShortcut,
    QKeySequence,
    QSizePolicy,
    QStyle,
    QTextBrowser,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    qconnect,
)
from PyQt6.QtCore import QRectF, QUrl
from PyQt6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.i18n import get_locale, t, tn
except ImportError:
    from backend.i18n import get_locale, t, tn


def _web_card_count_label(count: int) -> str:
    return tn("reader_web_cards_count", count)


def _web_bookmark_count_label(count: int) -> str:
    return tn("reader_web_bookmarks_count", count)

try:
    from ..backend import paths as _paths
    from ..backend.content_safety import (
        external_plain_text,
        external_plain_text_to_anki_html,
    )
    from ..backend.paths import get_active_profile as _active_profile
    from ..backend.video_manager import fmt_time as _fmt_media_time
    from ..backend.web_extract_anchors import (
        MAX_PENDING_WEB_EXTRACT_RECORDS,
        MAX_STORED_WEB_EXTRACT_ANCHORS,
        normalize_web_extract_anchor,
        normalize_web_extract_record,
        normalize_web_extract_records,
        normalize_web_extract_url,
    )
except ImportError:
    from backend import paths as _paths  # type: ignore
    from content_safety import external_plain_text, external_plain_text_to_anki_html  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore
    from video_manager import fmt_time as _fmt_media_time  # type: ignore
    from web_extract_anchors import (  # type: ignore
        MAX_PENDING_WEB_EXTRACT_RECORDS,
        MAX_STORED_WEB_EXTRACT_ANCHORS,
        normalize_web_extract_anchor,
        normalize_web_extract_record,
        normalize_web_extract_records,
        normalize_web_extract_url,
    )

try:
    from ..backend.db import (
        add_web_card_source,
        get_web_card_sources,
        get_web_extract_anchors,
    )
    from ..backend.web_manager import (
        WEB_NOTE_TYPE,
        add_web_card,
        build_web_media_resume_target,
        build_web_restore_payload,
        build_external_web_url,
        configured_track_web_window_with_extension,
        configured_prefer_web_card_resume_in_original_page,
        configured_remember_browser_card_scroll,
        ensure_web_note_type,
        get_web_progress,
        get_web_url,
        set_web_scroll_position,
        set_web_url,
    )
    from ..backend.reader_bookmarks import (
        add_reader_bookmark,
        delete_reader_bookmark,
        list_reader_bookmarks,
    )
except ImportError:
    from db import add_web_card_source, get_web_card_sources, get_web_extract_anchors
    from web_manager import (
        WEB_NOTE_TYPE,
        add_web_card,
        build_web_media_resume_target,
        build_web_restore_payload,
        build_external_web_url,
        configured_track_web_window_with_extension,
        configured_prefer_web_card_resume_in_original_page,
        configured_remember_browser_card_scroll,
        ensure_web_note_type,
        get_web_progress,
        get_web_url,
        set_web_scroll_position,
        set_web_url,
    )
    from reader_bookmarks import add_reader_bookmark, delete_reader_bookmark, list_reader_bookmarks  # type: ignore

try:
    from .reader_shell import configure_reader_shell_buttons
except ImportError:
    from reader_shell import configure_reader_shell_buttons  # type: ignore

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_WEB_BRIDGE_JS_PATH = os.path.join(_ADDON_DIR, "web", "web_dock_bridge.js")

_PYCMD_BRIDGE = "__incremento_webdock_pycmd__:"
_MSG_SELECTION_STATE = "incremento_selection_state:"
_MSG_FILL_FIELD = "incremento_web_fill_field:"
_MSG_SNAPSHOT = "incremento_web_snapshot:"
_MSG_PROGRESS = "incremento_web_progress:"
_MAX_WEB_BRIDGE_MESSAGE_CHARS = 64_000
_MAX_WEB_HIGHLIGHT_SCRIPT_CHARS = 512_000
_MAX_NATIVE_WEB_EXTRACTION_RECTS = 512
_MAX_NATIVE_WEB_RECTS_PER_MARKER = 128


@dataclass
class _WebDockRuntime:
    dock: object | None = None
    current_card_id: int | None = None
    current_home_url: str | None = None
    profile: object | None = None
    track_window_with_extension: bool = False
    shortcuts_registered: bool = False
    shortcuts: list[object] = field(default_factory=list)
    interaction_filter: object | None = None
    snapshot_mode: bool = False
    snapshot_origin: QPoint | None = None
    snapshot_shield: object | None = None
    snapshot_overlay: object | None = None
    snapshot_override_cursor: bool = False
    pending_restore: dict | None = None
    pending_bookmark_restore: dict | None = None
    bridge_js_template: str | None = None
    pending_extract_profile: str = ""
    pending_extract_records: list[dict] = field(default_factory=list)
    extraction_overlay: object | None = None
    extraction_refresh_generation: int = 0
    extraction_schedule_generation: int = 0


_runtime = _WebDockRuntime()


class _WebExtractionOverlay(QWidget):
    """Pointer-transparent native paint layer above untrusted Web content."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._markers: list[dict] = []
        self._scroll_x = 0.0
        self._scroll_y = 0.0
        self._zoom_factor = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(False)
        self.hide()

    def set_markers(
        self,
        markers: list[dict],
        *,
        scroll_x: float,
        scroll_y: float,
    ) -> None:
        self._markers = list(markers)
        self._scroll_x = float(scroll_x)
        self._scroll_y = float(scroll_y)
        if self._markers:
            self.raise_()
            self.show()
        else:
            self.hide()
        self.update()

    def set_scroll_position(self, x: float, y: float) -> None:
        self._scroll_x = float(x)
        self._scroll_y = float(y)
        if self._markers:
            self.update()

    def upsert_marker(
        self,
        marker: dict,
        *,
        scroll_x: float,
        scroll_y: float,
    ) -> None:
        marker_id = str(marker.get("id") or "")
        retained = [
            item for item in self._markers if str(item.get("id") or "") != marker_id
        ]
        retained.append(marker)
        self.set_markers(
            retained[-MAX_STORED_WEB_EXTRACT_ANCHORS:],
            scroll_x=scroll_x,
            scroll_y=scroll_y,
        )

    def remove_marker(self, marker_id: str) -> None:
        retained = [
            item
            for item in self._markers
            if str(item.get("id") or "") != str(marker_id or "")
        ]
        self.set_markers(
            retained,
            scroll_x=self._scroll_x,
            scroll_y=self._scroll_y,
        )

    def set_marker_state(self, marker_id: str, state: str) -> None:
        changed = False
        markers: list[dict] = []
        for item in self._markers:
            marker = dict(item)
            if str(marker.get("id") or "") == str(marker_id or ""):
                marker["state"] = state
                changed = True
            markers.append(marker)
        if changed:
            self.set_markers(
                markers,
                scroll_x=self._scroll_x,
                scroll_y=self._scroll_y,
            )

    def set_zoom_factor(self, value: float) -> None:
        try:
            zoom = float(value)
        except (TypeError, ValueError):
            zoom = 1.0
        self._zoom_factor = max(0.25, min(5.0, zoom))
        if self._markers:
            self.update()

    def paintEvent(self, _event) -> None:
        if not self._markers:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            viewport = QRectF(self.rect())
            for marker in self._markers:
                pending = marker["state"] == "pending"
                snapshot = marker["kind"] == "snapshot"
                fill = QColor(245, 158, 11, 92) if pending else QColor(34, 197, 94, 87)
                edge = QColor(180, 83, 9, 245) if pending else QColor(21, 128, 61, 235)
                line_style = (
                    Qt.PenStyle.DashLine
                    if pending and snapshot
                    else Qt.PenStyle.DotLine
                    if pending
                    else Qt.PenStyle.SolidLine
                )
                pen = QPen(edge, 3.0 if snapshot else 2.0, line_style)
                painter.setPen(pen)
                painter.setBrush(fill)
                for raw_rect in marker["rects"]:
                    rect = QRectF(
                        (float(raw_rect["x"]) - self._scroll_x)
                        * self._zoom_factor,
                        (float(raw_rect["y"]) - self._scroll_y)
                        * self._zoom_factor,
                        float(raw_rect["width"]) * self._zoom_factor,
                        float(raw_rect["height"]) * self._zoom_factor,
                    )
                    if not rect.intersects(viewport):
                        continue
                    if snapshot:
                        painter.drawRoundedRect(rect, 4.0, 4.0)
                    else:
                        painter.fillRect(rect, fill)
                        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        finally:
            painter.end()


def _run_web_javascript(page, script: str, callback=None) -> None:
    """Run Incremento helpers outside the remote page's JavaScript world."""
    world_id = int(QWebEngineScript.ScriptWorldId.ApplicationWorld.value)
    try:
        if callback is None:
            page.runJavaScript(script, world_id)
        else:
            page.runJavaScript(script, world_id, callback)
    except TypeError:
        if callback is None:
            page.runJavaScript(script)
        else:
            page.runJavaScript(script, callback)


def current_web_card_id() -> int | None:
    try:
        return int(_runtime.current_card_id) if _runtime.current_card_id is not None else None
    except Exception:
        return None


def _remember_browser_card_scroll() -> bool:
    try:
        return bool(configured_remember_browser_card_scroll())
    except Exception:
        return True


def _prefer_web_card_resume_in_original_page() -> bool:
    try:
        return bool(configured_prefer_web_card_resume_in_original_page())
    except Exception:
        return True


def _track_web_window_with_extension_default() -> bool:
    try:
        return bool(configured_track_web_window_with_extension())
    except Exception:
        return True


def _web_progress_state(card_id: int | None = None) -> dict:
    return _controller.progress_state(card_id)


def _refresh_web_bookmark_button() -> None:
    _controller.refresh_bookmark_button()


def _refresh_web_resume_button() -> None:
    _controller.refresh_resume_button()


def _persist_web_url(card_id: int | None, url: str | None) -> None:
    try:
        target_card_id = int(card_id) if card_id is not None else 0
    except Exception:
        target_card_id = 0
    target_url = str(url or "").strip()
    if target_card_id <= 0 or not target_url or target_url == "about:blank":
        return
    try:
        set_web_url(_ADDON_DIR, _active_profile(), target_card_id, target_url)
    except Exception:
        pass


def _persist_web_scroll(card_id: int | None, data) -> None:
    if not _remember_browser_card_scroll():
        return
    try:
        target_card_id = int(card_id if card_id is not None else _runtime.current_card_id)
    except Exception:
        target_card_id = 0
    if target_card_id <= 0 or not isinstance(data, dict):
        return
    target_url = str(data.get("url") or "").strip()
    if not target_url or target_url == "about:blank":
        return
    try:
        scroll_ratio = float(data.get("scrollRatio", 0.0) or 0.0)
    except Exception:
        scroll_ratio = 0.0
    try:
        set_web_scroll_position(
            _ADDON_DIR,
            _active_profile(),
            target_card_id,
            target_url,
            max(0.0, min(scroll_ratio, 1.0)),
        )
    except Exception:
        pass


def _persist_current_web_state() -> None:
    _controller.persist_current_state()


def _source_url_label(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return "Source"
    try:
        parsed = urlparse(raw)
        label = f"{parsed.netloc}{parsed.path or ''}"
        if parsed.fragment:
            label += f"#{parsed.fragment}"
        if not label:
            label = raw
    except Exception:
        label = raw
    label = label.strip() or raw
    return label if len(label) <= 72 else label[:69] + "..."


def _strip_resume_fragment(fragment: str) -> str:
    raw = str(fragment or "").lstrip("#").strip()
    if not raw:
        return ""
    marker = "__incremento_resume__=1"
    idx = raw.find(marker)
    if idx < 0:
        return raw
    return raw[:idx].rstrip("&?")


def _build_resume_tracking_url(
    url: str,
    *,
    card_id: int,
    seconds: float,
    media_url: str = "",
) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    sec = max(0, int(float(seconds or 0.0)))
    base = build_external_web_url(raw, card_id=card_id, track_with_extension=True)
    if sec <= 0:
        return base

    clean_media_url = str(media_url or "").strip()
    try:
        parsed = urlparse(base)
        fragment_parts = []
        existing_fragment = _strip_resume_fragment(parsed.fragment)
        if existing_fragment:
            fragment_parts.append(existing_fragment)
        fragment_parts.append("__incremento_resume__=1")
        fragment_parts.append(f"inc_resume_sec={sec}")
        if clean_media_url:
            fragment_parts.append(f"inc_resume_media={quote(clean_media_url, safe='')}")
        return urlunparse(parsed._replace(fragment="&".join(fragment_parts)))
    except Exception:
        fragment = f"__incremento_resume__=1&inc_resume_sec={sec}"
        if clean_media_url:
            fragment += f"&inc_resume_media={quote(clean_media_url, safe='')}"
        sep = "#" if "#" not in base else "&"
        return f"{base}{sep}{fragment}"


def _load_web_bridge_js_template() -> str:
    if _runtime.bridge_js_template is None:
        with open(_WEB_BRIDGE_JS_PATH, "r", encoding="utf-8") as fh:
            _runtime.bridge_js_template = fh.read()
    return _runtime.bridge_js_template


def _standard_icon(pixmap: QStyle.StandardPixmap):
    try:
        return mw.style().standardIcon(pixmap)
    except Exception:
        return None


def _make_web_button(
    parent,
    text: str,
    tooltip_text: str = "",
    *,
    icon=None,
) -> QPushButton:
    btn = QPushButton(text, parent)
    if tooltip_text:
        btn.setToolTip(tooltip_text)
    if icon is not None:
        btn.setIcon(icon)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return btn


def _make_web_group(parent, title: str, *widgets: QWidget) -> QWidget:
    frame = QFrame(parent)
    frame.setFrameShape(QFrame.Shape.NoFrame)
    frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    frame.setStyleSheet(
        "QFrame {"
        " background: rgba(255,255,255,0.03);"
        " border: 1px solid rgba(120,120,120,0.18);"
        " border-radius: 9px;"
        " }"
    )
    row = QHBoxLayout(frame)
    row.setContentsMargins(8, 5, 8, 5)
    row.setSpacing(5)

    tag = QLabel(title, frame)
    tag.setStyleSheet("color: #777; font-size: 10px; font-weight: 600;")
    row.addWidget(tag)
    for widget in widgets:
        row.addWidget(widget)
    return frame


class _WebDockController:
    def __init__(self, runtime: _WebDockRuntime):
        self.runtime = runtime

    def progress_state(self, card_id: int | None = None) -> dict:
        try:
            target_card_id = int(
                card_id if card_id is not None else self.runtime.current_card_id
            )
        except Exception:
            target_card_id = 0
        if target_card_id <= 0:
            return {
                "url": "",
                "scroll_ratio": 0.0,
                "bookmark_url": "",
                "bookmark_payload": {},
                "media_url": "",
                "media_title": "",
                "media_seconds": 0.0,
                "media_updated_at": 0,
            }
        try:
            return get_web_progress(_ADDON_DIR, _active_profile(), target_card_id)
        except Exception:
            return {
                "url": "",
                "scroll_ratio": 0.0,
                "bookmark_url": "",
                "bookmark_payload": {},
                "media_url": "",
                "media_title": "",
                "media_seconds": 0.0,
                "media_updated_at": 0,
            }

    def current_display_url(self) -> str:
        if self.runtime.dock is not None:
            try:
                current = (self.runtime.dock._view.url().toString() or "").strip()
                if current and current != "about:blank":
                    return current
            except Exception:
                pass
        return str(self.runtime.current_home_url or "").strip()

    def persist_current_state(self) -> None:
        try:
            target_card_id = (
                int(self.runtime.current_card_id)
                if self.runtime.current_card_id is not None
                else 0
            )
        except Exception:
            target_card_id = 0
        if self.runtime.dock is None:
            _persist_web_url(target_card_id, self.current_display_url())
            return
        current_url = self.current_display_url()
        _persist_web_url(target_card_id, current_url)
        if not _remember_browser_card_scroll():
            return
        try:
            _run_web_javascript(
                self.runtime.dock._view.page(),
                "(function(){"
                "  if (window.incrementoGetProgressPayload) {"
                "    return window.incrementoGetProgressPayload();"
                "  }"
                "  return {url: window.location.href || '', scrollRatio: 0};"
                "})();",
                lambda data, card_id=target_card_id: _persist_web_scroll(card_id, data),
            )
        except Exception:
            pass

    def citation(self, url: str | None = None) -> str:
        current_url = str(url or self.current_display_url()).strip()
        if not current_url or not self.runtime.current_card_id:
            return ""
        encoded_url = quote(current_url, safe="")
        label = (
            _source_url_label(current_url)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        cmd = f"incremento_open_web:{int(self.runtime.current_card_id)}:{encoded_url}"
        return (
            f"<a onclick=\"pycmd('{cmd}'); return false;\" "
            f"style=\"cursor:pointer; color:#4a90d9; text-decoration:none;\">"
            f"{label}</a>"
        )

    def refresh_bookmark_button(self) -> None:
        if self.runtime.dock is None:
            return
        try:
            self.runtime.dock._bookmark_btn.setText(t("reader_bookmark"))
            self.runtime.dock._bookmark_btn.setToolTip(
                t("reader_web_bookmark_hint")
            )
        except Exception:
            pass
        self.refresh_bookmarks_panel()

    def refresh_resume_button(self) -> None:
        if self.runtime.dock is None:
            return
        button = getattr(self.runtime.dock, "_resume_btn", None)
        if button is None:
            return
        progress = self.progress_state()
        seconds = float(progress.get("media_seconds") or 0.0)
        if seconds <= 0:
            try:
                button.setVisible(False)
                button.setText(t("reader_web_resume"))
                button.setToolTip("")
            except Exception:
                pass
            return

        time_text = _fmt_media_time(seconds)
        current_url = self.current_display_url() or str(progress.get("url") or "").strip()
        media_url = str(progress.get("media_url") or "").strip()
        resume_url = build_web_media_resume_target(current_url, media_url, seconds)
        media_title = str(progress.get("media_title") or "").strip()
        prefer_original_page = _prefer_web_card_resume_in_original_page()
        tooltip_parts = [t("reader_web_last_media_time", time=time_text)]
        if media_title:
            tooltip_parts.append(media_title)
        if prefer_original_page:
            tooltip_parts.append(t("reader_web_resume_original_hint"))
        elif resume_url:
            tooltip_parts.append(t("reader_web_resume_media_hint"))
        else:
            tooltip_parts.append(t("reader_web_resume_copy_hint"))
        try:
            button.setText(t("reader_web_resume_at", time=time_text))
            button.setToolTip(" ".join(tooltip_parts))
            button.setVisible(True)
        except Exception:
            pass

    def current_source_rows(self) -> list[dict]:
        if self.runtime.current_card_id is None:
            return []
        current_url = self.current_display_url()
        if not current_url:
            return []
        try:
            return get_web_card_sources(
                _ADDON_DIR,
                _active_profile(),
                int(self.runtime.current_card_id),
                current_url,
            )
        except Exception:
            return []

    def refresh_cards_panel(self) -> None:
        if self.runtime.dock is None:
            return
        current_url = self.current_display_url()
        rows = self.current_source_rows()
        count = len(rows)
        try:
            self.runtime.dock._cards_btn.setText(_web_card_count_label(count))
            self.runtime.dock._cards_btn.setVisible(count > 0)
        except Exception:
            pass
        if count <= 0:
            try:
                self.runtime.dock._cards_panel.hide()
                self.runtime.dock._cards_panel.setHtml("")
            except Exception:
                pass
            return
        html = [
            "<div style='font-family:sans-serif;font-size:12px;line-height:1.45'>",
            "<div style='font-weight:bold;color:rgb(74,144,217);margin-bottom:6px'>",
            escape(t("reader_web_cards_at_url")),
            "</div>",
            (
                "<div style='color:#888;margin-bottom:8px;word-break:break-all'>"
                + escape(current_url, quote=True)
                + "</div>"
            ),
        ]
        for row in rows:
            excerpt = str(row.get("excerpt") or "").strip()
            safe_excerpt = (
                excerpt.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                or f"<i style='color:#888'>{escape(t('reader_no_text'))}</i>"
            )
            html.append(
                "<div style='margin-bottom:6px;padding:6px 8px;"
                "background:rgba(74,144,217,0.08);border-left:3px solid rgba(74,144,217,0.55)'>"
                f"<a href='inc://card/{int(row['note_id'])}' "
                "style='text-decoration:none;color:inherit'>"
                f"{safe_excerpt}</a></div>"
            )
        html.append("</div>")
        try:
            self.runtime.dock._cards_panel.setHtml("".join(html))
        except Exception:
            pass

    def toggle_cards_panel(self) -> None:
        if self.runtime.dock is None:
            return
        rows = self.current_source_rows()
        if not rows:
            tooltip(t("reader_web_no_cards_at_url"))
            return
        self.refresh_cards_panel()
        try:
            visible = self.runtime.dock._cards_panel.isVisible()
            self.runtime.dock._cards_panel.setVisible(not visible)
        except Exception:
            pass

    def bookmark_rows(self) -> list[dict]:
        if self.runtime.current_card_id is None:
            return []
        try:
            return list_reader_bookmarks(
                _ADDON_DIR,
                _active_profile(),
                int(self.runtime.current_card_id),
                "web",
            )
        except Exception:
            return []

    def refresh_bookmarks_panel(self) -> None:
        if self.runtime.dock is None:
            return
        rows = self.bookmark_rows()
        try:
            self.runtime.dock._bookmarks_btn.setText(_web_bookmark_count_label(len(rows)))
        except Exception:
            pass
        panel = getattr(self.runtime.dock, "_bookmarks_panel", None)
        if panel is None:
            return
        html = [
            "<div style='font-family:sans-serif;font-size:12px;line-height:1.45'>",
            "<div style='font-weight:bold;color:rgb(234,179,8);margin-bottom:6px'>",
            escape(t("reader_interesting_bookmarks")),
            "</div>",
        ]
        if rows:
            for row in rows:
                bookmark_id = escape(str(row.get("id") or ""), quote=True)
                label = str(row.get("label") or t("reader_bookmark"))
                url = str((row.get("location") or {}).get("url") or "")
                safe_label = escape(label, quote=True)
                safe_url = escape(url, quote=True)
                html.append(
                    "<div style='margin-bottom:6px;padding:6px 8px;"
                    "background:rgba(234,179,8,0.08);border-left:3px solid rgba(234,179,8,0.55)'>"
                    f"<div><b>{safe_label}</b></div>"
                    f"<div style='color:#888;word-break:break-all'>{safe_url}</div>"
                    f"<a href='inc://web-bookmark-open/{bookmark_id}'>{escape(t('reader_jump'))}</a> "
                    f"<a href='inc://web-bookmark-delete/{bookmark_id}' style='color:#c66'>{escape(t('reader_delete'))}</a>"
                    "</div>"
                )
        else:
            html.append(f"<div style='color:#888'>{escape(t('reader_no_bookmarks'))}</div>")
        html.append("</div>")
        try:
            panel.setHtml("".join(html))
        except Exception:
            pass

    def toggle_bookmarks_panel(self) -> None:
        if self.runtime.dock is None:
            return
        self.refresh_bookmarks_panel()
        try:
            self.runtime.dock._bookmarks_panel.setVisible(
                not self.runtime.dock._bookmarks_panel.isVisible()
            )
        except Exception:
            pass

    def save_bookmark(self) -> None:
        if self.runtime.dock is None or self.runtime.current_card_id is None:
            tooltip(t("reader_web_no_browser_card"))
            return
        try:
            target_card_id = int(self.runtime.current_card_id)
        except Exception:
            tooltip(t("reader_web_no_browser_card"))
            return

        def _handle(payload) -> None:
            if not isinstance(payload, dict):
                tooltip(t("reader_web_bookmark_unavailable"))
                return
            current_url = str(payload.get("url") or "").strip()
            bookmark = payload.get("bookmark")
            if not current_url or not isinstance(bookmark, dict):
                tooltip(t("reader_web_bookmark_unavailable"))
                return
            try:
                add_reader_bookmark(
                    _ADDON_DIR,
                    _active_profile(),
                    target_card_id,
                    "web",
                    {
                        "url": current_url,
                        "scroll_ratio": bookmark.get("scrollRatio", 0.0),
                        "bookmark_payload": bookmark,
                        "text": bookmark.get("text", ""),
                    },
                )
            except Exception as exc:
                showInfo(t("reader_web_bookmark_save_failed", error=exc))
                return
            self.refresh_bookmark_button()
            try:
                self.runtime.dock._bookmarks_panel.setVisible(True)
            except Exception:
                pass
            tooltip(t("reader_web_bookmark_saved"))

        try:
            _run_web_javascript(
                self.runtime.dock._view.page(),
                "window.incrementoCaptureBookmark && window.incrementoCaptureBookmark();",
                _handle,
            )
        except Exception as exc:
            showInfo(t("reader_web_bookmark_save_failed", error=exc))

    def extract_selection_to_field(self, idx: int) -> None:
        expected_profile = str(_active_profile() or "")

        def _apply(text: str, extract_record: dict | None) -> None:
            if not text:
                tooltip(t("reader_select_text_first"))
                return
            try:
                from . import add_card_dock as _add_card_dock_mod

                marker_staged = bool(
                    extract_record is not None
                    and _accept_web_extract_record(
                        extract_record,
                        expected_profile=expected_profile,
                    )
                )
                fill_completion_seen = False

                def _fill_completed(success: bool) -> None:
                    nonlocal fill_completion_seen
                    if fill_completion_seen:
                        return
                    fill_completion_seen = True
                    if not success and marker_staged and extract_record is not None:
                        _remove_pending_web_extract_record(
                            extract_record,
                            expected_profile=expected_profile,
                        )

                fill_result = _add_card_dock_mod.fill_dock_field(
                    idx,
                    external_plain_text_to_anki_html(text),
                    include_pdf_citation=False,
                    citation_html=self.citation(),
                    source_link_kind="web",
                    on_complete=_fill_completed if marker_staged else None,
                )
                if fill_result is False and marker_staged:
                    _fill_completed(False)
            except Exception as exc:
                if "marker_staged" in locals() and marker_staged and extract_record is not None:
                    _remove_pending_web_extract_record(
                        extract_record,
                        expected_profile=expected_profile,
                    )
                showInfo(t("reader_web_extract_failed", error=exc))

        _resolve_web_extraction(_apply)

    def extract_selection_with_picker(self) -> None:
        target_idx = _prompt_extract_target_field()
        if target_idx < 0:
            return
        self.extract_selection_to_field(target_idx)

    def insert_snapshot_into_field(
        self,
        pixmap: QPixmap,
        current_url: str,
        *,
        extract_record: dict | None = None,
        expected_profile: str = "",
    ) -> None:
        from . import add_card_dock as _add_card_dock_mod

        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            if not pixmap.save(tmp_path, "PNG"):
                raise RuntimeError(t("web_snapshot_encode_failed"))
            media_filename = mw.col.media.add_file(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        _add_card_dock_mod.open_add_card_dock()
        field_names = []
        try:
            dock = _add_card_dock_mod.get_add_card_dock()
            if dock:
                note = dock.widget().editor.note
                if note:
                    field_names = [f["name"] for f in note.note_type()["flds"]]
        except Exception:
            pass
        if not field_names:
            field_names = [t("reader_field_number", number=i + 1) for i in range(4)]

        scaled = pixmap
        if scaled.width() > 300:
            scaled = scaled.scaledToWidth(
                300,
                Qt.TransformationMode.SmoothTransformation,
            )
        if scaled.height() > 180:
            scaled = scaled.scaledToHeight(
                180,
                Qt.TransformationMode.SmoothTransformation,
            )

        picker = QDialog(mw)
        picker.setWindowTitle(t("reader_web_insert_snapshot"))
        picker.setFixedWidth(340)
        layout = QVBoxLayout(picker)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        preview_lbl = QLabel()
        preview_lbl.setPixmap(scaled)
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview_lbl)

        layout.addSpacing(14)
        layout.addWidget(QLabel(t("reader_web_insert_image_into")))
        layout.addSpacing(8)

        chosen_idx = [-1]

        def _make_handler(idx):
            def _handler():
                chosen_idx[0] = idx
                picker.accept()

            return _handler

        for i, name in enumerate(field_names):
            btn = QPushButton(name)
            btn.setStyleSheet("text-align: left; padding: 7px 12px;")
            btn.clicked.connect(_make_handler(i))
            layout.addWidget(btn)
            layout.addSpacing(4)

        layout.addSpacing(8)
        cancel_btn = QPushButton(t("reader_cancel"))
        cancel_btn.clicked.connect(picker.reject)
        layout.addWidget(cancel_btn)

        if not picker.exec() or chosen_idx[0] < 0:
            return

        _fill_web_snapshot_field(
            _add_card_dock_mod,
            chosen_idx[0],
            media_filename,
            current_url,
            extract_record=extract_record,
            expected_profile=expected_profile,
            citation_html=self.citation(current_url),
        )

    def handle_snapshot(self, data: dict) -> None:
        if self.runtime.dock is None:
            return
        try:
            x = max(0, int(round(float(data.get("x") or 0))))
            y = max(0, int(round(float(data.get("y") or 0))))
            width = max(0, int(round(float(data.get("width") or 0))))
            height = max(0, int(round(float(data.get("height") or 0))))
        except Exception as exc:
            raise RuntimeError(t("web_snapshot_invalid_bounds", error=exc)) from exc
        if width < 6 or height < 6:
            return
        current_url = str(data.get("url") or self.current_display_url()).strip()
        try:
            pixmap = _grab_web_view_without_extraction_markers(
                self.runtime.dock._view
            )
        except Exception as exc:
            raise RuntimeError(t("web_snapshot_capture_failed_detail", error=exc)) from exc
        if pixmap.isNull():
            raise RuntimeError(t("web_snapshot_capture_failed"))
        try:
            dpr = float(pixmap.devicePixelRatio())
        except Exception:
            dpr = 1.0
        crop = pixmap.copy(
            int(round(x * dpr)),
            int(round(y * dpr)),
            int(round(width * dpr)),
            int(round(height * dpr)),
        )
        if crop.isNull():
            raise RuntimeError(t("web_snapshot_outside_viewport"))
        try:
            crop.setDevicePixelRatio(dpr)
        except Exception:
            pass
        rect = QRect(x, y, width, height)
        expected_profile = str(_active_profile() or "")
        _resolve_web_snapshot_anchor(
            rect,
            lambda record: self.insert_snapshot_into_field(
                crop,
                current_url,
                extract_record=record,
                expected_profile=expected_profile,
            ),
        )

    def build_dock(self):
        from PyQt6.QtWebEngineCore import (
            QWebEngineProfile as _WEProf,
            QWebEngineSettings as _WES,
        )

        self.runtime.track_window_with_extension = _track_web_window_with_extension_default()
        dock = QDockWidget(t("reader_web_name"), mw)
        dock.setObjectName("incremento_web_dock")
        dock.setMinimumWidth(600)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        view = QWebEngineView(container)

        if self.runtime.profile is None:
            self.runtime.profile = _WEProf("incremento_web")
            _web_profile_dir = str(_paths.get_web_profile_dir(_ADDON_DIR, _active_profile()))
            self.runtime.profile.setPersistentStoragePath(_web_profile_dir)
            self.runtime.profile.setPersistentCookiesPolicy(
                _WEProf.PersistentCookiesPolicy.ForcePersistentCookies
            )
            self.runtime.profile.setHttpUserAgent(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
            self.runtime.profile.settings().setAttribute(
                _WES.WebAttribute.PlaybackRequiresUserGesture, False
            )
            for attribute_name in (
                "DnsPrefetchEnabled",
                "HyperlinkAuditingEnabled",
                "JavascriptCanAccessClipboard",
                "JavascriptCanOpenWindows",
                "LocalContentCanAccessFileUrls",
                "LocalContentCanAccessRemoteUrls",
                "ScreenCaptureEnabled",
            ):
                attribute = getattr(_WES.WebAttribute, attribute_name, None)
                if attribute is not None:
                    self.runtime.profile.settings().setAttribute(attribute, False)

        page = _WebDockPage(self.runtime)
        view.setPage(page)

        def _on_load_started():
            page.rotate_bridge_nonce()
            _clear_native_web_extraction_markers()

        view.loadStarted.connect(_on_load_started)
        vbox.addWidget(view, 1)

        ctrl = QWidget(container)
        ctrl_layout = QGridLayout(ctrl)
        ctrl_layout.setContentsMargins(8, 4, 8, 4)
        ctrl_layout.setHorizontalSpacing(6)
        ctrl_layout.setVerticalSpacing(6)

        url_lbl = QLabel("")
        url_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #888;")
        url_lbl.setWordWrap(False)
        url_lbl.setAccessibleName(t("reader_web_status_accessible"))
        ctrl_layout.addWidget(url_lbl, 0, 0, 1, 2)

        back_btn = _make_web_button(
            ctrl,
            t("reader_back"),
            t("reader_web_back_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_ArrowBack),
        )
        search_btn = _make_web_button(
            ctrl,
            t("reader_search"),
            t("reader_web_search_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogContentsView),
        )

        add_card_btn = _make_web_button(
            ctrl,
            t("reader_add_card"),
            t("reader_web_add_card_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogNewFolder),
        )
        extract_btn = _make_web_button(
            ctrl,
            t("reader_extract"),
            t("reader_web_extract_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_DialogSaveButton),
        )
        snapshot_btn = _make_web_button(
            ctrl,
            t("reader_snapshot"),
            t("reader_web_snapshot_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogContentsView),
        )
        bookmark_btn = _make_web_button(
            ctrl,
            t("reader_bookmark"),
            t("reader_web_bookmark_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_DialogYesButton),
        )
        bookmarks_btn = _make_web_button(
            ctrl,
            _web_bookmark_count_label(0),
            t("reader_web_bookmarks_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        cards_btn = _make_web_button(
            ctrl,
            _web_card_count_label(0),
            t("reader_web_cards_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_FileDialogDetailedView),
        )
        cards_btn.setVisible(False)
        home_btn = _make_web_button(
            ctrl,
            t("reader_home"),
            t("reader_web_home_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_DirHomeIcon),
        )
        window_btn = _make_web_button(
            ctrl,
            t("reader_web_open_page"),
            t("reader_web_open_page_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_DialogOpenButton),
        )
        homepage_window_btn = _make_web_button(
            ctrl,
            t("reader_web_open_home"),
            t("reader_web_open_home_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        resume_btn = _make_web_button(
            ctrl,
            t("reader_web_resume"),
            t("reader_web_resume_hint"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_MediaPlay),
        )
        resume_btn.setVisible(False)
        review_all_btn = _make_web_button(
            ctrl,
            t("reader_review_all"),
            t("reader_web_review_all_unavailable"),
            icon=_standard_icon(QStyle.StandardPixmap.SP_MediaPlay),
        )

        configure_reader_shell_buttons(
            "web",
            {
                "back": back_btn,
                "search": search_btn,
                "extract": extract_btn,
                "bookmark": bookmark_btn,
                "review_all": review_all_btn,
            },
        )

        track_cb = QCheckBox(t("reader_web_track_extension"))
        track_cb.setChecked(bool(self.runtime.track_window_with_extension))
        track_cb.setToolTip(
            t("reader_web_track_extension_hint")
        )
        ctrl_layout.addWidget(track_cb, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)

        capture_group = _make_web_group(
            ctrl,
            t("reader_web_group_capture"),
            add_card_btn,
            extract_btn,
            snapshot_btn,
        )
        saved_group = _make_web_group(
            ctrl,
            t("reader_web_group_saved"),
            bookmark_btn,
            bookmarks_btn,
            cards_btn,
        )
        nav_group = _make_web_group(ctrl, t("reader_web_group_navigate"), back_btn, search_btn, home_btn)
        review_group = _make_web_group(ctrl, t("reader_web_group_review"), review_all_btn)
        external_group = _make_web_group(
            ctrl,
            t("reader_web_group_external"),
            window_btn,
            homepage_window_btn,
            resume_btn,
        )

        ctrl_layout.addWidget(capture_group, 1, 0, 1, 2)
        ctrl_layout.addWidget(saved_group, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
        ctrl_layout.addWidget(nav_group, 2, 0)
        ctrl_layout.addWidget(review_group, 2, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        ctrl_layout.addWidget(external_group, 3, 0, 1, 3, alignment=Qt.AlignmentFlag.AlignRight)

        ctrl_layout.setColumnStretch(0, 1)
        ctrl_layout.setColumnStretch(1, 1)

        vbox.addWidget(ctrl)

        cards_panel = QTextBrowser(container)
        cards_panel.setOpenLinks(False)
        cards_panel.anchorClicked.connect(_open_result_link)
        cards_panel.setVisible(False)
        cards_panel.setMaximumHeight(220)
        cards_panel.setStyleSheet(
            "border-top: 1px solid rgba(120,120,120,0.25);"
            "background: rgba(74,144,217,0.04);"
        )
        vbox.addWidget(cards_panel)

        bookmarks_panel = QTextBrowser(container)
        bookmarks_panel.setOpenLinks(False)
        bookmarks_panel.anchorClicked.connect(_open_result_link)
        bookmarks_panel.setVisible(False)
        bookmarks_panel.setMaximumHeight(190)
        bookmarks_panel.setStyleSheet(
            "border-top: 1px solid rgba(120,120,120,0.25);"
            "background: rgba(234,179,8,0.04);"
        )
        vbox.addWidget(bookmarks_panel)

        dock.setWidget(container)
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        dock._view = view
        dock._url_lbl = url_lbl
        dock._track_cb = track_cb
        dock._extract_btn = extract_btn
        dock._snapshot_btn = snapshot_btn
        dock._bookmark_btn = bookmark_btn
        dock._bookmarks_btn = bookmarks_btn
        dock._cards_btn = cards_btn
        dock._cards_panel = cards_panel
        dock._bookmarks_panel = bookmarks_panel
        dock._resume_btn = resume_btn
        dock._reader_back_btn = back_btn
        dock._reader_search_btn = search_btn
        dock._review_all_btn = review_all_btn

        if self.runtime.interaction_filter is None:
            self.runtime.interaction_filter = _WebInteractionFilter(self.runtime, mw)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self.runtime.interaction_filter)

        def _on_url_changed(qurl):
            url_str = qurl.toString()
            display = url_str if len(url_str) <= 80 else url_str[:77] + "..."
            try:
                url_lbl.setText(display)
            except RuntimeError:
                pass
            _persist_web_url(self.runtime.current_card_id, url_str)
            self.refresh_cards_panel()
            self.refresh_bookmark_button()
            self.refresh_resume_button()
            _clear_native_web_extraction_markers()

        def _on_load_finished(ok):
            if not ok or self.runtime.current_card_id is None:
                return
            url_str = view.url().toString()
            _persist_web_url(self.runtime.current_card_id, url_str)
            _set_web_snapshot_mode(False)

            def _bridge_installed(_result=None):
                try:
                    if (
                        self.runtime.dock is None
                        or self.runtime.dock._view.page() is not page
                        or int(self.runtime.current_card_id or 0) <= 0
                        or self.runtime.dock._view.url().toString() != url_str
                    ):
                        return
                except Exception:
                    return
                _refresh_web_extraction_highlights()

            try:
                _run_web_javascript(
                    page,
                    _build_web_bridge_js(
                        bridge_nonce=page.bridge_nonce(),
                        card_id=int(self.runtime.current_card_id),
                    ),
                    _bridge_installed,
                )
            except Exception:
                pass
            restore_cfg = self.runtime.pending_restore or {}
            if int(restore_cfg.get("card_id") or 0) == int(self.runtime.current_card_id):
                QTimer.singleShot(
                    0,
                    lambda url=url_str, cfg=dict(restore_cfg): _apply_web_restore_state(
                        url,
                        allow_bookmark=bool(cfg.get("allow_bookmark", True)),
                        allow_scroll=bool(cfg.get("allow_scroll", True)),
                    ),
                )
            self.runtime.pending_restore = None
            explicit_restore = self.runtime.pending_bookmark_restore
            if (
                isinstance(explicit_restore, dict)
                and int(explicit_restore.get("card_id") or 0) == int(self.runtime.current_card_id)
            ):
                payload = json.dumps(explicit_restore.get("payload") or {})
                QTimer.singleShot(
                    0,
                    lambda p=payload: _run_web_javascript(
                        view.page(),
                        f"window.incrementoApplyRestoreState && window.incrementoApplyRestoreState({p});",
                    ),
                )
            self.runtime.pending_bookmark_restore = None
            self.refresh_cards_panel()
            self.refresh_bookmark_button()
            self.refresh_resume_button()

        def _on_selection_changed():
            _update_native_selection_state()

        view.urlChanged.connect(_on_url_changed)
        view.loadFinished.connect(_on_load_finished)
        page.selectionChanged.connect(_on_selection_changed)

        def _on_scroll_position_changed(position) -> None:
            _sync_native_web_extraction_scroll(position)
            _schedule_web_extraction_highlight_refresh(delay_ms=140)

        page.scrollPositionChanged.connect(_on_scroll_position_changed)
        page.contentsSizeChanged.connect(
            lambda _size: _schedule_web_extraction_highlight_refresh(delay_ms=160)
        )
        qconnect(home_btn.clicked, self.go_home)
        qconnect(back_btn.clicked, view.back)

        def _find_in_page() -> None:
            previous = str(getattr(self.runtime, "last_find_query", "") or "")
            prompt = QInputDialog(dock)
            prompt.setWindowTitle(t("reader_web_search_page"))
            prompt.setLabelText(t("reader_text_prompt"))
            prompt.setTextValue(previous)
            prompt.setOkButtonText(t("reader_ok"))
            prompt.setCancelButtonText(t("reader_cancel"))
            accepted = prompt.exec()
            query = prompt.textValue()
            normalized = str(query or "").strip()
            if not accepted or not normalized:
                return
            self.runtime.last_find_query = normalized
            view.findText(normalized)

        qconnect(search_btn.clicked, _find_in_page)
        qconnect(homepage_window_btn.clicked, self.open_homepage_in_window)
        qconnect(extract_btn.clicked, self.extract_selection_with_picker)
        qconnect(snapshot_btn.clicked, _toggle_snapshot_mode)
        qconnect(bookmark_btn.clicked, self.save_bookmark)
        qconnect(bookmarks_btn.clicked, self.toggle_bookmarks_panel)
        qconnect(cards_btn.clicked, self.toggle_cards_panel)
        qconnect(window_btn.clicked, self.open_in_window)
        qconnect(resume_btn.clicked, self.open_media_resume_in_window)
        qconnect(track_cb.toggled, _on_track_web_window_toggled)

        def _open_add_card():
            from . import add_card_dock as _add_card_dock_mod

            _add_card_dock_mod.open_add_card_dock()

        qconnect(add_card_btn.clicked, _open_add_card)

        if not self.runtime.shortcuts_registered:
            for idx in range(4):
                for prefix in ("Ctrl", "Meta"):
                    sc = QShortcut(QKeySequence(f"{prefix}+{idx + 1}"), mw)
                    sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                    sc.activated.connect(
                        lambda idx=idx: (
                            self.extract_selection_to_field(idx)
                            if self.runtime.dock is not None and self.runtime.dock.isVisible()
                            else None
                        )
                    )
                    self.runtime.shortcuts.append(sc)
            esc = QShortcut(QKeySequence("Escape"), mw)
            esc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            esc.activated.connect(
                lambda: _set_web_snapshot_mode(False) if self.runtime.snapshot_mode else None
            )
            self.runtime.shortcuts.append(esc)
            self.runtime.shortcuts_registered = True

        self.runtime.dock = dock
        self.refresh_bookmark_button()
        return dock

    def open_in_window(self) -> None:
        if self.runtime.current_card_id is None:
            tooltip(t("reader_web_no_card"))
            return

        current_url = self.current_display_url()
        if not current_url:
            tooltip(t("reader_web_invalid_url"))
            return

        track_enabled = False
        if self.runtime.dock is not None:
            try:
                track_enabled = bool(self.runtime.dock._track_cb.isChecked())
            except Exception:
                track_enabled = False

        open_url = build_external_web_url(
            current_url,
            card_id=int(self.runtime.current_card_id),
            track_with_extension=track_enabled,
        )
        try:
            set_web_url(_ADDON_DIR, _active_profile(), self.runtime.current_card_id, current_url)
        except Exception:
            pass

        try:
            ok = bool(QDesktopServices.openUrl(QUrl(open_url)))
        except Exception:
            ok = False
        if not ok:
            tooltip(t("reader_open_system_browser_failed"))
            return

        if track_enabled:
            tooltip(
                t("reader_web_tracking_tab_enabled")
            )

    def _copy_text_to_clipboard(self, text: str) -> bool:
        raw = str(text or "")
        if not raw:
            return False
        try:
            app = QApplication.instance()
            if app is None:
                return False
            clipboard = app.clipboard()
            if clipboard is None:
                return False
            clipboard.setText(raw)
            return True
        except Exception:
            return False

    def open_media_resume_in_window(self) -> None:
        if self.runtime.current_card_id is None:
            tooltip(t("reader_web_no_card"))
            return

        progress = self.progress_state()
        seconds = float(progress.get("media_seconds") or 0.0)
        if seconds <= 0:
            tooltip(t("reader_web_no_saved_media_time"))
            return

        current_url = self.current_display_url() or str(progress.get("url") or "").strip()
        if not current_url:
            current_url = str(self.runtime.current_home_url or "").strip()
        if not current_url:
            tooltip(t("reader_web_invalid_url"))
            return

        media_url = str(progress.get("media_url") or "").strip()
        resume_url = build_web_media_resume_target(current_url, media_url, seconds)
        time_text = _fmt_media_time(seconds)

        track_enabled = False
        if self.runtime.dock is not None:
            try:
                track_enabled = bool(self.runtime.dock._track_cb.isChecked())
            except Exception:
                track_enabled = False

        prefer_original_page = _prefer_web_card_resume_in_original_page()

        copied_time = False
        if prefer_original_page:
            open_url = _build_resume_tracking_url(
                current_url,
                card_id=int(self.runtime.current_card_id),
                seconds=seconds,
                media_url=media_url,
            )
        elif resume_url:
            open_url = build_external_web_url(
                resume_url,
                card_id=int(self.runtime.current_card_id),
                track_with_extension=False,
            )
            copied_time = self._copy_text_to_clipboard(time_text)
        else:
            open_url = build_external_web_url(
                current_url,
                card_id=int(self.runtime.current_card_id),
                track_with_extension=track_enabled,
            )
            copied_time = self._copy_text_to_clipboard(time_text)
            try:
                set_web_url(_ADDON_DIR, _active_profile(), self.runtime.current_card_id, current_url)
            except Exception:
                pass

        try:
            ok = bool(QDesktopServices.openUrl(QUrl(open_url)))
        except Exception:
            ok = False
        if not ok:
            tooltip(t("reader_open_system_browser_failed"))
            return

        if prefer_original_page:
            tooltip(
                t("reader_web_resuming_original")
            )
            return

        if copied_time:
            tooltip(t("reader_web_media_time_copied", time=time_text))

    def open_homepage_in_window(self) -> None:
        if self.runtime.current_card_id is None:
            tooltip(t("reader_web_no_card"))
            return

        home_url = str(self.runtime.current_home_url or "").strip()
        if not home_url:
            tooltip(t("reader_web_no_homepage"))
            return

        track_enabled = False
        if self.runtime.dock is not None:
            try:
                track_enabled = bool(self.runtime.dock._track_cb.isChecked())
            except Exception:
                track_enabled = False

        open_url = build_external_web_url(
            home_url,
            card_id=int(self.runtime.current_card_id),
            track_with_extension=track_enabled,
        )

        try:
            ok = bool(QDesktopServices.openUrl(QUrl(open_url)))
        except Exception:
            ok = False
        if not ok:
            tooltip(t("reader_open_system_browser_failed"))
            return

        if track_enabled:
            tooltip(
                t("reader_web_tracking_home_enabled")
            )

    def go_home(self) -> None:
        if self.runtime.dock is None or not self.runtime.current_home_url:
            return
        try:
            self.runtime.dock._view.load(QUrl(self.runtime.current_home_url))
        except (RuntimeError, AttributeError):
            pass

    def show_in_dock(
        self,
        card_id: int,
        home_url: str,
        last_url: str,
        *,
        prefer_bookmark: bool = True,
        restore_scroll: bool = True,
    ) -> None:
        previous_card_id = self.runtime.current_card_id
        if previous_card_id is not None and int(previous_card_id) != int(card_id):
            _clear_native_web_extraction_markers()
        self.runtime.current_card_id = card_id
        self.runtime.current_home_url = home_url

        if self.runtime.dock is None:
            self.build_dock()
        else:
            try:
                self.runtime.dock.widget()
            except RuntimeError:
                self.runtime.dock = None
                self.build_dock()

        progress = self.progress_state(card_id)
        bookmark_url = str(progress.get("bookmark_url") or "").strip()
        load_url = (
            bookmark_url
            if prefer_bookmark and bookmark_url
            else (last_url if last_url else home_url)
        )
        current_url = ""
        try:
            current_url = (self.runtime.dock._view.url().toString() or "").strip()
        except Exception:
            current_url = ""
        self.runtime.dock.show()
        self.runtime.dock.raise_()
        try:
            _run_web_javascript(
                self.runtime.dock._view.page(),
                "window.incrementoSetActiveCardId && "
                f"window.incrementoSetActiveCardId({int(card_id)});",
            )
        except Exception:
            pass
        _set_web_snapshot_mode(False)
        try:
            self.runtime.dock._cards_panel.hide()
            self.runtime.dock._cards_panel.setHtml("")
            self.runtime.dock._cards_btn.setVisible(False)
            self.runtime.dock._cards_btn.setText(_web_card_count_label(0))
        except Exception:
            pass
        self.refresh_bookmark_button()
        self.refresh_resume_button()
        _set_pending_web_restore(
            card_id,
            allow_bookmark=prefer_bookmark,
            allow_scroll=restore_scroll,
        )
        if load_url and current_url != load_url:
            self.runtime.dock._view.load(QUrl(load_url))
        elif load_url:
            _apply_web_restore_state(
                load_url,
                allow_bookmark=prefer_bookmark,
                allow_scroll=restore_scroll,
            )
            self.runtime.pending_restore = None
        else:
            self.runtime.pending_restore = None
        _schedule_web_extraction_highlight_refresh()

    def open_location(self, card_id: int, target_url: str) -> bool:
        try:
            card = mw.col.get_card(int(card_id))
            note = mw.col.get_note(card.nid)
            home_url = note["URL"]
        except Exception:
            return False
        target = str(target_url or "").strip()
        if not target:
            target = get_web_url(_ADDON_DIR, _active_profile(), int(card_id)) or home_url
        try:
            set_web_url(_ADDON_DIR, _active_profile(), int(card_id), target)
        except Exception:
            pass
        self.show_in_dock(
            int(card_id),
            home_url,
            target,
            prefer_bookmark=False,
            restore_scroll=False,
        )
        return True

    def sync_external_url(self, card_id: int, url: str) -> bool:
        try:
            target_card_id = int(card_id)
        except Exception:
            return False
        target_url = str(url or "").strip()
        if target_card_id <= 0 or not target_url:
            return False
        if self.runtime.current_card_id != target_card_id:
            return False
        if self.runtime.dock is None:
            return False

        try:
            current_url = (self.runtime.dock._view.url().toString() or "").strip()
        except Exception:
            current_url = ""
        if current_url == target_url:
            return False

        try:
            _set_pending_web_restore(
                target_card_id,
                allow_bookmark=False,
                allow_scroll=False,
            )
            self.runtime.dock._view.load(QUrl(target_url))
            return True
        except Exception:
            return False

    def sync_external_media_state(
        self,
        card_id: int,
        url: str,
        media_url: str,
        media_title: str,
        media_seconds: float,
    ) -> bool:
        try:
            target_card_id = int(card_id)
        except Exception:
            return False
        if target_card_id <= 0 or float(media_seconds or 0.0) <= 0:
            return False
        if self.runtime.current_card_id != target_card_id:
            return False
        if self.runtime.dock is None:
            return False
        self.refresh_resume_button()
        return True

    def on_question_shown(self, card) -> None:
        try:
            if card is None:
                return
            try:
                note = mw.col.get_note(card.nid)
                model = mw.col.models.get(note.mid)
            except Exception:
                return
            if model is None or model.get("name") != WEB_NOTE_TYPE:
                if self.runtime.dock is not None:
                    self.persist_current_state()
                    try:
                        self.runtime.dock.hide()
                    except RuntimeError:
                        self.runtime.dock = None
                return
            try:
                home_url = note["URL"]
            except (KeyError, TypeError):
                return
            if not home_url:
                return
            last_url = get_web_url(_ADDON_DIR, _active_profile(), card.id)
            self.show_in_dock(card.id, home_url, last_url)
        except Exception as e:
            print(f"[Incremento] on_web_question_shown error: {e}")

    def on_reviewer_will_end(self) -> None:
        _set_web_snapshot_mode(False)
        self.persist_current_state()
        if self.runtime.dock is not None:
            try:
                self.runtime.dock.hide()
            except RuntimeError:
                pass

    def on_add_cards_did_add_note(self, note) -> None:
        try:
            note_id = int(note.id)
        except Exception:
            return
        parts = []
        for field in (note.fields or [])[:2]:
            plain = re.sub(r"<[^>]+>", "", field).strip()[:120]
            if plain:
                parts.append(plain)
        excerpt = " / ".join(parts)[:200]
        profile = str(_active_profile() or "")
        if note_id <= 0 or not profile:
            return

        records = normalize_web_extract_records(
            [
                *_pending_web_extract_records(),
                *_web_extract_records_for_note(note),
            ],
            limit=MAX_PENDING_WEB_EXTRACT_RECORDS,
        )
        if records and not _note_owns_web_extract_draft(note):
            # Another Anki Add window may save while Incremento's dock still
            # owns an unsaved extraction. Never attach that draft to the
            # unrelated note.
            return
        grouped: dict[tuple[int, str], list[dict]] = {}
        for record in records:
            key = (int(record["webCardId"]), str(record["url"]))
            grouped.setdefault(key, []).append(record["anchor"])

        saved_any = False
        failed_anchor_writes = 0
        saved_anchor_keys: set[tuple[int, str, str]] = set()
        if grouped:
            for (web_card_id, url), anchors in grouped.items():
                try:
                    add_web_card_source(
                        _ADDON_DIR,
                        profile,
                        web_card_id,
                        url,
                        note_id,
                        excerpt,
                        anchors=anchors,
                    )
                    saved_any = True
                    saved_anchor_keys.update(
                        (web_card_id, url, str(anchor["id"]))
                        for anchor in anchors
                    )
                except Exception:
                    failed_anchor_writes += 1
                    continue
        else:
            # Preserve the existing Add Card workflow for notes created while
            # a Web reader is visibly open, even when no text selection was
            # anchorable (for example, a cross-origin iframe selection).
            if self.runtime.current_card_id is None or self.runtime.dock is None:
                return
            try:
                if not self.runtime.dock.isVisible():
                    return
            except Exception:
                return
            current_url = self.current_display_url()
            if not current_url:
                return
            try:
                add_web_card_source(
                    _ADDON_DIR,
                    profile,
                    int(self.runtime.current_card_id),
                    current_url,
                    note_id,
                    excerpt,
                )
                saved_any = True
            except Exception:
                return

        if grouped:
            for record in records:
                _remove_runtime_pending_web_extract_record(record, profile)
                if _web_extract_record_key(record) in saved_anchor_keys:
                    _promote_native_web_extraction_marker(record)
                else:
                    _remove_native_web_extraction_marker(record)
            if failed_anchor_writes:
                tooltip(
                    t("reader_web_marker_save_failed")
                )
            # The Add Card hook clears the pending draft immediately after
            # this hook. Queue a repaint even when supplemental persistence
            # failed so an amber marker cannot remain stale on the page.
            _schedule_web_extraction_highlight_refresh()

        if not saved_any:
            return
        self.refresh_cards_panel()
        try:
            if (
                self.runtime.dock is not None
                and self.runtime.dock._cards_panel.isVisible()
            ):
                self.runtime.dock._cards_panel.show()
        except Exception:
            pass
        if not grouped:
            _schedule_web_extraction_highlight_refresh()

    def get_selected_text(self, callback) -> None:
        _resolve_web_selection(callback)


_controller = _WebDockController(_runtime)


def web_citation(url: str | None = None) -> str:
    return _controller.citation(url)


class _WebDockPage(QWebEnginePage):
    def __init__(self, runtime: _WebDockRuntime):
        super().__init__(runtime.profile)
        self._runtime = runtime
        self._bridge_nonce = secrets.token_urlsafe(24)

    def rotate_bridge_nonce(self) -> None:
        self._bridge_nonce = secrets.token_urlsafe(24)

    def bridge_nonce(self) -> str:
        return self._bridge_nonce

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if is_main_frame and str(url.scheme() or "").casefold() not in {
            "about",
            "http",
            "https",
        }:
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

    def javaScriptConsoleMessage(self, level, message, line, source):
        del level, line, source
        expected_prefix = f"{_PYCMD_BRIDGE}{self._bridge_nonce}:"
        if (
            len(message) > _MAX_WEB_BRIDGE_MESSAGE_CHARS
            or not message.startswith(expected_prefix)
        ):
            return
        msg = message[len(expected_prefix) :]
        if msg.startswith(_MSG_PROGRESS):
            try:
                data = json.loads(msg[len(_MSG_PROGRESS) :])
                if not _web_bridge_card_matches(self._runtime, data):
                    return
                data["url"] = _controller.current_display_url()
                _persist_web_scroll(self._runtime.current_card_id, data)
            except Exception:
                pass


def _web_bridge_card_matches(runtime: _WebDockRuntime, data: object) -> bool:
    if not isinstance(data, dict) or runtime.current_card_id is None:
        return False
    try:
        return int(data.get("cardId") or 0) == int(runtime.current_card_id)
    except (TypeError, ValueError):
        return False


class _WebInteractionFilter(QObject):
    def __init__(self, runtime: _WebDockRuntime, parent=None):
        super().__init__(parent)
        self._runtime = runtime

    def eventFilter(self, watched, event):
        if self._runtime.dock is None:
            return False
        try:
            view = self._runtime.dock._view
        except Exception:
            return False

        etype = event.type()
        if watched is view and etype == QEvent.Type.Resize:
            _sync_native_web_extraction_overlay_geometry(view)
            _schedule_web_extraction_highlight_refresh(delay_ms=120)
            return False

        if not self._runtime.snapshot_mode:
            return False
        try:
            if not self._runtime.dock.isVisible():
                return False
        except Exception:
            return False

        if etype == QEvent.Type.KeyPress:
            try:
                if event.key() == Qt.Key.Key_Escape:
                    _set_web_snapshot_mode(False)
                    return True
            except Exception:
                return False
            return False

        if etype not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
        ):
            return False

        try:
            global_pos = event.globalPosition().toPoint()
        except Exception:
            return False
        local_pos = view.mapFromGlobal(global_pos)
        if not view.rect().contains(local_pos):
            if (
                etype == QEvent.Type.MouseMove
                and self._runtime.snapshot_origin is not None
            ):
                local_pos = QPoint(
                    max(0, min(local_pos.x(), view.rect().right())),
                    max(0, min(local_pos.y(), view.rect().bottom())),
                )
            else:
                return False

        if etype == QEvent.Type.MouseButtonPress:
            try:
                if event.button() != Qt.MouseButton.LeftButton:
                    return False
            except Exception:
                return False
            self._runtime.snapshot_origin = local_pos
            _ensure_snapshot_band(view)
            self._runtime.snapshot_shield.setGeometry(view.rect())
            self._runtime.snapshot_shield.raise_()
            self._runtime.snapshot_shield.show()
            self._runtime.snapshot_overlay.setGeometry(
                QRect(self._runtime.snapshot_origin, self._runtime.snapshot_origin)
            )
            self._runtime.snapshot_overlay.raise_()
            self._runtime.snapshot_overlay.show()
            return True

        if etype == QEvent.Type.MouseMove:
            if self._runtime.snapshot_origin is None:
                return False
            _ensure_snapshot_band(view)
            self._runtime.snapshot_shield.setGeometry(view.rect())
            self._runtime.snapshot_shield.raise_()
            self._runtime.snapshot_shield.show()
            self._runtime.snapshot_overlay.setGeometry(
                QRect(self._runtime.snapshot_origin, local_pos).normalized()
            )
            self._runtime.snapshot_overlay.raise_()
            self._runtime.snapshot_overlay.show()
            return True

        if etype == QEvent.Type.MouseButtonRelease:
            try:
                if event.button() != Qt.MouseButton.LeftButton:
                    return False
            except Exception:
                return False
            if self._runtime.snapshot_origin is None:
                return False
            rect = QRect(
                self._runtime.snapshot_origin, local_pos
            ).normalized().intersected(view.rect())
            self._runtime.snapshot_origin = None
            if self._runtime.snapshot_overlay is not None:
                self._runtime.snapshot_overlay.hide()
            current_url = _current_web_display_url()
            _set_web_snapshot_mode(False)
            if rect.width() < 6 or rect.height() < 6:
                return True
            try:
                pixmap = _grab_web_view_without_extraction_markers(view, rect)
            except Exception as exc:
                showInfo(t("reader_web_snapshot_failed", error=exc))
                return True
            if pixmap.isNull():
                showInfo(t("reader_web_snapshot_capture_failed"))
                return True
            expected_profile = str(_active_profile() or "")

            def _insert_snapshot(record) -> None:
                try:
                    _insert_snapshot_into_field(
                        pixmap,
                        current_url,
                        extract_record=record,
                        expected_profile=expected_profile,
                    )
                except Exception as exc:
                    showInfo(t("reader_web_snapshot_failed", error=exc))

            _resolve_web_snapshot_anchor(rect, _insert_snapshot)
            return True

        return False


def _build_web_bridge_js(*, bridge_nonce: str, card_id: int) -> str:
    script = _load_web_bridge_js_template()
    return (
        script.replace(
            "__PYCMD_PREFIX__",
            json.dumps(f"{_PYCMD_BRIDGE}{str(bridge_nonce)}:"),
        )
        .replace("__CARD_ID__", str(max(0, int(card_id))))
        .replace("__MSG_PROGRESS__", json.dumps(_MSG_PROGRESS))
    )


def _current_web_display_url() -> str:
    return _controller.current_display_url()


def _current_selected_text() -> str:
    if _runtime.dock is None:
        return ""
    try:
        text = _runtime.dock._view.page().selectedText() or ""
        text = external_plain_text(str(text).replace("\u2029", "\n")).strip()
        if text:
            return text
    except Exception:
        pass
    return ""


def _normalized_web_selection_identity(value: object) -> str:
    """Compare Qt and Chromium selection text without layout-only whitespace."""
    normalized = external_plain_text(value).replace("\u2029", "\n")
    return re.sub(r"\s+", " ", normalized).strip()


def _bounded_native_geometry_number(
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < minimum or number > maximum:
        return None
    return number


def _normalize_native_web_extraction_geometry(
    payload: object,
    *,
    allowed_markers: dict[str, tuple[str, str]],
) -> tuple[list[dict], float, float] | None:
    """Validate geometry returned from the untrusted page world."""
    if not isinstance(payload, dict):
        return None
    scroll_x = _bounded_native_geometry_number(
        payload.get("scrollX"),
        minimum=0.0,
        maximum=10_000_000.0,
    )
    scroll_y = _bounded_native_geometry_number(
        payload.get("scrollY"),
        minimum=0.0,
        maximum=10_000_000.0,
    )
    raw_markers = payload.get("markers")
    if scroll_x is None or scroll_y is None or not isinstance(raw_markers, list):
        return None

    markers: list[dict] = []
    seen_ids: set[str] = set()
    total_rects = 0
    for raw_marker in raw_markers:
        if len(markers) >= MAX_STORED_WEB_EXTRACT_ANCHORS:
            break
        if not isinstance(raw_marker, dict):
            continue
        marker_id = str(raw_marker.get("id") or "")
        expected = allowed_markers.get(marker_id)
        if expected is None or marker_id in seen_ids:
            continue
        state, kind = expected
        if raw_marker.get("state") != state or raw_marker.get("kind") != kind:
            continue
        raw_rects = raw_marker.get("rects")
        if not isinstance(raw_rects, list):
            continue

        rects: list[dict] = []
        for raw_rect in raw_rects[:_MAX_NATIVE_WEB_RECTS_PER_MARKER]:
            if total_rects >= _MAX_NATIVE_WEB_EXTRACTION_RECTS:
                break
            if not isinstance(raw_rect, dict):
                continue
            x = _bounded_native_geometry_number(
                raw_rect.get("x"),
                minimum=0.0,
                maximum=10_000_000.0,
            )
            y = _bounded_native_geometry_number(
                raw_rect.get("y"),
                minimum=0.0,
                maximum=10_000_000.0,
            )
            width = _bounded_native_geometry_number(
                raw_rect.get("width"),
                minimum=0.5,
                maximum=100_000.0,
            )
            height = _bounded_native_geometry_number(
                raw_rect.get("height"),
                minimum=0.5,
                maximum=100_000.0,
            )
            if x is None or y is None or width is None or height is None:
                continue
            rects.append(
                {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                }
            )
            total_rects += 1
        if not rects:
            continue
        seen_ids.add(marker_id)
        markers.append(
            {
                "id": marker_id,
                "state": state,
                "kind": kind,
                "rects": rects,
            }
        )
        if total_rects >= _MAX_NATIVE_WEB_EXTRACTION_RECTS:
            break
    return markers, scroll_x, scroll_y


def _ensure_native_web_extraction_overlay(view) -> _WebExtractionOverlay | None:
    overlay = _runtime.extraction_overlay
    try:
        if overlay is not None and overlay.parent() is view:
            overlay.setGeometry(view.rect())
            return overlay
    except (AttributeError, RuntimeError):
        pass
    try:
        overlay = _WebExtractionOverlay(view)
        overlay.setGeometry(view.rect())
    except Exception:
        _runtime.extraction_overlay = None
        return None
    _runtime.extraction_overlay = overlay
    return overlay


def _set_native_web_extraction_markers(
    markers: list[dict],
    *,
    scroll_x: float,
    scroll_y: float,
) -> None:
    overlay = _runtime.extraction_overlay
    if not markers and overlay is None:
        return
    if _runtime.dock is None:
        return
    try:
        view = _runtime.dock._view
        overlay = _ensure_native_web_extraction_overlay(view)
        if overlay is not None:
            try:
                overlay.set_zoom_factor(float(view.zoomFactor()))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                overlay.set_zoom_factor(1.0)
            overlay.set_markers(
                markers,
                scroll_x=scroll_x,
                scroll_y=scroll_y,
            )
    except Exception:
        return


def _stage_native_web_extraction_marker(
    record: dict,
    geometry: object,
) -> None:
    if not isinstance(geometry, dict):
        return
    anchor = record["anchor"]
    marker_id = str(anchor["id"])
    kind = "snapshot" if anchor.get("kind") == "snapshot" else "text"
    payload = {
        "scrollX": geometry.get("scrollX"),
        "scrollY": geometry.get("scrollY"),
        "markers": [
            {
                "id": marker_id,
                "state": "pending",
                "kind": kind,
                "rects": geometry.get("rects"),
            }
        ],
    }
    normalized = _normalize_native_web_extraction_geometry(
        payload,
        allowed_markers={marker_id: ("pending", kind)},
    )
    if normalized is None or not normalized[0] or _runtime.dock is None:
        return
    markers, scroll_x, scroll_y = normalized
    try:
        view = _runtime.dock._view
        overlay = _ensure_native_web_extraction_overlay(view)
        if overlay is None:
            return
        try:
            overlay.set_zoom_factor(float(view.zoomFactor()))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            overlay.set_zoom_factor(1.0)
        overlay.upsert_marker(
            markers[0],
            scroll_x=scroll_x,
            scroll_y=scroll_y,
        )
    except Exception:
        return


def _remove_native_web_extraction_marker(record: dict) -> None:
    overlay = _runtime.extraction_overlay
    if overlay is None:
        return
    try:
        overlay.remove_marker(str(record["anchor"]["id"]))
    except (KeyError, TypeError, AttributeError, RuntimeError):
        pass


def _promote_native_web_extraction_marker(record: dict) -> None:
    overlay = _runtime.extraction_overlay
    if overlay is None:
        return
    try:
        overlay.set_marker_state(str(record["anchor"]["id"]), "saved")
    except (KeyError, TypeError, AttributeError, RuntimeError):
        pass


def _clear_native_web_extraction_markers() -> None:
    _runtime.extraction_refresh_generation += 1
    overlay = _runtime.extraction_overlay
    if overlay is None:
        return
    try:
        overlay.set_markers([], scroll_x=0.0, scroll_y=0.0)
    except (AttributeError, RuntimeError):
        _runtime.extraction_overlay = None


def _sync_native_web_extraction_scroll(position) -> None:
    overlay = _runtime.extraction_overlay
    if overlay is None:
        return
    try:
        overlay.set_scroll_position(float(position.x()), float(position.y()))
    except (AttributeError, RuntimeError, TypeError, ValueError):
        pass


def _sync_native_web_extraction_overlay_geometry(view) -> None:
    overlay = _runtime.extraction_overlay
    if overlay is None:
        return
    try:
        overlay.setGeometry(view.rect())
    except (AttributeError, RuntimeError):
        _runtime.extraction_overlay = None


def _grab_web_view_without_extraction_markers(view, region=None):
    """Keep native extraction marks out of captured webpage snapshots."""
    overlay = _runtime.extraction_overlay
    overlay_was_visible = False
    if overlay is not None:
        try:
            overlay_was_visible = bool(overlay.isVisible())
            if overlay_was_visible:
                overlay.hide()
        except (AttributeError, RuntimeError):
            overlay = None
            _runtime.extraction_overlay = None
    try:
        return view.grab() if region is None else view.grab(region)
    finally:
        if overlay is not None and overlay_was_visible:
            try:
                overlay.raise_()
                overlay.show()
            except (AttributeError, RuntimeError):
                _runtime.extraction_overlay = None


def _web_extract_record_key(record: dict) -> tuple[int, str, str]:
    return (
        int(record["webCardId"]),
        str(record["url"]),
        str(record["anchor"]["id"]),
    )


def _runtime_pending_web_extract_records(profile: str) -> list[dict]:
    normalized_profile = str(profile or "")
    if _runtime.pending_extract_profile != normalized_profile:
        _runtime.pending_extract_profile = normalized_profile
        _runtime.pending_extract_records = []
    records = normalize_web_extract_records(
        _runtime.pending_extract_records,
        limit=MAX_PENDING_WEB_EXTRACT_RECORDS,
    )
    _runtime.pending_extract_records = records
    return list(records)


def _store_runtime_pending_web_extract_record(record: dict, profile: str) -> bool:
    records = _runtime_pending_web_extract_records(profile)
    key = _web_extract_record_key(record)
    if all(_web_extract_record_key(item) != key for item in records):
        records.append(record)
    if len(records) > MAX_PENDING_WEB_EXTRACT_RECORDS:
        records = records[-MAX_PENDING_WEB_EXTRACT_RECORDS:]
    _runtime.pending_extract_records = normalize_web_extract_records(
        records,
        limit=MAX_PENDING_WEB_EXTRACT_RECORDS,
    )
    return any(
        _web_extract_record_key(item) == key
        for item in _runtime.pending_extract_records
    )


def _remove_runtime_pending_web_extract_record(record: dict, profile: str) -> bool:
    records = _runtime_pending_web_extract_records(profile)
    key = _web_extract_record_key(record)
    retained = [item for item in records if _web_extract_record_key(item) != key]
    removed = len(retained) != len(records)
    _runtime.pending_extract_records = retained
    return removed


def _pending_web_extract_records() -> list[dict]:
    profile = str(_active_profile() or "")
    runtime_records = _runtime_pending_web_extract_records(profile)
    try:
        from . import add_card_dock

        add_card_records = add_card_dock.pending_web_extract_records()
    except Exception:
        add_card_records = []
    return normalize_web_extract_records(
        [*runtime_records, *add_card_records],
        limit=MAX_PENDING_WEB_EXTRACT_RECORDS,
    )


def _note_owns_web_extract_draft(note) -> bool:
    try:
        from . import add_card_dock

        return bool(add_card_dock.note_owns_add_card_draft(note))
    except Exception:
        return bool(
            note is not None
            and getattr(note, "_incremento_add_card_draft_owner", False)
        )


def _web_extract_records_for_note(note) -> list[dict]:
    try:
        from . import add_card_dock

        records = add_card_dock.web_extract_records_for_note(note)
    except Exception:
        records = getattr(note, "_incremento_web_extract_records", [])
    return normalize_web_extract_records(
        records,
        limit=MAX_PENDING_WEB_EXTRACT_RECORDS,
    )


def _schedule_web_extraction_highlight_refresh(*, delay_ms: int = 0) -> None:
    _runtime.extraction_schedule_generation += 1
    schedule_generation = _runtime.extraction_schedule_generation

    def _run_if_current() -> None:
        if schedule_generation != _runtime.extraction_schedule_generation:
            return
        _refresh_web_extraction_highlights()

    try:
        QTimer.singleShot(max(0, min(int(delay_ms), 2_000)), _run_if_current)
    except Exception:
        _run_if_current()


def _accept_web_extract_record(
    record: object,
    *,
    expected_profile: str,
) -> bool:
    """Stage an amber anchor before its Add-dock field transfer completes."""
    if str(_active_profile() or "") != str(expected_profile or ""):
        return False
    native_geometry = (
        record.get("_nativeGeometry") if isinstance(record, dict) else None
    )
    normalized = normalize_web_extract_record(record)
    if normalized is None:
        return False
    accepted = _store_runtime_pending_web_extract_record(
        normalized,
        str(expected_profile or ""),
    )
    try:
        from . import add_card_dock

        add_card_dock.append_pending_web_extract_record(normalized)
    except Exception:
        pass
    if accepted:
        _stage_native_web_extraction_marker(normalized, native_geometry)
        _schedule_web_extraction_highlight_refresh()
    return accepted


def _remove_pending_web_extract_record(
    record: object,
    *,
    expected_profile: str,
) -> bool:
    """Rollback one amber marker after the target field rejects its content."""
    if str(_active_profile() or "") != str(expected_profile or ""):
        return False
    normalized = normalize_web_extract_record(record)
    if normalized is None:
        return False
    removed = _remove_runtime_pending_web_extract_record(
        normalized,
        str(expected_profile or ""),
    )
    try:
        from . import add_card_dock

        removed = bool(add_card_dock.remove_pending_web_extract_record(normalized)) or removed
    except Exception:
        pass
    if removed:
        _remove_native_web_extraction_marker(normalized)
        _schedule_web_extraction_highlight_refresh()
    return removed


def discard_pending_web_extract_records() -> None:
    """Drop Web-dock fallback markers owned by the discarded Add draft."""
    profile = str(_active_profile() or "")
    records = _runtime_pending_web_extract_records(profile)
    for record in records:
        _remove_native_web_extraction_marker(record)
    _runtime.pending_extract_records = []
    _schedule_web_extraction_highlight_refresh()


def _fill_web_snapshot_field(
    add_card_dock_module,
    field_index: int,
    media_filename: str,
    current_url: str,
    *,
    extract_record: object = None,
    expected_profile: str,
    citation_html: str | None = None,
):
    """Stage a snapshot marker, insert the image, and rollback rejection."""
    if citation_html is None:
        try:
            citation_html = _controller.citation(current_url)
        except Exception:
            citation_html = None
    normalized_record = normalize_web_extract_record(extract_record)
    marker_staged = bool(
        normalized_record is not None
        and _accept_web_extract_record(
            normalized_record,
            expected_profile=expected_profile,
        )
    )
    on_complete = None
    if marker_staged and normalized_record is not None:
        fill_completion_seen = False

        def _on_complete(success: bool) -> None:
            nonlocal fill_completion_seen
            if fill_completion_seen:
                return
            fill_completion_seen = True
            if success:
                return
            _remove_pending_web_extract_record(
                normalized_record,
                expected_profile=expected_profile,
            )

        on_complete = _on_complete
    try:
        result = add_card_dock_module.fill_dock_field(
            int(field_index),
            f'<img src="{media_filename}">',
            include_pdf_citation=False,
            citation_html=citation_html,
            source_link_kind="web",
            on_complete=on_complete,
        )
    except Exception:
        if on_complete is not None:
            on_complete(False)
        raise
    if result is False and on_complete is not None:
        on_complete(False)
    return result


def _refresh_web_extraction_highlights() -> None:
    _runtime.extraction_refresh_generation += 1
    refresh_generation = _runtime.extraction_refresh_generation
    if _runtime.dock is None or _runtime.current_card_id is None:
        _clear_native_web_extraction_markers()
        return
    try:
        card_id = int(_runtime.current_card_id)
        profile = str(_active_profile() or "")
        current_url = normalize_web_extract_url(
            _runtime.dock._view.url().toString()
        )
        page = _runtime.dock._view.page()
    except Exception:
        return
    if card_id <= 0 or not profile or not current_url:
        _clear_native_web_extraction_markers()
        return

    try:
        saved = [
            anchor
            for raw_anchor in get_web_extract_anchors(
                _ADDON_DIR,
                profile,
                card_id,
                current_url,
                limit=MAX_STORED_WEB_EXTRACT_ANCHORS,
            )
            if (anchor := normalize_web_extract_anchor(raw_anchor)) is not None
        ]
    except Exception:
        saved = []

    saved_ids = {str(anchor["id"]) for anchor in saved}
    pending: list[dict] = []
    for record in normalize_web_extract_records(
        _pending_web_extract_records(),
        limit=MAX_PENDING_WEB_EXTRACT_RECORDS,
    ):
        if int(record["webCardId"]) != card_id or record["url"] != current_url:
            continue
        anchor = record["anchor"]
        if str(anchor["id"]) in saved_ids:
            continue
        pending.append(anchor)
        if len(pending) >= MAX_STORED_WEB_EXTRACT_ANCHORS:
            break

    payload = {"saved": saved, "pending": pending}
    payload_json = json.dumps(payload, ensure_ascii=False)
    while len(payload_json) > _MAX_WEB_HIGHLIGHT_SCRIPT_CHARS and pending:
        pending.pop()
        payload_json = json.dumps(payload, ensure_ascii=False)
    while len(payload_json) > _MAX_WEB_HIGHLIGHT_SCRIPT_CHARS and saved:
        saved.pop()
        payload_json = json.dumps(payload, ensure_ascii=False)
    if len(payload_json) > _MAX_WEB_HIGHLIGHT_SCRIPT_CHARS:
        payload_json = '{"saved": [], "pending": []}'

    allowed_markers: dict[str, tuple[str, str]] = {}
    for anchor in saved:
        allowed_markers[str(anchor["id"])] = (
            "saved",
            "snapshot" if anchor.get("kind") == "snapshot" else "text",
        )
    for anchor in pending:
        allowed_markers[str(anchor["id"])] = (
            "pending",
            "snapshot" if anchor.get("kind") == "snapshot" else "text",
        )

    if not allowed_markers:
        _set_native_web_extraction_markers([], scroll_x=0.0, scroll_y=0.0)
        return

    def _resolved(raw_geometry) -> None:
        if refresh_generation != _runtime.extraction_refresh_generation:
            return
        try:
            if (
                str(_active_profile() or "") != profile
                or int(_runtime.current_card_id or 0) != card_id
                or _runtime.dock is None
                or _runtime.dock._view.page() is not page
                or normalize_web_extract_url(
                    _runtime.dock._view.url().toString()
                )
                != current_url
            ):
                return
        except Exception:
            return
        geometry = raw_geometry if isinstance(raw_geometry, dict) else {}
        try:
            returned_card_id = int(geometry.get("cardId") or 0)
        except (TypeError, ValueError):
            returned_card_id = 0
        if (
            returned_card_id != card_id
            or normalize_web_extract_url(geometry.get("url")) != current_url
        ):
            _set_native_web_extraction_markers([], scroll_x=0.0, scroll_y=0.0)
            return
        normalized = _normalize_native_web_extraction_geometry(
            geometry,
            allowed_markers=allowed_markers,
        )
        if normalized is None:
            _set_native_web_extraction_markers([], scroll_x=0.0, scroll_y=0.0)
            return
        markers, scroll_x, scroll_y = normalized
        _set_native_web_extraction_markers(
            markers,
            scroll_x=scroll_x,
            scroll_y=scroll_y,
        )

    try:
        action_script = (
            "window.incrementoResolveExtractionRects "
            f"? window.incrementoResolveExtractionRects({payload_json}) : null;"
        )
        _run_web_javascript(
            page,
            action_script,
            _resolved,
        )
    except Exception:
        _set_native_web_extraction_markers([], scroll_x=0.0, scroll_y=0.0)


def refresh_web_extraction_highlights() -> None:
    """Refresh saved and draft extraction markers in the open Web reader."""
    _schedule_web_extraction_highlight_refresh()


def _restore_payload_for_web_url(
    current_url: str,
    *,
    allow_bookmark: bool,
    allow_scroll: bool,
) -> dict:
    return build_web_restore_payload(
        _web_progress_state(),
        current_url,
        allow_bookmark=allow_bookmark,
        allow_scroll=allow_scroll,
        remember_scroll=_remember_browser_card_scroll(),
    )


def _set_pending_web_restore(
    card_id: int,
    *,
    allow_bookmark: bool,
    allow_scroll: bool,
) -> None:
    _runtime.pending_restore = {
        "card_id": int(card_id),
        "allow_bookmark": bool(allow_bookmark),
        "allow_scroll": bool(allow_scroll),
    }


def _apply_web_restore_state(
    current_url: str,
    *,
    allow_bookmark: bool,
    allow_scroll: bool,
) -> None:
    if _runtime.dock is None or not current_url or current_url == "about:blank":
        return
    payload = _restore_payload_for_web_url(
        current_url,
        allow_bookmark=allow_bookmark,
        allow_scroll=allow_scroll,
    )
    try:
        _run_web_javascript(
            _runtime.dock._view.page(),
            "window.incrementoApplyRestoreState && "
            f"window.incrementoApplyRestoreState({json.dumps(payload)});"
        )
    except Exception:
        pass


def _save_web_bookmark() -> None:
    _controller.save_bookmark()


def _resolve_web_snapshot_anchor(rect: QRect, callback) -> None:
    """Resolve one viewport capture to a bounded, same-card region marker."""
    finished = [False]

    def _finish(record: dict | None) -> None:
        if finished[0]:
            return
        finished[0] = True
        callback(record)

    if _runtime.dock is None or _runtime.current_card_id is None:
        _finish(None)
        return
    try:
        rect_payload = {
            "x": int(rect.x()),
            "y": int(rect.y()),
            "width": int(rect.width()),
            "height": int(rect.height()),
        }
        expected_card_id = int(_runtime.current_card_id)
        expected_profile = str(_active_profile() or "")
        expected_url = normalize_web_extract_url(
            _runtime.dock._view.url().toString()
        )
        page = _runtime.dock._view.page()
    except Exception:
        _finish(None)
        return
    if (
        rect_payload["width"] < 6
        or rect_payload["height"] < 6
        or expected_card_id <= 0
        or not expected_profile
        or not expected_url
    ):
        _finish(None)
        return

    def _resolved(payload) -> None:
        try:
            if (
                str(_active_profile() or "") != expected_profile
                or int(_runtime.current_card_id or 0) != expected_card_id
                or _runtime.dock is None
                or normalize_web_extract_url(
                    _runtime.dock._view.url().toString()
                )
                != expected_url
            ):
                _finish(None)
                return
        except Exception:
            _finish(None)
            return

        data = payload if isinstance(payload, dict) else {}
        try:
            captured_card_id = int(data.get("cardId") or 0)
        except (TypeError, ValueError):
            captured_card_id = 0
        captured_url = normalize_web_extract_url(data.get("url"))
        record = None
        if captured_card_id == expected_card_id and captured_url == expected_url:
            record = normalize_web_extract_record(
                {
                    "version": 1,
                    "webCardId": expected_card_id,
                    "url": expected_url,
                    "anchor": data.get("anchor"),
                }
            )
            if record is not None and record["anchor"].get("kind") != "snapshot":
                record = None
            if record is not None:
                anchor = record["anchor"]
                record["_nativeGeometry"] = {
                    "rects": data.get("rects")
                    if isinstance(data.get("rects"), list)
                    else [
                        {
                            "x": anchor["pageX"],
                            "y": anchor["pageY"],
                            "width": anchor["width"],
                            "height": anchor["height"],
                        }
                    ],
                    "scrollX": data.get("scrollX", 0),
                    "scrollY": data.get("scrollY", 0),
                }
        _finish(record)

    action_script = (
        "(function(){"
        "  return window.incrementoCaptureSnapshotAnchor "
        "    ? window.incrementoCaptureSnapshotAnchor("
        f"{json.dumps(rect_payload)}"
        ") : null;"
        "})();"
    )
    try:
        _run_web_javascript(
            page,
            action_script,
            _resolved,
        )
        # A destroyed or navigating page may drop the JavaScript callback.
        # Do not strand the already-captured image in that case.
        QTimer.singleShot(750, lambda: _finish(None))
    except Exception:
        _finish(None)


def _resolve_web_extraction(callback) -> None:
    """Resolve bounded selection text and its optional same-page DOM anchor."""
    native_text = _current_selected_text()
    if _runtime.dock is None or _runtime.current_card_id is None:
        callback(native_text, None)
        return
    try:
        expected_card_id = int(_runtime.current_card_id)
        expected_profile = str(_active_profile() or "")
        expected_url = normalize_web_extract_url(
            _runtime.dock._view.url().toString()
        )
        page = _runtime.dock._view.page()
    except Exception:
        callback(native_text, None)
        return
    if expected_card_id <= 0 or not expected_profile or not expected_url:
        callback(native_text, None)
        return

    def _resolved(payload) -> None:
        try:
            if (
                str(_active_profile() or "") != expected_profile
                or int(_runtime.current_card_id or 0) != expected_card_id
                or normalize_web_extract_url(
                    _runtime.dock._view.url().toString()
                )
                != expected_url
            ):
                callback("", None)
                return
        except Exception:
            callback("", None)
            return

        data = payload if isinstance(payload, dict) else {}
        captured_text = external_plain_text(data.get("text")).strip()
        text = native_text or captured_text
        record = None
        # A native selection from a cross-origin frame can differ from the
        # ApplicationWorld selection. Keep its text, but never attach a stale
        # top-frame anchor to it.
        selection_matches = not native_text or (
            _normalized_web_selection_identity(native_text)
            == _normalized_web_selection_identity(captured_text)
        )
        captured_url = normalize_web_extract_url(data.get("url"))
        try:
            captured_card_id = int(data.get("cardId") or 0)
        except (TypeError, ValueError):
            captured_card_id = 0
        if (
            selection_matches
            and captured_card_id == expected_card_id
            and captured_url == expected_url
        ):
            record = normalize_web_extract_record(
                {
                    "version": 1,
                    "webCardId": expected_card_id,
                    "url": expected_url,
                    "anchor": data.get("anchor"),
                }
            )
            if record is not None:
                record["_nativeGeometry"] = {
                    "rects": data.get("rects"),
                    "scrollX": data.get("scrollX"),
                    "scrollY": data.get("scrollY"),
                }
        callback(text, record)

    try:
        action_script = (
            "(function(){"
            "  return window.incrementoCaptureExtraction "
            "    ? window.incrementoCaptureExtraction() : null;"
            "})();"
        )
        _run_web_javascript(
            page,
            action_script,
            _resolved,
        )
    except Exception:
        callback(native_text, None)


def _resolve_web_selection(callback) -> None:
    _resolve_web_extraction(lambda text, _record: callback(text))


def _update_native_selection_state() -> None:
    try:
        from . import add_card_dock as _add_card_dock_mod

        _add_card_dock_mod.update_selection_state(
            "web",
            text=_current_selected_text(),
        )
    except Exception:
        pass


def _extract_web_selection_to_field(idx: int) -> None:
    _controller.extract_selection_to_field(idx)


def _get_add_card_field_names() -> list[str]:
    from . import add_card_dock as _add_card_dock_mod

    _add_card_dock_mod.open_add_card_dock()
    try:
        dock = _add_card_dock_mod.get_add_card_dock()
        if dock:
            note = dock.widget().editor.note
            if note:
                field_names = [f["name"] for f in note.note_type()["flds"]]
                if field_names:
                    return field_names
    except Exception:
        pass
    return [t("reader_field_number", number=i + 1) for i in range(4)]


def _prompt_extract_target_field() -> int:
    field_names = _get_add_card_field_names()
    picker = QDialog(mw)
    picker.setWindowTitle(t("reader_web_extract_into_field"))
    picker.setFixedWidth(340)
    layout = QVBoxLayout(picker)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(0)

    layout.addWidget(QLabel(t("reader_web_insert_text_into")))
    layout.addSpacing(12)

    chosen_idx = [-1]

    def _make_handler(idx):
        def _handler():
            chosen_idx[0] = idx
            picker.accept()

        return _handler

    for i, name in enumerate(field_names):
        btn = QPushButton(name)
        btn.setStyleSheet("text-align: left; padding: 7px 12px;")
        btn.clicked.connect(_make_handler(i))
        layout.addWidget(btn)
        layout.addSpacing(4)

    layout.addSpacing(8)
    cancel_btn = QPushButton(t("reader_cancel"))
    cancel_btn.clicked.connect(picker.reject)
    layout.addWidget(cancel_btn)

    if not picker.exec():
        return -1
    return chosen_idx[0]


def _extract_web_selection_with_picker() -> None:
    _controller.extract_selection_with_picker()


def _ensure_snapshot_band(view) -> None:
    if _runtime.snapshot_shield is None or _runtime.snapshot_shield.parent() is not view:
        _runtime.snapshot_shield = QWidget(view)
        _runtime.snapshot_shield.setCursor(Qt.CursorShape.CrossCursor)
        _runtime.snapshot_shield.setStyleSheet("background: rgba(37,99,235,0.02);")
        _runtime.snapshot_shield.hide()
    if _runtime.snapshot_overlay is None or _runtime.snapshot_overlay.parent() is not _runtime.snapshot_shield:
        _runtime.snapshot_overlay = QWidget(_runtime.snapshot_shield)
        _runtime.snapshot_overlay.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        _runtime.snapshot_overlay.setStyleSheet(
            "border: 2px solid rgba(37,99,235,0.95);"
            "background: rgba(37,99,235,0.22);"
        )
        _runtime.snapshot_overlay.hide()


def _set_web_snapshot_mode(active: bool) -> None:
    _runtime.snapshot_mode = bool(active)
    _runtime.snapshot_origin = None
    if _runtime.dock is not None:
        try:
            _ensure_snapshot_band(_runtime.dock._view)
        except Exception:
            pass
    if _runtime.snapshot_shield is not None:
        try:
            _runtime.snapshot_shield.hide()
        except Exception:
            pass
    if _runtime.snapshot_overlay is not None:
        try:
            _runtime.snapshot_overlay.hide()
        except Exception:
            pass
    if _runtime.dock is not None:
        try:
            _runtime.dock._view.setCursor(
                Qt.CursorShape.CrossCursor
                if _runtime.snapshot_mode
                else Qt.CursorShape.ArrowCursor
            )
        except Exception:
            pass
        try:
            _runtime.dock._view.unsetCursor() if not _runtime.snapshot_mode else None
        except Exception:
            pass
        if _runtime.snapshot_mode and _runtime.snapshot_shield is not None:
            try:
                _runtime.snapshot_shield.setGeometry(_runtime.dock._view.rect())
                _runtime.snapshot_shield.raise_()
                _runtime.snapshot_shield.show()
            except Exception:
                pass
        try:
            _runtime.dock._snapshot_btn.setText(
                t("reader_web_drag_to_capture") if _runtime.snapshot_mode else t("reader_snapshot")
            )
            _runtime.dock._snapshot_btn.setStyleSheet(
                (
                    "font-weight: bold;"
                    "color: white;"
                    "background: rgba(37,99,235,0.92);"
                    "border: 1px solid rgba(29,78,216,1.0);"
                    "border-radius: 4px;"
                    "padding: 0 8px;"
                    if _runtime.snapshot_mode
                    else ""
                )
            )
        except Exception:
            pass
    app = QApplication.instance()
    if app is not None:
        try:
            if _runtime.snapshot_mode and not _runtime.snapshot_override_cursor:
                app.setOverrideCursor(Qt.CursorShape.CrossCursor)
                _runtime.snapshot_override_cursor = True
            elif not _runtime.snapshot_mode and _runtime.snapshot_override_cursor:
                app.restoreOverrideCursor()
                _runtime.snapshot_override_cursor = False
        except Exception:
            _runtime.snapshot_override_cursor = False


def _current_web_source_rows() -> list[dict]:
    return _controller.current_source_rows()


def _refresh_web_cards_panel() -> None:
    _controller.refresh_cards_panel()


def _toggle_web_cards_panel() -> None:
    _controller.toggle_cards_panel()


def _insert_snapshot_into_field(
    pixmap: QPixmap,
    current_url: str,
    *,
    extract_record: dict | None = None,
    expected_profile: str = "",
) -> None:
    _controller.insert_snapshot_into_field(
        pixmap,
        current_url,
        extract_record=extract_record,
        expected_profile=expected_profile,
    )


def _handle_web_snapshot(data: dict) -> None:
    _controller.handle_snapshot(data)


def _toggle_snapshot_mode() -> None:
    _set_web_snapshot_mode(not _runtime.snapshot_mode)


def _open_result_link(qurl) -> None:
    s = qurl.toString() if hasattr(qurl, "toString") else str(qurl)
    if s.startswith("inc://web-bookmark-delete/"):
        bookmark_id = s.rsplit("/", 1)[-1]
        card_id = current_web_card_id()
        if card_id is None:
            return
        try:
            delete_reader_bookmark(
                _ADDON_DIR,
                _active_profile(),
                int(card_id),
                "web",
                bookmark_id,
            )
        except Exception as exc:
            showInfo(t("reader_web_bookmark_delete_failed", error=exc))
        _controller.refresh_bookmarks_panel()
        return
    if s.startswith("inc://web-bookmark-open/"):
        bookmark_id = s.rsplit("/", 1)[-1]
        card_id = current_web_card_id()
        if card_id is None or _runtime.dock is None:
            return
        bookmark = next((row for row in _controller.bookmark_rows() if str(row.get("id") or "") == bookmark_id), None)
        if not bookmark:
            return
        location = bookmark.get("location") or {}
        target_url = str(location.get("url") or "").strip()
        if not target_url:
            return
        payload = {
            "rememberScroll": True,
            "scrollRatio": float(location.get("scroll_ratio", 0.0) or 0.0),
            "bookmark": location.get("bookmark_payload") or None,
        }
        _runtime.pending_bookmark_restore = {
            "card_id": int(card_id),
            "payload": payload,
        }
        current_url = _runtime.dock._view.url().toString()
        if current_url == target_url:
            _run_web_javascript(
                _runtime.dock._view.page(),
                "window.incrementoApplyRestoreState && "
                f"window.incrementoApplyRestoreState({json.dumps(payload)});"
            )
            _runtime.pending_bookmark_restore = None
        else:
            _runtime.dock._view.load(QUrl(target_url))
        return
    if not s.startswith("inc://card/"):
        return
    try:
        note_id = int(s.rsplit("/", 1)[1])
    except Exception:
        return
    try:
        from aqt import dialogs

        b = dialogs.open("Browser", mw)
        b.search_for(f"nid:{note_id}")
    except Exception:
        pass


def _build_web_dock():
    return _controller.build_dock()


def _on_track_web_window_toggled(checked: bool) -> None:
    _runtime.track_window_with_extension = bool(checked)


def _open_web_in_window() -> None:
    _controller.open_in_window()


def _web_go_home() -> None:
    _controller.go_home()


def reset_for_profile_switch() -> None:
    """Reset Qt WebEngine profile singleton on Anki profile switch.

    Must be called before migrate_to_profile_dir so the new profile is created
    with the correct per-profile storage path on next dock open.
    """
    _clear_native_web_extraction_markers()
    _runtime.extraction_schedule_generation += 1
    _runtime.profile = None
    _runtime.current_card_id = None
    _runtime.current_home_url = None
    _runtime.pending_restore = None
    _runtime.pending_bookmark_restore = None
    if _runtime.dock is not None:
        try:
            _runtime.dock.hide()
            _runtime.dock.deleteLater()
        except Exception:
            pass
        _runtime.dock = None
    _runtime.extraction_overlay = None


def show_web_in_dock(
    card_id: int,
    home_url: str,
    last_url: str,
    *,
    prefer_bookmark: bool = True,
    restore_scroll: bool = True,
) -> None:
    _controller.show_in_dock(
        card_id,
        home_url,
        last_url,
        prefer_bookmark=prefer_bookmark,
        restore_scroll=restore_scroll,
    )


def open_web_location(card_id: int, target_url: str) -> bool:
    return _controller.open_location(card_id, target_url)


def sync_external_web_url(card_id: int, url: str) -> bool:
    """If this web card is currently open, load the latest externally synced URL."""
    return _controller.sync_external_url(card_id, url)


def sync_external_web_media_state(
    card_id: int,
    url: str,
    media_url: str,
    media_title: str,
    media_seconds: float,
) -> bool:
    return _controller.sync_external_media_state(
        card_id,
        url,
        media_url,
        media_title,
        media_seconds,
    )


def on_web_question_shown(card) -> None:
    _controller.on_question_shown(card)


def on_web_reviewer_will_end() -> None:
    _controller.on_reviewer_will_end()


def on_add_cards_did_add_note(note) -> None:
    _controller.on_add_cards_did_add_note(note)


def sync_web_note_type() -> None:
    try:
        ensure_web_note_type(mw.col)
    except Exception:
        pass


def add_web_function() -> None:
    """Incremento -> Add Content -> Web Page"""
    deck_names = [d.name for d in mw.col.decks.all_names_and_ids()]
    from .add_web_dialog import AddWebDialog

    dlg = AddWebDialog(deck_names, default_deck="Topics", parent=mw)
    if not dlg.exec():
        return
    url = dlg.url
    if not url:
        showInfo(t("reader_web_enter_url"))
        return
    title = dlg.title or url
    try:
        add_web_card(mw.col, url, title, dlg.deck_name, tags=dlg.tags)
        mw.col.reset()
        tooltip(t("reader_web_card_added", title=title, deck=dlg.deck_name))
    except Exception as e:
        showInfo(t("reader_web_card_add_failed", error=e))


def get_selected_text(callback) -> None:
    _controller.get_selected_text(callback)


def get_selected_extraction(callback) -> None:
    """Return ``(text, record)`` for Add Card's Web transfer buttons."""
    _resolve_web_extraction(callback)
