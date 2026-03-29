import os

from aqt import mw
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
    from ..backend.video_manager import (
        video_download_requirements,
        extract_video_id,
        list_available_video_resolutions,
    )
except ImportError:
    try:
        from backend.video_manager import (
            video_download_requirements,
            extract_video_id,
            list_available_video_resolutions,
        )
    except Exception:
        def video_download_requirements() -> list[str]:
            return []

        def extract_video_id(_url: str) -> str | None:
            return None

        def list_available_video_resolutions(_addon_dir: str, _url: str) -> list[int]:
            return []


class AddVideoDialog(QDialog):
    """Dialog to add a new YouTube video as an Incremento Video card."""

    def __init__(
        self,
        deck_names: list,
        default_deck: str = "Topics",
        addon_dir: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add YouTube Video")
        self.setMinimumWidth(440)
        self._addon_dir = addon_dir or os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
        self._resolution_fetch_token = 0

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

        self._res_row_wrap = QHBoxLayout()
        self._res_row_wrap.addWidget(QLabel("Max resolution:"))
        self._resolution_combo = QComboBox()
        self._resolution_combo.setEnabled(False)
        self._resolution_combo.addItem("Best available", None)
        self._res_row_wrap.addWidget(self._resolution_combo, 1)
        self._res_refresh_btn = QPushButton("Refresh")
        self._res_refresh_btn.setEnabled(False)
        self._res_row_wrap.addWidget(self._res_refresh_btn)
        layout.addLayout(self._res_row_wrap)

        self._resolution_hint = QLabel("")
        self._resolution_hint.setWordWrap(True)
        self._resolution_hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        layout.addWidget(self._resolution_hint)

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
        self._download_cb.toggled.connect(self._on_download_toggled)
        self._url_edit.editingFinished.connect(self._on_url_edited)
        self._res_refresh_btn.clicked.connect(self._refresh_resolutions)

        self._set_resolution_controls_visible(False)

    def _set_resolution_controls_visible(self, visible: bool) -> None:
        for i in range(self._res_row_wrap.count()):
            w = self._res_row_wrap.itemAt(i).widget()
            if w is not None:
                w.setVisible(bool(visible))
        self._resolution_hint.setVisible(bool(visible))

    def _populate_resolution_combo(self, heights: list[int]) -> None:
        prev_data = self._resolution_combo.currentData()
        self._resolution_combo.clear()
        self._resolution_combo.addItem("Best available", None)
        self._resolution_combo.addItem("Original quality (no re-encoding)", "original")
        for h in heights:
            self._resolution_combo.addItem(f"{int(h)}p", int(h))
        if prev_data is not None:
            for i in range(self._resolution_combo.count()):
                if self._resolution_combo.itemData(i) == prev_data:
                    self._resolution_combo.setCurrentIndex(i)
                    break
        self._resolution_combo.setEnabled(True)

    def _refresh_resolutions(self) -> None:
        if not self._download_cb.isChecked():
            return
        url = self.youtube_url
        if not extract_video_id(url):
            self._populate_resolution_combo([])
            self._resolution_combo.setEnabled(False)
            self._resolution_hint.setText("Enter a valid YouTube URL to load available resolutions.")
            return

        self._resolution_fetch_token += 1
        token = self._resolution_fetch_token
        self._resolution_combo.clear()
        self._resolution_combo.addItem("Loading resolutions…", None)
        self._resolution_combo.setEnabled(False)
        self._res_refresh_btn.setEnabled(False)
        self._resolution_hint.setText("Fetching available resolutions…")

        def _task():
            return list_available_video_resolutions(self._addon_dir, url)

        def _on_done(fut) -> None:
            if token != self._resolution_fetch_token:
                return
            self._res_refresh_btn.setEnabled(True)
            try:
                heights = fut.result()
            except Exception as e:
                self._populate_resolution_combo([])
                self._resolution_combo.setEnabled(True)
                msg = str(e).strip().splitlines()[0] if str(e).strip() else "Unknown error."
                self._resolution_hint.setText(
                    f"Could not load resolutions ({msg}). Using best available."
                )
                return
            self._populate_resolution_combo(heights)
            if heights:
                self._resolution_hint.setText(
                    f"Available: {', '.join(f'{h}p' for h in heights)}"
                )
            else:
                self._resolution_hint.setText("No explicit resolutions found. Using best available.")

        mw.taskman.run_in_background(_task, _on_done)

    def _on_download_toggled(self, checked: bool) -> None:
        self._set_resolution_controls_visible(checked)
        self._res_refresh_btn.setEnabled(checked)
        if checked:
            self._refresh_resolutions()
        else:
            self._resolution_hint.setText("")

    def _on_url_edited(self) -> None:
        if self._download_cb.isChecked():
            self._refresh_resolutions()

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

    @property
    def download_max_height(self) -> int | None:
        if not self._download_cb.isChecked():
            return None
        data = self._resolution_combo.currentData()
        try:
            value = int(data)
        except Exception:
            return None
        return value if value > 0 else None

    @property
    def download_original_quality(self) -> bool:
        if not self._download_cb.isChecked():
            return False
        return self._resolution_combo.currentData() == "original"
