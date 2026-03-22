from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton,
)


class AddVideoDialog(QDialog):
    """Dialog to add a new YouTube video as an Incremento Video card."""

    def __init__(self, deck_names: list, default_deck: str = "Topics", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add YouTube Video")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        layout.addWidget(QLabel("YouTube URL:"))
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://www.youtube.com/watch?v=\u2026")
        layout.addWidget(self._url_edit)

        layout.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit()
        layout.addWidget(self._title_edit)

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
        ok_btn = QPushButton("Add Video")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    @property
    def youtube_url(self) -> str:
        return self._url_edit.text().strip()

    @property
    def title(self) -> str:
        return self._title_edit.text().strip()

    @property
    def deck_name(self) -> str:
        return self._dk_combo.currentText()
