from pathlib import Path

from aqt.qt import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, Qt,
)


class AddPdfDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add PDF to Topics")
        self.setMinimumWidth(480)

        self._path_edit  = QLineEdit()
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("No file selected")

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)

        path_row = QHBoxLayout()
        path_row.addWidget(self._path_edit)
        path_row.addWidget(browse_btn)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Card title")

        self._error_lbl = QLabel()
        self._error_lbl.setStyleSheet("color: red;")
        self._error_lbl.setVisible(False)

        form = QFormLayout()
        form.addRow("PDF file:", path_row)
        form.addRow("Title:",    self._title_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._error_lbl)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select PDF", "", "PDF files (*.pdf)"
        )
        if not path:
            return
        self._path_edit.setText(path)
        if not self._title_edit.text().strip():
            self._title_edit.setText(Path(path).stem)

    def _accept(self) -> None:
        if not self._path_edit.text().strip():
            self._show_error("Please select a PDF file.")
            return
        if not self._title_edit.text().strip():
            self._show_error("Please enter a title.")
            return
        self._error_lbl.setVisible(False)
        self.accept()

    def _show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)
        self._error_lbl.setVisible(True)

    # ------------------------------------------------------------------

    @property
    def pdf_path(self) -> str:
        return self._path_edit.text().strip()

    @property
    def title_text(self) -> str:
        return self._title_edit.text().strip()
