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
    QPixmap,
    QProgressBar,
    QPushButton,
    QSize,
    QSizePolicy,
    QSplitter,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QVBoxLayout,
    QWidget,
    QEvent,
    QItemSelectionModel,
)
from PyQt6.QtGui import QColor
from PyQt6.QtPdf import QPdfDocument

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from incremento.frontend.tag_edit import QuickTagEdit


def _resolve_pdf_storage_abspath(
    stored_filename: str,
    *,
    pdf_dir: str,
    storage_abspath_resolver=None,
) -> str:
    if callable(storage_abspath_resolver):
        try:
            resolved = str(storage_abspath_resolver(stored_filename) or "").strip()
        except Exception:
            resolved = ""
        if resolved:
            return resolved

    raw = str(stored_filename or "").strip().replace("\\", "/")
    if not raw:
        return ""
    if raw.startswith("user_files/") and "/pdfs/" in raw:
        raw = raw.split("/pdfs/", 1)[1]
    elif raw.startswith("pdfs/"):
        raw = raw[len("pdfs/") :]

    root = Path(pdf_dir).resolve()
    raw_path = Path(raw)
    candidate = raw_path.resolve() if raw_path.is_absolute() else (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return ""
    return str(candidate)


class AddPdfDialog(QDialog):
    def __init__(
        self,
        addon_dir: str,
        deck_names: list[str] | None = None,
        default_deck: str = "Topics",
        parent=None,
    ):
        super().__init__(parent)
        self._addon_dir = addon_dir
        self.setWindowTitle("Add PDFs")
        self.setMinimumSize(900, 560)

        self._pdf_paths: list[str] = []
        self._tag_edits: dict[str, QuickTagEdit] = {}
        self._row_heights: dict[str, int] = {}
        self._preview_cache: dict[str, QPixmap] = {}
        self._preview_inflight: set[str] = set()
        self._has_text: dict[str, bool | None] = {}  # None=detecting
        self._ocr_checks: dict[str, QCheckBox] = {}
        self._import_checks: dict[str, QCheckBox] = {}
        self._lower_priority_more_important = self._load_priority_direction()
        self._priority_spins: dict[str, QDoubleSpinBox] = {}
        self._folder_pending_paths: list[str] = []
        self._folder_total_paths = 0
        self._last_removed_rows: list[dict] = []
        self._add_total_entries = 0
        self._folder_import_timer = QTimer(self)
        self._folder_import_timer.setSingleShot(True)
        self._folder_import_timer.timeout.connect(self._process_folder_queue)

        # Populated by _process_files; read by addPdfFunction after exec()
        self.created: list[tuple[str, str]] = []  # (path, title)
        self.failed: list[tuple[str, str]] = []

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)

        btn_row = QHBoxLayout()
        self._add_files_btn = QPushButton("Add files…")
        self._add_files_btn.clicked.connect(self._add_files)
        self._add_folder_btn = QPushButton("Add folder…")
        self._add_folder_btn.clicked.connect(self._add_folder)
        self._select_all_btn = QPushButton("Select all")
        self._select_all_btn.clicked.connect(lambda: self._set_visible_import_checks(True))
        self._deselect_all_btn = QPushButton("Deselect all")
        self._deselect_all_btn.clicked.connect(lambda: self._set_visible_import_checks(False))
        self._remove_selected_btn = QPushButton("Remove selected")
        self._remove_selected_btn.setVisible(False)
        self._remove_selected_btn.clicked.connect(self._remove_selected_rows)
        self._undo_remove_btn = QPushButton("Undo remove")
        self._undo_remove_btn.setVisible(False)
        self._undo_remove_btn.clicked.connect(self._undo_remove_rows)
        btn_row.addWidget(self._add_files_btn)
        btn_row.addWidget(self._add_folder_btn)
        btn_row.addWidget(self._select_all_btn)
        btn_row.addWidget(self._deselect_all_btn)
        btn_row.addWidget(self._remove_selected_btn)
        btn_row.addWidget(self._undo_remove_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Filter PDFs by file name…")
        self._search_edit.textChanged.connect(self._apply_table_filter)
        left_layout.addWidget(self._search_edit)

        self._folder_progress = QProgressBar()
        self._folder_progress.setVisible(False)
        self._folder_progress.setTextVisible(True)
        self._folder_progress.setMinimum(0)
        self._folder_progress.setMaximum(1)
        self._folder_progress.setValue(0)
        left_layout.addWidget(self._folder_progress)

        self._folder_status_lbl = QLabel()
        self._folder_status_lbl.setVisible(False)
        self._folder_status_lbl.setStyleSheet("font-size: 11px; color: gray;")
        left_layout.addWidget(self._folder_status_lbl)

        # Table: Import | File | Tags | Priority | OCR
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Import", "File", "Tags", "Priority", "OCR"])
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
        self._table.setColumnWidth(1, 260)
        self._table.setColumnWidth(2, 155)
        self._table.setColumnWidth(3, 120)
        self._table.setColumnWidth(4, 90)
        self._table.verticalHeader().setDefaultSectionSize(42)

        self._table.currentCellChanged.connect(lambda row, *_: self._on_row_changed(row))
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._table, stretch=1)

        options_widget = QWidget()
        form = QFormLayout(options_widget)
        form.setContentsMargins(0, 4, 0, 0)

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

        left_layout.addWidget(options_widget)
        splitter.addWidget(left)

        # ── Right panel (preview) ─────────────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(4)

        preview_header = QLabel("Preview")
        preview_header.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(preview_header)

        self._preview_lbl = QLabel("Select a file to preview")
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setStyleSheet(
            "background: #1e1e1e; border: 1px solid #444; border-radius: 4px; color: #888;"
        )
        self._preview_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._preview_lbl.setMinimumWidth(240)
        right_layout.addWidget(self._preview_lbl, stretch=1)

        self._preview_name = QLabel()
        self._preview_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_name.setWordWrap(True)
        self._preview_name.setStyleSheet("font-size: 11px; color: gray;")
        right_layout.addWidget(self._preview_name)

        splitter.addWidget(right)
        splitter.setSizes([560, 300])

        # ── Error + buttons ───────────────────────────────────────────────────
        self._error_lbl = QLabel()
        self._error_lbl.setStyleSheet("color: red;")
        self._error_lbl.setVisible(False)
        main_layout.addWidget(self._error_lbl)

        self._add_progress = QProgressBar()
        self._add_progress.setVisible(False)
        self._add_progress.setTextVisible(True)
        self._add_progress.setMinimum(0)
        self._add_progress.setMaximum(1)
        self._add_progress.setValue(0)
        main_layout.addWidget(self._add_progress)

        self._add_status_lbl = QLabel()
        self._add_status_lbl.setVisible(False)
        self._add_status_lbl.setStyleSheet("font-size: 11px; color: gray;")
        main_layout.addWidget(self._add_status_lbl)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Add")
        self._cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._buttons.accepted.connect(self._start_add)
        self._buttons.rejected.connect(self.reject)
        main_layout.addWidget(self._buttons)

        self._on_title_mode_changed(True)

    # ── File management ───────────────────────────────────────────────────────

    def _last_dir(self) -> str:
        if self._pdf_paths:
            return str(Path(self._pdf_paths[-1]).parent)
        return ""

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select PDF files", self._last_dir(), "PDF files (*.pdf)"
        )
        self._add_paths([p for p in paths if p])

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder with PDFs", self._last_dir()
        )
        if not folder:
            return
        paths = sorted(str(p) for p in Path(folder).glob("*.pdf"))
        self._start_folder_import(paths)

    def _add_paths(self, paths: list[str]) -> None:
        for path in paths:
            if path not in self._tag_edits:
                self._add_row(path)

    def _start_folder_import(self, paths: list[str]) -> None:
        unique_paths = [path for path in paths if path not in self._tag_edits]
        if not unique_paths:
            self._folder_status_lbl.setVisible(True)
            self._folder_status_lbl.setText("Found 0 new PDFs in folder")
            self._finish_folder_import()
            return

        self._folder_pending_paths = unique_paths
        self._folder_total_paths = len(unique_paths)
        self._folder_progress.setMaximum(self._folder_total_paths)
        self._folder_progress.setValue(0)
        self._folder_progress.setFormat(self._folder_status_text(0))
        self._folder_progress.setVisible(True)
        self._folder_status_lbl.setVisible(True)
        self._folder_status_lbl.setText(self._folder_status_text(0))
        self._add_files_btn.setEnabled(False)
        self._add_folder_btn.setEnabled(False)
        self._folder_import_timer.start(0)

    def _process_folder_queue(self) -> None:
        if not self._folder_pending_paths:
            self._finish_folder_import()
            return

        chunk_size = 8
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

    def _finish_folder_import(self) -> None:
        completed_total = self._folder_total_paths
        self._folder_pending_paths = []
        self._folder_total_paths = 0
        self._folder_import_timer.stop()
        self._folder_progress.setVisible(False)
        self._folder_progress.setValue(0)
        if completed_total > 0:
            self._folder_status_lbl.setVisible(True)
            self._folder_status_lbl.setText(
                f"Found {completed_total} PDFs in folder · loaded into dialog"
            )
        self._add_files_btn.setEnabled(True)
        self._add_folder_btn.setEnabled(True)

    def _add_row(self, path: str, *, row_idx: int | None = None, state: dict | None = None) -> None:
        if row_idx is None or row_idx < 0 or row_idx > self._table.rowCount():
            row_idx = self._table.rowCount()
        self._pdf_paths.insert(row_idx, path)
        self._table.insertRow(row_idx)
        self._table.setRowHeight(row_idx, 42)

        # Column 0: import checkbox
        import_check = QCheckBox("Add")
        import_check.setChecked(True if state is None else bool(state.get("import_enabled", True)))
        import_check.setToolTip("Checked PDFs will be imported when you click Add")
        import_check.setStyleSheet("font-size: 11px; font-weight: 600;")
        self._table.setCellWidget(row_idx, 0, self._wrap_cell_widget(import_check))
        self._import_checks[path] = import_check

        # Column 1: filename
        name_item = QTableWidgetItem(Path(path).name)
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        name_item.setToolTip(path)
        name_item.setTextAlignment(
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        )
        self._table.setItem(row_idx, 1, name_item)

        # Column 2: per-file tags
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

        self._has_text[path] = state.get("has_text") if state else None
        self._set_ocr_cell_from_state(path, row_idx, state)
        self._apply_filter_to_row(row_idx)
        if state and state.get("preview_pixmap") is not None:
            self._preview_cache[path] = state["preview_pixmap"]

        # Start background tasks
        self._ensure_preview(path)
        if self._has_text[path] is None:
            self._check_text_bg(path)

        if len(self._pdf_paths) == 1:
            self._table.setCurrentCell(0, 1)

    def _check_text_bg(self, path: str) -> None:
        """Detect whether PDF has selectable text; update OCR column when done."""
        def check():
            doc = QPdfDocument(None)
            try:
                doc.load(path)
                pages = min(doc.pageCount(), 3)
                for i in range(pages):
                    sel = doc.getAllText(i)
                    if sel.isValid() and sel.text().strip():
                        return True
                return False
            except Exception:
                return True  # assume text on error, don't force OCR
            finally:
                doc.close()

        def on_done(fut) -> None:
            try:
                has_text = fut.result()
            except Exception:
                has_text = True
            self._has_text[path] = has_text
            row = self._find_row(path)
            if row < 0:
                return
            if has_text:
                lbl = QLabel("—")
                lbl.setStyleSheet("font-size: 10px; color: gray;")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setCellWidget(row, 4, self._wrap_cell_widget(lbl))
            else:
                try:
                    from ..backend.deps import has_tesseract, tesseract_instructions
                except Exception:
                    from backend.deps import has_tesseract, tesseract_instructions
                if has_tesseract():
                    cb = QCheckBox("Use OCR")
                    cb.setChecked(True)
                    cb.setToolTip("Run Tesseract OCR to embed a text layer")
                    cb.setStyleSheet("font-size: 10px;")
                    self._table.setCellWidget(row, 4, self._wrap_cell_widget(cb))
                    self._ocr_checks[path] = cb
                else:
                    lbl = QLabel("No OCR ⚠")
                    lbl.setStyleSheet("font-size: 10px; color: #e0a020;")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    lbl.setToolTip(
                        "This PDF has no selectable text and Tesseract is not installed.\n\n"
                        + tesseract_instructions()
                    )
                    self._table.setCellWidget(row, 4, self._wrap_cell_widget(lbl))

        mw.taskman.run_in_background(check, on_done)

    def _find_row(self, path: str) -> int:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                return row
        return -1

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
        self._row_heights.pop(path, None)
        self._preview_inflight.discard(path)
        self._has_text.pop(path, None)
        self._ocr_checks.pop(path, None)
        self._import_checks.pop(path, None)
        self._priority_spins.pop(path, None)
        if path in self._pdf_paths:
            self._pdf_paths.remove(path)
        if not self._pdf_paths:
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText("Select a file to preview")
            self._preview_name.clear()
            self._on_selection_changed()
            return

        if removed_row >= 0:
            replacement_row = self._nearest_visible_row(min(removed_row, self._table.rowCount() - 1))
            if replacement_row >= 0:
                self._table.setCurrentCell(replacement_row, 1)
            else:
                self._preview_lbl.setPixmap(QPixmap())
                self._preview_lbl.setText("No PDFs match the current filter")
                self._preview_name.clear()
        self._on_selection_changed()

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

    # ── Preview ───────────────────────────────────────────────────────────────

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self._table.item(row, 1)
        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            self._show_preview(path)

    def _on_selection_changed(self) -> None:
        selected_count = len(self._selected_visible_rows())
        self._remove_selected_btn.setVisible(selected_count > 1)

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
                return

        replacement_row = self._nearest_visible_row(0)
        if replacement_row >= 0:
            self._table.setCurrentCell(replacement_row, 1)
        else:
            self._table.clearSelection()
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText("No PDFs match the current filter")
            self._preview_name.clear()
        self._on_selection_changed()

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

    def _checked_paths(self) -> list[str]:
        checked_paths: list[str] = []
        for path in self._pdf_paths:
            checkbox = self._import_checks.get(path)
            if checkbox is not None and checkbox.isChecked():
                checked_paths.append(path)
        return checked_paths

    def _ensure_import_checked(self, path: str) -> None:
        checkbox = self._import_checks.get(path)
        if checkbox is not None and not checkbox.isChecked():
            checkbox.setChecked(True)

    def _apply_preview_pixmap(self, pixmap: QPixmap) -> None:
        lbl_w = max(self._preview_lbl.width(), 240)
        lbl_h = max(self._preview_lbl.height(), 300)
        self._preview_lbl.setPixmap(
            pixmap.scaled(
                lbl_w, lbl_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _ensure_preview(self, path: str) -> None:
        if path in self._preview_cache or path in self._preview_inflight:
            return
        self._preview_inflight.add(path)

        def render():
            doc = QPdfDocument(None)
            try:
                doc.load(path)
                if doc.pageCount() == 0:
                    return None
                page_size = doc.pagePointSize(0)
                render_w = 260
                render_h = (
                    int(render_w * page_size.height() / page_size.width())
                    if page_size.width() > 0
                    else int(render_w * 1.414)
                )
                img = doc.render(0, QSize(render_w, render_h))
                return img if not img.isNull() else None
            except Exception:
                return None
            finally:
                doc.close()

        def on_done(fut) -> None:
            self._preview_inflight.discard(path)
            try:
                img = fut.result()
            except Exception:
                return
            if img is None:
                return
            pixmap = QPixmap.fromImage(img)
            self._preview_cache[path] = pixmap
            current_row = self._table.currentRow()
            if current_row >= 0:
                item = self._table.item(current_row, 1)
                if item and item.data(Qt.ItemDataRole.UserRole) == path:
                    self._apply_preview_pixmap(pixmap)
                    self._preview_name.setText(Path(path).name)

        mw.taskman.run_in_background(render, on_done)

    def _show_preview(self, path: str) -> None:
        self._preview_name.setText(Path(path).name)
        if path in self._preview_cache:
            self._apply_preview_pixmap(self._preview_cache[path])
        else:
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText("Loading…")
            self._ensure_preview(path)

    # ── Adding files ──────────────────────────────────────────────────────────

    def _start_add(self) -> None:
        if not self._pdf_paths:
            self._show_error("Please add at least one PDF file.")
            return
        checked_paths = self._checked_paths()
        if not checked_paths:
            self._show_error("Please check at least one PDF to import.")
            return
        if not self._title_from_filename.isChecked() and len(checked_paths) > 1:
            self._show_error("For multiple PDFs, enable 'Use file name as title'.")
            return
        if not self._title_from_filename.isChecked() and not self._title_edit.text().strip():
            self._show_error("Please enter a title.")
            return
        self._error_lbl.setVisible(False)

        global_tags = self._global_tag_edit.tags()
        entries = []
        for path in checked_paths:
            title = (
                Path(path).stem
                if self._title_from_filename.isChecked()
                else self._title_edit.text().strip()
            )
            tag_edit = self._tag_edits.get(path)
            file_tags = tag_edit.tags() if tag_edit else []
            merged = global_tags + [t for t in file_tags if t not in global_tags]
            ocr_check = self._ocr_checks.get(path)
            do_ocr = ocr_check is not None and ocr_check.isChecked()
            priority = self._priority_for_path(path)
            entries.append((path, title, merged, do_ocr, priority))

        self._start_add_progress(len(entries))

        # Lock the UI during adding
        self._ok_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._add_files_btn.setEnabled(False)
        self._add_folder_btn.setEnabled(False)

        self._process_files(entries, 0)

    def _set_row_status(self, path: str, text: str, color: str = "") -> None:
        row = self._find_row(path)
        if row < 0:
            return
        self._table.setRowHeight(row, self._row_heights.get(path, 42))
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style = "font-size: 10px;"
        if color:
            style += f" color: {color};"
        lbl.setStyleSheet(style)
        self._table.setCellWidget(row, 4, self._wrap_cell_widget(lbl))

    def _process_files(self, entries: list, idx: int) -> None:
        if idx >= len(entries):
            self._finish_add_progress()
            self.accept()
            return

        path, title, tags, do_ocr, priority = entries[idx]
        deck = self._deck_combo.currentText()
        self._update_add_progress(idx, len(entries), path, phase="Starting")

        try:
            from ..backend import pdf_manager as _pdf_manager
            from ..backend.db import replace_pdf_text_index
            from ..backend.priority_manager import set_priority
            from ..backend import paths as _paths
            from ..backend.paths import get_active_profile as _active_profile
        except Exception:
            import pdf_manager as _pdf_manager
            from db import replace_pdf_text_index
            from priority_manager import set_priority
            import paths as _paths
            from paths import get_active_profile as _active_profile

        self._set_row_status(path, "OCR…" if do_ocr else "Adding…")

        try:
            cid = _pdf_manager.add_pdf_card(
                self._addon_dir,
                mw.col,
                path,
                title,
                deck_name=deck,
                tags=tags,
            )
            set_priority(self._addon_dir, _active_profile(), cid, priority)
        except Exception as e:
            self.failed.append((path, str(e)))
            self._set_row_status(path, "✗", color="red")
            self._update_add_progress(idx + 1, len(entries), path, phase="Failed")
            self._process_files(entries, idx + 1)
            return

        if not do_ocr:
            self.created.append((path, title))
            self._set_row_status(path, "✓", color="#4caf50")
            self._update_add_progress(idx + 1, len(entries), path, phase="Done")
            self._process_files(entries, idx + 1)
            return

        # OCR path: copy is already in pdf_dir; OCR it in background, then re-index
        note = mw.col.get_note(mw.col.get_card(cid).nid)
        dest_path = _resolve_pdf_storage_abspath(
            note["PDF_Filename"],
            pdf_dir=str(_paths.get_pdf_dir(self._addon_dir, _active_profile())),
            storage_abspath_resolver=getattr(_pdf_manager, "pdf_storage_abspath", None),
        )

        def _progress(current, total, _path=path):
            mw.taskman.run_on_main(
                lambda c=current, t=total, p=_path: (
                    self._set_row_status(p, f"OCR {c}/{t}"),
                    self._update_add_progress(
                        idx,
                        len(entries),
                        p,
                        phase=f"OCR {c}/{t}",
                    ),
                )
            )

        def ocr_task():
            success = _pdf_manager.ocr_pdf_in_place(dest_path, progress_cb=_progress)
            if success:
                return _pdf_manager.extract_pdf_pages_text(dest_path)
            return []

        def ocr_done(fut) -> None:
            ocr_ok = False
            try:
                page_texts = fut.result()
                if page_texts:
                    replace_pdf_text_index(self._addon_dir, _active_profile(), cid, page_texts)
                    ocr_ok = True
            except Exception:
                pass
            self.created.append((path, title))
            status = "✓" if ocr_ok else "✓ (no text)"
            color = "#4caf50" if ocr_ok else "#ff9800"
            self._set_row_status(path, status, color=color)
            self._update_add_progress(idx + 1, len(entries), path, phase="Done")
            self._process_files(entries, idx + 1)

        mw.taskman.run_in_background(ocr_task, ocr_done)

    # ── Helpers ───────────────────────────────────────────────────────────────

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

    def _snapshot_row(self, path: str, row: int) -> dict:
        tag_edit = self._tag_edits.get(path)
        ocr_check = self._ocr_checks.get(path)
        return {
            "row": row,
            "path": path,
            "import_enabled": bool(self._import_checks.get(path).isChecked()) if self._import_checks.get(path) is not None else True,
            "tags": tag_edit.tags() if tag_edit else [],
            "priority": self._priority_for_path(path),
            "has_text": self._has_text.get(path),
            "ocr_enabled": bool(ocr_check.isChecked()) if ocr_check is not None else None,
            "preview_pixmap": self._preview_cache.get(path),
        }

    def _set_ocr_cell_from_state(self, path: str, row: int, state: dict | None) -> None:
        if not state or state.get("has_text") is None:
            lbl = QLabel("Detecting…")
            lbl.setStyleSheet("font-size: 10px; color: gray;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, 4, self._wrap_cell_widget(lbl))
            return

        has_text = bool(state.get("has_text"))
        if has_text:
            lbl = QLabel("—")
            lbl.setStyleSheet("font-size: 10px; color: gray;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setCellWidget(row, 4, self._wrap_cell_widget(lbl))
            return

        try:
            from ..backend.deps import has_tesseract, tesseract_instructions
        except Exception:
            from backend.deps import has_tesseract, tesseract_instructions
        if has_tesseract():
            cb = QCheckBox("Use OCR")
            cb.setChecked(True if state.get("ocr_enabled") is None else bool(state.get("ocr_enabled")))
            cb.setToolTip("Run Tesseract OCR to embed a text layer")
            cb.setStyleSheet("font-size: 10px;")
            self._table.setCellWidget(row, 4, self._wrap_cell_widget(cb))
            self._ocr_checks[path] = cb
        else:
            lbl = QLabel("No OCR ⚠")
            lbl.setStyleSheet("font-size: 10px; color: #e0a020;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setToolTip(
                "This PDF has no selectable text and Tesseract is not installed.\n\n"
                + tesseract_instructions()
            )
            self._table.setCellWidget(row, 4, self._wrap_cell_widget(lbl))

    def _build_priority_spin(self) -> QDoubleSpinBox:
        spin = _FreshStartPrioritySpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.1)
        spin.setValue(50.0)
        spin.setFixedWidth(94)
        important_end = "0" if self._lower_priority_more_important else "100"
        spin.setToolTip(
            f"Priority for this PDF. {important_end} is highest importance, 50 is default."
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
            from priority_manager import configured_priority_lower_is_more_important
        return bool(configured_priority_lower_is_more_important())

    def _show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    def _start_add_progress(self, total_entries: int) -> None:
        self._add_total_entries = max(0, int(total_entries))
        self._add_progress.setMaximum(max(1, self._add_total_entries))
        self._add_progress.setValue(0)
        self._add_progress.setFormat(
            f"Adding PDFs… 0 / {self._add_total_entries}"
            if self._add_total_entries
            else "Adding PDFs…"
        )
        self._add_progress.setVisible(self._add_total_entries > 0)
        self._add_status_lbl.setVisible(self._add_total_entries > 0)
        if self._add_total_entries > 0:
            self._add_status_lbl.setText(f"Adding PDFs… 0 / {self._add_total_entries}")

    def _update_add_progress(self, completed: int, total: int, path: str, *, phase: str) -> None:
        total = max(0, int(total))
        completed = max(0, min(int(completed), total))
        self._add_progress.setMaximum(max(1, total))
        self._add_progress.setValue(completed)
        self._add_progress.setFormat(f"Adding PDFs… {completed} / {total}")
        self._add_status_lbl.setText(
            f"Adding PDFs… {completed} / {total} · {phase}: {Path(path).name}"
        )

    def _finish_add_progress(self) -> None:
        if self._add_total_entries > 0:
            self._add_progress.setValue(self._add_total_entries)
            self._add_progress.setFormat(
                f"Adding PDFs… {self._add_total_entries} / {self._add_total_entries}"
            )
            self._add_status_lbl.setText(
                f"Adding PDFs… {self._add_total_entries} / {self._add_total_entries}"
            )
        self._add_progress.setVisible(False)
        self._add_status_lbl.setVisible(False)
        self._add_total_entries = 0

    def _folder_status_text(self, completed: int) -> str:
        remaining = max(0, self._folder_total_paths - completed)
        return (
            f"Found {self._folder_total_paths} PDFs in folder · "
            f"{remaining} remaining · adding… {completed} / {self._folder_total_paths}"
        )

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Delete:
            if self._table.hasFocus() or any(index.isValid() for index in self._table.selectedIndexes()):
                self._remove_selected_rows()
                event.accept()
                return
        super().keyPressEvent(event)

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def pdf_path(self) -> str:
        return self._pdf_paths[0] if self._pdf_paths else ""

    @property
    def pdf_paths(self) -> list[str]:
        return list(self._pdf_paths)

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
        if not self._pdf_paths:
            return 50.0
        row = self._table.currentRow()
        if row >= 0:
            item = self._table.item(row, 1)
            if item:
                path = item.data(Qt.ItemDataRole.UserRole)
                if path:
                    return self._priority_for_path(path)
        return self._priority_for_path(self._pdf_paths[0])

    def selected_entries(self) -> list[tuple[str, str, list[str]]]:
        """Return (path, title, tags) — kept for API compatibility."""
        global_tags = self._global_tag_edit.tags()
        checked_paths = self._checked_paths()
        paths = checked_paths if self._title_from_filename.isChecked() else checked_paths[:1]
        result = []
        for path in paths:
            title = Path(path).stem if self._title_from_filename.isChecked() else self.title_text
            tag_edit = self._tag_edits.get(path)
            file_tags = tag_edit.tags() if tag_edit else []
            merged = global_tags + [t for t in file_tags if t not in global_tags]
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
