"""Shared native book details editor for the bookshelf and document imports."""

from __future__ import annotations

from pathlib import Path

from aqt.qt import (QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout,
                    QInputDialog, QLabel, QLineEdit, QListWidget,
                    QListWidgetItem, QPlainTextEdit, QPushButton, QSignalBlocker, QSplitter, QVBoxLayout,
                    QWidget, Qt, pyqtSignal)
from aqt.utils import showInfo

try:
    from ..backend import document_lists as library, paths
    from ..backend.i18n import t
except ImportError:
    from backend import document_lists as library, paths
    from backend.i18n import t


class DocumentListPickerDialog(QDialog):
    """Search all categories while reviewing selected categories alongside them."""

    def __init__(self, addon_dir: str, profile: str, available_lists, selected_ids, parent=None):
        super().__init__(parent)
        self._addon_dir, self._profile = addon_dir, profile
        self.available_lists = list(available_lists)
        self.setWindowTitle(t("reader_library_choose_lists"))
        self.resize(760, 560)
        self.setMinimumSize(560, 380)
        layout = QVBoxLayout(self)
        help_label = QLabel(t("reader_library_list_picker_help"))
        help_label.setWordWrap(True)
        layout.addWidget(help_label)
        self._search = QLineEdit()
        self._search.setPlaceholderText(t("reader_library_find_lists"))
        self._search.setAccessibleName(t("reader_library_find_lists"))
        self._search.setClearButtonEnabled(True)
        search_row = QHBoxLayout()
        search_row.addWidget(self._search, 1)
        self._search_button = QPushButton(t("reader_search"))
        self._search_button.setAutoDefault(False)
        self._search_button.setToolTip(t("reader_library_find_lists"))
        self._search_button.clicked.connect(self._search_lists)
        search_row.addWidget(self._search_button)
        layout.addLayout(search_row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        all_panel, selected_panel = QWidget(), QWidget()
        all_layout, selected_layout = QVBoxLayout(all_panel), QVBoxLayout(selected_panel)
        all_label = QLabel(t("reader_library_all_lists"))
        all_layout.addWidget(all_label)
        self._lists = QListWidget()
        self._lists.setAccessibleName(t("reader_library_all_lists"))
        self._lists.setWordWrap(True)
        all_label.setBuddy(self._lists)
        all_layout.addWidget(self._lists, 1)
        self._matches = QLabel()
        all_layout.addWidget(self._matches)
        self._new_button = QPushButton(t("reader_library_new_list"))
        self._new_button.setAutoDefault(False)
        self._new_button.clicked.connect(self._create_list)
        all_layout.addWidget(self._new_button)
        self._selected_heading = QLabel()
        selected_layout.addWidget(self._selected_heading)
        self._selected = QListWidget()
        self._selected.setAccessibleName(t("reader_library_selected_lists"))
        self._selected.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._selected.setWordWrap(True)
        self._selected_heading.setBuddy(self._selected)
        selected_layout.addWidget(self._selected, 1)
        self._remove_button = QPushButton(t("reader_library_remove_selected_lists"))
        self._remove_button.setAutoDefault(False)
        self._remove_button.clicked.connect(self._remove_selected)
        self._selected.itemSelectionChanged.connect(
            lambda: self._remove_button.setEnabled(bool(self._selected.selectedItems())))
        selected_layout.addWidget(self._remove_button)
        splitter.addWidget(all_panel)
        splitter.addWidget(selected_panel)
        splitter.setSizes([420, 300])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText(t("reader_ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("reader_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._lists.itemChanged.connect(self._update_selected)
        self._search.textChanged.connect(self._filter_lists)
        self._populate(selected_ids)
        self._search_button.setDefault(True)
        self._search.setFocus()

    @property
    def selected_list_ids(self) -> list[int]:
        return sorted(key for key, item in self._list_items.items() if item.checkState() == Qt.CheckState.Checked)

    def _populate(self, selected_ids) -> None:
        blocker = QSignalBlocker(self._lists)
        self._lists.clear()
        self._list_items = {}
        for key, name in self.available_lists:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if key in selected_ids else Qt.CheckState.Unchecked)
            self._lists.addItem(item)
            self._list_items[key] = item
        blocker.unblock()
        self._filter_lists()
        self._update_selected()

    def _search_lists(self) -> None:
        self._filter_lists()
        self._search.setFocus()

    def _filter_lists(self, *_args) -> None:
        query = self._search.text().strip().casefold()
        count = 0
        for item in self._list_items.values():
            item.setHidden(query not in item.text().casefold())
            count += not item.isHidden()
        self._matches.setText(t("reader_library_list_matches", count=count, total=len(self._list_items)))

    def _update_selected(self, *_args) -> None:
        selected = set(self.selected_list_ids)
        self._selected.clear()
        for key, name in self.available_lists:
            if key in selected:
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self._selected.addItem(item)
        self._remove_button.setEnabled(False)
        self._selected_heading.setText(t("reader_library_selected_lists_count", count=len(selected), maximum=library.MAX_BOOK_LISTS))
        self._ok_button.setEnabled(len(selected) <= library.MAX_BOOK_LISTS)

    def _remove_selected(self) -> None:
        blocker = QSignalBlocker(self._lists)
        for item in self._selected.selectedItems():
            self._list_items[item.data(Qt.ItemDataRole.UserRole)].setCheckState(Qt.CheckState.Unchecked)
        blocker.unblock()
        self._update_selected()

    def _create_list(self) -> None:
        if paths.get_active_profile() != self._profile:
            self.reject()
            return
        name, accepted = QInputDialog.getText(self, t("reader_library_new_list"), t("reader_library_list_name"))
        if not accepted or paths.get_active_profile() != self._profile:
            return
        try:
            list_id = library.create_document_list(self._addon_dir, self._profile, name)
            self.available_lists = library.get_document_lists(self._addon_dir, self._profile)
            selected = set(self.selected_list_ids) | {list_id}
            self._search.clear()
            self._populate(selected)
        except Exception:
            showInfo(t("reader_library_list_error"), parent=self)

    def accept(self) -> None:
        if paths.get_active_profile() != self._profile:
            self.reject()
        elif len(self.selected_list_ids) <= library.MAX_BOOK_LISTS:
            super().accept()


class BookDetailsEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, addon_dir: str, profile: str, parent=None, *, available_lists=None):
        super().__init__(parent)
        self._addon_dir, self._profile = addon_dir, profile
        self._loading = False
        self._available_lists = []
        self._list_ids: set[int] = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("reader_library_lists")))
        row.addStretch()
        self._edit_lists = QPushButton(t("reader_library_edit_lists"))
        self._edit_lists.setAutoDefault(False)
        self._edit_lists.clicked.connect(self._choose_lists)
        row.addWidget(self._edit_lists)
        layout.addLayout(row)
        self._list_summary = QLabel()
        self._list_summary.setTextFormat(Qt.TextFormat.PlainText)
        self._list_summary.setWordWrap(True)
        layout.addWidget(self._list_summary)
        hint = QLabel(t("reader_library_lists_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        reason_label = QLabel(t("reader_library_reason"))
        layout.addWidget(reason_label)
        self._reason = QPlainTextEdit()
        self._reason.setPlaceholderText(t("reader_library_reason_placeholder"))
        self._reason.setAccessibleName(t("reader_library_reason"))
        self._reason.setAccessibleDescription(t("reader_library_reason_limit", count=library.MAX_REASON))
        self._reason.setMinimumHeight(100)
        self._reason.setMaximumHeight(180)
        reason_label.setBuddy(self._reason)
        layout.addWidget(self._reason)
        self._length = QLabel()
        layout.addWidget(self._length)
        source_label = QLabel(t("reader_library_source"))
        layout.addWidget(source_label)
        self._source = QLineEdit()
        self._source.setMaxLength(library.MAX_SOURCE)
        self._source.setPlaceholderText(t("reader_library_source_placeholder"))
        self._source.setAccessibleName(t("reader_library_source"))
        source_label.setBuddy(self._source)
        layout.addWidget(self._source)
        self._reason.textChanged.connect(self._changed)
        self._source.textChanged.connect(self._changed)
        self.reload_lists(available_lists)
        self.set_details({})

    def raw_details(self) -> dict:
        return {"reason": self._reason.toPlainText(), "source": self._source.text(),
                "list_ids": sorted(self._list_ids)}

    def details(self) -> dict:
        return library.normalize_document_details(self.raw_details())

    def set_details(self, details: dict) -> None:
        self._loading = True
        try:
            self._reason.setPlainText(details.get("reason", ""))
            self._source.setText(details.get("source", ""))
            self._list_ids = set(details.get("list_ids", [])) & {key for key, _name in self._available_lists}
            self._update_summary()
            self._update_length()
        finally:
            self._loading = False

    def reload_lists(self, available=None) -> None:
        self._available_lists = library.get_document_lists(self._addon_dir, self._profile) if available is None else list(available)
        self._list_ids.intersection_update(key for key, _name in self._available_lists)
        self._update_summary()

    def _update_summary(self) -> None:
        names = [name for key, name in self._available_lists if key in self._list_ids]
        summary = " · ".join(names[:3])
        if len(names) > 3:
            summary = t("reader_library_list_summary_more", names=summary, count=len(names) - 3)
        self._list_summary.setText(summary or t("reader_library_unlisted"))

    def _update_length(self) -> None:
        self._length.setText(t("reader_library_reason_count", count=len(self._reason.toPlainText()),
                               maximum=library.MAX_REASON))

    def _changed(self, *_args) -> None:
        if not self._loading:
            if self.sender() is self._reason:
                self._update_length()
            self.changed.emit()

    def _choose_lists(self) -> None:
        if paths.get_active_profile() != self._profile:
            return
        previous_ids, previous_lists = self._list_ids.copy(), self._available_lists[:]
        picker = DocumentListPickerDialog(self._addon_dir, self._profile, self._available_lists, self._list_ids, self)
        accepted = picker.exec()
        available, selected = picker.available_lists, picker.selected_list_ids
        picker.deleteLater()
        if paths.get_active_profile() != self._profile:
            return
        self.reload_lists(available)
        if accepted:
            self._list_ids = set(selected)
            self._update_summary()
        if self._list_ids != previous_ids or self._available_lists != previous_lists:
            self.changed.emit()


class ImportBookDetails(BookDetailsEditor):
    """Keep separate unsaved details for each selected import file."""

    def __init__(self, addon_dir: str, profile: str, parent=None):
        super().__init__(addon_dir, profile, parent)
        self._drafts: dict[str, dict] = {}
        self._path: str | None = None
        self.setEnabled(False)
        self.setToolTip(t("reader_library_import_hint"))

    def set_path(self, path: str | None) -> None:
        if self._path:
            self._drafts[self._path] = self.raw_details()
        self._path = path
        self.setEnabled(bool(path))
        self.set_details(self._drafts.get(path, {}))
        self.setAccessibleName(Path(path).name if path else t("reader_library_select_book"))

    def for_path(self, path: str) -> dict:
        if self._path:
            self._drafts[self._path] = self.raw_details()
        return library.normalize_document_details(self._drafts.get(path, {}))
