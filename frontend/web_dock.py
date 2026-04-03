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
import os
import re
import tempfile
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse

from aqt import mw
from aqt.utils import showInfo, tooltip
from aqt.qt import (
    QApplication,
    QCheckBox,
    QDialog,
    QDockWidget,
    QEvent,
    QHBoxLayout,
    QLabel,
    QObject,
    QPoint,
    QPushButton,
    QRect,
    QShortcut,
    QKeySequence,
    QTextBrowser,
    QTimer,
    QVBoxLayout,
    QWidget,
    Qt,
    qconnect,
)
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.db import add_web_card_source, get_web_card_sources
    from ..backend.web_manager import (
        WEB_NOTE_TYPE,
        add_web_card,
        build_web_restore_payload,
        build_external_web_url,
        configured_remember_browser_card_scroll,
        ensure_web_note_type,
        get_web_progress,
        get_web_url,
        set_web_bookmark,
        set_web_scroll_position,
        set_web_url,
    )
except ImportError:
    from db import add_web_card_source, get_web_card_sources
    from web_manager import (
        WEB_NOTE_TYPE,
        add_web_card,
        build_web_restore_payload,
        build_external_web_url,
        configured_remember_browser_card_scroll,
        ensure_web_note_type,
        get_web_progress,
        get_web_url,
        set_web_bookmark,
        set_web_scroll_position,
        set_web_url,
    )

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)
_WEB_BRIDGE_JS_PATH = os.path.join(_ADDON_DIR, "web", "web_dock_bridge.js")

_PYCMD_BRIDGE = "__incremento_webdock_pycmd__:"
_MSG_SELECTION_STATE = "incremento_selection_state:"
_MSG_FILL_FIELD = "incremento_web_fill_field:"
_MSG_SNAPSHOT = "incremento_web_snapshot:"
_MSG_PROGRESS = "incremento_web_progress:"


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
    bridge_js_template: str | None = None


_runtime = _WebDockRuntime()


def _remember_browser_card_scroll() -> bool:
    try:
        return bool(configured_remember_browser_card_scroll())
    except Exception:
        return True


def _web_progress_state(card_id: int | None = None) -> dict:
    return _controller.progress_state(card_id)


def _refresh_web_bookmark_button() -> None:
    _controller.refresh_bookmark_button()


def _persist_web_url(card_id: int | None, url: str | None) -> None:
    try:
        target_card_id = int(card_id) if card_id is not None else 0
    except Exception:
        target_card_id = 0
    target_url = str(url or "").strip()
    if target_card_id <= 0 or not target_url or target_url == "about:blank":
        return
    try:
        set_web_url(_ADDON_DIR, target_card_id, target_url)
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


