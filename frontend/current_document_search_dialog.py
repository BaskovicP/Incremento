"""Small dialog for searching within the currently open PDF or EPUB."""

from __future__ import annotations

from aqt.qt import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    Qt,
)


def _document_hit_title(document_kind: str, hit: dict) -> str:
    if document_kind == "pdf":
        return f"Page {int(hit.get('page', 1) or 1)}"
    section_title = str(hit.get("sectionTitle") or "").strip()
    if section_title:
        return section_title
    return f"Section {int(hit.get('sectionIndex', 0) or 0) + 1}"


def _document_hit_summary(document_kind: str, hit: dict) -> str:
    primary = _document_hit_title(document_kind, hit)
    snippet = " ".join(str(hit.get("snippet") or "").split())
    return primary if not snippet else f"{primary}  |  {snippet}"


class _CurrentDocumentSearchDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        document_kind: str,
        document_label: str,
        initial_query: str,
        search_hits_fn,
        open_hit_fn,
        open_search_all_fn,
    ):
        super().__init__(parent)
        self._document_kind = str(document_kind or "")
        self._search_hits_fn = search_hits_fn
        self._open_hit_fn = open_hit_fn
        self._open_search_all_fn = open_search_all_fn
        self._hits: list[dict] = []

        label = str(document_label or "").strip() or "Current Document"
        self.setWindowTitle(f"Find In {label}")
        self.resize(720, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText(f"Find in {label.lower()}")
        self._count = QLabel("", self)
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._count.setStyleSheet("color: #7a7a7a;")
        search_row.addWidget(self._search, 1)
        search_row.addWidget(self._count)
        layout.addLayout(search_row)

        self._results = QListWidget(self)
        self._results.itemClicked.connect(self._open_selected_hit)
        self._results.itemActivated.connect(self._open_selected_hit)
        layout.addWidget(self._results, 1)

        self._hint = QLabel(
            f"Click a result to jump to that part of the {label.lower()}.",
            self,
        )
        self._hint.setStyleSheet("color: #7a7a7a;")
        layout.addWidget(self._hint)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self._search_all_btn = QPushButton("Search ALL", self)
        self._close_btn = QPushButton("Close", self)
        button_row.addWidget(self._search_all_btn)
        button_row.addWidget(self._close_btn)
        layout.addLayout(button_row)

        self._search.textChanged.connect(self._refresh_results)
        self._search.returnPressed.connect(self._open_first_hit)
        self._search_all_btn.clicked.connect(self._open_search_all)
        self._close_btn.clicked.connect(self.reject)

        normalized_query = str(initial_query or "").strip()
        if normalized_query:
            self._search.setText(normalized_query)
        else:
            self._refresh_results("")

        self._search.setFocus()
        self._search.selectAll()

    def _refresh_results(self, query: str) -> None:
        normalized_query = str(query or "").strip()
        self._results.clear()
        self._hits = []
        self._search_all_btn.setEnabled(bool(normalized_query))
        if not normalized_query:
            self._count.setText("")
            placeholder = QListWidgetItem("Type to search the current document.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._results.addItem(placeholder)
            return

        self._hits = list(self._search_hits_fn(normalized_query) or [])
        if not self._hits:
            self._count.setText("0 results")
            placeholder = QListWidgetItem("No matches found in the current document.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._results.addItem(placeholder)
            return

        self._count.setText(f"{len(self._hits)} results")
        for index, hit in enumerate(self._hits):
            item = QListWidgetItem(_document_hit_summary(self._document_kind, hit))
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._results.addItem(item)
        self._results.setCurrentRow(0)

    def _open_first_hit(self) -> None:
        if not self._hits:
            return
        item = self._results.currentItem() or self._results.item(0)
        if item is not None:
            self._open_selected_hit(item)

    def _open_selected_hit(self, item) -> None:
        try:
            index = int(item.data(Qt.ItemDataRole.UserRole))
        except Exception:
            return
        if not (0 <= index < len(self._hits)):
            return
        query = str(self._search.text() or "").strip()
        self._open_hit_fn(self._hits[index], index, query)

    def _open_search_all(self) -> None:
        query = str(self._search.text() or "").strip()
        if not query:
            return
        self._open_search_all_fn(query)
        self.accept()
