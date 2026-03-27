from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
)

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from tag_edit import QuickTagEdit


class AddWebDialog(QDialog):
    """Dialog to add a new web page as an Incremento Web card."""

    def __init__(self, deck_names: list, default_deck: str = "Topics", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Web Page")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(QLabel("URL:"))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://…")
        layout.addWidget(self._url_edit)

        layout.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        layout.addWidget(self._title_edit)

        layout.addWidget(QLabel("Tags:"))
        self._tag_edit = QuickTagEdit()
        layout.addWidget(self._tag_edit)

        dk_row = QHBoxLayout()
        dk_row.addWidget(QLabel("Deck:"))
        self._dk_combo = QComboBox()
        for d in deck_names:
            self._dk_combo.addItem(d)
        if default_deck:
            idx = self._dk_combo.findText(default_deck)
            if idx >= 0:
                self._dk_combo.setCurrentIndex(idx)
        dk_row.addWidget(self._dk_combo, 1)
        layout.addLayout(dk_row)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Add Page")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    @property
    def url(self) -> str:
        u = self._url_edit.text().strip()
        if u and not u.startswith(("http://", "https://")):
            u = "https://" + u
        return u

    @property
    def title(self) -> str:
        return self._title_edit.text().strip()

    @property
    def deck_name(self) -> str:
        return self._dk_combo.currentText()

    @property
    def tags(self) -> list[str]:
        return self._tag_edit.tags()
