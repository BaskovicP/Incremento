"""Batch Markdown study-document import with inert rendered previews."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from aqt import mw
from aqt.qt import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTimer,
    Qt,
    QVBoxLayout,
    QWidget,
)

try:
    from ..backend import paths, markdown_manager, epub_manager
    from ..backend.i18n import t
    from ..backend.priority_manager import set_priority
    from .tag_edit import QuickTagEdit
except ImportError:
    from backend import paths, markdown_manager, epub_manager
    from backend.i18n import t
    from backend.priority_manager import set_priority
    from frontend.tag_edit import QuickTagEdit


class MarkdownPreview(QTextBrowser):
    """Never let Qt resolve local or remote resources from untrusted Markdown."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.setObjectName("incremento_markdown_preview")
        self.setAccessibleName(t("imports_preview"))
        self.setStyleSheet(
            "QTextBrowser#incremento_markdown_preview { padding: 16px; border: 1px solid palette(mid); border-radius: 6px; }"
        )

    def loadResource(self, _kind, _url):
        return None


class AddMarkdownDocumentDialog(QDialog):
    def __init__(self, addon_dir: str, deck_names: list[str] | None = None, default_deck: str = "Topics", parent=None):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self._profile = paths.get_active_profile()
        self._collection = mw.col
        self._closed = self._busy = False
        self._preview_generation = 0
        self.created: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.finished.connect(self._on_finished)
        self.setWindowTitle(t("imports_markdown_document_title"))
        self.resize(1120, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)
        description = QLabel(t("imports_markdown_document_description"))
        description.setWordWrap(True)
        description.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(description)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        left, right = QWidget(splitter), QWidget(splitter)
        left_layout, right_layout = QVBoxLayout(left), QVBoxLayout(right)
        left_layout.setContentsMargins(0, 0, 8, 0)
        right_layout.setContentsMargins(8, 0, 0, 0)
        left_layout.setSpacing(10)
        right_layout.setSpacing(8)
        file_row = QHBoxLayout()
        self._browse_btn = QPushButton(t("imports_add_files"))
        self._browse_btn.clicked.connect(self._choose_file)
        self._folder_btn = QPushButton(t("imports_add_folder"))
        self._folder_btn.clicked.connect(self._choose_folder)
        self._select_btn = QPushButton(t("imports_select_all"))
        self._select_btn.clicked.connect(lambda: self._select_all(True))
        self._deselect_btn = QPushButton(t("imports_deselect_all"))
        self._deselect_btn.clicked.connect(lambda: self._select_all(False))
        for button in (self._browse_btn, self._folder_btn, self._select_btn, self._deselect_btn):
            file_row.addWidget(button)
        file_row.addStretch()
        left_layout.addLayout(file_row)
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText(t("imports_markdown_filter_names"))
        self._filter_edit.setAccessibleName(t("imports_markdown_filter_names"))
        self._filter_edit.textChanged.connect(self._filter_rows)
        left_layout.addWidget(self._filter_edit)
        self._table = QTableWidget(0, 4)
        self._table.setAccessibleName(t("imports_markdown_files"))
        self._table.setHorizontalHeaderLabels(
            [t("imports_import"), t("imports_table_file"), t("imports_table_tags"), t("imports_table_priority")]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 70)
        self._table.setColumnWidth(2, 220)
        self._table.setColumnWidth(3, 120)
        self._table.currentCellChanged.connect(self._schedule_preview)
        left_layout.addWidget(self._table, 1)
        form = QFormLayout()
        self._tag_edit = QuickTagEdit(compact=True)
        form.addRow(t("imports_tags_for_all"), self._tag_edit)
        self._filename_title_cb = QCheckBox(t("imports_use_filename_title"))
        self._filename_title_cb.setChecked(True)
        form.addRow("", self._filename_title_cb)
        self._title_edit = QLineEdit()
        self._title_edit.setEnabled(False)
        self._title_edit.setPlaceholderText(t("imports_derived_filename"))
        self._filename_title_cb.toggled.connect(
            lambda checked: self._title_edit.setEnabled(not checked and not self._busy)
        )
        form.addRow(t("imports_title_label"), self._title_edit)
        self._deck_combo = QComboBox()
        self._deck_combo.addItems(deck_names or ["Topics"])
        index = self._deck_combo.findText(default_deck)
        if index >= 0:
            self._deck_combo.setCurrentIndex(index)
        form.addRow(t("imports_deck_label"), self._deck_combo)
        left_layout.addLayout(form)
        preview_title = QLabel(t("imports_preview"))
        preview_title.setStyleSheet("font-weight: 600;")
        right_layout.addWidget(preview_title)
        self._preview = MarkdownPreview(right)
        self._preview.setMinimumWidth(280)
        self._preview.setPlainText(t("imports_preview_select_file"))
        right_layout.addWidget(self._preview, 1)
        self._preview_name = QLabel("")
        self._preview_name.setTextFormat(Qt.TextFormat.PlainText)
        self._preview_name.setWordWrap(True)
        self._preview_name.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        right_layout.addWidget(self._preview_name)
        splitter.setSizes([650, 420])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter, 1)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self._status)
        self._progress = QProgressBar()
        self._progress.hide()
        layout.addWidget(self._progress)
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText(t("imports_add"))
        self._ok_btn.setDefault(True)
        self._cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._cancel_btn.setText(t("imports_cancel"))
        self._buttons.accepted.connect(self._start_import)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()

    @property
    def _priority_spin(self):
        return self._table.cellWidget(0, 3)

    def _on_finished(self, _result) -> None:
        self._closed = True
        self._preview_generation += 1

    def _request_current(self) -> bool:
        return not self._closed and paths.get_active_profile() == self._profile and mw.col is self._collection

    def _set_path(self, path: str) -> None:
        self._add_paths([path])

    def _add_paths(self, filenames: list[str]) -> None:
        if self._busy or not self._request_current():
            return
        existing = {self._table.item(row, 1).data(Qt.ItemDataRole.UserRole) for row in range(self._table.rowCount())}
        for filename in filenames:
            path = str(Path(filename).absolute())
            if path in existing or Path(path).suffix.casefold() not in {".md", ".markdown"}:
                continue
            if self._table.rowCount() >= 1000:
                self._status.setText(t("imports_markdown_batch_limit"))
                break
            existing.add(path)
            row = self._table.rowCount()
            self._table.insertRow(row)
            checked = QTableWidgetItem()
            checked.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
            checked.setCheckState(Qt.CheckState.Checked)
            self._table.setItem(row, 0, checked)
            item = QTableWidgetItem(Path(path).name)
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self._table.setItem(row, 1, item)
            tags = QuickTagEdit(compact=True)
            tags.setAccessibleName(t("imports_table_tags") + ": " + Path(path).name)
            self._table.setCellWidget(row, 2, tags)
            priority = QDoubleSpinBox()
            priority.setRange(0, 100)
            priority.setDecimals(4)
            priority.setValue(50)
            priority.setAccessibleName(t("imports_table_priority") + ": " + Path(path).name)
            self._table.setCellWidget(row, 3, priority)
            self._table.setRowHeight(row, max(42, tags.sizeHint().height(), priority.sizeHint().height()))
        if self._table.rowCount() == 1 and not self._title_edit.text():
            self._title_edit.setText(Path(self._table.item(0, 1).data(Qt.ItemDataRole.UserRole)).stem)
        self._filter_rows()

    def _choose_file(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(
            self, t("imports_markdown_choose_file"), "", t("imports_markdown_file_filter")
        )
        self._add_paths(filenames)
        if filenames:
            self._table.setCurrentCell(self._table.rowCount() - 1, 1)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("imports_add_folder"))
        if not folder or self._busy:
            return
        self._set_busy(True)
        self._status.setText(t("imports_markdown_scanning"))

        def scan():
            files, visited = [], 0
            for root, directories, names in os.walk(folder, followlinks=False):
                visited += 1 + len(directories)
                if visited >= 50_000:
                    return files, True
                directories[:] = sorted(d for d in directories if not Path(root, d).is_symlink())
                for name in sorted(names):
                    visited += 1
                    candidate = Path(root, name)
                    if not candidate.is_symlink() and candidate.suffix.casefold() in {".md", ".markdown"}:
                        files.append(str(candidate))
                    if visited >= 50_000 or len(files) >= 1000:
                        return files, True
            return files, False

        def done(future):
            if not self._request_current():
                return
            self._set_busy(False)
            try:
                files, limited = future.result()
                self._add_paths(files)
                self._status.setText(t("imports_markdown_batch_limit") if limited else "")
            except Exception as exc:
                self._status.setText(t("imports_markdown_failed", error=str(exc)))

        try:
            mw.taskman.run_in_background(scan, done, uses_collection=False)
        except Exception as exc:
            self._set_busy(False)
            self._status.setText(t("imports_markdown_failed", error=str(exc)))

    def _filter_rows(self, *_args) -> None:
        query = self._filter_edit.text().strip().casefold()
        for row in range(self._table.rowCount()):
            self._table.setRowHidden(row, query not in self._table.item(row, 1).text().casefold())

    def _select_all(self, checked: bool) -> None:
        for row in range(self._table.rowCount()):
            if not self._table.isRowHidden(row):
                self._table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def _schedule_preview(self, *_args) -> None:
        self._preview_generation += 1
        generation = self._preview_generation
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 1)
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        self._preview_name.setText(Path(path).name)

        def start():
            if not self._request_current() or generation != self._preview_generation or self._busy:
                return

            def done(future):
                if not self._request_current() or generation != self._preview_generation:
                    return
                try:
                    self._preview.setHtml(future.result())
                except Exception as exc:
                    self._preview.setPlainText(t("imports_markdown_failed", error=str(exc)))

            mw.taskman.run_in_background(
                lambda: markdown_manager.render_markdown_preview(path), done, uses_collection=False
            )

        QTimer.singleShot(120, start)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        for widget in (
            self._ok_btn,
            self._browse_btn,
            self._folder_btn,
            self._select_btn,
            self._deselect_btn,
            self._filter_edit,
            self._table,
            self._filename_title_cb,
            self._deck_combo,
            self._tag_edit,
        ):
            widget.setEnabled(not busy)
        self._title_edit.setEnabled(not busy and not self._filename_title_cb.isChecked())
        self._progress.setVisible(busy)
        if busy:
            self._progress.setRange(0, 0)

    def _import_requests(self) -> list[tuple[str, str, list[str], float]]:
        requests = []
        for row in range(self._table.rowCount()):
            if self._table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            path = self._table.item(row, 1).data(Qt.ItemDataRole.UserRole)
            title = Path(path).stem if self._filename_title_cb.isChecked() else self._title_edit.text().strip()
            tags = list(dict.fromkeys([*self._tag_edit.tags(), *self._table.cellWidget(row, 2).tags()]))
            requests.append((path, title, tags, self._table.cellWidget(row, 3).value()))
        return requests

    def _start_import(self) -> None:
        if self._busy or not self._request_current():
            return
        requests = self._import_requests()
        if not requests:
            self._status.setText(t("imports_markdown_choose_file"))
            return
        if any(not title for _, title, _, _ in requests):
            self._status.setText(t("imports_enter_title"))
            return
        self._set_busy(True)
        self._preview_generation += 1
        self._process_next(requests, self.deck_name)

    def _process_next(self, requests, deck) -> None:
        if not self._request_current():
            return
        if not requests:
            self._set_busy(False)
            self._cancel_btn.setEnabled(True)
            if not self.failed:
                self.accept()
            else:
                self._status.setText(
                    t("imports_markdown_batch_result", added=len(self.created), failed=len(self.failed))
                    + "\n"
                    + "\n".join(Path(path).name + ": " + error for path, error in self.failed[:5])
                )
                self._ok_btn.setEnabled(False)
                self._cancel_btn.setText(t("common_close"))
            return
        path, title, tags, priority = requests[0]
        addon_dir, profile, collection = self._addon_dir, self._profile, self._collection
        self._status.setText(t("imports_markdown_rendering") + " " + Path(path).name)

        def failure(exc):
            if self._request_current():
                self.failed.append((path, str(exc)))
                self._cancel_btn.setEnabled(True)
                self._process_next(requests[1:], deck)

        def prepared_done(future):
            try:
                prepared = future.result()
            except Exception as exc:
                failure(exc)
                return
            if not self._request_current():
                prepared.close()
                return
            try:
                from aqt.operations import CollectionOp

                def operation(col):
                    if col is not collection or paths.get_active_profile() != profile or self._closed:
                        raise markdown_manager.MarkdownImportError(t("imports_markdown_cancelled"))
                    step = col.add_custom_undo_entry(t("imports_markdown_undo"))
                    cid = epub_manager.add_epub_card(
                        addon_dir,
                        col,
                        prepared.path,
                        title,
                        deck_name=deck,
                        tags=tags,
                        profile=profile,
                        source_type="Markdown",
                    )
                    set_priority(addon_dir, profile, cid, priority)
                    return SimpleNamespace(changes=col.merge_undo_entries(step), card_id=cid)

                def success(_result):
                    prepared.close()
                    if self._request_current():
                        self.created.append((path, title))
                        self._cancel_btn.setEnabled(True)
                        self._process_next(requests[1:], deck)

                def import_failure(exc):
                    prepared.close()
                    failure(exc)

                self._cancel_btn.setEnabled(False)
                CollectionOp(self, operation).success(success).failure(import_failure).run_in_background()
            except Exception as exc:
                prepared.close()
                failure(exc)

        try:
            mw.taskman.run_in_background(
                lambda: markdown_manager.prepare_markdown_epub(path, title=title), prepared_done, uses_collection=False
            )
        except Exception as exc:
            failure(exc)
