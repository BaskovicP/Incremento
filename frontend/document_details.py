"""Shared native book details editor for the bookshelf and document imports."""

from __future__ import annotations

from pathlib import Path

from aqt.qt import (QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                    QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout,
                    QWidget, Qt, pyqtSignal)
from aqt.utils import showInfo

try:
    from ..backend import document_lists as library, paths
    from ..backend.i18n import t
except ImportError:
    from backend import document_lists as library, paths
    from backend.i18n import t


class BookDetailsEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, addon_dir: str, profile: str, parent=None, *, available_lists=None):
        super().__init__(parent)
        self._addon_dir, self._profile = addon_dir, profile
        self._loading = False
        self._available_lists = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("reader_library_lists")))
        row.addStretch()
        self._edit_lists = QPushButton(t("reader_library_edit_lists"))
        self._edit_lists.setCheckable(True)
        row.addWidget(self._edit_lists)
        layout.addLayout(row)
        self._list_summary = QLabel()
        self._list_summary.setTextFormat(Qt.TextFormat.PlainText)
        self._list_summary.setWordWrap(True)
        layout.addWidget(self._list_summary)
        self._list_picker = QWidget()
        picker = QVBoxLayout(self._list_picker)
        picker.setContentsMargins(0, 0, 0, 0)
        self._lists = QListWidget()
        self._lists.setMaximumHeight(130)
        self._lists.setAccessibleName(t("reader_library_choose_lists"))
        picker.addWidget(self._lists)
        new_button = QPushButton(t("reader_library_new_list"))
        new_button.clicked.connect(self._create_list)
        picker.addWidget(new_button)
        layout.addWidget(self._list_picker)
        self._list_picker.hide()
        self._edit_lists.toggled.connect(self._list_picker.setVisible)
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
        self._lists.itemChanged.connect(self._changed)
        self._reason.textChanged.connect(self._changed)
        self._source.textChanged.connect(self._changed)
        self.reload_lists(available_lists)
        self.set_details({})

    def raw_details(self) -> dict:
        return {"reason": self._reason.toPlainText(), "source": self._source.text(),
                "list_ids": sorted(self._lists.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self._lists.count())
                    if self._lists.item(i).checkState() == Qt.CheckState.Checked)}

    def details(self) -> dict:
        return library.normalize_document_details(self.raw_details())

    def set_details(self, details: dict) -> None:
        self._loading = True
        try:
            self._reason.setPlainText(details.get("reason", ""))
            self._source.setText(details.get("source", ""))
            ids = details.get("list_ids", [])
            for i in range(self._lists.count()):
                item = self._lists.item(i)
                item.setCheckState(Qt.CheckState.Checked if item.data(Qt.ItemDataRole.UserRole) in ids
                                   else Qt.CheckState.Unchecked)
            self._update_summary()
        finally:
            self._loading = False

    def reload_lists(self, available=None) -> None:
        details = self.raw_details()
        self._available_lists = library.get_document_lists(self._addon_dir, self._profile) if available is None else list(available)
        self._loading = True
        self._lists.clear()
        for list_id, name in self._available_lists:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, list_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._lists.addItem(item)
        self.set_details(details)

    def _update_summary(self) -> None:
        selected = set(self.raw_details()["list_ids"])
        self._list_summary.setText(" · ".join(name for key, name in self._available_lists if key in selected)
                                   or t("reader_library_unlisted"))
        self._length.setText(t("reader_library_reason_count", count=len(self._reason.toPlainText()),
                               maximum=library.MAX_REASON))

    def _changed(self, *_args) -> None:
        if not self._loading:
            self._update_summary()
            self.changed.emit()

    def _create_list(self) -> None:
        if paths.get_active_profile() != self._profile:
            return
        name, accepted = QInputDialog.getText(self, t("reader_library_new_list"), t("reader_library_list_name"))
        if not accepted or paths.get_active_profile() != self._profile:
            return
        try:
            list_id = library.create_document_list(self._addon_dir, self._profile, name)
            self.reload_lists()
            for i in range(self._lists.count()):
                if self._lists.item(i).data(Qt.ItemDataRole.UserRole) == list_id:
                    self._lists.item(i).setCheckState(Qt.CheckState.Checked)
        except Exception:
            showInfo(t("reader_library_list_error"), parent=self)


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
