from aqt.qt import (
    QCheckBox,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
)

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from tag_edit import QuickTagEdit

try:
    from ..backend.video_manager import video_download_requirements
except ImportError:
    try:
        from backend.video_manager import video_download_requirements
    except Exception:
        def video_download_requirements() -> list[str]:
            return []


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

        self._download_cb = QCheckBox("Download & compress into user_files/videos")
        self._download_cb.setChecked(False)
        self._download_cb.setToolTip("Requires yt-dlp and ffmpeg installed on your system.")
        layout.addWidget(self._download_cb)
        self._download_hint = QLabel("")
        self._download_hint.setWordWrap(True)
        self._download_hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        layout.addWidget(self._download_hint)
        self._download_missing = [m for m in video_download_requirements() if m]
        if self._download_missing:
            has_yt = any(m == "yt-dlp" for m in self._download_missing)
            has_ffmpeg = any(m.startswith("ffmpeg") for m in self._download_missing)
            if has_yt and has_ffmpeg:
                self._download_hint.setText(
                    "Will try to auto-install yt-dlp on first use. Compression runs when ffmpeg is available."
                )
            elif has_yt:
                self._download_hint.setText(
                    "Will try to auto-install yt-dlp on first use."
                )
            else:
                self._download_hint.setText(
                    "ffmpeg not found: video will still download, but compression is skipped."
                )
        else:
            self._download_hint.setText("Optional: creates a local compressed copy for offline playback.")

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

    @property
    def tags(self) -> list[str]:
        return self._tag_edit.tags()

    @property
    def download_locally(self) -> bool:
        return self._download_cb.isChecked()

    @property
    def missing_download_tools(self) -> list[str]:
        return list(self._download_missing)
