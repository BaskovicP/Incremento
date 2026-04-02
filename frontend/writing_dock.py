"""
writing_dock.py — Markdown writing dock with autosave.

Shows a QTextEdit for Incremento Writing cards and writes markdown changes
to user_files/writing/<file>.md while typing.
"""

import datetime
import os

from aqt import mw
from aqt.utils import tooltip
from aqt.qt import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QTextBrowser,
    QSplitter,
    Qt,
    qconnect,
    QTimer,
    QTextCursor,
)
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices, QFontDatabase

try:
    from ..backend.writing_manager import (
        WRITING_NOTE_TYPE,
        WRITING_FILE_FIELD,
        ensure_writing_note_type,
        get_writing_dir,
        build_writing_relpath,
        ensure_writing_file,
        read_writing_text,
        write_writing_text,
    )
except ImportError:
    from writing_manager import (
        WRITING_NOTE_TYPE,
        WRITING_FILE_FIELD,
        ensure_writing_note_type,
        get_writing_dir,
        build_writing_relpath,
        ensure_writing_file,
        read_writing_text,
        write_writing_text,
    )

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_writing_dock = None
_current_writing_card_id: int | None = None
_current_writing_relpath: str = ""
_loading_editor = False
_autosave_timer = None


def _refresh_markdown_preview(text: str | None = None) -> None:
    if _writing_dock is None:
        return
    preview = getattr(_writing_dock, "_preview", None)
    editor = getattr(_writing_dock, "_editor", None)
    if preview is None or editor is None:
        return
    md = editor.toPlainText() if text is None else str(text)
    try:
        preview.setMarkdown(md)
    except Exception:
        # Fallback for older/limited Qt markdown support.
        preview.setPlainText(md)


def _build_writing_dock():
    global _writing_dock, _autosave_timer

    dock = QDockWidget("Writing", mw)
    dock.setObjectName("incremento_writing_dock")
    dock.setMinimumWidth(560)

    root = QWidget(dock)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(8, 6, 8, 8)
    layout.setSpacing(6)

    top = QHBoxLayout()
    title_lbl = QLabel("")
    title_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
    file_lbl = QLabel("")
    file_lbl.setStyleSheet("font-family: monospace; color: #8a8f99;")
    open_dir_btn = QPushButton("Open Folder")
    top.addWidget(title_lbl, 1)
    top.addWidget(file_lbl, 2)
    top.addWidget(open_dir_btn)
    layout.addLayout(top)

    split = QSplitter(Qt.Orientation.Horizontal, root)

    editor_host = QWidget(split)
    editor_layout = QVBoxLayout(editor_host)
    editor_layout.setContentsMargins(0, 0, 0, 0)
    editor_layout.setSpacing(4)
    editor_layout.addWidget(QLabel("Markdown"))
    editor = QTextEdit(editor_host)
    editor.setAcceptRichText(False)
    editor.setPlaceholderText(
        "# Markdown writing\n\nThis note autosaves while you type."
    )
    mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    editor.setFont(mono)
    editor_layout.addWidget(editor, 1)
    split.addWidget(editor_host)

    preview_host = QWidget(split)
    preview_layout = QVBoxLayout(preview_host)
    preview_layout.setContentsMargins(0, 0, 0, 0)
    preview_layout.setSpacing(4)
    preview_layout.addWidget(QLabel("Preview"))
    preview = QTextBrowser(preview_host)
    preview.setOpenExternalLinks(True)
    preview_layout.addWidget(preview, 1)
    split.addWidget(preview_host)
    split.setStretchFactor(0, 1)
    split.setStretchFactor(1, 1)
    layout.addWidget(split, 1)

    bottom = QHBoxLayout()
    status_lbl = QLabel("Idle")
    status_lbl.setStyleSheet("font-size: 11px; color: #9aa0a6;")
    saved_lbl = QLabel("")
    saved_lbl.setStyleSheet("font-size: 11px; color: #9aa0a6;")
    bottom.addWidget(status_lbl, 1)
    bottom.addWidget(saved_lbl, 0, Qt.AlignmentFlag.AlignRight)
    layout.addLayout(bottom)

    dock.setWidget(root)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._title_lbl = title_lbl
    dock._file_lbl = file_lbl
    dock._editor = editor
    dock._preview = preview
    dock._status_lbl = status_lbl
    dock._saved_lbl = saved_lbl

    _autosave_timer = QTimer(dock)
    _autosave_timer.setSingleShot(True)
    _autosave_timer.setInterval(180)
    qconnect(_autosave_timer.timeout, _autosave_from_editor)

    qconnect(editor.textChanged, _on_editor_text_changed)
    qconnect(open_dir_btn.clicked, _open_writing_folder)

    _writing_dock = dock
    return dock


