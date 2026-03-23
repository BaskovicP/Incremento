from pathlib import Path

from aqt.qt import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class AddPdfDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add PDF to Topics")
        self.setMinimumWidth(480)

        self._pdf_paths: list[str] = []

        self._path_edit = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("No files selected")

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)

        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit)
        path_row.addWidget(browse_btn)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Card title")

        self._title_from_filename = QCheckBox("Use file name as title")
        self._title_from_filename.setChecked(True)
        self._title_from_filename.toggled.connect(self._on_title_mode_changed)

        self._add_tag_checkbox = QCheckBox("Add tag to imported cards")
        self._add_tag_checkbox.setChecked(False)
        self._add_tag_checkbox.toggled.connect(self._on_tag_mode_changed)

        self._tag_edit = QLineEdit()
        self._tag_edit.setPlaceholderText("e.g. incremento::pdf")

        self._error_lbl = QLabel()
        self._error_lbl.setStyleSheet("color: red;")
        self._error_lbl.setVisible(False)

        form = QFormLayout()
        form.addRow("PDF files:", path_row)
        form.addRow("", self._title_from_filename)
        form.addRow("Title:", self._title_edit)
        form.addRow("", self._add_tag_checkbox)
        form.addRow("Tag:", self._tag_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_lbl)
        layout.addWidget(buttons)

        self._on_title_mode_changed(self._title_from_filename.isChecked())
        self._on_tag_mode_changed(self._add_tag_checkbox.isChecked())

    # ------------------------------------------------------------------

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select PDF files", "", "PDF files (*.pdf)"
        )
        if not paths:
            return
        self._pdf_paths = [p for p in paths if p]
        if len(self._pdf_paths) == 1:
            self._path_edit.setText(self._pdf_paths[0])
        else:
            self._path_edit.setText(f"{len(self._pdf_paths)} files selected")

        if (
            len(self._pdf_paths) == 1
            and not self._title_from_filename.isChecked()
            and not self._title_edit.text().strip()
        ):
            self._title_edit.setText(Path(self._pdf_paths[0]).stem)

    def _accept(self) -> None:
        if not self._pdf_paths:
            self._show_error("Please select at least one PDF file.")
            return
        if (not self._title_from_filename.isChecked()) and len(self._pdf_paths) > 1:
            self._show_error("For multiple PDFs, enable 'Use file name as title'.")
            return
        if (not self._title_from_filename.isChecked()) and (
            not self._title_edit.text().strip()
        ):
            self._show_error("Please enter a title.")
            return
        if self._add_tag_checkbox.isChecked() and (not self._tag_edit.text().strip()):
            self._show_error("Please enter a tag, or disable tag appending.")
            return
        self._error_lbl.setVisible(False)
        self.accept()

    def _on_title_mode_changed(self, checked: bool) -> None:
        self._title_edit.setEnabled(not checked)
        if checked:
            self._title_edit.setPlaceholderText("Derived from each file name")
        else:
            self._title_edit.setPlaceholderText("Card title")

    def _on_tag_mode_changed(self, checked: bool) -> None:
        self._tag_edit.setEnabled(checked)

    def _show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    # ------------------------------------------------------------------

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
    def tags_to_apply(self) -> list[str]:
        if not self._add_tag_checkbox.isChecked():
            return []
        raw = self._tag_edit.text().strip()
        if not raw:
            return []
        tags = [t.lstrip("#") for t in raw.split() if t.strip()]
        return [t for t in tags if t]

    def selected_entries(self) -> list[tuple[str, str]]:
        if self._title_from_filename.isChecked():
            return [(path, Path(path).stem) for path in self._pdf_paths]
        if not self._pdf_paths:
            return []
        return [(self._pdf_paths[0], self.title_text)]
