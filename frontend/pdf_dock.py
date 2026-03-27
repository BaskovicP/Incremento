"""PDF viewer dock (QWebEngineView + PDF.js / React).

All state globals, the _PdfDockPage class, and the lifecycle functions live here
so __init__.py is not the only place these reside.

Circular-import problem: the PDF dock needs _open_add_card_dock and _fill_dock_field
which live in __init__.py. These are registered after import via register_add_card_callbacks().
Until that function is called the callbacks are None — they are never called at module-load
time so there is no practical issue.
"""

import json
import os

from aqt import mw
from aqt.qt import (
    QApplication,
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QShortcut,
    QKeySequence,
    QTimer,
    Qt,
    QDialog,
    QLabel,
    QPushButton,
    QPixmap,
    qconnect,
)
from aqt.utils import showInfo, tooltip
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtCore import QEvent, QObject, QUrl

try:
    from ..backend.pdf_manager import (
        PDF_NOTE_TYPE,
        get_page,
        get_pdf_dir,
        get_zoom,
        get_read_page,
        set_page,
        set_zoom,
        set_read_page,
    )
except ImportError:
    from pdf_manager import (
        PDF_NOTE_TYPE,
        get_page,
        get_pdf_dir,
        get_zoom,
        get_read_page,
        set_page,
        set_zoom,
        set_read_page,
    )
try:
    from ..backend.pdf_highlights import load_highlights, add_highlight, remove_highlight
except ImportError:
    from pdf_highlights import load_highlights, add_highlight, remove_highlight
try:
    from ..backend.db import add_pdf_card_source, get_pdf_card_sources, get_pdf_page_card_counts
except ImportError:
    from db import add_pdf_card_source, get_pdf_card_sources, get_pdf_page_card_counts
from . import timer_widget as _timer_mod

# ── Addon root ────────────────────────────────────────────────────────────────

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

_DOCK_HTML = QUrl.fromLocalFile(
    os.path.join(_ADDON_DIR, "user_files", "pdf_dock.html")
).toString()

_WORKER_URL = QUrl.fromLocalFile(
    os.path.join(_ADDON_DIR, "user_files", "pdfjs", "pdf.worker.min.js")
).toString()

# ── Module state ──────────────────────────────────────────────────────────────

_pdf_dock = None
_shortcuts_registered = False
_current_pdf_card_id = None
_current_pdf_filename = None
_pdf_via_link = False  # True when dock was opened via a cross-reference link
_pdf_shortcuts = []
_pdf_key_filter = None

# ── Callback injection (breaks circular import with __init__.py) ──────────────

_cb_open_add_card_dock = None  # () -> None
_cb_fill_dock_field = None  # (idx: int, text: str) -> None
_cb_get_add_card_dock = None  # () -> QDockWidget | None
_cb_pdf_view_started = None  # (card_id: int) -> None
_cb_pdf_view_stopped = None  # (card_id: int | None) -> None


def register_add_card_callbacks(open_fn, fill_fn, get_dock_fn) -> None:
    """Called by __init__.py after its own functions are defined.

    Must be called before any PDF card is reviewed.  In practice it is called
    at module-load time of __init__.py, which is always before the reviewer
    opens.
    """
    global _cb_open_add_card_dock, _cb_fill_dock_field, _cb_get_add_card_dock
    _cb_open_add_card_dock = open_fn
    _cb_fill_dock_field = fill_fn
    _cb_get_add_card_dock = get_dock_fn


def register_pdf_view_callbacks(start_fn, stop_fn) -> None:
    global _cb_pdf_view_started, _cb_pdf_view_stopped
    _cb_pdf_view_started = start_fn
    _cb_pdf_view_stopped = stop_fn


# ── Citation helper (called by _fill_dock_field in __init__.py) ───────────────


def pdf_citation() -> str:
    """Return an HTML link 'Page N. of name' that reopens the PDF dock at that page."""
    if not _current_pdf_card_id or not _current_pdf_filename:
        return ""
    page = get_page(_ADDON_DIR, _current_pdf_card_id)
    name = os.path.splitext(_current_pdf_filename)[0]
    cmd = f"incremento_open_pdf:{_current_pdf_card_id}:{page}"
    return (
        f"<a onclick=\"pycmd('{cmd}'); return false;\" "
        f'style="cursor:pointer; color:#4a90d9; text-decoration:none;">'
        f"Page {page}. of {name}</a>"
    )


