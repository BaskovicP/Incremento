from aqt.qt import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTextEdit,
)

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from incremento.frontend.tag_edit import QuickTagEdit


class AddWritingDialog(QDialog):
    """Dialog to create an Incremento writing card backed by a markdown file."""

    def __init__(self, deck_names: list[str], default_deck: str = "Topics", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Writing")
        self.setMinimumWidth(560)
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Writing topic title")
        layout.addWidget(self._title_edit)

        layout.addWidget(QLabel("Filename (optional):"))
        self._filename_edit = QLineEdit()
        self._filename_edit.setPlaceholderText("my-note.md  (stored under user_files/writing)")
        layout.addWidget(self._filename_edit)

        self._tag_edit = QuickTagEdit()
        layout.addWidget(self._tag_edit)

        deck_row = QHBoxLayout()
        deck_row.addWidget(QLabel("Deck:"))
        self._deck_combo = QComboBox()
        for d in deck_names:
            self._deck_combo.addItem(d)
        if default_deck:
            idx = self._deck_combo.findText(default_deck)
            if idx >= 0:
                self._deck_combo.setCurrentIndex(idx)
        deck_row.addWidget(self._deck_combo, 1)
        layout.addLayout(deck_row)

        layout.addWidget(QLabel("Initial markdown:"))
        self._markdown_edit = QTextEdit()
        self._markdown_edit.setAcceptRichText(False)
        self._markdown_edit.setPlaceholderText(
            "# Heading\n\nWrite initial content here…"
        )
        layout.addWidget(self._markdown_edit, 1)

        hint = QLabel(
            "The markdown file is autosaved while typing when this card is reviewed."
        )
        hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Add Writing Card")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    @property
    def title(self) -> str:
        return self._title_edit.text().strip()

    @property
    def filename(self) -> str:
        return self._filename_edit.text().strip()

    @property
    def deck_name(self) -> str:
        return self._deck_combo.currentText()

    @property
    def tags(self) -> list[str]:
        return self._tag_edit.tags()

    @property
    def initial_markdown(self) -> str:
        return self._markdown_edit.toPlainText()
