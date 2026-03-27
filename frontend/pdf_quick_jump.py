"""Quick Open dialog — fuzzy-search PDF cards by title with priority display."""

from __future__ import annotations

import random as _random

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QColor,
    QDialog,
    QEvent,
    QHeaderView,
    QKeySequence,
    QLabel,
    QLineEdit,
    QPushButton,
    QShortcut,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    Qt,
    qconnect,
)

try:
    from ..backend.pdf_manager import PDF_NOTE_TYPE, get_page
    from ..backend.priority_manager import get_all_priorities
except ImportError:
    from pdf_manager import PDF_NOTE_TYPE, get_page  # type: ignore
    from priority_manager import get_all_priorities  # type: ignore


class _PdfQuickJumpDialog(QDialog):
    """Quick Open dialog: fuzzy-search PDF cards by title with priority display."""

    def __init__(self, parent=None, *, addon_dir: str, last_opened_pdf_cid: int | None):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._last_opened_pdf_cid = last_opened_pdf_cid
        self.setWindowTitle("Quick Open")
        self.resize(860, 580)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(12, 12, 12, 12)

        # ── Search box ─────────────────────────────────────────────────────────
        self._search = QLineEdit()
        self._search.setStyleSheet(
            "QLineEdit { border: 2px solid #2979ff; border-radius: 3px;"
            " padding: 6px 10px; font-size: 15px; }"
        )
        layout.addWidget(self._search)
        layout.addSpacing(10)

        # ── Results table ──────────────────────────────────────────────────────
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Title", "Type", "Prio", ""])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(1, 52)
        self._table.setColumnWidth(2, 48)
        self._table.setColumnWidth(3, 28)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(True)
        self._table.setWordWrap(True)
        layout.addWidget(self._table)
        layout.addSpacing(10)

        # ── Keyboard shortcut hints ────────────────────────────────────────────
        for key, desc in [
            ("Ctrl + F", "Open First in Queue"),
            ("Ctrl + R", "Open Random Note"),
            ("Ctrl + L", "Open Last Opened Note"),
        ]:
            lbl = QLabel(f"<b>{key}</b>: {desc}")
            lbl.setStyleSheet("font-size: 13px; padding: 2px 0;")
            layout.addWidget(lbl)
        layout.addSpacing(10)

        # ── Cancel button ──────────────────────────────────────────────────────
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #2979ff; color: white; border: none;"
            " padding: 10px; font-size: 14px; border-radius: 3px; }"
            " QPushButton:hover { background: #1565c0; }"
        )
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        # ── Load data ──────────────────────────────────────────────────────────
        self._all_entries: list[tuple[str, int, int, float | None]] = []
        self._load_entries()
        self._refresh("")

        qconnect(self._search.textChanged, self._refresh)
        self._search.returnPressed.connect(self._accept_current)
        self._table.itemDoubleClicked.connect(lambda _: self._accept_current())
        self._search.installEventFilter(self)

        # In-dialog shortcuts (Ctrl+F/R/L)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._open_first)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._open_random)
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._open_last)

    def _load_entries(self) -> None:
        all_prios = get_all_priorities(self._addon_dir)  # {cid: priority}
        try:
            note_ids = mw.col.find_notes(f'note:"{PDF_NOTE_TYPE}" -is:suspended')
            for nid in note_ids:
                try:
                    note = mw.col.get_note(nid)
                    title = note.fields[0] if note.fields else str(nid)
                    cids = mw.col.find_cards(f"nid:{nid}")
                    if cids:
                        cid = cids[0]
                        page = get_page(self._addon_dir, cid)
                        prio = all_prios.get(cid)  # None = not explicitly set
                        self._all_entries.append((title, cid, page, prio))
                except Exception:
                    pass
        except Exception:
            pass
        self._all_entries.sort(key=lambda e: e[0].lower())

    @staticmethod
    def _prio_bg(p) -> QColor:
        if p is None:
            return QColor(80, 80, 80)
        if p >= 75:
            return QColor(160, 20, 20)
        if p >= 55:
            return QColor(150, 80, 0)
        if p >= 35:
            return QColor(110, 100, 0)
        return QColor(50, 110, 35)

    def _refresh(self, query: str) -> None:
        self._table.setRowCount(0)
        q = query.lower()
        n = 0
        for title, cid, page, prio in self._all_entries:
            if q in title.lower():
                n += 1
                row = self._table.rowCount()
                self._table.insertRow(row)

                title_item = QTableWidgetItem(f"{n}.  {title}")
                title_item.setData(Qt.ItemDataRole.UserRole, cid)
                self._table.setItem(row, 0, title_item)

                type_item = QTableWidgetItem("PDF")
                type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 1, type_item)

                if prio is not None:
                    prio_item = QTableWidgetItem(str(int(round(prio))))
                    prio_item.setBackground(self._prio_bg(prio))
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
        """Open the highest-priority entry (lowest priority value = most important)."""
        if not self._all_entries:
            return
        best = min(self._all_entries, key=lambda e: e[3] if e[3] is not None else 50.0)
        self._select_cid_and_accept(best[1])

    def _open_random(self) -> None:
        if self._all_entries:
            self._select_cid_and_accept(_random.choice(self._all_entries)[1])

    def _open_last(self) -> None:
        if self._last_opened_pdf_cid is not None:
            self._select_cid_and_accept(self._last_opened_pdf_cid)

    def _select_cid_and_accept(self, cid: int) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == cid:
                self._table.selectRow(row)
                break
        self.accept()

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

    @property
    def selected_card_id(self) -> int | None:
        item = self._table.item(self._table.currentRow(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None