# ── pycmd message protocol constants ─────────────────────────────────────────
# All pycmd messages from the PDF viewer JS are prefixed with _PYCMD_BRIDGE.
# Each handler constant names one message type, making typos compile-time errors.

_PYCMD_BRIDGE = "__incremento_pycmd__:"
_MSG_NAV = "incremento_pdf_nav:"
_MSG_ZOOM = "incremento_pdf_zoom:"
_MSG_HL_ADD = "incremento_pdf_hl_add:"
_MSG_HL_DEL = "incremento_pdf_hl_del:"
_MSG_MARK_READ = "incremento_pdf_mark_read:"
_MSG_CMD1 = "incremento_pdf_cmd1:"
_MSG_OPEN_ADD_CARD = "incremento_open_add_card"
_MSG_FILL_FIELD = "incremento_fill_field:"
_MSG_SNAPSHOT = "incremento_pdf_snapshot:"
_MSG_FINISHED = "incremento_pdf_finished:"
_MSG_OPEN_CARD = "incremento_open_card:"


# ── pycmd bridge (console.log interceptor) ───────────────────────────────────


class _PdfDockPage(QWebEnginePage):
    """Intercepts console.log to get pycmd messages from the PDF viewer JS."""

    def javaScriptConsoleMessage(self, level, message, line, source):
        if not message.startswith(_PYCMD_BRIDGE):
            return
        msg = message[len(_PYCMD_BRIDGE) :]

        if msg.startswith(_MSG_NAV):
            parts = msg.split(":")
            if len(parts) == 3:
                try:
                    cid = int(parts[1])
                    pg = int(parts[2])
                    if not _pdf_via_link:
                        set_page(_ADDON_DIR, cid, pg)
                    if _timer_mod._timer_running:
                        _timer_mod._timer_pdf_pages.add((cid, pg))
                except ValueError:
                    pass
        elif msg.startswith(_MSG_ZOOM):
            parts = msg.split(":")
            if len(parts) == 3:
                try:
                    set_zoom(_ADDON_DIR, int(parts[1]), float(parts[2]))
                except ValueError:
                    pass
        elif msg.startswith(_MSG_HL_ADD):
            try:
                data = json.loads(msg[len(_MSG_HL_ADD) :])
                add_highlight(_ADDON_DIR, int(data["cardId"]), data["highlight"])
            except Exception as e:
                print(f"[Incremento] pdf_dock: highlight add failed: {e}")
        elif msg.startswith(_MSG_HL_DEL):
            try:
                data = json.loads(msg[len(_MSG_HL_DEL) :])
                remove_highlight(_ADDON_DIR, int(data["cardId"]), data["id"])
            except Exception as e:
                print(f"[Incremento] pdf_dock: highlight delete failed: {e}")
        elif msg.startswith(_MSG_MARK_READ):
            parts = msg.split(":")
            if len(parts) == 3:
                try:
                    set_read_page(_ADDON_DIR, int(parts[1]), int(parts[2]))
                except ValueError:
                    pass
        elif msg.startswith(_MSG_CMD1):
            text = msg[len(_MSG_CMD1) :]
            if text:
                QTimer.singleShot(0, lambda t=text: _on_pdf_selection(0, t))
        elif msg == _MSG_OPEN_ADD_CARD:
            if _cb_open_add_card_dock:
                _cb_open_add_card_dock()
        elif msg.startswith(_MSG_FILL_FIELD):
            try:
                data = json.loads(msg[len(_MSG_FILL_FIELD) :])
                if _cb_fill_dock_field:
                    _cb_fill_dock_field(int(data["idx"]), data["text"])
            except Exception:
                pass
        elif msg.startswith(_MSG_SNAPSHOT):
            QTimer.singleShot(0, lambda m=msg: _handle_pdf_snapshot(m))
        elif msg.startswith(_MSG_FINISHED):
            try:
                card_id = int(msg[len(_MSG_FINISHED) :])
                mw.col.sched.suspend_cards([card_id])
                mw.col.reset()
                tooltip("PDF card suspended — it won't appear in future sessions.")
                if _pdf_dock:
                    _pdf_dock.hide()
            except Exception as e:
                showInfo(f"Could not suspend card:\n{e}")
        elif msg.startswith(_MSG_OPEN_CARD):
            try:
                note_id = int(msg[len(_MSG_OPEN_CARD) :])
                from aqt import dialogs

                def _browse(nid=note_id):
                    b = dialogs.open("Browser", mw)
                    b.search_for(f"nid:{nid}")

                QTimer.singleShot(0, _browse)
            except Exception:
                pass
        elif msg.startswith("incremento_get_page_cards:"):
            try:
                parts = msg.split(":")
                if len(parts) == 3:
                    cid = int(parts[1])
                    page = int(parts[2])
                    cards = get_pdf_card_sources(_ADDON_DIR, cid, page)
                    counts = get_pdf_page_card_counts(_ADDON_DIR, cid)
                    data = {"page": page, "cards": cards, "pageCounts": counts}
                    js = (
                        "window.incrementoReceivePageCards && "
                        f"window.incrementoReceivePageCards({json.dumps(data)})"
                    )
                    QTimer.singleShot(
                        0,
                        lambda j=js: (
                            _pdf_dock._view.page().runJavaScript(j)
                            if _pdf_dock
                            else None
                        ),
                    )
            except Exception:
                pass