def _load_web_bridge_js_template() -> str:
    if _runtime.bridge_js_template is None:
        with open(_WEB_BRIDGE_JS_PATH, "r", encoding="utf-8") as fh:
            _runtime.bridge_js_template = fh.read()
    return _runtime.bridge_js_template


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
            }
        try:
            return get_web_progress(_ADDON_DIR, target_card_id)
        except Exception:
            return {
                "url": "",
                "scroll_ratio": 0.0,
                "bookmark_url": "",
                "bookmark_payload": {},
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
            self.runtime.dock._view.page().runJavaScript(
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
        progress = self.progress_state()
        has_bookmark = bool(progress.get("bookmark_url")) and bool(
            progress.get("bookmark_payload")
        )
        try:
            self.runtime.dock._bookmark_btn.setText("Bookmark")
            self.runtime.dock._bookmark_btn.setToolTip(
                "Replace the saved browser-card bookmark with the current reading position."
                if has_bookmark
                else "Save the current reading position as the browser-card bookmark."
            )
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
            self.runtime.dock._cards_btn.setText(f"Cards {count}")
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
            "Cards created at this URL",
            "</div>",
            (
                "<div style='color:#888;margin-bottom:8px;word-break:break-all'>"
                + current_url.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                + "</div>"
            ),
        ]
        for row in rows:
            excerpt = str(row.get("excerpt") or "").strip()
            safe_excerpt = (
                excerpt.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                or "<i style='color:#888'>No text</i>"
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
            tooltip("Incremento: no cards recorded for this URL yet.")
            return
        self.refresh_cards_panel()
        try:
            visible = self.runtime.dock._cards_panel.isVisible()
            self.runtime.dock._cards_panel.setVisible(not visible)
        except Exception:
            pass

    def save_bookmark(self) -> None:
        if self.runtime.dock is None or self.runtime.current_card_id is None:
            tooltip("Incremento: no browser card is currently open.")
            return
        try:
            target_card_id = int(self.runtime.current_card_id)
        except Exception:
            tooltip("Incremento: no browser card is currently open.")
            return

        def _handle(payload) -> None:
            if not isinstance(payload, dict):
                tooltip("Incremento: couldn't place a bookmark here.")
                return
            current_url = str(payload.get("url") or "").strip()
            bookmark = payload.get("bookmark")
            if not current_url or not isinstance(bookmark, dict):
                tooltip("Incremento: couldn't place a bookmark here.")
                return
            try:
                set_web_bookmark(
                    _ADDON_DIR,
                    target_card_id,
                    url=current_url,
                    bookmark_payload=bookmark,
                )
            except Exception as exc:
                showInfo(f"Failed to save bookmark:\n{exc}")
                return
            self.refresh_bookmark_button()
            tooltip("Incremento: bookmark saved.")

        try:
            self.runtime.dock._view.page().runJavaScript(
                "window.incrementoCaptureBookmark && window.incrementoCaptureBookmark();",
                _handle,
            )
        except Exception as exc:
            showInfo(f"Failed to save bookmark:\n{exc}")

    def extract_selection_to_field(self, idx: int) -> None:
        def _apply(text: str) -> None:
            if not text:
                tooltip("Select some text first.")
                return
            try:
                from . import add_card_dock as _add_card_dock_mod

                _add_card_dock_mod.fill_dock_field(
                    idx,
                    text,
                    include_pdf_citation=False,
                    citation_html=self.citation(),
                    source_link_kind="web",
                )
            except Exception as exc:
                showInfo(f"Web extraction failed:\n{exc}")

        _resolve_web_selection(_apply)

    def extract_selection_with_picker(self) -> None:
        target_idx = _prompt_extract_target_field()
        if target_idx < 0:
            return
        self.extract_selection_to_field(target_idx)

    def insert_snapshot_into_field(self, pixmap: QPixmap, current_url: str) -> None:
        from . import add_card_dock as _add_card_dock_mod

        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            if not pixmap.save(tmp_path, "PNG"):
                raise RuntimeError("Could not encode snapshot image.")
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
            field_names = [f"Field {i + 1}" for i in range(4)]

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
        picker.setWindowTitle("Insert snapshot into field")
        picker.setFixedWidth(340)
        layout = QVBoxLayout(picker)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(0)

        preview_lbl = QLabel()
        preview_lbl.setPixmap(scaled)
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview_lbl)

        layout.addSpacing(14)
        layout.addWidget(QLabel("Insert image into:"))
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
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(picker.reject)
        layout.addWidget(cancel_btn)

        if not picker.exec() or chosen_idx[0] < 0:
            return

        html = f'<img src="{media_filename}">'
        _add_card_dock_mod.fill_dock_field(
            chosen_idx[0],
            html,
            include_pdf_citation=False,
            citation_html=self.citation(current_url),
            source_link_kind="web",
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
            raise RuntimeError(f"Invalid snapshot bounds: {exc}") from exc
        if width < 6 or height < 6:
            return
        current_url = str(data.get("url") or self.current_display_url()).strip()
        try:
            pixmap = self.runtime.dock._view.grab()
        except Exception as exc:
            raise RuntimeError(f"Could not capture web view: {exc}") from exc
        if pixmap.isNull():
            raise RuntimeError("Could not capture web view.")
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
            raise RuntimeError("The selected region was outside the current viewport.")
        try:
            crop.setDevicePixelRatio(dpr)
        except Exception:
            pass
        self.insert_snapshot_into_field(crop, current_url)

    def build_dock(self):
        from PyQt6.QtWebEngineCore import (
            QWebEngineProfile as _WEProf,
            QWebEngineSettings as _WES,
        )

        dock = QDockWidget("Web", mw)
        dock.setObjectName("incremento_web_dock")
        dock.setMinimumWidth(600)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        view = QWebEngineView(container)

        if self.runtime.profile is None:
            self.runtime.profile = _WEProf("incremento_web")
            self.runtime.profile.setPersistentStoragePath(
                os.path.join(_ADDON_DIR, "user_files", "web_profile")
            )
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

        page = _WebDockPage(self.runtime)
        view.setPage(page)
        vbox.addWidget(view, 1)

        ctrl = QWidget(container)
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(8, 4, 8, 4)
        ctrl_layout.setSpacing(6)

        url_lbl = QLabel("")
        url_lbl.setStyleSheet("font-family: monospace; font-size: 11px; color: #888;")
        url_lbl.setWordWrap(False)
        url_lbl.setMaximumWidth(360)
        ctrl_layout.addWidget(url_lbl, 1)

        add_card_btn = QPushButton("+ Add Card")
        ctrl_layout.addWidget(add_card_btn)

        extract_btn = QPushButton("Extract")
        extract_btn.setToolTip(
            "Copy the current text selection into a field in the Add Card dock."
        )
        ctrl_layout.addWidget(extract_btn)

        snapshot_btn = QPushButton("Snapshot")
        snapshot_btn.setToolTip(
            "Capture an image from the current viewport, like the PDF snapshot tool."
        )
        ctrl_layout.addWidget(snapshot_btn)

        bookmark_btn = QPushButton("Bookmark")
        ctrl_layout.addWidget(bookmark_btn)

        cards_btn = QPushButton("Cards 0")
        cards_btn.setVisible(False)
        ctrl_layout.addWidget(cards_btn)

        home_btn = QPushButton("Home")
        home_btn.setFixedWidth(70)
        ctrl_layout.addWidget(home_btn)

        track_cb = QCheckBox("Track via Chrome extension")
        track_cb.setChecked(bool(self.runtime.track_window_with_extension))
        track_cb.setToolTip(
            "When checked, opening this page externally lets the Incremento Companion "
            "extension keep the web card synced to the latest page visited in that tab."
        )
        ctrl_layout.addWidget(track_cb)

        window_btn = QPushButton("Open in Window")
        ctrl_layout.addWidget(window_btn)

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

        dock.setWidget(container)
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        dock._view = view
        dock._url_lbl = url_lbl
        dock._track_cb = track_cb
        dock._extract_btn = extract_btn
        dock._snapshot_btn = snapshot_btn
        dock._bookmark_btn = bookmark_btn
        dock._cards_btn = cards_btn
        dock._cards_panel = cards_panel

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

        def _on_load_finished(ok):
            if not ok or self.runtime.current_card_id is None:
                return
            url_str = view.url().toString()
            _persist_web_url(self.runtime.current_card_id, url_str)
            _set_web_snapshot_mode(False)
            try:
                view.page().runJavaScript(_build_web_bridge_js())
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
            self.refresh_cards_panel()
            self.refresh_bookmark_button()

        def _on_selection_changed():
            _update_native_selection_state()

        view.urlChanged.connect(_on_url_changed)
        view.loadFinished.connect(_on_load_finished)
        view.page().selectionChanged.connect(_on_selection_changed)
        qconnect(home_btn.clicked, self.go_home)
        qconnect(extract_btn.clicked, self.extract_selection_with_picker)
        qconnect(snapshot_btn.clicked, _toggle_snapshot_mode)
        qconnect(bookmark_btn.clicked, self.save_bookmark)
        qconnect(cards_btn.clicked, self.toggle_cards_panel)
        qconnect(window_btn.clicked, self.open_in_window)
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
            tooltip("Incremento: no web card is currently open.")
            return

        current_url = self.current_display_url()
        if not current_url:
            tooltip("Incremento: this web card has no valid URL.")
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
            set_web_url(_ADDON_DIR, self.runtime.current_card_id, current_url)
        except Exception:
            pass

        try:
            ok = bool(QDesktopServices.openUrl(QUrl(open_url)))
        except Exception:
            ok = False
        if not ok:
            tooltip("Incremento: failed to open system browser.")
            return

        if track_enabled:
            tooltip(
                "Incremento: browser tracking enabled for this web card tab "
                "(requires the Incremento Companion extension)."
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
        _set_web_snapshot_mode(False)
        try:
            self.runtime.dock._cards_panel.hide()
            self.runtime.dock._cards_panel.setHtml("")
            self.runtime.dock._cards_btn.setVisible(False)
            self.runtime.dock._cards_btn.setText("Cards 0")
        except Exception:
            pass
        self.refresh_bookmark_button()
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

    def open_location(self, card_id: int, target_url: str) -> bool:
        try:
            card = mw.col.get_card(int(card_id))
            note = mw.col.get_note(card.nid)
            home_url = note["URL"]
        except Exception:
            return False
        target = str(target_url or "").strip()
        if not target:
            target = get_web_url(_ADDON_DIR, int(card_id)) or home_url
        try:
            set_web_url(_ADDON_DIR, int(card_id), target)
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
            last_url = get_web_url(_ADDON_DIR, card.id)
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
        parts = []
        for field in (note.fields or [])[:2]:
            plain = re.sub(r"<[^>]+>", "", field).strip()[:120]
            if plain:
                parts.append(plain)
        excerpt = " / ".join(parts)[:200]
        try:
            add_web_card_source(
                _ADDON_DIR,
                int(self.runtime.current_card_id),
                current_url,
                note.id,
                excerpt,
            )
        except Exception:
            return
        self.refresh_cards_panel()
        try:
            if self.runtime.dock._cards_panel.isVisible():
                self.runtime.dock._cards_panel.show()
        except Exception:
            pass

    def get_selected_text(self, callback) -> None:
        _resolve_web_selection(callback)


_controller = _WebDockController(_runtime)


def web_citation(url: str | None = None) -> str:
    return _controller.citation(url)


class _WebDockPage(QWebEnginePage):
    def __init__(self, runtime: _WebDockRuntime):
        super().__init__(runtime.profile)
        self._runtime = runtime

    def javaScriptConsoleMessage(self, level, message, line, source):
        if not message.startswith(_PYCMD_BRIDGE):
            return
        msg = message[len(_PYCMD_BRIDGE) :]
        if msg.startswith(_MSG_SELECTION_STATE):
            try:
                data = json.loads(msg[len(_MSG_SELECTION_STATE) :])
                from . import add_card_dock as _add_card_dock_mod

                _add_card_dock_mod.update_selection_state(
                    "web",
                    has_text=bool(data.get("hasText")),
                )
            except Exception:
                pass
            return
        if msg.startswith(_MSG_FILL_FIELD):
            try:
                data = json.loads(msg[len(_MSG_FILL_FIELD) :])
                from . import add_card_dock as _add_card_dock_mod

                _add_card_dock_mod.fill_dock_field(
                    int(data["idx"]),
                    str(data.get("text") or ""),
                    include_pdf_citation=False,
                    citation_html=web_citation(data.get("url")),
                    source_link_kind="web",
                )
            except Exception:
                pass
            return
        if msg.startswith(_MSG_SNAPSHOT):
            try:
                data = json.loads(msg[len(_MSG_SNAPSHOT) :])
                _handle_web_snapshot(data)
            except Exception as exc:
                showInfo(f"Web snapshot failed:\n{exc}")
            return
        if msg.startswith(_MSG_PROGRESS):
            try:
                data = json.loads(msg[len(_MSG_PROGRESS) :])
                _persist_web_scroll(self._runtime.current_card_id, data)
            except Exception:
                pass


class _WebInteractionFilter(QObject):
    def __init__(self, runtime: _WebDockRuntime, parent=None):
        super().__init__(parent)
        self._runtime = runtime

    def eventFilter(self, watched, event):
        if self._runtime.dock is None or not self._runtime.snapshot_mode:
            return False
        try:
            if not self._runtime.dock.isVisible():
                return False
            view = self._runtime.dock._view
        except Exception:
            return False

        etype = event.type()
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
                pixmap = view.grab(rect)
            except Exception as exc:
                showInfo(f"Web snapshot failed:\n{exc}")
                return True
            if pixmap.isNull():
                showInfo("Web snapshot failed:\nCould not capture selected region.")
                return True
            try:
                _insert_snapshot_into_field(pixmap, current_url)
            except Exception as exc:
                showInfo(f"Web snapshot failed:\n{exc}")
            return True

        return False


def _build_web_bridge_js() -> str:
    script = _load_web_bridge_js_template()
    return (
        script.replace("__PYCMD_PREFIX__", json.dumps(_PYCMD_BRIDGE))
        .replace("__MSG_SELECTION__", json.dumps(_MSG_SELECTION_STATE))
        .replace("__MSG_FILL__", json.dumps(_MSG_FILL_FIELD))
        .replace("__MSG_SNAPSHOT__", json.dumps(_MSG_SNAPSHOT))
        .replace("__MSG_PROGRESS__", json.dumps(_MSG_PROGRESS))
    )


def _current_web_display_url() -> str:
    return _controller.current_display_url()


def _current_selected_text() -> str:
    if _runtime.dock is None:
        return ""
    try:
        text = _runtime.dock._view.page().selectedText() or ""
        text = str(text).replace("\u2029", "\n").strip()
        if text:
            return text
    except Exception:
        pass
    return ""


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
        _runtime.dock._view.page().runJavaScript(
            "window.incrementoApplyRestoreState && "
            f"window.incrementoApplyRestoreState({json.dumps(payload)});"
        )
    except Exception:
        pass


def _save_web_bookmark() -> None:
    _controller.save_bookmark()


def _resolve_web_selection(callback) -> None:
    text = _current_selected_text()
    if text:
        callback(text)
        return
    if _runtime.dock is None:
        callback("")
        return
    try:
        _runtime.dock._view.page().runJavaScript(
            "(function(){ return (window._incrementoLastSelection || "
            "(window.getSelection && window.getSelection().toString()) || '').trim(); })();",
            lambda text: callback(str(text or "").strip()),
        )
    except Exception:
        callback("")


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
    return [f"Field {i + 1}" for i in range(4)]


def _prompt_extract_target_field() -> int:
    field_names = _get_add_card_field_names()
    picker = QDialog(mw)
    picker.setWindowTitle("Extract selection into field")
    picker.setFixedWidth(340)
    layout = QVBoxLayout(picker)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(0)

    layout.addWidget(QLabel("Insert selected text into:"))
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
    cancel_btn = QPushButton("Cancel")
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
                "Drag to Capture" if _runtime.snapshot_mode else "Snapshot"
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


def _insert_snapshot_into_field(pixmap: QPixmap, current_url: str) -> None:
    _controller.insert_snapshot_into_field(pixmap, current_url)


def _handle_web_snapshot(data: dict) -> None:
    _controller.handle_snapshot(data)


def _toggle_snapshot_mode() -> None:
    _set_web_snapshot_mode(not _runtime.snapshot_mode)


def _open_result_link(qurl) -> None:
    s = qurl.toString() if hasattr(qurl, "toString") else str(qurl)
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
        showInfo("Please enter a URL.")
        return
    title = dlg.title or url
    try:
        add_web_card(mw.col, url, title, dlg.deck_name, tags=dlg.tags)
        mw.col.reset()
        tooltip(f"Web card '{title}' added to {dlg.deck_name}.")
    except Exception as e:
        showInfo(f"Failed to add web card:\n{e}")


def get_selected_text(callback) -> None:
    _controller.get_selected_text(callback)
