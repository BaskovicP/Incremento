"""Quick Open dialog — fuzzy-search docs and writing cards by title."""

from __future__ import annotations

import random as _random
from dataclasses import dataclass

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QColor,
    QDialog,
    QEvent,
    QHeaderView,
    QHBoxLayout,
    QKeySequence,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QShortcut,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
    qconnect,
)

try:
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from paths import get_active_profile as _active_profile

try:
    from ..backend.pdf_manager import PDF_NOTE_TYPE
    from ..backend.epub_manager import EPUB_NOTE_TYPE
    from ..backend.priority_manager import get_all_priorities
    from ..backend.writing_manager import WRITING_FILE_FIELD, WRITING_NOTE_TYPE
except ImportError:
    from pdf_manager import PDF_NOTE_TYPE  # type: ignore
    from epub_manager import EPUB_NOTE_TYPE  # type: ignore
    from priority_manager import get_all_priorities  # type: ignore
    from writing_manager import WRITING_FILE_FIELD, WRITING_NOTE_TYPE  # type: ignore


_MODE_DOCS = "docs"
_MODE_WRITING = "writing"
_TYPE_PDF = "PDF"
_TYPE_EPUB = "EPUB"
_TYPE_WRITING = "WRITING"


@dataclass(frozen=True)
class _QuickOpenEntry:
    title: str
    card_id: int
    kind: str
    priority: float | None
    relpath: str = ""


def _filter_quick_open_entries(
    entries: list[_QuickOpenEntry],
    query: str,
) -> list[_QuickOpenEntry]:
    needle = str(query or "").strip().lower()
    if not needle:
        return list(entries)
    return [entry for entry in entries if needle in entry.title.lower()]


def _best_quick_open_entry(entries: list[_QuickOpenEntry]) -> _QuickOpenEntry | None:
    if not entries:
        return None
    return min(entries, key=lambda entry: entry.priority if entry.priority is not None else 50.0)


def _load_doc_quick_open_entries(
    addon_dir: str,
    *,
    collection=None,
) -> list[_QuickOpenEntry]:
    col = collection or mw.col
    all_prios = get_all_priorities(addon_dir, _active_profile())
    entries: list[_QuickOpenEntry] = []
    try:
        for note_type_name, kind in ((PDF_NOTE_TYPE, _TYPE_PDF), (EPUB_NOTE_TYPE, _TYPE_EPUB)):
            note_ids = col.find_notes(f'note:"{note_type_name}" -is:suspended')
            for nid in note_ids:
                try:
                    note = col.get_note(nid)
                    title = str(note.fields[0] if getattr(note, "fields", None) else nid).strip()
                    cids = col.find_cards(f"nid:{nid}")
                    if not cids:
                        continue
                    entries.append(
                        _QuickOpenEntry(
                            title=title or str(nid),
                            card_id=int(cids[0]),
                            kind=kind,
                            priority=all_prios.get(int(cids[0])),
                        )
                    )
                except Exception:
                    pass
    except Exception:
        pass
    return sorted(entries, key=lambda entry: entry.title.lower())


def _load_writing_quick_open_entries(
    addon_dir: str,
    *,
    collection=None,
) -> list[_QuickOpenEntry]:
    col = collection or mw.col
    all_prios = get_all_priorities(addon_dir, _active_profile())
    entries: list[_QuickOpenEntry] = []
    try:
        note_ids = col.find_notes(f'note:"{WRITING_NOTE_TYPE}" -is:suspended')
        for nid in note_ids:
            try:
                note = col.get_note(nid)
                title = str(note["Title"] or "").strip()
                if not title:
                    title = str(note.fields[0] if getattr(note, "fields", None) else nid).strip() or str(nid)
                relpath = str(note[WRITING_FILE_FIELD] or "").strip()
                cids = col.find_cards(f"nid:{nid}")
                if not cids:
                    continue
                entries.append(
                    _QuickOpenEntry(
                        title=title,
                        card_id=int(cids[0]),
                        kind=_TYPE_WRITING,
                        priority=all_prios.get(int(cids[0])),
                        relpath=relpath,
                    )
                )
            except Exception:
                pass
    except Exception:
        pass
    return sorted(entries, key=lambda entry: entry.title.lower())