class _PdfShortcutFilter(QObject):
    """Capture Cmd/Ctrl+1..4 before WebEngine or menu handling consumes them."""

    def eventFilter(self, watched, event):
        try:
            if event.type() not in (
                QEvent.Type.ShortcutOverride,
                QEvent.Type.KeyPress,
            ):
                return False

            if _pdf_dock is None or not _pdf_dock.isVisible():
                return False

            mods = event.modifiers()
            if not (
                mods
                & (
                    Qt.KeyboardModifier.MetaModifier
                    | Qt.KeyboardModifier.ControlModifier
                )
            ):
                return False

            key_to_idx = {
                Qt.Key.Key_1: 0,
                Qt.Key.Key_Exclam: 0,
                Qt.Key.Key_2: 1,
                Qt.Key.Key_At: 1,
                Qt.Key.Key_3: 2,
                Qt.Key.Key_NumberSign: 2,
                Qt.Key.Key_4: 3,
                Qt.Key.Key_Dollar: 3,
            }
            idx = key_to_idx.get(event.key())
            if idx is None:
                text_to_idx = {
                    "1": 0,
                    "!": 0,
                    "2": 1,
                    "@": 1,
                    "3": 2,
                    "#": 2,
                    "4": 3,
                    "$": 3,
                }
                idx = text_to_idx.get((event.text() or "")[:1])
            if idx is None:
                return False

            event.accept()

            if event.type() == QEvent.Type.ShortcutOverride:
                return True

            try:
                _pdf_dock._view.page().runJavaScript(
                    f"window.incrementoHandleExtractShortcut && window.incrementoHandleExtractShortcut({idx});"
                )
            except Exception:
                pass
            return True
        except Exception:
            return False


# ── Snapshot handler ──────────────────────────────────────────────────────────


def _handle_pdf_snapshot(msg: str) -> None:
    """Save snapshot image to media and fill a chosen field in the Add Card dock."""
    import base64 as _b64, tempfile as _tmp
    from PyQt6.QtGui import QImage

    try:
        data = json.loads(msg[len("incremento_pdf_snapshot:") :])
        img_b64 = data["image"]
        if "," in img_b64:
            img_b64 = img_b64.split(",", 1)[1]
        img_bytes = _b64.b64decode(img_b64)

        with _tmp.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(img_bytes)
            tmp_path = f.name
        try:
            media_filename = mw.col.media.add_file(tmp_path)
        finally:
            os.unlink(tmp_path)

        # Open Add Card dock and read its current field names
        if _cb_open_add_card_dock:
            _cb_open_add_card_dock()
        field_names = []
        try:
            dock = _cb_get_add_card_dock() if _cb_get_add_card_dock else None
            if dock:
                note = dock.widget().editor.note
                if note:
                    field_names = [f["name"] for f in note.note_type()["flds"]]
        except Exception:
            pass
        if not field_names:
            field_names = [f"Field {i + 1}" for i in range(4)]

        # Build pixmap preview
        pixmap = QPixmap.fromImage(QImage.fromData(img_bytes))
        scaled = pixmap.scaledToWidth(300, Qt.TransformationMode.SmoothTransformation)
        if scaled.height() > 180:
            scaled = pixmap.scaledToHeight(
                180, Qt.TransformationMode.SmoothTransformation
            )

        # Dialog: image preview + one button per field name
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

        if _cb_fill_dock_field:
            _cb_fill_dock_field(chosen_idx[0], f'<img src="{media_filename}">')
    except Exception as e:
        showInfo(f"Snapshot failed:\n{e}")


