"""
add_card_dock.py — persistent Add Card dock widget.

Wraps Anki's native AddCards dialog inside a QDockWidget so it stays
open across card reviews.

Public API:
    open_add_card_dock() — show or rebuild the dock
    fill_dock_field(idx, text) — append text (with PDF citation) to field idx
    do_fill(idx, text) — inner fill, bypasses citation
    get_add_card_dock() — return the current dock instance (may be None)
"""

from aqt import mw
from aqt.qt import QDockWidget, QTimer, Qt

_add_card_dock = None  # QDockWidget instance, persists across card reviews


def build_add_card_dock():
    """Embed the native AddCards dialog into a left dock widget."""
    global _add_card_dock
    from aqt.addcards import AddCards

    dock = QDockWidget("Add Card", mw)
    dock.setObjectName("incremento_add_card_dock")
    dock.setMinimumWidth(400)

    # Open the native dialog; hide it before the event loop renders it as a
    # floating window, then reparent it into the dock as a plain widget.
    dlg = AddCards(mw)
    dlg.hide()
    dlg.setParent(dock)
    dlg.setWindowFlags(Qt.WindowType.Widget)
    dock.setWidget(dlg)

    mw.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
    _add_card_dock = dock
    dlg.show()

    def _set_field(idx, text):
        note = dlg.editor.note
        if note and idx < len(note.fields):
            existing = note.fields[idx]
            note.fields[idx] = (existing + '<br><br>' + text) if existing else text
            try:
                dlg.editor.loadNote()
            except Exception:
                pass

    dock._set_field = _set_field
    return dock


def open_add_card_dock():
    global _add_card_dock
    if _add_card_dock is not None:
        try:
            _add_card_dock.show()
            _add_card_dock.raise_()
            return
        except RuntimeError:
            _add_card_dock = None
    build_add_card_dock()


def fill_dock_field(idx, text):
    global _add_card_dock
    try:
        from .pdf_dock import pdf_citation
        citation = pdf_citation()
    except Exception:
        citation = None
    if citation:
        text = text + '<br>' + citation
    if _add_card_dock is None:
        build_add_card_dock()
        QTimer.singleShot(600, lambda: do_fill(idx, text))
        return
    try:
        _add_card_dock.show()
        _add_card_dock.raise_()
        do_fill(idx, text)
    except RuntimeError:
        _add_card_dock = None


def do_fill(idx, text):
    if _add_card_dock is None:
        return
    try:
        _add_card_dock._set_field(idx, text)
    except (RuntimeError, AttributeError):
        pass


def get_add_card_dock():
    return _add_card_dock