def _open_writing_folder() -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(get_writing_dir()))


def _set_status(text: str) -> None:
    if _writing_dock is None:
        return
    try:
        _writing_dock._status_lbl.setText(text)
    except Exception:
        pass


def _set_saved_time() -> None:
    if _writing_dock is None:
        return
    now_txt = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        _writing_dock._saved_lbl.setText(f"Saved {now_txt}")
    except Exception:
        pass


def _on_editor_text_changed() -> None:
    if _writing_dock is None or _loading_editor:
        return
    if not _current_writing_relpath:
        return
    _refresh_markdown_preview()
    _set_status("Saving…")
    if _autosave_timer is not None:
        _autosave_timer.start()


def _autosave_from_editor() -> None:
    if _writing_dock is None or not _current_writing_relpath:
        return
    try:
        text = _writing_dock._editor.toPlainText()
        write_writing_text(_ADDON_DIR, _current_writing_relpath, text)
    except Exception:
        _set_status("Autosave failed")
        return
    _set_status("Autosave on typing")
    _set_saved_time()


def show_writing_in_dock(card_id: int, title: str, relpath: str) -> None:
    global _writing_dock, _current_writing_card_id, _current_writing_relpath, _loading_editor

    _current_writing_card_id = card_id
    _current_writing_relpath = relpath

    if _writing_dock is None:
        _build_writing_dock()
    else:
        try:
            _writing_dock.widget()
        except RuntimeError:
            _writing_dock = None
            _build_writing_dock()

    ensure_writing_file(_ADDON_DIR, relpath, initial_text=f"# {title}\n\n")
    text = read_writing_text(_ADDON_DIR, relpath)

    _loading_editor = True
    try:
        _writing_dock._title_lbl.setText(title or "Writing")
        _writing_dock._file_lbl.setText(relpath)
        _writing_dock._editor.setPlainText(text)
        _refresh_markdown_preview(text)
        _writing_dock._editor.moveCursor(QTextCursor.MoveOperation.End)
    finally:
        _loading_editor = False

    _set_status("Autosave on typing")
    _writing_dock.show()
    _writing_dock.raise_()


def on_writing_question_shown(card) -> None:
    global _writing_dock
    try:
        if card is None:
            return
        try:
            note = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != WRITING_NOTE_TYPE:
            if _writing_dock is not None:
                if _autosave_timer is not None:
                    _autosave_timer.stop()
                _autosave_from_editor()
                try:
                    _writing_dock.hide()
                except RuntimeError:
                    _writing_dock = None
            return

        title = (note["Title"] or "").strip()
        relpath = (note[WRITING_FILE_FIELD] or "").strip()
        if not relpath:
            relpath = build_writing_relpath(title=title or f"writing-{card.id}")
            try:
                note[WRITING_FILE_FIELD] = relpath
                mw.col.update_note(note)
            except Exception:
                pass
        show_writing_in_dock(card.id, title, relpath)
    except Exception as e:
        print(f"[Incremento] on_writing_question_shown error: {e}")


def on_writing_reviewer_will_end() -> None:
    if _autosave_timer is not None:
        _autosave_timer.stop()
    _autosave_from_editor()
    if _writing_dock is not None:
        try:
            _writing_dock.hide()
        except RuntimeError:
            pass


def sync_writing_note_type() -> None:
    try:
        ensure_writing_note_type(mw.col)
    except Exception:
        pass


def add_writing_function() -> None:
    """Legacy entry point kept for parity with other dock modules."""
    tooltip("Use Incremento → Add Content → Add Writing.")