# ── Dock construction ─────────────────────────────────────────────────────────


def _build_pdf_dock():
    global _pdf_dock, _shortcuts_registered, _pdf_key_filter

    dock = QDockWidget("PDF Viewer", mw)
    dock.setObjectName("incremento_pdf_dock")
    dock.setMinimumWidth(550)

    page = _PdfDockPage(dock)
    # Allow file:// page to load other file:// resources (worker, PDF)
    s = page.settings()
    s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    s.setAttribute(
        QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
    )

    view = QWebEngineView(dock)
    view.setPage(page)
    dock.setWidget(view)
    dock._view = view

    if _pdf_key_filter is None:
        _pdf_key_filter = _PdfShortcutFilter(mw)

    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(_pdf_key_filter)
    mw.installEventFilter(_pdf_key_filter)
    view.installEventFilter(_pdf_key_filter)
    page.installEventFilter(_pdf_key_filter)

    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _on_visibility_changed(visible: bool) -> None:
        if visible:
            return
        if _cb_pdf_view_stopped:
            try:
                _cb_pdf_view_stopped(_current_pdf_card_id)
            except Exception:
                pass

    dock.visibilityChanged.connect(_on_visibility_changed)

    # Inject fake pycmd bridge + Cmd+1 keydown listener after every page load
    def _on_load_finished(ok):
        if ok:
            view.page().runJavaScript(
                f"window.pycmd = function(msg) {{"
                f"  console.log('{_PYCMD_BRIDGE}' + msg);"
                f"}};"
                # Cache selection on change so the keydown handler can read it.
                "document.addEventListener('selectionchange', function() {"
                "  var s = window.getSelection();"
                "  window._lastPdfSelection = s ? s.toString() : '';"
                "});"
                # Cmd/Ctrl+1 inside the webview.
                "document.addEventListener('keydown', function(e) {"
                "  var digit1 = (e.code === 'Digit1' || e.key === '1');"
                "  if ((e.metaKey || e.ctrlKey) && digit1) {"
                "    e.preventDefault();"
                "    e.stopPropagation();"
                "    var sel = window._lastPdfSelection || '';"
                "    if (sel) { window.pycmd('incremento_pdf_cmd1:' + sel); }"
                "  }"
                "}, true);"
            )

    view.loadFinished.connect(_on_load_finished)

    # Fallback app-level shortcuts in case WebEngine consumes the key event.
    if not _shortcuts_registered:

        def _act_extract_field1():
            if _pdf_dock is None:
                return
            try:
                _pdf_dock._view.page().runJavaScript(
                    "window.incrementoHandleExtractShortcut && window.incrementoHandleExtractShortcut(0);",
                )
            except Exception:
                pass

        for seq in ("Ctrl+1", "Meta+1"):
            sc = QShortcut(QKeySequence(seq), mw)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(_act_extract_field1)
            _pdf_shortcuts.append(sc)

        globals()["_shortcuts_registered"] = True

    _pdf_dock = dock
    return dock


def _on_pdf_selection(idx: int, text: str) -> None:
    text = (text or "").strip()
    if text:
        if _cb_open_add_card_dock:
            _cb_open_add_card_dock()
        if _cb_fill_dock_field:
            QTimer.singleShot(150, lambda: _cb_fill_dock_field(idx, text))


def trigger_viewer_action(action: str) -> None:
    """Invoke a viewer action in the PDF dock if it is currently available."""
    if _pdf_dock is None:
        return
    try:
        view = _pdf_dock._view
        if not _pdf_dock.isVisible():
            return
    except Exception:
        return

    js_by_action = {
        "prev_page": "window.incrementoPdfNav && window.incrementoPdfNav(-1);",
        "next_page": "window.incrementoPdfNav && window.incrementoPdfNav(1);",
        "zoom_out": "window.incrementoPdfZoom && window.incrementoPdfZoom(-1);",
        "zoom_in": "window.incrementoPdfZoom && window.incrementoPdfZoom(1);",
        "mark_read": "window.incrementoPdfMarkRead && window.incrementoPdfMarkRead();",
    }
    js = js_by_action.get(action)
    if not js:
        return
    try:
        view.page().runJavaScript(js)
    except Exception:
        pass


# ── Show PDF in dock ──────────────────────────────────────────────────────────


