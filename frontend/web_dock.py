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
        build_external_web_url,
        ensure_web_note_type,
        get_web_url,
        set_web_url,
    )
except ImportError:
    from db import add_web_card_source, get_web_card_sources
    from web_manager import (
        WEB_NOTE_TYPE,
        add_web_card,
        build_external_web_url,
        ensure_web_note_type,
        get_web_url,
        set_web_url,
    )

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_web_dock = None
_current_web_card_id = None
_current_web_home_url = None
_web_profile = None
_PYCMD_BRIDGE = "__incremento_webdock_pycmd__:"
_MSG_SELECTION_STATE = "incremento_selection_state:"
_MSG_FILL_FIELD = "incremento_web_fill_field:"
_MSG_SNAPSHOT = "incremento_web_snapshot:"
_track_web_window_with_extension = False
_web_shortcuts_registered = False
_web_shortcuts = []
_web_interaction_filter = None
_web_snapshot_mode = False
_web_snapshot_origin = None
_web_snapshot_shield = None
_web_snapshot_overlay = None
_web_snapshot_override_cursor = False


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


def web_citation(url: str | None = None) -> str:
    current_url = str(url or _current_web_display_url()).strip()
    if not current_url or not _current_web_card_id:
        return ""
    encoded_url = quote(current_url, safe="")
    label = (
        _source_url_label(current_url)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    cmd = f"incremento_open_web:{int(_current_web_card_id)}:{encoded_url}"
    return (
        f"<a onclick=\"pycmd('{cmd}'); return false;\" "
        f"style=\"cursor:pointer; color:#4a90d9; text-decoration:none;\">"
        f"{label}</a>"
    )


class _WebDockPage(QWebEnginePage):
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


class _WebInteractionFilter(QObject):
    def eventFilter(self, watched, event):
        global _web_snapshot_origin
        if _web_dock is None or not _web_snapshot_mode:
            return False
        try:
            if not _web_dock.isVisible():
                return False
            view = _web_dock._view
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
            if etype == QEvent.Type.MouseMove and _web_snapshot_origin is not None:
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
            _web_snapshot_origin = local_pos
            _ensure_snapshot_band(view)
            _web_snapshot_shield.setGeometry(view.rect())
            _web_snapshot_shield.raise_()
            _web_snapshot_shield.show()
            _web_snapshot_overlay.setGeometry(
                QRect(_web_snapshot_origin, _web_snapshot_origin)
            )
            _web_snapshot_overlay.raise_()
            _web_snapshot_overlay.show()
            return True

        if etype == QEvent.Type.MouseMove:
            if _web_snapshot_origin is None:
                return False
            _ensure_snapshot_band(view)
            _web_snapshot_shield.setGeometry(view.rect())
            _web_snapshot_shield.raise_()
            _web_snapshot_shield.show()
            _web_snapshot_overlay.setGeometry(
                QRect(_web_snapshot_origin, local_pos).normalized()
            )
            _web_snapshot_overlay.raise_()
            _web_snapshot_overlay.show()
            return True

        if etype == QEvent.Type.MouseButtonRelease:
            try:
                if event.button() != Qt.MouseButton.LeftButton:
                    return False
            except Exception:
                return False
            if _web_snapshot_origin is None:
                return False
            rect = QRect(_web_snapshot_origin, local_pos).normalized().intersected(
                view.rect()
            )
            _web_snapshot_origin = None
            if _web_snapshot_overlay is not None:
                _web_snapshot_overlay.hide()
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
    return (
        f"window.pycmd = function(msg) {{"
        f"  console.log('{_PYCMD_BRIDGE}' + msg);"
        f"}};"
        "(function() {"
        "  if (window._incrementoWebBridgeInstalled) {"
        "    return;"
        "  }"
        "  window._incrementoWebBridgeInstalled = true;"
        "  window._incrementoLastSelection = '';"
        "  window._incrementoWebSnapshotActive = false;"
        "  window._incrementoWebSnapshotBox = null;"
        "  window._incrementoWebSnapshotStart = null;"
        "  function ensureBox() {"
        "    if (window._incrementoWebSnapshotBox && document.documentElement && document.documentElement.contains(window._incrementoWebSnapshotBox)) {"
        "      return window._incrementoWebSnapshotBox;"
        "    }"
        "    var box = document.createElement('div');"
        "    box.style.position = 'fixed';"
        "    box.style.zIndex = '2147483647';"
        "    box.style.border = '2px solid rgba(37,99,235,0.95)';"
        "    box.style.background = 'rgba(37,99,235,0.16)';"
        "    box.style.pointerEvents = 'none';"
        "    box.style.display = 'none';"
        "    box.style.boxSizing = 'border-box';"
        "    document.documentElement.appendChild(box);"
        "    window._incrementoWebSnapshotBox = box;"
        "    return box;"
        "  }"
        "  function hideBox() {"
        "    var box = ensureBox();"
        "    box.style.display = 'none';"
        "  }"
        "  function drawBox(a, b) {"
        "    var box = ensureBox();"
        "    var left = Math.min(a.x, b.x);"
        "    var top = Math.min(a.y, b.y);"
        "    var width = Math.abs(a.x - b.x);"
        "    var height = Math.abs(a.y - b.y);"
        "    box.style.left = left + 'px';"
        "    box.style.top = top + 'px';"
        "    box.style.width = width + 'px';"
        "    box.style.height = height + 'px';"
        "    box.style.display = 'block';"
        "  }"
        "  function setSnapshotActive(active) {"
        "    window._incrementoWebSnapshotActive = !!active;"
        "    if (!window._incrementoWebSnapshotActive) {"
        "      window._incrementoWebSnapshotStart = null;"
        "      hideBox();"
        "    }"
        "    try {"
        "      document.documentElement.style.cursor = window._incrementoWebSnapshotActive ? 'crosshair' : '';"
        "      if (document.body) {"
        "        document.body.style.cursor = window._incrementoWebSnapshotActive ? 'crosshair' : '';"
        "      }"
        "    } catch (_err) {}"
        "    return window._incrementoWebSnapshotActive;"
        "  }"
        "  window.incrementoToggleSnapshotMode = function() {"
        "    return setSnapshotActive(!window._incrementoWebSnapshotActive);"
        "  };"
        "  window.incrementoDisableSnapshotMode = function() {"
        "    return setSnapshotActive(false);"
        "  };"
        "  document.addEventListener('selectionchange', function() {"
        "    var sel = window.getSelection ? window.getSelection() : null;"
        "    var text = sel ? sel.toString().trim() : '';"
        "    if (!text) {"
        "      return;"
        "    }"
        "    window._incrementoLastSelection = text;"
        "    window.pycmd('incremento_selection_state:' + JSON.stringify({source: 'web', hasText: true}));"
        "  });"
        "  document.addEventListener('keydown', function(e) {"
        "    if (e.key === 'Escape' && window._incrementoWebSnapshotActive) {"
        "      e.preventDefault();"
        "      e.stopPropagation();"
        "      setSnapshotActive(false);"
        "      return;"
        "    }"
        "    if (!(e.metaKey || e.ctrlKey)) {"
        "      return;"
        "    }"
        "    var map = { Digit1: 0, Digit2: 1, Digit3: 2, Digit4: 3 };"
        "    var idx = Object.prototype.hasOwnProperty.call(map, e.code) ? map[e.code] : null;"
        "    if (idx === null) {"
        "      var n = parseInt(e.key, 10);"
        "      if (!Number.isNaN(n) && n >= 1 && n <= 4) {"
        "        idx = n - 1;"
        "      }"
        "    }"
        "    if (idx === null) {"
        "      return;"
        "    }"
        "    var sel = window.getSelection ? window.getSelection() : null;"
        "    var text = sel ? sel.toString().trim() : '';"
        "    if (!text) {"
        "      return;"
        "    }"
        "    e.preventDefault();"
        "    e.stopPropagation();"
        "    window._incrementoLastSelection = text;"
        "    window.pycmd('incremento_web_fill_field:' + JSON.stringify({"
        "      idx: idx,"
        "      text: text,"
        "      url: window.location.href || ''"
        "    }));"
        "  }, true);"
        "  document.addEventListener('mousedown', function(e) {"
        "    if (!window._incrementoWebSnapshotActive || e.button !== 0) {"
        "      return;"
        "    }"
        "    window._incrementoWebSnapshotStart = { x: e.clientX, y: e.clientY };"
        "    drawBox(window._incrementoWebSnapshotStart, window._incrementoWebSnapshotStart);"
        "    e.preventDefault();"
        "    e.stopPropagation();"
        "  }, true);"
        "  document.addEventListener('mousemove', function(e) {"
        "    if (!window._incrementoWebSnapshotActive || !window._incrementoWebSnapshotStart) {"
        "      return;"
        "    }"
        "    drawBox(window._incrementoWebSnapshotStart, { x: e.clientX, y: e.clientY });"
        "    e.preventDefault();"
        "    e.stopPropagation();"
        "  }, true);"
        "  document.addEventListener('mouseup', function(e) {"
        "    if (!window._incrementoWebSnapshotActive || !window._incrementoWebSnapshotStart || e.button !== 0) {"
        "      return;"
        "    }"
        "    var start = window._incrementoWebSnapshotStart;"
        "    var end = { x: e.clientX, y: e.clientY };"
        "    var left = Math.min(start.x, end.x);"
        "    var top = Math.min(start.y, end.y);"
        "    var width = Math.abs(start.x - end.x);"
        "    var height = Math.abs(start.y - end.y);"
        "    window._incrementoWebSnapshotStart = null;"
        "    setSnapshotActive(false);"
        "    if (width < 6 || height < 6) {"
        "      return;"
        "    }"
        "    window.pycmd('incremento_web_snapshot:' + JSON.stringify({"
        "      x: left,"
        "      y: top,"
        "      width: width,"
        "      height: height,"
        "      url: window.location.href || ''"
        "    }));"
        "    e.preventDefault();"
        "    e.stopPropagation();"
        "  }, true);"
        "})();"
    )


def _current_web_display_url() -> str:
    if _web_dock is not None:
        try:
            current = (_web_dock._view.url().toString() or "").strip()
            if current and current != "about:blank":
                return current
        except Exception:
            pass
    return str(_current_web_home_url or "").strip()


def _current_selected_text() -> str:
    if _web_dock is None:
        return ""
    try:
        text = _web_dock._view.page().selectedText() or ""
        text = str(text).replace("\u2029", "\n").strip()
        if text:
            return text
    except Exception:
        pass
    return ""


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
    text = _current_selected_text()
    if not text:
        tooltip("Select some text first.")
        return
    try:
        from . import add_card_dock as _add_card_dock_mod

        _add_card_dock_mod.fill_dock_field(
            idx,
            text,
            include_pdf_citation=False,
            citation_html=web_citation(),
            source_link_kind="web",
        )
    except Exception as exc:
        showInfo(f"Web extraction failed:\n{exc}")


def _ensure_snapshot_band(view) -> None:
    global _web_snapshot_shield, _web_snapshot_overlay
    if _web_snapshot_shield is None or _web_snapshot_shield.parent() is not view:
        _web_snapshot_shield = QWidget(view)
        _web_snapshot_shield.setCursor(Qt.CursorShape.CrossCursor)
        _web_snapshot_shield.setStyleSheet("background: rgba(37,99,235,0.02);")
        _web_snapshot_shield.hide()
    if _web_snapshot_overlay is None or _web_snapshot_overlay.parent() is not _web_snapshot_shield:
        _web_snapshot_overlay = QWidget(_web_snapshot_shield)
        _web_snapshot_overlay.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        _web_snapshot_overlay.setStyleSheet(
            "border: 2px solid rgba(37,99,235,0.95);"
            "background: rgba(37,99,235,0.22);"
        )
        _web_snapshot_overlay.hide()


def _set_web_snapshot_mode(active: bool) -> None:
    global _web_snapshot_mode, _web_snapshot_origin, _web_snapshot_override_cursor
    _web_snapshot_mode = bool(active)
    _web_snapshot_origin = None
    if _web_dock is not None:
        try:
            _ensure_snapshot_band(_web_dock._view)
        except Exception:
            pass
    if _web_snapshot_shield is not None:
        try:
            _web_snapshot_shield.hide()
        except Exception:
            pass
    if _web_snapshot_overlay is not None:
        try:
            _web_snapshot_overlay.hide()
        except Exception:
            pass
    if _web_dock is not None:
        try:
            _web_dock._view.setCursor(
                Qt.CursorShape.CrossCursor
                if _web_snapshot_mode
                else Qt.CursorShape.ArrowCursor
            )
        except Exception:
            pass
        try:
            _web_dock._view.unsetCursor() if not _web_snapshot_mode else None
        except Exception:
            pass
        if _web_snapshot_mode and _web_snapshot_shield is not None:
            try:
                _web_snapshot_shield.setGeometry(_web_dock._view.rect())
                _web_snapshot_shield.raise_()
                _web_snapshot_shield.show()
            except Exception:
                pass
        try:
            _web_dock._snapshot_btn.setText(
                "Drag to Capture" if _web_snapshot_mode else "Snapshot"
            )
            _web_dock._snapshot_btn.setStyleSheet(
                (
                    "font-weight: bold;"
                    "color: white;"
                    "background: rgba(37,99,235,0.92);"
                    "border: 1px solid rgba(29,78,216,1.0);"
                    "border-radius: 4px;"
                    "padding: 0 8px;"
                    if _web_snapshot_mode
                    else ""
                )
            )
        except Exception:
            pass
    app = QApplication.instance()
    if app is not None:
        try:
            if _web_snapshot_mode and not _web_snapshot_override_cursor:
                app.setOverrideCursor(Qt.CursorShape.CrossCursor)
                _web_snapshot_override_cursor = True
            elif not _web_snapshot_mode and _web_snapshot_override_cursor:
                app.restoreOverrideCursor()
                _web_snapshot_override_cursor = False
        except Exception:
            _web_snapshot_override_cursor = False


def _current_web_source_rows() -> list[dict]:
    if _current_web_card_id is None:
        return []
    current_url = _current_web_display_url()
    if not current_url:
        return []
    try:
        return get_web_card_sources(_ADDON_DIR, int(_current_web_card_id), current_url)
    except Exception:
        return []


def _refresh_web_cards_panel() -> None:
    if _web_dock is None:
        return
    current_url = _current_web_display_url()
    rows = _current_web_source_rows()
    count = len(rows)
    try:
        _web_dock._cards_btn.setText(f"Cards {count}")
        _web_dock._cards_btn.setVisible(count > 0)
    except Exception:
        pass
    if count <= 0:
        try:
            _web_dock._cards_panel.hide()
            _web_dock._cards_panel.setHtml("")
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
            + current_url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            + "</div>"
        ),
    ]
    for row in rows:
        excerpt = str(row.get("excerpt") or "").strip()
        safe_excerpt = (
            excerpt.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
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
        _web_dock._cards_panel.setHtml("".join(html))
    except Exception:
        pass


def _toggle_web_cards_panel() -> None:
    if _web_dock is None:
        return
    rows = _current_web_source_rows()
    if not rows:
        tooltip("Incremento: no cards recorded for this URL yet.")
        return
    _refresh_web_cards_panel()
    try:
        visible = _web_dock._cards_panel.isVisible()
        _web_dock._cards_panel.setVisible(not visible)
    except Exception:
        pass


def _insert_snapshot_into_field(pixmap: QPixmap, current_url: str) -> None:
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
        scaled = scaled.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
    if scaled.height() > 180:
        scaled = scaled.scaledToHeight(180, Qt.TransformationMode.SmoothTransformation)

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

    citation = web_citation(current_url)
    html = f'<img src="{media_filename}">'
    _add_card_dock_mod.fill_dock_field(
        chosen_idx[0],
        html,
        include_pdf_citation=False,
        citation_html=citation,
        source_link_kind="web",
    )


def _handle_web_snapshot(data: dict) -> None:
    if _web_dock is None:
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
    current_url = str(data.get("url") or _current_web_display_url()).strip()
    try:
        pixmap = _web_dock._view.grab()
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
    _insert_snapshot_into_field(crop, current_url)


def _toggle_snapshot_mode() -> None:
    _set_web_snapshot_mode(not _web_snapshot_mode)


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
    global _web_dock, _web_profile, _web_interaction_filter, _web_shortcuts_registered

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

    if _web_profile is None:
        _web_profile = _WEProf("incremento_web")
        _web_profile.setPersistentStoragePath(
            os.path.join(_ADDON_DIR, "user_files", "web_profile")
        )
        _web_profile.setPersistentCookiesPolicy(
            _WEProf.PersistentCookiesPolicy.ForcePersistentCookies
        )
        _web_profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        _web_profile.settings().setAttribute(
            _WES.WebAttribute.PlaybackRequiresUserGesture, False
        )

    _page = _WebDockPage(_web_profile)
    view.setPage(_page)

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

    snapshot_btn = QPushButton("Snapshot")
    snapshot_btn.setToolTip(
        "Capture an image from the current viewport, like the PDF snapshot tool."
    )
    ctrl_layout.addWidget(snapshot_btn)

    cards_btn = QPushButton("Cards 0")
    cards_btn.setVisible(False)
    ctrl_layout.addWidget(cards_btn)

    home_btn = QPushButton("Home")
    home_btn.setFixedWidth(70)
    ctrl_layout.addWidget(home_btn)

    track_cb = QCheckBox("Track via Chrome extension")
    track_cb.setChecked(bool(_track_web_window_with_extension))
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
    dock._snapshot_btn = snapshot_btn
    dock._cards_btn = cards_btn
    dock._cards_panel = cards_panel

    if _web_interaction_filter is None:
        _web_interaction_filter = _WebInteractionFilter(mw)
    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(_web_interaction_filter)

    def _on_url_changed(qurl):
        url_str = qurl.toString()
        display = url_str if len(url_str) <= 80 else url_str[:77] + "..."
        try:
            url_lbl.setText(display)
        except RuntimeError:
            pass
        _refresh_web_cards_panel()

    def _on_load_finished(ok):
        if not ok or _current_web_card_id is None:
            return
        url_str = view.url().toString()
        if url_str and url_str != "about:blank":
            try:
                set_web_url(_ADDON_DIR, _current_web_card_id, url_str)
            except Exception:
                pass
        _set_web_snapshot_mode(False)
        try:
            view.page().runJavaScript(_build_web_bridge_js())
        except Exception:
            pass
        _refresh_web_cards_panel()

    def _on_selection_changed():
        _update_native_selection_state()

    view.urlChanged.connect(_on_url_changed)
    view.loadFinished.connect(_on_load_finished)
    view.page().selectionChanged.connect(_on_selection_changed)
    qconnect(home_btn.clicked, _web_go_home)
    qconnect(snapshot_btn.clicked, _toggle_snapshot_mode)
    qconnect(cards_btn.clicked, _toggle_web_cards_panel)
    qconnect(window_btn.clicked, _open_web_in_window)
    qconnect(track_cb.toggled, _on_track_web_window_toggled)

    def _open_add_card():
        from . import add_card_dock as _add_card_dock_mod

        _add_card_dock_mod.open_add_card_dock()

    qconnect(add_card_btn.clicked, _open_add_card)

    if not _web_shortcuts_registered:
        for idx in range(4):
            for prefix in ("Ctrl", "Meta"):
                sc = QShortcut(QKeySequence(f"{prefix}+{idx + 1}"), mw)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(
                    lambda idx=idx: (
                        _extract_web_selection_to_field(idx)
                        if _web_dock is not None and _web_dock.isVisible()
                        else None
                    )
                )
                _web_shortcuts.append(sc)
        esc = QShortcut(QKeySequence("Escape"), mw)
        esc.setContext(Qt.ShortcutContext.ApplicationShortcut)
        esc.activated.connect(
            lambda: _set_web_snapshot_mode(False) if _web_snapshot_mode else None
        )
        _web_shortcuts.append(esc)
        _web_shortcuts_registered = True

    _web_dock = dock
    return dock


def _on_track_web_window_toggled(checked: bool) -> None:
    global _track_web_window_with_extension
    _track_web_window_with_extension = bool(checked)


def _open_web_in_window() -> None:
    if _current_web_card_id is None:
        tooltip("Incremento: no web card is currently open.")
        return

    current_url = _current_web_display_url()
    if not current_url:
        tooltip("Incremento: this web card has no valid URL.")
        return

    track_enabled = False
    if _web_dock is not None:
        try:
            track_enabled = bool(_web_dock._track_cb.isChecked())
        except Exception:
            track_enabled = False

    open_url = build_external_web_url(
        current_url,
        card_id=int(_current_web_card_id),
        track_with_extension=track_enabled,
    )
    try:
        set_web_url(_ADDON_DIR, _current_web_card_id, current_url)
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


def _web_go_home() -> None:
    if _web_dock is None or not _current_web_home_url:
        return
    try:
        _web_dock._view.load(QUrl(_current_web_home_url))
    except (RuntimeError, AttributeError):
        pass


def show_web_in_dock(card_id: int, home_url: str, last_url: str) -> None:
    global _web_dock, _current_web_card_id, _current_web_home_url

    _current_web_card_id = card_id
    _current_web_home_url = home_url

    if _web_dock is None:
        _build_web_dock()
    else:
        try:
            _web_dock.widget()
        except RuntimeError:
            _web_dock = None
            _build_web_dock()

    load_url = last_url if last_url else home_url
    _web_dock.show()
    _web_dock.raise_()
    _set_web_snapshot_mode(False)
    try:
        _web_dock._cards_panel.hide()
        _web_dock._cards_panel.setHtml("")
        _web_dock._cards_btn.setVisible(False)
        _web_dock._cards_btn.setText("Cards 0")
    except Exception:
        pass
    _web_dock._view.load(QUrl(load_url))


def open_web_location(card_id: int, target_url: str) -> bool:
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
    show_web_in_dock(int(card_id), home_url, target)
    return True


def sync_external_web_url(card_id: int, url: str) -> bool:
    """If this web card is currently open, load the latest externally synced URL."""
    global _web_dock

    try:
        target_card_id = int(card_id)
    except Exception:
        return False
    target_url = str(url or "").strip()
    if target_card_id <= 0 or not target_url:
        return False
    if _current_web_card_id != target_card_id:
        return False
    if _web_dock is None:
        return False

    try:
        current_url = (_web_dock._view.url().toString() or "").strip()
    except Exception:
        current_url = ""
    if current_url == target_url:
        return False

    try:
        _web_dock._view.load(QUrl(target_url))
        return True
    except Exception:
        return False


def on_web_question_shown(card) -> None:
    global _web_dock
    try:
        if card is None:
            return
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != WEB_NOTE_TYPE:
            if _web_dock is not None:
                try:
                    _web_dock.hide()
                except RuntimeError:
                    _web_dock = None
            return
        try:
            home_url = note["URL"]
        except (KeyError, TypeError):
            return
        if not home_url:
            return
        last_url = get_web_url(_ADDON_DIR, card.id)
        show_web_in_dock(card.id, home_url, last_url)
    except Exception as e:
        print(f"[Incremento] on_web_question_shown error: {e}")


def on_web_reviewer_will_end() -> None:
    _set_web_snapshot_mode(False)
    if _web_dock is not None:
        try:
            _web_dock.hide()
        except RuntimeError:
            pass


def on_add_cards_did_add_note(note) -> None:
    if _current_web_card_id is None or _web_dock is None:
        return
    try:
        if not _web_dock.isVisible():
            return
    except Exception:
        return
    current_url = _current_web_display_url()
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
            int(_current_web_card_id),
            current_url,
            note.id,
            excerpt,
        )
    except Exception:
        return
    _refresh_web_cards_panel()
    try:
        if _web_dock._cards_panel.isVisible():
            _web_dock._cards_panel.show()
    except Exception:
        pass


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
    text = _current_selected_text()
    if text:
        callback(text)
        return
    if _web_dock is None:
        callback("")
        return
    try:
        _web_dock._view.page().runJavaScript(
            "(function(){ return (window._incrementoLastSelection || "
            "(window.getSelection && window.getSelection().toString()) || '').trim(); })();",
            lambda text: callback(text or ""),
        )
    except Exception:
        callback("")
