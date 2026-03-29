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
    QFileDialog,
)

try:
    from .tag_edit import QuickTagEdit
except ImportError:
    from tag_edit import QuickTagEdit

try:
    from ..backend.video_manager import (
        video_download_requirements,
        is_supported_video_url,
        canonicalize_video_url,
        list_available_video_resolutions,
        supported_local_video_extensions,
    )
except ImportError:
    try:
        from backend.video_manager import (
            video_download_requirements,
            is_supported_video_url,
            canonicalize_video_url,
            list_available_video_resolutions,
            supported_local_video_extensions,
        )
    except Exception:
        def video_download_requirements() -> list[str]:
            return []

        def is_supported_video_url(_url: str) -> bool:
            return False

        def canonicalize_video_url(url: str) -> str:
            return (url or "").strip()

        def list_available_video_resolutions(_addon_dir: str, _url: str) -> list[int]:
            return []

        def supported_local_video_extensions() -> tuple[str, ...]:
            return (".mp4", ".mkv", ".webm", ".mov", ".m4v")


class AddVideoDialog(QDialog):
    """Dialog to add a new URL/local video as an Incremento Video card."""

    def __init__(
        self,
        deck_names: list,
        default_deck: str = "Topics",
        addon_dir: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Video")
        self.setMinimumWidth(440)
        self._addon_dir = addon_dir or os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
        self._resolution_fetch_token = 0

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source:"))
        self._source_combo = QComboBox()
        self._source_combo.addItem("YouTube URL", "youtube")
        self._source_combo.addItem("Vimeo URL", "vimeo")
        self._source_combo.addItem("Local video file", "local")
        src_row.addWidget(self._source_combo, 1)
        layout.addLayout(src_row)

        self._url_label = QLabel("Video URL:")
        layout.addWidget(self._url_label)
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText(
            "https://www.youtube.com/watch?v=\u2026 or https://player.vimeo.com/video/\u2026"
        )
        layout.addWidget(self._url_edit)

        self._local_label = QLabel("Local video file:")
        layout.addWidget(self._local_label)
        local_row = QHBoxLayout()
        self._local_file_edit = QLineEdit()
        self._local_file_edit.setReadOnly(True)
        self._local_file_edit.setPlaceholderText("Choose a local video file…")
        local_row.addWidget(self._local_file_edit, 1)
        self._local_browse_btn = QPushButton("Browse…")
        local_row.addWidget(self._local_browse_btn)
        layout.addLayout(local_row)

        self._local_encode_label = QLabel("Encoding:")
        layout.addWidget(self._local_encode_label)
        self._local_encode_combo = QComboBox()
        self._local_encode_combo.addItem("Original quality (no re-encoding)", "original")
        self._local_encode_combo.addItem("Encode H.264 high quality", "h264_high")
        self._local_encode_combo.addItem("Encode H.264 smaller size", "h264_small")
        layout.addWidget(self._local_encode_combo)

        self._local_hint = QLabel("")
        self._local_hint.setWordWrap(True)
        self._local_hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        self._local_hint.setText(
            "Local import copies file into user_files/videos. "
            "Use original quality for no re-encoding."
        )
        layout.addWidget(self._local_hint)

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
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        self._download_cb.toggled.connect(self._on_download_toggled)
        self._url_edit.editingFinished.connect(self._on_url_edited)
        self._res_refresh_btn.clicked.connect(self._refresh_resolutions)
        self._local_browse_btn.clicked.connect(self._browse_local_video)

        self._set_resolution_controls_visible(False)
        self._on_source_changed()

    def _is_url_source(self) -> bool:
        return self.source_mode in ("youtube", "vimeo")

    def _local_file_filter(self) -> str:
        exts = supported_local_video_extensions()
        patterns = " ".join(f"*{e}" for e in exts) if exts else "*.mp4 *.mkv *.webm *.mov *.m4v"
        return f"Video files ({patterns});;All files (*)"

    def _browse_local_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Local Video",
            "",
            self._local_file_filter(),
        )
        if not path:
            return
        self._local_file_edit.setText(path)
        if not self.title:
            base = os.path.basename(path)
            stem = os.path.splitext(base)[0]
            self._title_edit.setText(stem)

    def _on_source_changed(self) -> None:
        is_url_source = self._is_url_source()
        self._url_label.setVisible(is_url_source)
        self._url_edit.setVisible(is_url_source)
        self._download_cb.setVisible(is_url_source)
        self._download_hint.setVisible(is_url_source)

        self._local_label.setVisible(not is_url_source)
        self._local_file_edit.setVisible(not is_url_source)
        self._local_browse_btn.setVisible(not is_url_source)
        self._local_encode_label.setVisible(not is_url_source)
        self._local_encode_combo.setVisible(not is_url_source)
        self._local_hint.setVisible(not is_url_source)

        if self.source_mode == "youtube":
            self._url_label.setText("YouTube URL:")
            self._url_edit.setPlaceholderText("https://www.youtube.com/watch?v=\u2026")
        elif self.source_mode == "vimeo":
            self._url_label.setText("Vimeo URL:")
            self._url_edit.setPlaceholderText("https://player.vimeo.com/video/\u2026")
        else:
            self._url_label.setText("Video URL:")
            self._url_edit.setPlaceholderText("")

        if is_url_source:
            self._on_download_toggled(self._download_cb.isChecked())
        else:
            self._set_resolution_controls_visible(False)
            self._resolution_hint.setText("")

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
        url = self.video_url
        if not is_supported_video_url(url):
            self._populate_resolution_combo([])
            self._resolution_combo.setEnabled(False)
            self._resolution_hint.setText("Enter a valid YouTube or Vimeo URL to load available resolutions.")
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
        if not self._is_url_source():
            self._set_resolution_controls_visible(False)
            return
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
    def video_url(self) -> str:
        return canonicalize_video_url(self._url_edit.text().strip())

    @property
    def youtube_url(self) -> str:
        return self.video_url

    @property
    def source_mode(self) -> str:
        data = self._source_combo.currentData()
        return str(data or "youtube")

    @property
    def local_video_path(self) -> str:
        return self._local_file_edit.text().strip()

    @property
    def local_encode_mode(self) -> str:
        data = self._local_encode_combo.currentData()
        return str(data or "original")

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
        return self._is_url_source() and self._download_cb.isChecked()

    @property
    def missing_download_tools(self) -> list[str]:
        return list(self._download_missing)

    @property
    def download_max_height(self) -> int | None:
        if not self._is_url_source() or not self._download_cb.isChecked():
            return None
        data = self._resolution_combo.currentData()
        try:
            value = int(data)
        except Exception:
            return None
        return value if value > 0 else None

    @property
    def download_original_quality(self) -> bool:
        if not self._is_url_source() or not self._download_cb.isChecked():
            return False
        return self._resolution_combo.currentData() == "original"
