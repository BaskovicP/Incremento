from __future__ import annotations

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
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
)

try:
    from .priority_dialog import (
        SLIDER_MAX,
        _priority_mid,
        _priority_to_slider,
        _slider_to_priority,
    )
    from .tag_edit import QuickTagEdit
except ImportError:
    from incremento.frontend.priority_dialog import (  # type: ignore
        SLIDER_MAX,
        _priority_mid,
        _priority_to_slider,
        _slider_to_priority,
    )
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
        self.setMinimumSize(760, 480)

        self._epub_paths: list[str] = []
        self._priority_building = False
        self._lower_priority_more_important = self._load_priority_direction()
        self.created: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        btn_row = QHBoxLayout()
        self._add_files_btn = QPushButton("Add files…")
        self._add_folder_btn = QPushButton("Add folder…")
        self._add_files_btn.clicked.connect(self._add_files)
        self._add_folder_btn.clicked.connect(self._add_folder)
        btn_row.addWidget(self._add_files_btn)
        btn_row.addWidget(self._add_folder_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["", "File", "Status"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setColumnWidth(0, 32)
        self._table.setColumnWidth(1, 520)
        self._table.setColumnWidth(2, 120)
        layout.addWidget(self._table, stretch=1)

        options = QWidget()
        form = QFormLayout(options)
        form.setContentsMargins(0, 0, 0, 0)

        self._global_tag_edit = QuickTagEdit(compact=True)
        form.addRow("Tags:", self._global_tag_edit)

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

        priority_wrap = QWidget()
        priority_layout = QVBoxLayout(priority_wrap)
        priority_layout.setContentsMargins(0, 0, 0, 0)
        priority_layout.setSpacing(4)

        self._priority_slider = QSlider(Qt.Orientation.Horizontal)
        self._priority_slider.setRange(0, SLIDER_MAX)
        priority_layout.addWidget(self._priority_slider)

        priority_bottom = QHBoxLayout()
        self._priority_spin = QLabel()
        self._priority_spin_value = QLineEdit()
        self._priority_spin_value.setFixedWidth(96)
        priority_bottom.addWidget(self._priority_spin_value)
        priority_bottom.addStretch()
        important_end = "0" if self._lower_priority_more_important else "100"
        hint = QLabel(f"{important_end} = highest importance, 50 = default")
        hint.setStyleSheet("font-size: 11px; color: gray;")
        priority_bottom.addWidget(hint)
        priority_layout.addLayout(priority_bottom)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel("0"))
        scale_row.addStretch()
        scale_row.addWidget(QLabel(str(int(_priority_mid(self._lower_priority_more_important)))))
        scale_row.addStretch()
        scale_row.addWidget(QLabel("100"))
        priority_layout.addLayout(scale_row)
        form.addRow("Priority:", priority_wrap)

        layout.addWidget(options)

        self._error_lbl = QLabel()
        self._error_lbl.setStyleSheet("color: red;")
        self._error_lbl.setVisible(False)
        layout.addWidget(self._error_lbl)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_btn = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_btn.setText("Add")
        self._buttons.accepted.connect(self._start_add)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._priority_slider.valueChanged.connect(self._on_priority_slider_changed)
        self._priority_spin_value.editingFinished.connect(self._on_priority_text_changed)
        self._set_priority_value(50.0)
        self._on_title_mode_changed(True)

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
        self._append_paths(paths)

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose folder", self._last_dir())
        if not folder:
            return
        found: list[str] = []
        for root, _, filenames in os.walk(folder):
            for name in filenames:
                if name.lower().endswith(".epub"):
                    found.append(os.path.join(root, name))
        self._append_paths(sorted(found))

    def _append_paths(self, paths: list[str]) -> None:
        added = False
        for path in paths:
            if not path or path in self._epub_paths:
                continue
            self._epub_paths.append(path)
            row = self._table.rowCount()
            self._table.insertRow(row)
            remove_item = QTableWidgetItem("✕")
            remove_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, remove_item)
            self._table.setItem(row, 1, QTableWidgetItem(path))
            self._table.setItem(row, 2, QTableWidgetItem(""))
            added = True
        if added:
            self._error_lbl.setVisible(False)

    def _set_row_status(self, path: str, text: str) -> None:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            if item and item.text() == path:
                self._table.setItem(row, 2, QTableWidgetItem(text))
                return

    def _title_for_path(self, path: str) -> str:
        if self._title_from_filename.isChecked():
            return Path(path).stem
        return self._title_edit.text().strip()

    def _current_priority(self) -> float:
        try:
            return round(float(self._priority_spin_value.text().strip() or "50"), 4)
        except Exception:
            return 50.0

    def _start_add(self) -> None:
        if not self._epub_paths:
            self._show_error("Choose at least one EPUB file.")
            return
        if not self._title_from_filename.isChecked() and not self._title_edit.text().strip():
            self._show_error("Please enter a title or enable file-name titles.")
            return

        try:
            from ..backend.epub_manager import add_epub_card
            from ..backend.priority_manager import set_priority
        except Exception:
            from epub_manager import add_epub_card  # type: ignore
            from priority_manager import set_priority  # type: ignore

        deck = self._deck_combo.currentText()
        tags = self._global_tag_edit.tags()
        priority = self._current_priority()

        self._ok_btn.setEnabled(False)
        self._add_files_btn.setEnabled(False)
        self._add_folder_btn.setEnabled(False)

        for path in list(self._epub_paths):
            title = self._title_for_path(path)
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
                set_priority(self._addon_dir, cid, priority)
                self.created.append((path, title))
                self._set_row_status(path, "✓")
            except Exception as exc:
                self.failed.append((path, str(exc)))
                self._set_row_status(path, "✗")

        self.accept()

    def _on_title_mode_changed(self, checked: bool) -> None:
        self._title_edit.setEnabled(not checked)
        self._title_edit.setPlaceholderText(
            "Derived from each file name" if checked else "Card title"
        )

    def _load_priority_direction(self) -> bool:
        try:
            from ..backend.priority_manager import configured_priority_lower_is_more_important
        except Exception:
            from priority_manager import configured_priority_lower_is_more_important  # type: ignore
        return bool(configured_priority_lower_is_more_important())

    def _set_priority_value(self, priority: float) -> None:
        self._priority_building = True
        clamped = max(0.0, min(100.0, round(float(priority), 4)))
        self._priority_spin_value.setText(f"{clamped:.4f}".rstrip("0").rstrip(".") or "0")
        self._priority_slider.setValue(
            _priority_to_slider(clamped, self._lower_priority_more_important)
        )
        self._priority_building = False

    def _on_priority_slider_changed(self, slider_value: int) -> None:
        if self._priority_building:
            return
        self._priority_building = True
        value = _slider_to_priority(slider_value, self._lower_priority_more_important)
        self._priority_spin_value.setText(f"{value:.4f}".rstrip("0").rstrip(".") or "0")
        self._priority_building = False

    def _on_priority_text_changed(self) -> None:
        if self._priority_building:
            return
        try:
            value = float(self._priority_spin_value.text().strip() or "50")
        except Exception:
            value = 50.0
        self._set_priority_value(value)

    def _show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()
