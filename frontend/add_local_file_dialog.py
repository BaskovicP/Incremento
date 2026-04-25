import os

from aqt.qt import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from incremento.frontend.tag_edit import QuickTagEdit

try:
    from ..backend.local_file_manager import (
        LOCAL_FILE_MODE_MANAGED_COPY,
        LOCAL_FILE_MODE_REFERENCE,
    )
except ImportError:
    from backend.local_file_manager import (  # type: ignore
        LOCAL_FILE_MODE_MANAGED_COPY,
        LOCAL_FILE_MODE_REFERENCE,
    )


class AddLocalFileDialog(QDialog):
    def __init__(self, deck_names: list[str], default_deck: str = "Topics", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Local File")
        self.setMinimumWidth(560)
        self.resize(660, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(QLabel("File:"))
        file_row = QHBoxLayout()
        self._file_edit = QLineEdit()
        self._file_edit.setReadOnly(True)
        self._file_edit.setPlaceholderText("Choose a local file…")
        file_row.addWidget(self._file_edit, 1)
        self._browse_btn = QPushButton("Browse…")
        file_row.addWidget(self._browse_btn)
        layout.addLayout(file_row)

        layout.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Card title")
        layout.addWidget(self._title_edit)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Storage mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Reference original file", LOCAL_FILE_MODE_REFERENCE)
        self._mode_combo.addItem("Copy into Incremento", LOCAL_FILE_MODE_MANAGED_COPY)
        mode_row.addWidget(self._mode_combo, 1)
        layout.addLayout(mode_row)

        self._mode_hint = QLabel("")
        self._mode_hint.setWordWrap(True)
        self._mode_hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        layout.addWidget(self._mode_hint)

        self._tag_edit = QuickTagEdit()
        layout.addWidget(self._tag_edit)

        deck_row = QHBoxLayout()
        deck_row.addWidget(QLabel("Deck:"))
        self._deck_combo = QComboBox()
        for name in deck_names:
            self._deck_combo.addItem(name)
        if default_deck:
            idx = self._deck_combo.findText(default_deck)
            if idx >= 0:
                self._deck_combo.setCurrentIndex(idx)
        deck_row.addWidget(self._deck_combo, 1)
        layout.addLayout(deck_row)

        layout.addWidget(QLabel("Note / instructions (optional):"))
        self._note_edit = QTextEdit()
        self._note_edit.setAcceptRichText(False)
        self._note_edit.setPlaceholderText("Describe what to do with this file when the card appears…")
        layout.addWidget(self._note_edit, 1)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Add Local File Card")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._browse_btn.clicked.connect(self._browse_file)
        self._mode_combo.currentIndexChanged.connect(self._refresh_mode_hint)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        self._refresh_mode_hint()

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose local file", "", "All files (*)")
        if not path:
            return
        self._file_edit.setText(path)
        if not self.title:
            self._title_edit.setText(os.path.splitext(os.path.basename(path))[0])

    def _refresh_mode_hint(self) -> None:
        if self.storage_mode == LOCAL_FILE_MODE_MANAGED_COPY:
            self._mode_hint.setText(
                "Copies the file into Incremento's per-profile storage so the card keeps working even if the original is moved."
            )
            return
        self._mode_hint.setText(
            "Stores the current path on your computer. If the file is moved or deleted later, the card will need relinking."
        )

    @property
    def source_path(self) -> str:
        return self._file_edit.text().strip()

    @property
    def title(self) -> str:
        return self._title_edit.text().strip()

    @property
    def storage_mode(self) -> str:
        return str(self._mode_combo.currentData() or LOCAL_FILE_MODE_REFERENCE)

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()

    @property
    def tags(self) -> list[str]:
        return self._tag_edit.tags()

    @property
    def note_text(self) -> str:
        return self._note_edit.toPlainText().strip()