class _PdfQuickJumpDialog(QDialog):
    """Quick Open dialog: fuzzy-search docs and writing cards by title."""

    def __init__(
        self,
        parent=None,
        *,
        addon_dir: str,
        last_opened_pdf_cid: int | None,
        last_opened_writing_cid: int | None,
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._last_opened_pdf_cid = last_opened_pdf_cid
        self._last_opened_writing_cid = last_opened_writing_cid
        self._entries_by_mode = {
            _MODE_DOCS: _load_doc_quick_open_entries(addon_dir),
            _MODE_WRITING: _load_writing_quick_open_entries(addon_dir),
        }
        self._visible_entries: list[_QuickOpenEntry] = []

        self.setWindowTitle("Quick Open Content")
        self.resize(860, 580)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(12, 12, 12, 12)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_label = QLabel("<b>Mode</b>")
        mode_row.addWidget(mode_label)
        self._mode_group = QButtonGroup(self)
        self._docs_radio = QRadioButton("Docs")
        self._writing_radio = QRadioButton("Writing")
        self._mode_group.addButton(self._docs_radio)
        self._mode_group.addButton(self._writing_radio)
        self._docs_radio.setChecked(True)
        mode_row.addWidget(self._docs_radio)
        mode_row.addWidget(self._writing_radio)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)
        layout.addSpacing(10)

        self._search = QLineEdit()
        self._search.setStyleSheet(
            "QLineEdit { border: 2px solid #2979ff; border-radius: 3px;"
            " padding: 6px 10px; font-size: 15px; }"
        )
        layout.addWidget(self._search)
        layout.addSpacing(10)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Title", "Type", "Prio", ""])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 74)
        self._table.setColumnWidth(2, 48)
        self._table.setColumnWidth(3, 28)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(True)
        self._table.setWordWrap(True)
        layout.addWidget(self._table)
        layout.addSpacing(10)

        for key, desc in [
            ("Ctrl + F", "Open First in Queue"),
            ("Ctrl + R", "Open Random Note"),
            ("Ctrl + L", "Open Last Opened Note"),
        ]:
            lbl = QLabel(f"<b>{key}</b>: {desc}")
            lbl.setStyleSheet("font-size: 13px; padding: 2px 0;")
            layout.addWidget(lbl)
        layout.addSpacing(6)

        self._preserve_history_cb = QCheckBox(
            "Don't change cards attached to PDF reading history"
        )
        self._preserve_history_cb.setChecked(False)
        layout.addWidget(self._preserve_history_cb)
        self._study_card_cb = QCheckBox("Open the card also to study")
        self._study_card_cb.setChecked(False)
        layout.addWidget(self._study_card_cb)
        layout.addSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #2979ff; color: white; border: none;"
            " padding: 10px; font-size: 14px; border-radius: 3px; }"
            " QPushButton:hover { background: #1565c0; }"
        )
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        qconnect(self._search.textChanged, self._refresh)
        self._search.returnPressed.connect(self._accept_current)
        self._table.itemDoubleClicked.connect(lambda _: self._accept_current())
        self._search.installEventFilter(self)
        qconnect(self._docs_radio.toggled, lambda checked: self._on_mode_toggled(checked))
        qconnect(self._writing_radio.toggled, lambda checked: self._on_mode_toggled(checked))

        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._open_first)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._open_random)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._open_last)

        self._refresh("")

    def _current_mode(self) -> str:
        return _MODE_WRITING if self._writing_radio.isChecked() else _MODE_DOCS

    def _on_mode_toggled(self, checked: bool) -> None:
        if checked:
            self._refresh(self._search.text())

    @staticmethod
    def _prio_bg(priority: float | None) -> QColor:
        if priority is None:
            return QColor(80, 80, 80)
        if priority >= 75:
            return QColor(160, 20, 20)
        if priority >= 55:
            return QColor(150, 80, 0)
        if priority >= 35:
            return QColor(110, 100, 0)
        return QColor(50, 110, 35)

    def _refresh(self, query: str) -> None:
        mode = self._current_mode()
        self._visible_entries = _filter_quick_open_entries(self._entries_by_mode.get(mode, []), query)

        self._preserve_history_cb.setVisible(mode == _MODE_DOCS)
        self._study_card_cb.setVisible(mode == _MODE_DOCS)
        self._table.setRowCount(0)

        for index, entry in enumerate(self._visible_entries, start=1):
            row = self._table.rowCount()
            self._table.insertRow(row)

            title_item = QTableWidgetItem(f"{index}.  {entry.title}")
            title_item.setData(Qt.ItemDataRole.UserRole, entry)
            self._table.setItem(row, 0, title_item)

            type_item = QTableWidgetItem(entry.kind)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, type_item)

            if entry.priority is not None:
                prio_item = QTableWidgetItem(str(int(round(entry.priority))))
                prio_item.setBackground(self._prio_bg(entry.priority))
                prio_item.setForeground(QColor("white"))
            else:
                prio_item = QTableWidgetItem("-")
                prio_item.setForeground(QColor("#888888"))
            prio_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, prio_item)

            self._table.setItem(row, 3, QTableWidgetItem(""))

        self._table.resizeRowsToContents()
        if self._table.rowCount():
            self._table.selectRow(0)

    def _open_first(self) -> None:
        best = _best_quick_open_entry(self._visible_entries)
        if best is not None:
            self._select_cid_and_accept(best.card_id)

    def _open_random(self) -> None:
        if self._visible_entries:
            self._select_cid_and_accept(_random.choice(self._visible_entries).card_id)

    def _open_last(self) -> None:
        cid = (
            self._last_opened_writing_cid
            if self._current_mode() == _MODE_WRITING
            else self._last_opened_pdf_cid
        )
        if cid is not None:
            self._select_cid_and_accept(cid)

    def _select_cid_and_accept(self, cid: int) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(entry, _QuickOpenEntry) and int(entry.card_id) == int(cid):
                self._table.selectRow(row)
                self.accept()
                return

    def eventFilter(self, obj, event):
        if obj is self._search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._table.selectRow(
                    min(self._table.currentRow() + 1, self._table.rowCount() - 1)
                )
                return True
            if key == Qt.Key.Key_Up:
                self._table.selectRow(max(self._table.currentRow() - 1, 0))
                return True
        return super().eventFilter(obj, event)

    def _accept_current(self) -> None:
        if self._table.currentRow() >= 0:
            self.accept()

    def _selected_entry(self) -> _QuickOpenEntry | None:
        item = self._table.item(self._table.currentRow(), 0)
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return entry if isinstance(entry, _QuickOpenEntry) else None

    @property
    def selected_card_id(self) -> int | None:
        entry = self._selected_entry()
        return int(entry.card_id) if entry is not None else None

    @property
    def selected_card_type(self) -> str:
        entry = self._selected_entry()
        return str(entry.kind if entry is not None else _TYPE_PDF).upper()

    @property
    def selected_relpath(self) -> str:
        entry = self._selected_entry()
        return str(entry.relpath if entry is not None else "")

    @property
    def preserve_history(self) -> bool:
        return bool(self._preserve_history_cb.isChecked())

    @property
    def open_card_to_study(self) -> bool:
        return bool(self._study_card_cb.isChecked())
