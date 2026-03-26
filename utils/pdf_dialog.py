from pathlib import Path

from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QCheckBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPixmap,
    QPushButton,
    QSize,
    QSizePolicy,
    QSplitter,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtPdf import QPdfDocument

from .tag_edit import QuickTagEdit


class AddPdfDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add PDFs to Topics")
        self.setMinimumSize(860, 560)

        self._pdf_paths: list[str] = []
        # path → tag_edit widget
        self._tag_edits: dict[str, QuickTagEdit] = {}
        self._preview_cache: dict[str, QPixmap] = {}   # path → rendered first page
        self._preview_inflight: set[str] = set()        # paths currently being rendered

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)

        # ── Splitter: left (file list) | right (preview) ──────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)

        # Add buttons
        btn_row = QHBoxLayout()
        add_files_btn = QPushButton("Add files…")
        add_files_btn.clicked.connect(self._add_files)
        add_folder_btn = QPushButton("Add folder…")
        add_folder_btn.clicked.connect(self._add_folder)
        btn_row.addWidget(add_files_btn)
        btn_row.addWidget(add_folder_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        # File table — columns: ✕ | File | Tags
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["", "File", "Tags"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        self._table.setColumnWidth(0, 28)
        self._table.setColumnWidth(1, 300)
        self._table.setColumnWidth(2, 180)

        self._table.currentCellChanged.connect(lambda row, *_: self._on_row_changed(row))
        left_layout.addWidget(self._table, stretch=1)

        # Global options (tags + title)
        options_widget = QWidget()
        form = QFormLayout(options_widget)
        form.setContentsMargins(0, 4, 0, 0)

        self._global_tag_edit = QuickTagEdit()
        form.addRow("Tags for all:", self._global_tag_edit)

        self._title_from_filename = QCheckBox("Use file name as title")
        self._title_from_filename.setChecked(True)
        self._title_from_filename.toggled.connect(self._on_title_mode_changed)
        form.addRow("", self._title_from_filename)

        self._title_edit = QLineEdit()
        form.addRow("Title:", self._title_edit)
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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        main_layout.addWidget(buttons)

        self._on_title_mode_changed(True)

    # ── Internal ──────────────────────────────────────────────────────────────

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
        self._add_paths(paths)

    def _add_paths(self, paths: list[str]) -> None:
        for path in paths:
            if path not in self._tag_edits:
                self._add_row(path)

    def _add_row(self, path: str) -> None:
        self._pdf_paths.append(path)

        row_idx = self._table.rowCount()
        self._table.insertRow(row_idx)
        self._table.setRowHeight(row_idx, 28)

        # ✕ remove button
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setFlat(True)
        remove_btn.setToolTip("Remove this file")
        remove_btn.clicked.connect(lambda _=False, p=path: self._remove_row(p))
        self._table.setCellWidget(row_idx, 0, remove_btn)

        # Filename item — stores path in UserRole
        name_item = QTableWidgetItem(Path(path).name)
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        name_item.setToolTip(path)
        self._table.setItem(row_idx, 1, name_item)

        # Per-file tag edit
        tag_edit = QuickTagEdit()
        tag_edit.setPlaceholderText("Tags (optional)")
        self._table.setCellWidget(row_idx, 2, tag_edit)
        self._tag_edits[path] = tag_edit
        self._ensure_preview(path)  # start prefetch immediately

        # Auto-select the first file added
        if len(self._pdf_paths) == 1:
            self._table.setCurrentCell(0, 1)

    def _remove_row(self, path: str) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                self._table.removeRow(row)
                break
        self._tag_edits.pop(path, None)
        self._preview_cache.pop(path, None)
        self._preview_inflight.discard(path)
        if path in self._pdf_paths:
            self._pdf_paths.remove(path)
        if not self._pdf_paths:
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText("Select a file to preview")
            self._preview_name.clear()

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self._table.item(row, 1)
        if item:
            self._show_preview(item.data(Qt.ItemDataRole.UserRole))

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
        """Start a background render for path if not already cached or in-flight."""
        if path in self._preview_cache or path in self._preview_inflight:
            return
        from aqt import mw
        self._preview_inflight.add(path)

        def render():
            doc = QPdfDocument(None)
            try:
                doc.load(path)
                if doc.pageCount() == 0:
                    return None
                page_size = doc.pagePointSize(0)
                render_w = 260
                render_h = int(render_w * page_size.height() / page_size.width()) if page_size.width() > 0 else int(render_w * 1.414)
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
            # Update display if this path is currently selected
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
            self._ensure_preview(path)  # no-op if prefetch already running

    def _accept(self) -> None:
        if not self._pdf_paths:
            self._show_error("Please add at least one PDF file.")
            return
        if not self._title_from_filename.isChecked() and len(self._pdf_paths) > 1:
            self._show_error("For multiple PDFs, enable 'Use file name as title'.")
            return
        if not self._title_from_filename.isChecked() and not self._title_edit.text().strip():
            self._show_error("Please enter a title.")
            return
        self._error_lbl.setVisible(False)
        self.accept()

    def _on_title_mode_changed(self, checked: bool) -> None:
        self._title_edit.setEnabled(not checked)
        self._title_edit.setPlaceholderText(
            "Derived from each file name" if checked else "Card title"
        )

    def _show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

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

    def selected_entries(self) -> list[tuple[str, str, list[str]]]:
        """Return (path, title, tags) for each selected PDF."""
        global_tags = self._global_tag_edit.tags()

        if self._title_from_filename.isChecked():
            paths = self._pdf_paths
        elif self._pdf_paths:
            paths = [self._pdf_paths[0]]
        else:
            return []

        result = []
        for path in paths:
            title = Path(path).stem if self._title_from_filename.isChecked() else self.title_text
            tag_edit = self._tag_edits.get(path)
            file_tags = tag_edit.tags() if tag_edit else []
            merged = global_tags + [t for t in file_tags if t not in global_tags]
            result.append((path, title, merged))
        return result
