import os

from aqt import mw
from aqt.qt import (
    QFileDialog,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    Qt,
    QVBoxLayout,
    QWidget,
)
from aqt.utils import showInfo, tooltip

try:
    from ..backend.local_file_manager import (
        LOCAL_FILE_MODE_FIELD,
        LOCAL_FILE_MODE_MANAGED_COPY,
        LOCAL_FILE_NAME_FIELD,
        LOCAL_FILE_NOTE_FIELD,
        LOCAL_FILE_NOTE_TYPE,
        LOCAL_FILE_PATH_FIELD,
        relink_local_file,
        resolve_local_file_abspath,
    )
    from ..backend.note_metadata import INCREMENTO_SOURCE_LINK_FIELD
    from ..backend.paths import get_active_profile as _active_profile
    from .file_shell import open_local_file, reveal_local_file
except ImportError:
    from local_file_manager import (  # type: ignore
        LOCAL_FILE_MODE_FIELD,
        LOCAL_FILE_MODE_MANAGED_COPY,
        LOCAL_FILE_NAME_FIELD,
        LOCAL_FILE_NOTE_FIELD,
        LOCAL_FILE_NOTE_TYPE,
        LOCAL_FILE_PATH_FIELD,
        relink_local_file,
        resolve_local_file_abspath,
    )
    from note_metadata import INCREMENTO_SOURCE_LINK_FIELD  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore
    from file_shell import open_local_file, reveal_local_file  # type: ignore


_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_local_file_dock = None
_current_note_id: int | None = None
_current_card_id: int | None = None
_current_mode: str = ""
_current_stored_path: str = ""
_current_resolved_path: str = ""


def _mode_label(mode: str) -> str:
    if mode == LOCAL_FILE_MODE_MANAGED_COPY:
        return "Managed copy"
    return "Referenced original file"


def _create_local_file_dock():
    global _local_file_dock
    if _local_file_dock is not None:
        return _local_file_dock

    dock = QDockWidget("Local File", mw)
    dock.setObjectName("incremento_local_file_dock")
    body = QWidget(dock)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(6)

    dock._status_lbl = QLabel("")
    dock._status_lbl.setWordWrap(True)
    layout.addWidget(dock._status_lbl)

    dock._name_lbl = QLabel("")
    dock._name_lbl.setWordWrap(True)
    layout.addWidget(dock._name_lbl)

    dock._path_lbl = QLabel("")
    dock._path_lbl.setWordWrap(True)
    dock._path_lbl.setTextInteractionFlags(dock._path_lbl.textInteractionFlags())
    layout.addWidget(dock._path_lbl)

    dock._mode_lbl = QLabel("")
    dock._mode_lbl.setWordWrap(True)
    layout.addWidget(dock._mode_lbl)

    dock._note_lbl = QLabel("")
    dock._note_lbl.setWordWrap(True)
    layout.addWidget(dock._note_lbl)

    actions = QHBoxLayout()
    dock._reveal_btn = QPushButton("Reveal")
    dock._open_btn = QPushButton("Open")
    dock._relink_btn = QPushButton("Relink")
    actions.addWidget(dock._reveal_btn)
    actions.addWidget(dock._open_btn)
    actions.addWidget(dock._relink_btn)
    actions.addStretch()
    layout.addLayout(actions)

    dock._reveal_btn.clicked.connect(_reveal_current_file)
    dock._open_btn.clicked.connect(_open_current_file)
    dock._relink_btn.clicked.connect(_relink_current_file)

    dock.setWidget(body)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    _local_file_dock = dock
    return dock


