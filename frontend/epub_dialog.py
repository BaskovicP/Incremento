from __future__ import annotations

import os
from pathlib import Path

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
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QVBoxLayout,
    QWidget,
    QEvent,
    QItemSelectionModel,
    Qt,
)
from PyQt6.QtGui import QColor

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from incremento.frontend.tag_edit import QuickTagEdit  # type: ignore


class AddEpubDialog(QDialog):
    def __init__(
        self,
        addon_dir: str,
        deck_names: list[str] | None = None,
        default_deck: str = "Topics",
        parent=None,
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self.setWindowTitle("Add EPUBs")
        self.setMinimumSize(900, 560)

        self._epub_paths: list[str] = []
        self._tag_edits: dict[str, QuickTagEdit] = {}
        self._import_checks: dict[str, QCheckBox] = {}
        self._priority_spins: dict[str, QDoubleSpinBox] = {}
        self._row_heights: dict[str, int] = {}
        self._lower_priority_more_important = self._load_priority_direction()
        self._folder_pending_paths: list[str] = []
        self._folder_total_paths = 0
        self._last_removed_rows: list[dict] = []
        self._add_total_entries = 0
        self._folder_import_timer = QTimer(self)
        self._folder_import_timer.setSingleShot(True)
        self._folder_import_timer.timeout.connect(self._process_folder_queue)

        self.created: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        btn_row = QHBoxLayout()
        self._add_files_btn = QPushButton("Add files…")
        self._add_folder_btn = QPushButton("Add folder…")
        self._select_all_btn = QPushButton("Select all")
        self._deselect_all_btn = QPushButton("Deselect all")
        self._remove_selected_btn = QPushButton("Remove selected")
        self._undo_remove_btn = QPushButton("Undo remove")
        self._remove_selected_btn.setVisible(False)
        self._undo_remove_btn.setVisible(False)
        self._add_files_btn.clicked.connect(self._add_files)
        self._add_folder_btn.clicked.connect(self._add_folder)
        self._select_all_btn.clicked.connect(lambda: self._set_visible_import_checks(True))
        self._deselect_all_btn.clicked.connect(lambda: self._set_visible_import_checks(False))
        self._remove_selected_btn.clicked.connect(self._remove_selected_rows)
        self._undo_remove_btn.clicked.connect(self._undo_remove_rows)
        btn_row.addWidget(self._add_files_btn)
        btn_row.addWidget(self._add_folder_btn)
        btn_row.addWidget(self._select_all_btn)
        btn_row.addWidget(self._deselect_all_btn)
        btn_row.addWidget(self._remove_selected_btn)
        btn_row.addWidget(self._undo_remove_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter EPUBs by file name…")
        self._search_edit.textChanged.connect(self._apply_table_filter)
        layout.addWidget(self._search_edit)

        self._folder_progress = QProgressBar()
        self._folder_progress.setVisible(False)
        self._folder_progress.setTextVisible(True)
        self._folder_progress.setMinimum(0)
        self._folder_progress.setMaximum(1)
        self._folder_progress.setValue(0)
        layout.addWidget(self._folder_progress)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(self._status_lbl)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Import", "File", "Tags", "Priority", "Status"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        hdr.setStretchLastSection(False)
        self._table.setColumnWidth(0, 64)
        self._table.setColumnWidth(1, 360)
        self._table.setColumnWidth(2, 180)
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 90)
        self._table.verticalHeader().setDefaultSectionSize(42)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table, stretch=1)

        options = QWidget()
        form = QFormLayout(options)
        form.setContentsMargins(0, 0, 0, 0)

        self._global_tag_edit = QuickTagEdit(compact=True)
        form.addRow("Tags for all:", self._global_tag_edit)

        self._title_from_filename = QCheckBox("Use file name as title")
        self._title_from_filename.setChecked(True)
        self._title_from_filename.toggled.connect(self._on_title_mode_changed)
        form.addRow("", self._title_from_filename)

        self._title_edit = QLineEdit()
        form.addRow("Title:", self._title_edit)

        self._deck_combo = QComboBox()
        for name in (deck_names or ["Topics"]):
            self._deck_combo.addItem(name)
        idx = self._deck_combo.findText(default_deck)
        if idx >= 0:
            self._deck_combo.setCurrentIndex(idx)
        form.addRow("Deck:", self._deck_combo)

        layout.addWidget(options)

        self._error_lbl = QLabel()
        self._error_lbl.setStyleSheet("color: red;")
        self._error_lbl.setVisible(False)
        layout.addWidget(self._error_lbl)

        self._add_progress = QProgressBar()
        self._add_progress.setVisible(False)
        self._add_progress.setTextVisible(True)
        self._add_progress.setMinimum(0)
        self._add_progress.setMaximum(1)
        self._add_progress.setValue(0)
        layout.addWidget(self._add_progress)

        self._add_status_lbl = QLabel()
        self._add_status_lbl.setVisible(False)
        self._add_status_lbl.setStyleSheet("font-size: 11px; color: gray;")
        layout.addWidget(self._add_status_lbl)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Add")
        self._cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self._start_add)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._on_title_mode_changed(True)
        self._update_counts()

    def _last_dir(self) -> str:
        if self._epub_paths:
            return str(Path(self._epub_paths[-1]).parent)
        return ""

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Choose EPUB files",
            self._last_dir(),
            "EPUB files (*.epub)",
        )
        self._add_paths([p for p in paths if p])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder", self._last_dir())
        if not folder:
            return
        self._folder_progress.setRange(0, 0)
        self._folder_progress.setFormat("Scanning EPUB folder…")
        self._folder_progress.setVisible(True)
        self._status_lbl.setText("Scanning EPUB folder…")
        self._add_files_btn.setEnabled(False)
        self._add_folder_btn.setEnabled(False)

        def scan_folder() -> list[str]:
            found: list[str] = []
            for root, _, filenames in os.walk(folder):
                for name in filenames:
                    if name.lower().endswith(".epub"):
                        found.append(os.path.join(root, name))
            return sorted(found)

        def on_done(fut) -> None:
            try:
                paths = fut.result()
            except Exception as exc:
                self._folder_progress.setVisible(False)
                self._add_files_btn.setEnabled(True)
                self._add_folder_btn.setEnabled(True)
                self._show_error(f"Failed to scan EPUB folder: {exc}")
                self._update_counts()
                return
            self._folder_progress.setRange(0, 1)
            self._start_folder_import(paths)

        mw.taskman.run_in_background(scan_folder, on_done)

    def _add_paths(self, paths: list[str]) -> None:
        added = False
        for path in paths:
            if path and path not in self._tag_edits:
                self._add_row(path)
                added = True
        if added:
            self._error_lbl.setVisible(False)
            self._update_counts()

    def _start_folder_import(self, paths: list[str]) -> None:
        unique_paths = [path for path in paths if path not in self._tag_edits]
        if not unique_paths:
            self._status_lbl.setText("Found 0 new EPUBs in folder")
            self._finish_folder_import()
            return

        self._folder_pending_paths = unique_paths
        self._folder_total_paths = len(unique_paths)
        self._folder_progress.setMaximum(self._folder_total_paths)
        self._folder_progress.setValue(0)
        self._folder_progress.setFormat(self._folder_status_text(0))
        self._folder_progress.setVisible(True)
        self._status_lbl.setText(self._folder_status_text(0))
        self._add_files_btn.setEnabled(False)
        self._add_folder_btn.setEnabled(False)
        self._folder_import_timer.start(0)

    def _process_folder_queue(self) -> None:
        if not self._folder_pending_paths:
            self._finish_folder_import()
            return

        chunk_size = 12
        for _ in range(min(chunk_size, len(self._folder_pending_paths))):
            path = self._folder_pending_paths.pop(0)
            if path not in self._tag_edits:
                self._add_row(path)

        completed = self._folder_total_paths - len(self._folder_pending_paths)
        self._folder_progress.setValue(completed)
        self._folder_progress.setFormat(self._folder_status_text(completed))
        self._status_lbl.setText(self._folder_status_text(completed))

        if self._folder_pending_paths:
            self._folder_import_timer.start(0)
        else:
            self._finish_folder_import()

    def _finish_folder_import(self) -> None:
        completed_total = self._folder_total_paths
        self._folder_pending_paths = []
        self._folder_total_paths = 0
        self._folder_import_timer.stop()
        self._folder_progress.setVisible(False)
        self._folder_progress.setValue(0)
        if completed_total > 0:
            self._status_lbl.setText(
                f"Found {completed_total} EPUBs in folder · loaded into dialog"
            )
        self._add_files_btn.setEnabled(True)
        self._add_folder_btn.setEnabled(True)
        self._update_counts(prefix=self._status_lbl.text())

    def _add_row(self, path: str, *, row_idx: int | None = None, state: dict | None = None) -> None:
        if row_idx is None or row_idx < 0 or row_idx > self._table.rowCount():
            row_idx = self._table.rowCount()
        self._epub_paths.insert(row_idx, path)
        self._table.insertRow(row_idx)
        self._table.setRowHeight(row_idx, 42)

        import_check = QCheckBox("Add")
        import_check.setChecked(True if state is None else bool(state.get("import_enabled", True)))
        import_check.setToolTip("Checked EPUBs will be imported when you click Add")
        import_check.setStyleSheet("font-size: 11px; font-weight: 600;")
        import_check.toggled.connect(lambda _checked: self._update_counts())
        self._table.setCellWidget(row_idx, 0, self._wrap_cell_widget(import_check))
        self._import_checks[path] = import_check

        name_item = QTableWidgetItem(Path(path).name)
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        name_item.setToolTip(path)
        name_item.setTextAlignment(
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        )
        self._table.setItem(row_idx, 1, name_item)

        tag_edit = QuickTagEdit(compact=True)
        tag_edit.setMinimumHeight(34)
        if state and state.get("tags"):
            tag_edit.setTags(state["tags"])
        tag_edit.tagsChanged.connect(lambda _tags, p=path: self._ensure_import_checked(p))
        self._table.setCellWidget(row_idx, 2, self._wrap_cell_widget(tag_edit, fill_width=True))
        self._tag_edits[path] = tag_edit
        self._row_heights[path] = 42

        priority_spin = self._build_priority_spin()
        if state and state.get("priority") is not None:
            priority_spin.setValue(float(state["priority"]))
        priority_spin.valueChanged.connect(lambda _value, p=path: self._ensure_import_checked(p))
        self._table.setCellWidget(row_idx, 3, self._wrap_cell_widget(priority_spin))
        self._priority_spins[path] = priority_spin

        status = str(state.get("status") or "") if state else ""
        self._set_row_status_widget(row_idx, status)
        self._apply_filter_to_row(row_idx)
        if len(self._epub_paths) == 1:
            self._table.setCurrentCell(0, 1)

    def _find_row(self, path: str) -> int:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                return row
        return -1

    def _set_row_status(self, path: str, text: str, color: str = "") -> None:
        row = self._find_row(path)
        if row < 0:
            return
        self._table.setRowHeight(row, self._row_heights.get(path, 42))
        self._set_row_status_widget(row, text, color=color)

    def _set_row_status_widget(self, row: int, text: str, color: str = "") -> None:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style = "font-size: 10px;"
        if color:
            style += f" color: {color};"
        lbl.setStyleSheet(style)
        self._table.setCellWidget(row, 4, self._wrap_cell_widget(lbl))

    def _remove_row(self, path: str, *, track_undo: bool = True) -> None:
        removed_row = -1
        snapshot = None
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                snapshot = self._snapshot_row(path, row)
                removed_row = row
                self._table.removeRow(row)
                break
        if snapshot and track_undo:
            self._last_removed_rows = [snapshot]
            self._undo_remove_btn.setVisible(True)
        self._tag_edits.pop(path, None)
        self._import_checks.pop(path, None)
        self._priority_spins.pop(path, None)
        self._row_heights.pop(path, None)
        if path in self._epub_paths:
            self._epub_paths.remove(path)

        if self._epub_paths and removed_row >= 0:
            replacement_row = self._nearest_visible_row(min(removed_row, self._table.rowCount() - 1))
            if replacement_row >= 0:
                self._table.setCurrentCell(replacement_row, 1)
        self._on_selection_changed()
        self._update_counts()

    def _remove_selected_rows(self) -> None:
        selected_rows = self._selected_visible_rows()
        if not selected_rows:
            return
        snapshots = []
        paths = []
        for row in selected_rows:
            item = self._table.item(row, 1)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    snapshots.append(self._snapshot_row(path, row))
                    paths.append(path)
        if not paths:
            return

        self._last_removed_rows = snapshots
        self._undo_remove_btn.setVisible(True)
        anchor_row = selected_rows[0]
        for path in paths:
            self._remove_row(path, track_undo=False)

        if self._table.rowCount() > 0:
            replacement_row = self._nearest_visible_row(min(anchor_row, self._table.rowCount() - 1))
            if replacement_row >= 0:
                self._table.setCurrentCell(replacement_row, 1)
        self._on_selection_changed()
        self._update_counts()

    def _undo_remove_rows(self) -> None:
        if not self._last_removed_rows:
            return
        restored_paths = []
        for snapshot in sorted(self._last_removed_rows, key=lambda row: row["row"]):
            path = snapshot["path"]
            if path in self._tag_edits:
                continue
            insert_row = min(snapshot["row"], self._table.rowCount())
            self._add_row(path, row_idx=insert_row, state=snapshot)
            restored_paths.append(path)
        self._last_removed_rows = []
        self._undo_remove_btn.setVisible(False)
        if restored_paths:
            row = self._find_row(restored_paths[0])
            if row >= 0 and not self._table.isRowHidden(row):
                self._table.setCurrentCell(row, 1)
        self._on_selection_changed()
        self._update_counts()

    def _on_selection_changed(self) -> None:
        self._remove_selected_btn.setVisible(bool(self._selected_visible_rows()))

    def _apply_table_filter(self, _text: str) -> None:
        current_row = self._table.currentRow()
        current_path = None
        if current_row >= 0:
            item = self._table.item(current_row, 1)
            if item:
                current_path = item.data(Qt.ItemDataRole.UserRole)

        for row in range(self._table.rowCount()):
            self._apply_filter_to_row(row)

        self._clear_hidden_selection()

        if current_path:
            row = self._find_row(current_path)
            if row >= 0 and not self._table.isRowHidden(row):
                self._table.setCurrentCell(row, 1)
                self._on_selection_changed()
                self._update_counts()
                return

        replacement_row = self._nearest_visible_row(0)
        if replacement_row >= 0:
            self._table.setCurrentCell(replacement_row, 1)
        else:
            self._table.clearSelection()
        self._on_selection_changed()
        self._update_counts()

    def _apply_filter_to_row(self, row: int) -> None:
        item = self._table.item(row, 1)
        if item is None:
            return
        query = self._search_edit.text().strip().lower()
        matches = not query or query in item.text().lower()
        self._table.setRowHidden(row, not matches)

    def _nearest_visible_row(self, start_row: int) -> int:
        if self._table.rowCount() <= 0:
            return -1
        for row in range(max(0, start_row), self._table.rowCount()):
            if not self._table.isRowHidden(row):
                return row
        for row in range(min(start_row - 1, self._table.rowCount() - 1), -1, -1):
            if not self._table.isRowHidden(row):
                return row
        return -1

    def _selected_visible_rows(self) -> list[int]:
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return []
        return sorted(
            {
                index.row()
                for index in selection_model.selectedRows()
                if not self._table.isRowHidden(index.row())
            }
        )

    def _clear_hidden_selection(self) -> None:
        selection_model = self._table.selectionModel()
        if selection_model is None:
            return
        for row in range(self._table.rowCount()):
            if not self._table.isRowHidden(row):
                continue
            for col in range(self._table.columnCount()):
                index = self._table.model().index(row, col)
                if index.isValid():
                    selection_model.select(
                        index,
                        QItemSelectionModel.SelectionFlag.Deselect,
                    )

    def _visible_rows(self) -> list[int]:
        return [
            row for row in range(self._table.rowCount()) if not self._table.isRowHidden(row)
        ]

    def _set_visible_import_checks(self, checked: bool) -> None:
        changed = False
        for row in self._visible_rows():
            item = self._table.item(row, 1)
            if item is None:
                continue
            path = item.data(Qt.ItemDataRole.UserRole)
            checkbox = self._import_checks.get(path)
            if checkbox is None:
                continue
            if checkbox.isChecked() != checked:
                checkbox.setChecked(checked)
                changed = True
        if changed:
            self._error_lbl.setVisible(False)
            self._update_counts()

    def _checked_paths(self) -> list[str]:
        checked_paths: list[str] = []
        for path in self._epub_paths:
            checkbox = self._import_checks.get(path)
            if checkbox is not None and checkbox.isChecked():
                checked_paths.append(path)
        return checked_paths

    def _ensure_import_checked(self, path: str) -> None:
        checkbox = self._import_checks.get(path)
        if checkbox is not None and not checkbox.isChecked():
            checkbox.setChecked(True)

    def _snapshot_row(self, path: str, row: int) -> dict:
        tag_edit = self._tag_edits.get(path)
        status = ""
        status_widget = self._table.cellWidget(row, 4)
        if status_widget:
            label = status_widget.findChild(QLabel)
            if label:
                status = label.text()
        return {
            "row": row,
            "path": path,
            "import_enabled": bool(self._import_checks.get(path).isChecked())
            if self._import_checks.get(path) is not None
            else True,
            "tags": tag_edit.tags() if tag_edit else [],
            "priority": self._priority_for_path(path),
            "status": status,
        }

    def _title_for_path(self, path: str) -> str:
        if self._title_from_filename.isChecked():
            return Path(path).stem
        return self._title_edit.text().strip()

    def _start_add(self) -> None:
        if not self._epub_paths:
            self._show_error("Choose at least one EPUB file.")
            return
        checked_paths = self._checked_paths()
        if not checked_paths:
            self._show_error("Please check at least one EPUB to import.")
            return
        if not self._title_from_filename.isChecked() and len(checked_paths) > 1:
            self._show_error("For multiple EPUBs, enable 'Use file name as title'.")
            return
        if not self._title_from_filename.isChecked() and not self._title_edit.text().strip():
            self._show_error("Please enter a title.")
            return
        self._error_lbl.setVisible(False)

        global_tags = self._global_tag_edit.tags()
        entries = []
        for path in checked_paths:
            title = self._title_for_path(path)
            tag_edit = self._tag_edits.get(path)
            file_tags = tag_edit.tags() if tag_edit else []
            merged = global_tags + [tag for tag in file_tags if tag not in global_tags]
            priority = self._priority_for_path(path)
            entries.append((path, title, merged, priority))

        self._start_add_progress(len(entries))
        self._ok_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._add_files_btn.setEnabled(False)
        self._add_folder_btn.setEnabled(False)
        self._select_all_btn.setEnabled(False)
        self._deselect_all_btn.setEnabled(False)
        self._remove_selected_btn.setEnabled(False)
        self._undo_remove_btn.setEnabled(False)

        self._process_files(entries, 0)

    def _process_files(self, entries: list, idx: int) -> None:
        if idx >= len(entries):
            self._finish_add_progress()
            self.accept()
            return

        path, title, tags, priority = entries[idx]
        deck = self._deck_combo.currentText()
        self._update_add_progress(idx, len(entries), path, phase="Starting")

        try:
            from ..backend.epub_manager import add_epub_card
            from ..backend.priority_manager import set_priority
            from ..backend.paths import get_active_profile as _active_profile
        except Exception:
            from epub_manager import add_epub_card  # type: ignore
            from priority_manager import set_priority  # type: ignore
            from paths import get_active_profile as _active_profile  # type: ignore

        self._set_row_status(path, "Adding…")
        try:
            cid = add_epub_card(
                self._addon_dir,
                mw.col,
                path,
                title,
                deck_name=deck,
                tags=tags,
            )
            set_priority(self._addon_dir, _active_profile(), cid, priority)
            self.created.append((path, title))
            self._set_row_status(path, "✓", color="#4caf50")
            self._update_add_progress(idx + 1, len(entries), path, phase="Done")
        except Exception as exc:
            self.failed.append((path, str(exc)))
            self._set_row_status(path, "✗", color="red")
            self._update_add_progress(idx + 1, len(entries), path, phase="Failed")

        QTimer.singleShot(0, lambda: self._process_files(entries, idx + 1))

    def _on_title_mode_changed(self, checked: bool) -> None:
        self._title_edit.setEnabled(not checked)
        self._title_edit.setPlaceholderText(
            "Derived from each file name" if checked else "Card title"
        )

    def _wrap_cell_widget(self, widget: QWidget, *, fill_width: bool = False) -> QWidget:
        host = QWidget(self._table)
        layout = QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if fill_width:
            layout.addWidget(widget, 1, Qt.AlignmentFlag.AlignVCenter)
        else:
            layout.addStretch()
            layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
            layout.addStretch()
        return host

    def _build_priority_spin(self) -> QDoubleSpinBox:
        spin = _FreshStartPrioritySpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.1)
        spin.setValue(50.0)
        spin.setFixedWidth(94)
        important_end = "0" if self._lower_priority_more_important else "100"
        spin.setToolTip(
            f"Priority for this EPUB. {important_end} is highest importance, 50 is default."
        )
        spin.valueChanged.connect(lambda _value, s=spin: self._apply_priority_spin_style(s))
        self._apply_priority_spin_style(spin)
        return spin

    def _priority_for_path(self, path: str) -> float:
        spin = self._priority_spins.get(path)
        if spin is None:
            return 50.0
        return round(spin.value(), 4)

    def _apply_priority_spin_style(self, spin: QDoubleSpinBox) -> None:
        bg = self._priority_color(spin.value())
        fg = "#000000"
        border = bg.darker(135).name()
        spin.setStyleSheet(
            f"""
            QDoubleSpinBox {{
                background-color: {bg.name()};
                color: {fg};
                border: 1px solid {border};
                border-radius: 5px;
                padding: 2px 6px;
                font-weight: 700;
            }}
            QDoubleSpinBox QLineEdit {{
                color: {fg};
                font-weight: 700;
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                width: 18px;
                border: none;
                background: transparent;
            }}
            """
        )

    def _priority_color(self, priority: float) -> QColor:
        clamped = max(0.0, min(100.0, float(priority)))
        fraction = clamped / 100.0
        stops = [
            (0.00, QColor("#ff0000")),
            (0.17, QColor("#ff8800")),
            (0.33, QColor("#ffff00")),
            (0.50, QColor("#00cc00")),
            (0.67, QColor("#00cccc")),
            (0.83, QColor("#0000ff")),
            (1.00, QColor("#8800cc")),
        ]
        if not self._lower_priority_more_important:
            fraction = 1.0 - fraction

        if fraction <= stops[0][0]:
            return stops[0][1]
        for idx in range(1, len(stops)):
            left_pos, left_color = stops[idx - 1]
            right_pos, right_color = stops[idx]
            if fraction <= right_pos:
                span = right_pos - left_pos
                mix = 0.0 if span <= 0 else (fraction - left_pos) / span
                red = round(left_color.red() + (right_color.red() - left_color.red()) * mix)
                green = round(left_color.green() + (right_color.green() - left_color.green()) * mix)
                blue = round(left_color.blue() + (right_color.blue() - left_color.blue()) * mix)
                return QColor(red, green, blue)
        return stops[-1][1]

    def _load_priority_direction(self) -> bool:
        try:
            from ..backend.priority_manager import configured_priority_lower_is_more_important
        except Exception:
            from priority_manager import configured_priority_lower_is_more_important  # type: ignore
        return bool(configured_priority_lower_is_more_important())

    def _start_add_progress(self, total_entries: int) -> None:
        self._add_total_entries = max(0, int(total_entries))
        self._add_progress.setMaximum(max(1, self._add_total_entries))
        self._add_progress.setValue(0)
        self._add_progress.setFormat(
            f"Adding EPUBs… 0 / {self._add_total_entries}"
            if self._add_total_entries
            else "Adding EPUBs…"
        )
        self._add_progress.setVisible(self._add_total_entries > 0)
        self._add_status_lbl.setVisible(self._add_total_entries > 0)
        if self._add_total_entries > 0:
            self._add_status_lbl.setText(f"Adding EPUBs… 0 / {self._add_total_entries}")

    def _update_add_progress(self, completed: int, total: int, path: str, *, phase: str) -> None:
        total = max(0, int(total))
        completed = max(0, min(int(completed), total))
        self._add_progress.setMaximum(max(1, total))
        self._add_progress.setValue(completed)
        self._add_progress.setFormat(f"Adding EPUBs… {completed} / {total}")
        self._add_status_lbl.setText(
            f"Adding EPUBs… {completed} / {total} · {phase}: {Path(path).name}"
        )

    def _finish_add_progress(self) -> None:
        if self._add_total_entries > 0:
            self._add_progress.setValue(self._add_total_entries)
            self._add_progress.setFormat(
                f"Adding EPUBs… {self._add_total_entries} / {self._add_total_entries}"
            )
            self._add_status_lbl.setText(
                f"Adding EPUBs… {self._add_total_entries} / {self._add_total_entries}"
            )
        self._add_progress.setVisible(False)
        self._add_status_lbl.setVisible(False)
        self._add_total_entries = 0

    def _folder_status_text(self, completed: int) -> str:
        remaining = max(0, self._folder_total_paths - completed)
        return (
            f"Found {self._folder_total_paths} EPUBs in folder · "
            f"{remaining} remaining · adding… {completed} / {self._folder_total_paths}"
        )

    def _update_counts(self, *, prefix: str = "") -> None:
        total = len(self._epub_paths)
        visible = len(self._visible_rows())
        checked = len(self._checked_paths())
        query = self._search_edit.text().strip()
        counts = f"{total} EPUBs in dialog · {checked} checked to import"
        if query:
            counts += f" · {visible} visible"
        self._status_lbl.setText(f"{prefix} · {counts}" if prefix else counts)

    def _show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            if self._table.hasFocus() or any(index.isValid() for index in self._table.selectedIndexes()):
                self._remove_selected_rows()
                event.accept()
                return
        super().keyPressEvent(event)

    @property
    def epub_path(self) -> str:
        return self._epub_paths[0] if self._epub_paths else ""

    @property
    def epub_paths(self) -> list[str]:
        return list(self._epub_paths)

    @property
    def title_text(self) -> str:
        return self._title_edit.text().strip()

    @property
    def use_filename_titles(self) -> bool:
        return self._title_from_filename.isChecked()

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()

    @property
    def priority(self) -> float:
        if not self._epub_paths:
            return 50.0
        row = self._table.currentRow()
        if row >= 0:
            item = self._table.item(row, 1)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    return self._priority_for_path(path)
        return self._priority_for_path(self._epub_paths[0])

    def selected_entries(self) -> list[tuple[str, str, list[str]]]:
        global_tags = self._global_tag_edit.tags()
        checked_paths = self._checked_paths()
        paths = checked_paths if self._title_from_filename.isChecked() else checked_paths[:1]
        result = []
        for path in paths:
            title = Path(path).stem if self._title_from_filename.isChecked() else self.title_text
            tag_edit = self._tag_edits.get(path)
            file_tags = tag_edit.tags() if tag_edit else []
            merged = global_tags + [tag for tag in file_tags if tag not in global_tags]
            result.append((path, title, merged))
        return result


class _FreshStartPrioritySpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cleared_for_edit = False
        self._saved_value = 50.0
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        line_edit = self.lineEdit()
        if obj is line_edit and line_edit is not None:
            if event.type() == QEvent.Type.MouseButtonPress:
                self._saved_value = float(self.value())
                self._cleared_for_edit = True
                QTimer.singleShot(0, line_edit.clear)
            elif event.type() == QEvent.Type.FocusOut:
                if self._cleared_for_edit and not line_edit.text().strip():
                    self.setValue(self._saved_value)
                self._cleared_for_edit = False
        return super().eventFilter(obj, event)
