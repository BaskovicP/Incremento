import os
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
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

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from tag_edit import QuickTagEdit


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
        self._preview_cache: dict[str, QPixmap] = {}
        self._preview_inflight: set[str] = set()
        self._has_text: dict[str, bool | None] = {}  # None=detecting
        self._ocr_checks: dict[str, QCheckBox] = {}

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
        btn_row.addWidget(self._add_files_btn)
        btn_row.addWidget(self._add_folder_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        # Table: ✕ | File | Tags | OCR
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["", "File", "Tags", "OCR"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setShowGrid(False)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setStretchLastSection(False)
        self._table.setColumnWidth(0, 28)
        self._table.setColumnWidth(1, 260)
        self._table.setColumnWidth(2, 155)
        self._table.setColumnWidth(3, 90)

        self._table.currentCellChanged.connect(lambda row, *_: self._on_row_changed(row))
        left_layout.addWidget(self._table, stretch=1)

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

        # Column 0: ✕ remove
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(22, 22)
        remove_btn.setFlat(True)
        remove_btn.setToolTip("Remove this file")
        remove_btn.clicked.connect(lambda _=False, p=path: self._remove_row(p))
        self._table.setCellWidget(row_idx, 0, remove_btn)

        # Column 1: filename
        name_item = QTableWidgetItem(Path(path).name)
        name_item.setData(Qt.ItemDataRole.UserRole, path)
        name_item.setToolTip(path)
        self._table.setItem(row_idx, 1, name_item)

        # Column 2: per-file tags
        tag_edit = QuickTagEdit()
        tag_edit.setPlaceholderText("Tags (optional)")
        self._table.setCellWidget(row_idx, 2, tag_edit)
        self._tag_edits[path] = tag_edit

        # Column 3: OCR detection placeholder
        lbl = QLabel("Detecting…")
        lbl.setStyleSheet("font-size: 10px; color: gray;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setCellWidget(row_idx, 3, lbl)
        self._has_text[path] = None

        # Start background tasks
        self._ensure_preview(path)
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
                self._table.setCellWidget(row, 3, lbl)
            else:
                from .deps import has_tesseract, tesseract_instructions
                if has_tesseract():
                    cb = QCheckBox("Use OCR")
                    cb.setChecked(True)
                    cb.setToolTip("Run Tesseract OCR to embed a text layer")
                    cb.setStyleSheet("font-size: 10px;")
                    self._table.setCellWidget(row, 3, cb)
                    self._ocr_checks[path] = cb
                else:
                    lbl = QLabel("No OCR ⚠")
                    lbl.setStyleSheet("font-size: 10px; color: #e0a020;")
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    lbl.setToolTip(
                        "This PDF has no selectable text and Tesseract is not installed.\n\n"
                        + tesseract_instructions()
                    )
                    self._table.setCellWidget(row, 3, lbl)

        mw.taskman.run_in_background(check, on_done)

    def _find_row(self, path: str) -> int:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                return row
        return -1

    def _remove_row(self, path: str) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == path:
                self._table.removeRow(row)
                break
        self._tag_edits.pop(path, None)
        self._preview_cache.pop(path, None)
        self._preview_inflight.discard(path)
        self._has_text.pop(path, None)
        self._ocr_checks.pop(path, None)
        if path in self._pdf_paths:
            self._pdf_paths.remove(path)
        if not self._pdf_paths:
            self._preview_lbl.setPixmap(QPixmap())
            self._preview_lbl.setText("Select a file to preview")
            self._preview_name.clear()

    # ── Preview ───────────────────────────────────────────────────────────────

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
        if not self._title_from_filename.isChecked() and len(self._pdf_paths) > 1:
            self._show_error("For multiple PDFs, enable 'Use file name as title'.")
            return
        if not self._title_from_filename.isChecked() and not self._title_edit.text().strip():
            self._show_error("Please enter a title.")
            return
        self._error_lbl.setVisible(False)

        global_tags = self._global_tag_edit.tags()
        entries = []
        for path in self._pdf_paths:
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
            entries.append((path, title, merged, do_ocr))

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
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style = "font-size: 10px;"
        if color:
            style += f" color: {color};"
        lbl.setStyleSheet(style)
        self._table.setCellWidget(row, 3, lbl)

    def _process_files(self, entries: list, idx: int) -> None:
        if idx >= len(entries):
            self.accept()
            return

        path, title, tags, do_ocr = entries[idx]
        deck = self._deck_combo.currentText()

        try:
            from .pdf_manager import add_pdf_card, ocr_pdf_in_place, extract_pdf_pages_text, get_pdf_dir
            from .db import replace_pdf_text_index
        except ImportError:
            from pdf_manager import add_pdf_card, ocr_pdf_in_place, extract_pdf_pages_text, get_pdf_dir
            from db import replace_pdf_text_index

        self._set_row_status(path, "OCR…" if do_ocr else "Adding…")

        try:
            cid = add_pdf_card(self._addon_dir, mw.col, path, title, deck_name=deck, tags=tags)
        except Exception as e:
            self.failed.append((path, str(e)))
            self._set_row_status(path, "✗", color="red")
            self._process_files(entries, idx + 1)
            return

        if not do_ocr:
            self.created.append((path, title))
            self._set_row_status(path, "✓", color="#4caf50")
            self._process_files(entries, idx + 1)
            return

        # OCR path: copy is already in pdf_dir; OCR it in background, then re-index
        note = mw.col.get_note(mw.col.get_card(cid).nid)
        dest_path = os.path.join(get_pdf_dir(), note["PDF_Filename"])

        def _progress(current, total, _path=path):
            mw.taskman.run_on_main(
                lambda c=current, t=total: self._set_row_status(_path, f"OCR {c}/{t}")
            )

        def ocr_task():
            success = ocr_pdf_in_place(dest_path, progress_cb=_progress)
            if success:
                return extract_pdf_pages_text(dest_path)
            return []

        def ocr_done(fut) -> None:
            ocr_ok = False
            try:
                page_texts = fut.result()
                if page_texts:
                    replace_pdf_text_index(self._addon_dir, cid, page_texts)
                    ocr_ok = True
            except Exception:
                pass
            self.created.append((path, title))
            status = "✓" if ocr_ok else "✓ (no text)"
            color = "#4caf50" if ocr_ok else "#ff9800"
            self._set_row_status(path, status, color=color)
            self._process_files(entries, idx + 1)

        mw.taskman.run_in_background(ocr_task, ocr_done)

    # ── Helpers ───────────────────────────────────────────────────────────────

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

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()

    def selected_entries(self) -> list[tuple[str, str, list[str]]]:
        """Return (path, title, tags) — kept for API compatibility."""
        global_tags = self._global_tag_edit.tags()
        paths = self._pdf_paths if self._title_from_filename.isChecked() else self._pdf_paths[:1]
        result = []
        for path in paths:
            title = Path(path).stem if self._title_from_filename.isChecked() else self.title_text
            tag_edit = self._tag_edits.get(path)
            file_tags = tag_edit.tags() if tag_edit else []
            merged = global_tags + [t for t in file_tags if t not in global_tags]
            result.append((path, title, merged))
        return result