def _refresh_dock_labels(filename: str, stored_path: str, mode: str, note_text: str) -> None:
    if _local_file_dock is None:
        return
    exists = bool(_current_resolved_path) and os.path.isfile(_current_resolved_path)
    if exists:
        _local_file_dock._status_lbl.setText("Local file available.")
        _local_file_dock._status_lbl.setStyleSheet("color: #7fb36b;")
    else:
        _local_file_dock._status_lbl.setText("Linked file is missing. Use Relink to choose a replacement.")
        _local_file_dock._status_lbl.setStyleSheet("color: #d17b49;")
    _local_file_dock._name_lbl.setText(f"<b>File:</b> {filename or '(none)'}")
    _local_file_dock._path_lbl.setText(f"<b>Path:</b> {stored_path or '(none)'}")
    _local_file_dock._mode_lbl.setText(f"<b>Mode:</b> {_mode_label(mode)}")
    _local_file_dock._note_lbl.setText(f"<b>Note:</b> {note_text or '(none)'}")
    _local_file_dock._reveal_btn.setEnabled(exists)
    _local_file_dock._open_btn.setEnabled(exists)
    _local_file_dock._relink_btn.setEnabled(_current_note_id is not None)


def _reveal_current_file() -> None:
    if not _current_resolved_path:
        return
    if not reveal_local_file(_current_resolved_path):
        showInfo("Could not reveal the linked file in Finder/Explorer.")


def _open_current_file() -> None:
    if not _current_resolved_path:
        return
    if not open_local_file(_current_resolved_path):
        showInfo("Could not open the linked file in the default native app.")


def _relink_current_file() -> None:
    global _current_stored_path, _current_resolved_path
    if _current_note_id is None:
        return
    path, _ = QFileDialog.getOpenFileName(mw, "Choose replacement file", "", "All files (*)")
    if not path:
        return
    try:
        note = mw.col.get_note(_current_note_id)
        stored_path, filename = relink_local_file(
            _ADDON_DIR,
            _active_profile(),
            note,
            new_source_path=path,
        )
        note[INCREMENTO_SOURCE_LINK_FIELD] = stored_path
        mw.col.update_note(note)
        _current_stored_path = stored_path
        _current_resolved_path = resolve_local_file_abspath(
            _ADDON_DIR,
            _active_profile(),
            stored_path,
            str(note[LOCAL_FILE_MODE_FIELD] or ""),
        )
        _refresh_dock_labels(
            filename,
            stored_path,
            str(note[LOCAL_FILE_MODE_FIELD] or ""),
            str(note[LOCAL_FILE_NOTE_FIELD] or "").strip(),
        )
        tooltip("Local file relinked.")
    except Exception as exc:
        showInfo(f"Could not relink this local file:\n{exc}")


def on_local_file_question_shown(card) -> None:
    global _current_card_id, _current_note_id, _current_mode, _current_stored_path, _current_resolved_path
    try:
        if card is None:
            return
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        if model is None or model.get("name") != LOCAL_FILE_NOTE_TYPE:
            if _local_file_dock is not None:
                _local_file_dock.hide()
            _current_card_id = None
            _current_note_id = None
            _current_mode = ""
            _current_stored_path = ""
            _current_resolved_path = ""
            return

        filename = str(note[LOCAL_FILE_NAME_FIELD] or "").strip()
        stored_path = str(note[LOCAL_FILE_PATH_FIELD] or "").strip()
        mode = str(note[LOCAL_FILE_MODE_FIELD] or "").strip()
        note_text = str(note[LOCAL_FILE_NOTE_FIELD] or "").strip()
        resolved = resolve_local_file_abspath(_ADDON_DIR, _active_profile(), stored_path, mode)

        _current_card_id = int(card.id)
        _current_note_id = int(note.id)
        _current_mode = mode
        _current_stored_path = stored_path
        _current_resolved_path = resolved

        dock = _create_local_file_dock()
        _refresh_dock_labels(filename, stored_path, mode, note_text)
        dock.show()
        dock.raise_()
    except Exception as exc:
        print(f"[Incremento] on_local_file_question_shown error: {exc}")


def on_local_file_reviewer_will_end() -> None:
    global _current_card_id, _current_note_id, _current_mode, _current_stored_path, _current_resolved_path
    _current_card_id = None
    _current_note_id = None
    _current_mode = ""
    _current_stored_path = ""
    _current_resolved_path = ""
    if _local_file_dock is not None:
        try:
            _local_file_dock.hide()
        except RuntimeError:
            pass