def show_pdf_in_dock(
    card_id, filename, page, zoom=1.0, via_link=False, read_page=0, search_query=""
) -> None:
    global _pdf_dock, _current_pdf_card_id, _current_pdf_filename, _pdf_via_link
    _current_pdf_card_id = card_id
    _current_pdf_filename = filename
    _pdf_via_link = via_link
    if _pdf_dock is None:
        _build_pdf_dock()
    else:
        try:
            _pdf_dock.widget()
        except RuntimeError:
            _pdf_dock = None
            _build_pdf_dock()

    _pdf_dock.show()
    _pdf_dock.raise_()

    if _cb_pdf_view_started:
        try:
            _cb_pdf_view_started(card_id)
        except Exception:
            pass

    pdf_file_url = QUrl.fromLocalFile(
        os.path.join(get_pdf_dir(), filename)
    ).toString()

    hls = load_highlights(_ADDON_DIR, card_id)

    js = (
        f"window._pdfWorkerSrc    = {json.dumps(_WORKER_URL)};"
        f"window._pdfFileUrl      = {json.dumps(pdf_file_url)};"
        f"window._incPdfHighlights = {json.dumps(hls)};"
        f"window._incPdfPending   = {{cardId: {card_id}, filename: {json.dumps(filename)}, page: {page}, zoom: {zoom}, readPage: {read_page}, searchQuery: {json.dumps(search_query or '')}}};"
        f"typeof incrementoPdfStart === 'function' && "
        f"(window._incPdfPending = null,"
        f" incrementoPdfStart({card_id}, {json.dumps(filename)}, {page}, {zoom}, {read_page}, {json.dumps(search_query or '')}));"
    )

    current = _pdf_dock._view.url().toString()
    if current != _DOCK_HTML:

        def _on_first_load(ok):
            _pdf_dock._view.loadFinished.disconnect(_on_first_load)
            if ok:
                _pdf_dock._view.page().runJavaScript(js)

        _pdf_dock._view.loadFinished.connect(_on_first_load)
        _pdf_dock._view.load(QUrl(_DOCK_HTML))
    else:
        _pdf_dock._view.page().runJavaScript(js)


# ── Reviewer hooks ────────────────────────────────────────────────────────────


def on_pdf_question_shown(card) -> None:
    global _pdf_dock
    try:
        if card is None:
            return
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != PDF_NOTE_TYPE:
            if _pdf_dock is not None:
                try:
                    _pdf_dock.hide()
                    if _cb_pdf_view_stopped:
                        _cb_pdf_view_stopped(_current_pdf_card_id)
                except RuntimeError:
                    _pdf_dock = None
            return
        try:
            filename = note["PDF_Filename"]
        except (KeyError, TypeError):
            return
        page = get_page(_ADDON_DIR, card.id)
        zoom = get_zoom(_ADDON_DIR, card.id)
        read_page = get_read_page(_ADDON_DIR, card.id)
        show_pdf_in_dock(card.id, filename, page, zoom, read_page=read_page)
    except Exception as e:
        print(f"[Incremento] on_pdf_question_shown error: {e}")


def on_pdf_reviewer_will_end() -> None:
    global _pdf_dock
    if _pdf_dock is not None:
        try:
            _pdf_dock.hide()
            if _cb_pdf_view_stopped:
                _cb_pdf_view_stopped(_current_pdf_card_id)
        except RuntimeError:
            _pdf_dock = None


def on_add_cards_did_add_note(note) -> None:
    """When a card is saved in the AddCards dock, record it against the current PDF page."""
    if _current_pdf_card_id is None:
        return
    page = get_page(_ADDON_DIR, _current_pdf_card_id)
    import re as _re

    parts = []
    for field in (note.fields or [])[:2]:
        plain = _re.sub(r"<[^>]+>", "", field).strip()[:120]
        if plain:
            parts.append(plain)
    excerpt = " / ".join(parts)[:200]
    try:
        add_pdf_card_source(_ADDON_DIR, _current_pdf_card_id, page, note.id, excerpt)
    except Exception:
        pass
    if _pdf_dock is None:
        return
    try:
        cards = get_pdf_card_sources(_ADDON_DIR, _current_pdf_card_id, page)
        counts = get_pdf_page_card_counts(_ADDON_DIR, _current_pdf_card_id)
        data = {"page": page, "cards": cards, "pageCounts": counts}
        js = (
            "window.incrementoReceivePageCards && "
            f"window.incrementoReceivePageCards({json.dumps(data)})"
        )
        _pdf_dock._view.page().runJavaScript(js)
    except Exception:
        pass
