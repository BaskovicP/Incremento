"""Common table actions, progress, and priority styling for PDF/EPUB imports."""
from pathlib import Path

from aqt.qt import QDoubleSpinBox, QItemSelectionModel, Qt
from PyQt6.QtGui import QColor

try:
    from .reviewer_priority_badge import get_reviewer_priority_palette
except ImportError:
    from reviewer_priority_badge import get_reviewer_priority_palette

try:
    from ..backend.i18n import t as _t
except ImportError:
    from backend.i18n import t as _t


class DocumentImportControls:
    """Reuse controls while each dialog owns its row state and import lifecycle."""

    def _refresh_import_counts(self) -> None:
        pass

    def _priority_color(self, priority: float) -> QColor:
        return QColor(get_reviewer_priority_palette(
            priority, lower_is_more_important=self._lower_priority_more_important,
        )["accent"])

    def _process_folder_queue(self) -> None:
        if not self._folder_pending_paths:
            self._finish_folder_import()
            return

        chunk_size = self._folder_batch_size
        for _ in range(min(chunk_size, len(self._folder_pending_paths))):
            path = self._folder_pending_paths.pop(0)
            if path not in self._tag_edits:
                self._add_row(path)

        completed = self._folder_total_paths - len(self._folder_pending_paths)
        self._folder_progress.setValue(completed)
        self._folder_progress.setFormat(self._folder_status_text(completed))
        self._folder_status_lbl.setText(self._folder_status_text(completed))

        if self._folder_pending_paths:
            self._folder_import_timer.start(0)
        else:
            self._finish_folder_import()

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
        self._refresh_import_counts()

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
        self._refresh_import_counts()

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
            self._refresh_import_counts()

    def _start_add_progress(self, total_entries: int) -> None:
        self._add_total_entries = max(0, int(total_entries))
        self._add_progress.setMaximum(max(1, self._add_total_entries))
        self._add_progress.setValue(0)
        self._add_progress.setFormat(
            _t(self._import_progress_key, completed=0, total=self._add_total_entries)
            if self._add_total_entries
            else _t(self._import_adding_key)
        )
        self._add_progress.setVisible(self._add_total_entries > 0)
        self._add_status_lbl.setVisible(self._add_total_entries > 0)
        if self._add_total_entries > 0:
            self._add_status_lbl.setText(_t(self._import_progress_key, completed=0, total=self._add_total_entries))

    def _update_add_progress(self, completed: int, total: int, path: str, *, phase: str) -> None:
        total = max(0, int(total))
        completed = max(0, min(int(completed), total))
        self._add_progress.setMaximum(max(1, total))
        self._add_progress.setValue(completed)
        self._add_progress.setFormat(_t(self._import_progress_key, completed=completed, total=total))
        self._add_status_lbl.setText(
            _t(self._import_progress_detail_key, completed=completed, total=total, phase=phase, filename=Path(path).name)
        )

    def _finish_add_progress(self) -> None:
        if self._add_total_entries > 0:
            self._add_progress.setValue(self._add_total_entries)
            self._add_progress.setFormat(
                _t(self._import_progress_key, completed=self._add_total_entries, total=self._add_total_entries)
            )
            self._add_status_lbl.setText(
                _t(self._import_progress_key, completed=self._add_total_entries, total=self._add_total_entries)
            )
        self._add_progress.setVisible(False)
        self._add_status_lbl.setVisible(False)
        self._add_total_entries = 0

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
