"""
video_dock.py — Video dock (QWebEngineView + position tracking).

Displays URL/local videos in a right-side dock that persists across card reviews.
Position is polled every second and saved every 5 ticks to pdf_progress storage.

Public API:
    show_video_in_dock(card_id, video_url, position)
    on_video_question_shown(card)
    on_video_reviewer_will_end()
    sync_video_note_type()
"""

import html
import math
import mimetypes
import os
import re
import time
from pathlib import Path

from aqt import mw
from aqt.utils import tooltip
from aqt.qt import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                    QPushButton, QLabel, QTimer, Qt, qconnect, QStackedLayout,
                    QComboBox, QSlider, QApplication, QDialog, QLineEdit,
                    QFileDialog,
                    QSpinBox, QDialogButtonBox, QTextBrowser)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
    from PyQt6.QtMultimediaWidgets import QVideoWidget
except Exception:
    QMediaPlayer = None
    QAudioOutput = None
    QVideoWidget = None

try:
    from ..backend import paths as _paths
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from backend import paths as _paths  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore

try:
    from ..backend.video_manager import (
        VIDEO_NOTE_TYPE,
        build_remote_video_watch_url,
        detect_video_provider,
        resolve_video_url_for_embed,
        is_supported_video_url,
        extract_start_seconds,
        fmt_time,
        get_video_position,
        get_video_note_media,
        import_local_subtitle_file,
        set_video_position,
        list_available_video_subtitles,
        load_subtitle_cues,
        ensure_video_note_type,
        local_video_abspath,
        TARGET_SUBTITLE_FILE_FIELD,
        TARGET_SUBTITLE_LABEL_FIELD,
        REFERENCE_SUBTITLE_FILE_FIELD,
        REFERENCE_SUBTITLE_LABEL_FIELD,
        LOCAL_VIDEO_FIELD,
        download_and_compress_video,
        download_video_subtitle,
        supported_subtitle_extensions,
        update_video_note_media,
    )
    from ..backend.reader_bookmarks import (
        add_reader_bookmark,
        delete_reader_bookmark,
        list_reader_bookmarks,
    )
except ImportError:
    from video_manager import (
        VIDEO_NOTE_TYPE,
        build_remote_video_watch_url,
        detect_video_provider,
        resolve_video_url_for_embed,
        is_supported_video_url,
        extract_start_seconds,
        fmt_time,
        get_video_position,
        get_video_note_media,
        import_local_subtitle_file,
        set_video_position,
        list_available_video_subtitles,
        load_subtitle_cues,
        ensure_video_note_type,
        local_video_abspath,
        TARGET_SUBTITLE_FILE_FIELD,
        TARGET_SUBTITLE_LABEL_FIELD,
        REFERENCE_SUBTITLE_FILE_FIELD,
        REFERENCE_SUBTITLE_LABEL_FIELD,
        LOCAL_VIDEO_FIELD,
        download_and_compress_video,
        download_video_subtitle,
        supported_subtitle_extensions,
        update_video_note_media,
    )
    from reader_bookmarks import add_reader_bookmark, delete_reader_bookmark, list_reader_bookmarks  # type: ignore

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_video_dock            = None
_current_video_card_id = None
_video_timer           = None
_video_tick_count      = 0
_video_profile         = None  # module-level singleton — avoids use-after-free on exit
_current_video_url     = ""
_current_local_relpath = ""
_local_fallback_done   = False
_using_local_qt_player = False
_last_known_position   = 0.0
_local_resume_pending  = False
_local_resume_ms       = 0
_local_resume_attempts = 0
_last_known_duration   = 0.0
_seek_dragging         = False
_seek_ui_updating      = False
_app_state_connected   = False
_browser_sync_pending  = False
_browser_sync_wait_bg  = False
_browser_sync_card_id  = None
_browser_sync_seed_sec = 0
_position_lock_card_id = None
_position_lock_until   = 0.0
_position_lock_sec     = 0.0
_recent_video_extract_source_card_id = None
_recent_video_extract_child_card_ids: set[int] = set()
_recent_video_extract_until = 0.0
_recent_video_extract_position_sec = 0.0
_remote_resume_target  = 0.0
_remote_resume_attempts = 0
_using_local_web_player = False
_target_caption_enabled = True
_reference_caption_enabled = True
_current_target_subtitle_relpath = ""
_current_target_subtitle_label = ""
_current_reference_subtitle_relpath = ""
_current_reference_subtitle_label = ""

_PLAYBACK_STATUS_JS = (
    "(function(){"
    "if(typeof window.__incrementoGetStatus==='function'){"
    "try{return window.__incrementoGetStatus();}catch(_e){}"
    "}"
    "var v=document.querySelector('video');"
    "if(!v){return {hasVideo:false,currentTime:0,readyState:0,networkState:0,duration:null,errorCode:0};}"
    "var t=Number.isFinite(v.currentTime)?v.currentTime:0;"
    "var d=Number.isFinite(v.duration)?v.duration:null;"
    "var rs=(typeof v.readyState==='number')?v.readyState:0;"
    "var ns=(typeof v.networkState==='number')?v.networkState:0;"
    "var ec=(v.error&&typeof v.error.code==='number')?v.error.code:0;"
    "return {hasVideo:true,currentTime:t,readyState:rs,networkState:ns,duration:d,errorCode:ec};"
    "})()"
)
_CURRENT_TIME_JS = (
    "(function(){"
    "if(typeof window.__incrementoGetCurrentTime==='function'){"
    "try{return window.__incrementoGetCurrentTime();}catch(_e){}"
    "}"
    "var v=document.querySelector('video');"
    "return v ? v.currentTime : 0;"
    "})()"
)

_HMS_INPUT_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?$")


def current_video_card_id() -> int | None:
    try:
        return int(_current_video_card_id) if _current_video_card_id is not None else None
    except Exception:
        return None


def _build_video_dock():
    global _video_dock, _video_profile, _app_state_connected

    from PyQt6.QtWebEngineCore import (QWebEngineSettings as _WES,
                                       QWebEngineProfile as _WEProf,
                                       QWebEnginePage as _WEPage)

    dock = QDockWidget("Video", mw)
    dock.setObjectName("incremento_video_dock")
    dock.setMinimumWidth(560)

    container = QWidget()
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(0, 0, 0, 0)
    vbox.setSpacing(0)

    media_host = QWidget(container)
    media_stack = QStackedLayout(media_host)
    media_stack.setContentsMargins(0, 0, 0, 0)

    view = QWebEngineView(media_host)

    # Module-level profile with no parent — avoids use-after-free segfault on exit
    # that occurs when the profile is parented to the view and both get destroyed.
    # Persistent named profile so video-site cookies survive across restarts.
    if _video_profile is None:
        _video_profile = _WEProf("incremento_video")
        _video_profile_dir = str(_paths.get_video_profile_dir(_ADDON_DIR, _active_profile()))
        _video_profile.setPersistentStoragePath(_video_profile_dir)
        _video_profile.setPersistentCookiesPolicy(
            _WEProf.PersistentCookiesPolicy.ForcePersistentCookies
        )
        _video_profile.setHttpUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        _video_profile.settings().setAttribute(
            _WES.WebAttribute.PlaybackRequiresUserGesture, False
        )
        _video_profile.settings().setAttribute(
            _WES.WebAttribute.LocalContentCanAccessFileUrls, True
        )

    _page = _WEPage(_video_profile)  # no parent — profile must outlive page
    view.setPage(_page)
    media_stack.addWidget(view)
    web_index = 0

    local_player = None
    local_audio = None
    local_video_widget = None
    local_index = None
    if QMediaPlayer is not None and QAudioOutput is not None and QVideoWidget is not None:
        local_video_widget = QVideoWidget(media_host)
        media_stack.addWidget(local_video_widget)
        local_index = 1
        local_audio = QAudioOutput(media_host)
        local_player = QMediaPlayer(media_host)
        local_player.setAudioOutput(local_audio)
        local_player.setVideoOutput(local_video_widget)
        local_audio.setVolume(1.0)

    vbox.addWidget(media_host, 1)

    ctrl = QWidget(container)
    ctrl_layout = QHBoxLayout(ctrl)
    ctrl_layout.setContentsMargins(8, 4, 8, 4)

    ts_lbl = QLabel("\u25b6  0:00")
    ts_lbl.setStyleSheet("font-family: monospace; font-size: 12px;")
    ctrl_layout.addWidget(ts_lbl)

    seek_slider = QSlider(Qt.Orientation.Horizontal)
    seek_slider.setRange(0, 0)
    seek_slider.setEnabled(False)
    seek_slider.setMinimumWidth(200)
    ctrl_layout.addWidget(seek_slider, 1)

    add_btn = QPushButton("+ Add Card at this point")
    ctrl_layout.addWidget(add_btn)
    bookmark_btn = QPushButton("Bookmark")
    ctrl_layout.addWidget(bookmark_btn)
    bookmarks_btn = QPushButton("Bookmarks 0")
    ctrl_layout.addWidget(bookmarks_btn)
    browser_btn = QPushButton("Open in Browser")
    browser_btn.setEnabled(False)
    ctrl_layout.addWidget(browser_btn)
    download_btn = QPushButton("Download Local Copy…")
    download_btn.setEnabled(False)
    ctrl_layout.addWidget(download_btn)
    captions_btn = QPushButton("Captions…")
    captions_btn.setEnabled(False)
    ctrl_layout.addWidget(captions_btn)
    vbox.addWidget(ctrl)

    manual_ctrl = QWidget(container)
    manual_layout = QHBoxLayout(manual_ctrl)
    manual_layout.setContentsMargins(8, 0, 8, 4)
    manual_layout.setSpacing(4)
    resume_lbl = QLabel("Resume at")
    resume_input = QLineEdit()
    resume_input.setPlaceholderText("mm:ss or 123s")
    resume_input.setMaximumWidth(150)
    resume_btn = QPushButton("Set time")
    manual_layout.addWidget(resume_lbl)
    manual_layout.addWidget(resume_input, 1)
    manual_layout.addWidget(resume_btn)
    manual_layout.addStretch()
    vbox.addWidget(manual_ctrl)

    local_ctrl = QWidget(container)
    local_layout = QHBoxLayout(local_ctrl)
    local_layout.setContentsMargins(8, 0, 8, 8)

    back_btn = QPushButton("−10s")
    play_btn = QPushButton("Pause")
    fwd_btn = QPushButton("+10s")
    rate_combo = QComboBox()
    rate_combo.addItems(["0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
    rate_combo.setCurrentText("1.0x")
    vol_lbl = QLabel("Vol")
    vol_slider = QSlider(Qt.Orientation.Horizontal)
    vol_slider.setRange(0, 100)
    vol_slider.setValue(100)
    vol_slider.setFixedWidth(120)

    local_layout.addWidget(back_btn)
    local_layout.addWidget(play_btn)
    local_layout.addWidget(fwd_btn)
    local_layout.addWidget(QLabel("Speed"))
    local_layout.addWidget(rate_combo)
    local_layout.addWidget(vol_lbl)
    local_layout.addWidget(vol_slider)
    local_layout.addStretch()
    local_ctrl.setVisible(False)
    vbox.addWidget(local_ctrl)

    caption_ctrl = QWidget(container)
    caption_layout = QHBoxLayout(caption_ctrl)
    caption_layout.setContentsMargins(8, 0, 8, 8)
    caption_layout.setSpacing(6)
    target_cc_btn = QPushButton("Target CC")
    target_cc_btn.setCheckable(True)
    target_cc_btn.setChecked(True)
    reference_cc_btn = QPushButton("Reference CC")
    reference_cc_btn.setCheckable(True)
    reference_cc_btn.setChecked(True)
    caption_status = QLabel("")
    caption_status.setWordWrap(True)
    caption_status.setStyleSheet("font-size: 11px; color: #9aa0a6;")
    caption_layout.addWidget(target_cc_btn)
    caption_layout.addWidget(reference_cc_btn)
    caption_layout.addWidget(caption_status, 1)
    caption_ctrl.setVisible(False)
    vbox.addWidget(caption_ctrl)

    bookmarks_panel = QTextBrowser(container)
    bookmarks_panel.setOpenLinks(False)
    bookmarks_panel.setOpenExternalLinks(False)
    bookmarks_panel.anchorClicked.connect(_open_video_bookmark_link)
    bookmarks_panel.setVisible(False)
    bookmarks_panel.setMaximumHeight(150)
    vbox.addWidget(bookmarks_panel)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._view   = view
    dock._ts_lbl = ts_lbl
    dock._seek_slider = seek_slider
    dock._media_stack = media_stack
    dock._web_index = web_index
    dock._local_index = local_index
    dock._local_player = local_player
    dock._local_audio = local_audio
    dock._local_video_widget = local_video_widget
    dock._local_ctrl = local_ctrl
    dock._local_back_btn = back_btn
    dock._local_play_btn = play_btn
    dock._local_fwd_btn = fwd_btn
    dock._local_rate_combo = rate_combo
    dock._local_vol_slider = vol_slider
    dock._browser_btn = browser_btn
    dock._bookmark_btn = bookmark_btn
    dock._bookmarks_btn = bookmarks_btn
    dock._bookmarks_panel = bookmarks_panel
    dock._download_btn = download_btn
    dock._captions_btn = captions_btn
    dock._resume_input = resume_input
    dock._resume_btn = resume_btn
    dock._caption_ctrl = caption_ctrl
    dock._target_cc_btn = target_cc_btn
    dock._reference_cc_btn = reference_cc_btn
    dock._caption_status = caption_status
    qconnect(add_btn.clicked, _video_add_card_at_point)
    qconnect(bookmark_btn.clicked, _add_current_video_bookmark)
    qconnect(bookmarks_btn.clicked, _toggle_video_bookmarks_panel)
    qconnect(browser_btn.clicked, _open_video_in_browser)
    qconnect(download_btn.clicked, download_current_video_locally)
    qconnect(captions_btn.clicked, configure_current_video_captions)
    qconnect(resume_btn.clicked, _on_manual_time_submit)
    qconnect(resume_input.returnPressed, _on_manual_time_submit)
    qconnect(seek_slider.sliderPressed, _on_seek_slider_pressed)
    qconnect(seek_slider.sliderReleased, _on_seek_slider_released)
    qconnect(seek_slider.valueChanged, _on_seek_slider_value_changed)
    qconnect(back_btn.clicked, lambda: _local_seek(-10))
    qconnect(play_btn.clicked, _toggle_local_playback)
    qconnect(fwd_btn.clicked, lambda: _local_seek(10))
    qconnect(rate_combo.currentTextChanged, _set_local_rate)
    qconnect(vol_slider.valueChanged, _set_local_volume)
    qconnect(target_cc_btn.clicked, lambda checked: _set_caption_visibility("target", checked))
    qconnect(reference_cc_btn.clicked, lambda checked: _set_caption_visibility("reference", checked))
    if local_player is not None:
        qconnect(local_player.errorOccurred, _on_local_player_error)
        qconnect(local_player.playbackStateChanged, _on_local_playback_state_changed)
        qconnect(local_player.mediaStatusChanged, _on_local_media_status_changed)
    if not _app_state_connected:
        app = QApplication.instance()
        if app is not None:
            qconnect(app.applicationStateChanged, _on_application_state_changed)
            _app_state_connected = True

    _video_dock = dock
    return dock


def _local_video_html(
    video_src: str,
    mime_type: str,
    start_sec: int,
    *,
    target_cues: list[dict] | None = None,
    reference_cues: list[dict] | None = None,
    target_enabled: bool = True,
    reference_enabled: bool = True,
) -> str:
    src = html.escape(video_src, quote=True)
    mime = html.escape(mime_type or "video/mp4", quote=True)
    target_payload = json.dumps(target_cues or [])
    reference_payload = json.dumps(reference_cues or [])
    target_visible = "true" if target_enabled else "false"
    reference_visible = "true" if reference_enabled else "false"
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {{ margin:0; padding:0; background:#000; width:100%; height:100%; overflow:hidden; }}
#player {{ width:100vw; height:100vh; background:#000; }}
#caption-root {{
  position: fixed;
  left: 3vw;
  right: 3vw;
  bottom: 8vh;
  z-index: 10;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
}}
.caption-line {{
  max-width: 90vw;
  padding: 8px 14px;
  border-radius: 12px;
  text-align: center;
  white-space: pre-line;
  font-family: sans-serif;
  font-size: 22px;
  line-height: 1.35;
  text-shadow: 0 2px 10px rgba(0,0,0,0.8);
  box-shadow: 0 8px 24px rgba(0,0,0,0.35);
}}
#target-caption {{
  background: rgba(15, 20, 28, 0.78);
  color: #ffffff;
  border: 1px solid rgba(255,255,255,0.1);
}}
#reference-caption {{
  background: rgba(18, 59, 44, 0.72);
  color: #ecfff7;
  border: 1px solid rgba(176, 255, 220, 0.2);
  font-size: 18px;
}}
</style>
</head>
<body>
<video id="player" controls playsinline>
  <source src="{src}" type="{mime}">
</video>
<div id="caption-root">
  <div id="target-caption" class="caption-line" style="display:none;"></div>
  <div id="reference-caption" class="caption-line" style="display:none;"></div>
</div>
<script>
const startSec = {max(0, int(start_sec))};
const v = document.getElementById("player");
const targetCues = {target_payload};
const referenceCues = {reference_payload};
let showTarget = {target_visible};
let showReference = {reference_visible};

function cueAtTime(cues, timeSec) {{
  if(!Array.isArray(cues) || !cues.length) return "";
  for(const cue of cues) {{
    const start = Number(cue.start || 0);
    const end = Number(cue.end || 0);
    if(timeSec >= start && timeSec <= end) {{
      return String(cue.text || "");
    }}
  }}
  return "";
}}

function renderCaption(elementId, text, visible) {{
  const el = document.getElementById(elementId);
  if(!el) return;
  if(!visible || !text) {{
    el.style.display = "none";
    el.textContent = "";
    return;
  }}
  el.style.display = "block";
  el.textContent = text;
}}

function updateCaptions() {{
  const timeSec = Number.isFinite(v.currentTime) ? v.currentTime : 0;
  renderCaption("target-caption", cueAtTime(targetCues, timeSec), showTarget);
  renderCaption("reference-caption", cueAtTime(referenceCues, timeSec), showReference);
}}

window.__incrementoSetCaptionVisibility = function(slot, visible) {{
  if(slot === "target") showTarget = !!visible;
  if(slot === "reference") showReference = !!visible;
  updateCaptions();
  return true;
}};

window.__incrementoGetCaptionState = function() {{
  return {{
    hasTarget: targetCues.length > 0,
    hasReference: referenceCues.length > 0,
    showTarget,
    showReference
  }};
}};

v.addEventListener("loadedmetadata", () => {{
  if (startSec > 0) {{
    try {{ v.currentTime = startSec; }} catch (_e) {{}}
  }}
  updateCaptions();
}});
v.addEventListener("timeupdate", updateCaptions);
setInterval(updateCaptions, 150);
</script>
</body>
</html>"""


def _set_local_controls_visible(visible: bool) -> None:
    if _video_dock is None:
        return
    ctrl = getattr(_video_dock, "_local_ctrl", None)
    if ctrl is not None:
        ctrl.setVisible(bool(visible))


def _set_browser_button_enabled(enabled: bool) -> None:
    if _video_dock is None:
        return
    btn = getattr(_video_dock, "_browser_btn", None)
    if btn is None:
        return
    try:
        btn.setEnabled(bool(enabled))
    except Exception:
        pass


def _set_download_button_enabled(enabled: bool, *, has_local_copy: bool = False) -> None:
    if _video_dock is None:
        return
    btn = getattr(_video_dock, "_download_btn", None)
    if btn is None:
        return
    try:
        btn.setEnabled(bool(enabled))
        btn.setText("Re-download Local Copy…" if has_local_copy else "Download Local Copy…")
    except Exception:
        pass


def _set_captions_button_enabled(enabled: bool) -> None:
    if _video_dock is None:
        return
    btn = getattr(_video_dock, "_captions_btn", None)
    if btn is None:
        return
    try:
        btn.setEnabled(bool(enabled))
    except Exception:
        pass


def _set_caption_controls_state(
    *,
    has_target: bool,
    has_reference: bool,
    use_local_player: bool,
) -> None:
    if _video_dock is None:
        return
    ctrl = getattr(_video_dock, "_caption_ctrl", None)
    target_btn = getattr(_video_dock, "_target_cc_btn", None)
    reference_btn = getattr(_video_dock, "_reference_cc_btn", None)
    status_lbl = getattr(_video_dock, "_caption_status", None)
    if ctrl is None or target_btn is None or reference_btn is None or status_lbl is None:
        return

    any_captions = bool(has_target or has_reference)
    try:
        ctrl.setVisible(any_captions)
        target_btn.setEnabled(bool(has_target and use_local_player))
        target_btn.setVisible(bool(has_target))
        target_btn.setChecked(bool(_target_caption_enabled))
        reference_btn.setEnabled(bool(has_reference and use_local_player))
        reference_btn.setVisible(bool(has_reference))
        reference_btn.setChecked(bool(_reference_caption_enabled))
        if not any_captions:
            status_lbl.setText("")
        elif use_local_player:
            parts = []
            if has_target:
                parts.append("target")
            if has_reference:
                parts.append("reference")
            status_lbl.setText(f"Local subtitle overlays active: {', '.join(parts)}.")
        else:
            status_lbl.setText("Subtitles are configured. Download a local copy to use dual caption overlays.")
    except Exception:
        pass


def _set_caption_visibility(slot: str, enabled: bool) -> None:
    global _target_caption_enabled, _reference_caption_enabled
    slot_name = str(slot or "").strip().lower()
    if slot_name == "target":
        _target_caption_enabled = bool(enabled)
    elif slot_name == "reference":
        _reference_caption_enabled = bool(enabled)
    else:
        return

    if _video_dock is None or not _using_local_web_player:
        return
    js = (
        "(function(slot, visible){"
        "if(typeof window.__incrementoSetCaptionVisibility!=='function'){return false;}"
        "try{return !!window.__incrementoSetCaptionVisibility(slot, visible);}catch(_e){return false;}"
        f"}})({json.dumps(slot_name)}, {str(bool(enabled)).lower()})"
    )
    try:
        _video_dock._view.page().runJavaScript(js)
    except Exception:
        pass


def _fmt_progress_label(current_sec: float, duration_sec: float | None) -> str:
    cur = max(0.0, float(current_sec or 0.0))
    if duration_sec is None or duration_sec <= 0:
        return f"\u25b6  {fmt_time(cur)}"
    dur = max(0.0, float(duration_sec))
    return f"\u25b6  {fmt_time(cur)} / {fmt_time(dur)}"


def _set_seek_ui(current_sec: float, duration_sec: float | None) -> None:
    global _seek_ui_updating
    if _video_dock is None:
        return
    try:
        _video_dock._ts_lbl.setText(_fmt_progress_label(current_sec, duration_sec))
    except (RuntimeError, AttributeError):
        pass

    slider = getattr(_video_dock, "_seek_slider", None)
    if slider is None:
        return

    dur = float(duration_sec or 0.0)
    if dur > 0.5 and math.isfinite(dur):
        max_pos = max(1, int(round(dur)))
        _seek_ui_updating = True
        try:
            if slider.minimum() != 0 or slider.maximum() != max_pos:
                slider.setRange(0, max_pos)
            slider.setEnabled(True)
            if not _seek_dragging:
                cur = max(0, min(max_pos, int(round(float(current_sec or 0.0)))))
                slider.setValue(cur)
        finally:
            _seek_ui_updating = False
    else:
        _seek_ui_updating = True
        try:
            slider.setRange(0, 0)
            slider.setEnabled(False)
        finally:
            _seek_ui_updating = False


def _reset_seek_ui() -> None:
    global _seek_ui_updating, _seek_dragging
    _seek_dragging = False
    if _video_dock is None:
        return
    slider = getattr(_video_dock, "_seek_slider", None)
    if slider is None:
        return
    _seek_ui_updating = True
    try:
        slider.setRange(0, 0)
        slider.setValue(0)
        slider.setEnabled(False)
        _video_dock._ts_lbl.setText("\u25b6  0:00")
    except Exception:
        pass
    finally:
        _seek_ui_updating = False


def _current_video_card():
    if _current_video_card_id is None or getattr(mw, "col", None) is None:
        return None
    try:
        return mw.col.get_card(int(_current_video_card_id))
    except Exception:
        return None


def _current_video_note():
    card = _current_video_card()
    if card is None:
        return None
    try:
        note = card.note()
        model = mw.col.models.get(note.mid)
    except Exception:
        return None
    if model is None or model.get("name") != VIDEO_NOTE_TYPE:
        return None
    return note


def _persist_current_video_note_media(**updates) -> bool:
    note = _current_video_note()
    if note is None:
        return False
    if not update_video_note_media(note, **updates):
        return True
    try:
        mw.col.update_note(note)
    except Exception:
        try:
            note.flush()
        except Exception:
            return False
    return True


def _parse_manual_time(text: str) -> float | None:
    raw = (text or "").strip().lower()
    if not raw:
        return None
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) not in (2, 3):
            return None
        values: list[float] = []
        for part in parts:
            if not part:
                return None
            try:
                values.append(float(part))
            except Exception:
                return None
        if len(values) == 2:
            return max(0.0, values[0] * 60.0 + values[1])
        return max(0.0, values[0] * 3600.0 + values[1] * 60.0 + values[2])
    match = _HMS_INPUT_RE.fullmatch(raw)
    if match and any(match.groups()):
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        try:
            s = float(match.group(3) or 0.0)
        except Exception:
            s = 0.0
        return max(0.0, h * 3600.0 + m * 60.0 + s)
    if raw.endswith("s"):
        candidate = raw[:-1]
        if candidate:
            try:
                return max(0.0, float(candidate))
            except Exception:
                return None
        return None
    try:
        return max(0.0, float(raw))
    except Exception:
        return None


def _apply_manual_time(seconds: float) -> None:
    global _last_known_position
    if _current_video_card_id is None:
        tooltip("Incremento: no active video card.")
        return
    target = max(0.0, float(seconds or 0.0))
    _last_known_position = target
    _seek_to_seconds(target)
    _set_seek_ui(target, _last_known_duration if _last_known_duration > 0 else None)
    try:
        set_video_position(_ADDON_DIR, _active_profile(), _current_video_card_id, target)
    except Exception:
        pass
    tooltip(f"Incremento: stored resume time at {fmt_time(target)}.")
    if _video_dock is not None:
        try:
            inp = getattr(_video_dock, "_resume_input", None)
            if inp is not None:
                inp.setText(fmt_time(target))
        except Exception:
            pass


def _on_manual_time_submit() -> None:
    if _video_dock is None:
        return
    inp = getattr(_video_dock, "_resume_input", None)
    if inp is None:
        return
    seconds = _parse_manual_time(inp.text())
    if seconds is None:
        tooltip("Incremento: enter a time like mm:ss, 1m30s, or 90s.")
        return
    _apply_manual_time(seconds)


def _video_bookmarks() -> list[dict]:
    if _current_video_card_id is None:
        return []
    try:
        return list_reader_bookmarks(
            _ADDON_DIR,
            _active_profile(),
            int(_current_video_card_id),
            "video",
        )
    except Exception:
        return []


def _refresh_video_bookmarks_panel() -> None:
    if _video_dock is None:
        return
    bookmarks = _video_bookmarks()
    try:
        _video_dock._bookmarks_btn.setText(f"Bookmarks {len(bookmarks)}")
    except Exception:
        pass
    panel = getattr(_video_dock, "_bookmarks_panel", None)
    if panel is None:
        return
    html_parts = ["<div style='font-family:sans-serif;font-size:12px;line-height:1.45'>"]
    html_parts.append("<b>Interesting-place bookmarks</b>")
    if bookmarks:
        html_parts.append("<ul>")
        for bookmark in bookmarks:
            bookmark_id = html.escape(str(bookmark.get("id") or ""))
            label = html.escape(str(bookmark.get("label") or "Bookmark"))
            html_parts.append(
                "<li>"
                f"{label} "
                f"<a href='inc://video-bookmark-open/{bookmark_id}'>Jump</a> "
                f"<a href='inc://video-bookmark-delete/{bookmark_id}' style='color:#c66'>Delete</a>"
                "</li>"
            )
        html_parts.append("</ul>")
    else:
        html_parts.append("<div style='color:#888;padding:6px 0 0'>No bookmarks yet.</div>")
    html_parts.append("</div>")
    panel.setHtml("".join(html_parts))


def _add_current_video_bookmark() -> None:
    if _current_video_card_id is None:
        tooltip("Incremento: no active video card.")
        return
    seconds = float(_last_known_position or 0.0)
    if _using_local_qt_player and _video_dock is not None:
        player = getattr(_video_dock, "_local_player", None)
        if player is not None:
            try:
                seconds = max(seconds, float(player.position()) / 1000.0)
            except Exception:
                pass
    try:
        add_reader_bookmark(
            _ADDON_DIR,
            _active_profile(),
            int(_current_video_card_id),
            "video",
            {"seconds": seconds},
        )
    except Exception:
        tooltip("Incremento: could not save video bookmark.")
        return
    _refresh_video_bookmarks_panel()
    try:
        _video_dock._bookmarks_panel.setVisible(True)
    except Exception:
        pass
    tooltip(f"Incremento: video bookmark saved at {fmt_time(seconds)}.")


def _toggle_video_bookmarks_panel() -> None:
    if _video_dock is None:
        return
    _refresh_video_bookmarks_panel()
    try:
        _video_dock._bookmarks_panel.setVisible(not _video_dock._bookmarks_panel.isVisible())
    except Exception:
        pass


def _open_video_bookmark_link(url: QUrl) -> None:
    global _last_known_position
    if _current_video_card_id is None:
        return
    s = url.toString()
    bookmark_id = s.rsplit("/", 1)[-1]
    if s.startswith("inc://video-bookmark-delete/"):
        try:
            delete_reader_bookmark(
                _ADDON_DIR,
                _active_profile(),
                int(_current_video_card_id),
                "video",
                bookmark_id,
            )
        except Exception:
            tooltip("Incremento: could not delete video bookmark.")
        _refresh_video_bookmarks_panel()
        return
    if not s.startswith("inc://video-bookmark-open/"):
        return
    bookmark = next((item for item in _video_bookmarks() if str(item.get("id") or "") == bookmark_id), None)
    if not bookmark:
        return
    seconds = float((bookmark.get("location") or {}).get("seconds", 0.0) or 0.0)
    _last_known_position = max(0.0, seconds)
    _seek_to_seconds(seconds)
    _set_seek_ui(seconds, _last_known_duration if _last_known_duration > 0 else None)


def _seek_to_seconds(seconds: float) -> None:
    global _last_known_position
    if _video_dock is None:
        return
    t = max(0.0, float(seconds or 0.0))
    _last_known_position = t
    if _using_local_qt_player:
        player = getattr(_video_dock, "_local_player", None)
        if player is not None:
            try:
                player.setPosition(int(round(t * 1000.0)))
            except Exception:
                pass
        return
    js = (
        "(function(sec){"
        "if(typeof window.__incrementoSeekTo==='function'){"
        "try{return !!window.__incrementoSeekTo(sec);}catch(_e){}"
        "}"
        "var v=document.querySelector('video');"
        "if(!v){return false;}"
        "try{v.currentTime=sec; return true;}catch(_e){return false;}"
        f"}})({t:.3f})"
    )
    try:
        _video_dock._view.page().runJavaScript(js)
    except Exception:
        pass


def _on_seek_slider_pressed() -> None:
    global _seek_dragging
    _seek_dragging = True


def _on_seek_slider_released() -> None:
    global _seek_dragging
    if _video_dock is None:
        _seek_dragging = False
        return
    slider = getattr(_video_dock, "_seek_slider", None)
    if slider is None:
        _seek_dragging = False
        return
    target = float(slider.value())
    _seek_dragging = False
    _seek_to_seconds(target)
    _set_seek_ui(target, _last_known_duration if _last_known_duration > 0 else None)
    if _current_video_card_id is not None and target > 0:
        try:
            set_video_position(_ADDON_DIR, _active_profile(), _current_video_card_id, target)
        except Exception:
            pass


def _on_seek_slider_value_changed(value: int) -> None:
    if _seek_ui_updating or not _seek_dragging or _video_dock is None:
        return
    cur = max(0.0, float(value))
    dur = _last_known_duration if _last_known_duration > 0 else None
    try:
        _video_dock._ts_lbl.setText(_fmt_progress_label(cur, dur))
    except Exception:
        pass


def _local_seek(delta_seconds: int) -> None:
    if _video_dock is None:
        return
    player = getattr(_video_dock, "_local_player", None)
    if player is None:
        return
    try:
        cur = int(player.position())
        nxt = max(0, cur + int(delta_seconds * 1000))
        player.setPosition(nxt)
    except Exception:
        pass


def _toggle_local_playback() -> None:
    if _video_dock is None:
        return
    player = getattr(_video_dock, "_local_player", None)
    if player is None or QMediaPlayer is None:
        return
    try:
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        else:
            player.play()
    except Exception:
        pass


def _set_local_rate(text: str) -> None:
    if _video_dock is None:
        return
    player = getattr(_video_dock, "_local_player", None)
    if player is None:
        return
    raw = (text or "").strip().lower().replace("x", "")
    try:
        rate = float(raw)
    except Exception:
        rate = 1.0
    rate = max(0.25, min(4.0, rate))
    try:
        player.setPlaybackRate(rate)
    except Exception:
        pass


def _set_local_volume(value: int) -> None:
    if _video_dock is None:
        return
    audio = getattr(_video_dock, "_local_audio", None)
    if audio is None:
        return
    try:
        audio.setVolume(max(0.0, min(1.0, float(value) / 100.0)))
    except Exception:
        pass


def _on_local_playback_state_changed(state) -> None:
    if _video_dock is None:
        return
    btn = getattr(_video_dock, "_local_play_btn", None)
    if btn is None:
        return
    if QMediaPlayer is None:
        btn.setText("Play")
        return
    if state == QMediaPlayer.PlaybackState.PlayingState:
        btn.setText("Pause")
    else:
        btn.setText("Play")


def _on_local_media_status_changed(status) -> None:
    global _local_resume_pending, _local_resume_ms, _last_known_position
    global _local_resume_attempts
    if _video_dock is None or not _using_local_qt_player:
        return
    if not _local_resume_pending or QMediaPlayer is None:
        return
    if status in (
        QMediaPlayer.MediaStatus.LoadedMedia,
        QMediaPlayer.MediaStatus.BufferedMedia,
    ):
        player = getattr(_video_dock, "_local_player", None)
        if player is None:
            return
        try:
            player.setPosition(max(0, int(_local_resume_ms)))
            player.pause()
            _last_known_position = max(_last_known_position, float(_local_resume_ms) / 1000.0)
        except Exception:
            pass
        _local_resume_pending = False
        _local_resume_attempts = 0


def _persist_position_now() -> None:
    if _current_video_card_id is None:
        return
    t = max(0.0, float(_last_known_position or 0.0))
    if _using_local_qt_player and _video_dock is not None:
        player = getattr(_video_dock, "_local_player", None)
        if player is not None:
            try:
                t = max(t, float(player.position()) / 1000.0)
            except Exception:
                pass
    if t <= 0.0:
        return
    try:
        set_video_position(_ADDON_DIR, _active_profile(), _current_video_card_id, t)
    except Exception:
        pass


def reset_for_profile_switch() -> None:
    """Reset Qt WebEngine profile singleton on Anki profile switch.

    Must be called before migrate_to_profile_dir so the new profile is created
    with the correct per-profile storage path on next dock open.
    """
    global _video_profile, _video_dock
    _video_profile = None
    if _video_dock is not None:
        try:
            _video_dock.hide()
            _video_dock.deleteLater()
        except Exception:
            pass
        _video_dock = None


def show_video_in_dock(
    card_id: int,
    video_url: str,
    position: float = 0.0,
    local_video_file: str = "",
    *,
    target_subtitle_file: str = "",
    target_subtitle_label: str = "",
    reference_subtitle_file: str = "",
    reference_subtitle_label: str = "",
    preserve_loaded: bool = False,
) -> None:
    global _video_dock, _current_video_card_id, _current_video_url
    global _current_local_relpath, _local_fallback_done, _using_local_qt_player
    global _last_known_position, _local_resume_pending, _local_resume_ms
    global _local_resume_attempts, _last_known_duration
    global _position_lock_card_id, _position_lock_until, _position_lock_sec
    global _remote_resume_target, _remote_resume_attempts
    global _using_local_web_player
    global _current_target_subtitle_relpath, _current_target_subtitle_label
    global _current_reference_subtitle_relpath, _current_reference_subtitle_label
    global _target_caption_enabled, _reference_caption_enabled

    previous_dock = _video_dock
    previous_card_id = _current_video_card_id
    previous_video_url = _current_video_url
    previous_remote_loaded = (
        _video_dock is not None
        and not _using_local_qt_player
        and not _using_local_web_player
        and not bool(_current_local_relpath)
    )
    previous_duration = float(_last_known_duration or 0.0)
    try:
        same_active_card = (
            previous_card_id is not None
            and int(previous_card_id) == int(card_id)
        )
    except Exception:
        same_active_card = False

    normalized_url = (video_url or "").strip()
    if detect_video_provider(normalized_url) == "vimeo":
        try:
            normalized_url = resolve_video_url_for_embed(normalized_url, timeout_sec=1.5)
        except Exception:
            pass

    requested_position = max(0.0, float(position or 0.0))
    if preserve_loaded and same_active_card:
        position = max(requested_position, float(_last_known_position or 0.0))
    else:
        position = requested_position

    _current_video_card_id = card_id
    _current_video_url = normalized_url
    _last_known_position = max(0.0, float(position or 0.0))
    _last_known_duration = previous_duration if preserve_loaded and same_active_card else 0.0
    _remote_resume_target = 0.0
    _remote_resume_attempts = 0
    _using_local_web_player = False
    _current_target_subtitle_relpath = str(target_subtitle_file or "").strip()
    _current_target_subtitle_label = str(target_subtitle_label or "").strip()
    _current_reference_subtitle_relpath = str(reference_subtitle_file or "").strip()
    _current_reference_subtitle_label = str(reference_subtitle_label or "").strip()
    _target_caption_enabled = True
    _reference_caption_enabled = True
    if _position_lock_card_id is not None and _position_lock_card_id != int(card_id):
        _position_lock_card_id = None
        _position_lock_until = 0.0
        _position_lock_sec = 0.0

    if _video_dock is None:
        _build_video_dock()
    else:
        try:
            _video_dock.widget()
        except RuntimeError:
            _video_dock = None
            _build_video_dock()
    existing_dock_reused = previous_dock is not None and _video_dock is previous_dock
    _set_browser_button_enabled(bool(build_remote_video_watch_url(_current_video_url, start_sec=0)))
    _set_download_button_enabled(
        bool(is_supported_video_url(_current_video_url)),
        has_local_copy=bool(local_video_file),
    )
    _set_captions_button_enabled(True)
    _refresh_video_bookmarks_panel()

    local_relpath = (local_video_file or "").strip()
    start_sec = int(position)
    if local_relpath:
        local_abs = local_video_abspath(_ADDON_DIR, _active_profile(), local_relpath)
        if os.path.exists(local_abs):
            local_path = Path(local_abs)
            _current_local_relpath = local_relpath
            _local_fallback_done = False
            _video_dock.show()
            _video_dock.raise_()
            target_cues = load_subtitle_cues(
                _ADDON_DIR,
                _active_profile(),
                _current_target_subtitle_relpath,
            )
            reference_cues = load_subtitle_cues(
                _ADDON_DIR,
                _active_profile(),
                _current_reference_subtitle_relpath,
            )
            use_local_web_player = bool(target_cues or reference_cues)
            local_player = getattr(_video_dock, "_local_player", None)
            local_index = getattr(_video_dock, "_local_index", None)
            media_stack = getattr(_video_dock, "_media_stack", None)
            if use_local_web_player and media_stack is not None:
                _using_local_qt_player = False
                _using_local_web_player = True
                _set_local_controls_visible(False)
                _local_resume_pending = False
                _local_resume_ms = 0
                _local_resume_attempts = 0
                try:
                    mime_type = mimetypes.guess_type(str(local_path))[0] or "video/mp4"
                except Exception:
                    mime_type = "video/mp4"
                html_text = _local_video_html(
                    QUrl.fromLocalFile(str(local_path)).toString(),
                    mime_type,
                    start_sec,
                    target_cues=target_cues,
                    reference_cues=reference_cues,
                    target_enabled=_target_caption_enabled,
                    reference_enabled=_reference_caption_enabled,
                )
                web_index = getattr(_video_dock, "_web_index", None)
                if local_player is not None:
                    try:
                        local_player.stop()
                    except Exception:
                        pass
                if web_index is not None:
                    media_stack.setCurrentIndex(web_index)
                _video_dock._view.setHtml(
                    html_text,
                    QUrl.fromLocalFile(str(local_path.parent) + os.sep),
                )
                _set_caption_controls_state(
                    has_target=bool(target_cues),
                    has_reference=bool(reference_cues),
                    use_local_player=True,
                )
                _start_video_timer()
                return
            if local_player is not None and local_index is not None and media_stack is not None:
                _using_local_qt_player = True
                _using_local_web_player = False
                _set_local_controls_visible(True)
                try:
                    local_player.stop()
                except Exception:
                    pass
                media_stack.setCurrentIndex(local_index)
                _local_resume_ms = max(0, int(start_sec * 1000))
                _local_resume_pending = _local_resume_ms > 0
                _local_resume_attempts = 0
                local_player.setSource(QUrl.fromLocalFile(str(local_path)))
                if _local_resume_pending:
                    try:
                        local_player.setPosition(_local_resume_ms)
                    except Exception:
                        pass
                else:
                    try:
                        local_player.setPosition(0)
                    except Exception:
                        pass
                local_player.pause()
                if _local_resume_ms > 0:
                    try:
                        _set_seek_ui(float(_local_resume_ms) / 1000.0, None)
                    except Exception:
                        pass
            else:
                tooltip("Incremento: local playback requires Qt multimedia support; falling back to web playback.")
            _set_caption_controls_state(
                has_target=bool(target_cues),
                has_reference=bool(reference_cues),
                use_local_player=False,
            )
            _start_video_timer()
            if _using_local_qt_player:
                return
        print(f"[Incremento] Local video missing for card {card_id}: {local_relpath!r}")

    remote_watch_url = build_remote_video_watch_url(_current_video_url, start_sec=start_sec)
    if remote_watch_url:
        same_loaded_remote = (
            preserve_loaded
            and same_active_card
            and previous_remote_loaded
            and existing_dock_reused
            and not local_relpath
            and str(previous_video_url or "").strip() == _current_video_url
        )
        url = QUrl(remote_watch_url)
        _current_local_relpath = ""
        _local_fallback_done = False
        _using_local_qt_player = False
        _using_local_web_player = False
        _local_resume_pending = False
        _local_resume_ms = 0
        _local_resume_attempts = 0
        _last_known_duration = 0.0
        _remote_resume_target = max(0.0, float(start_sec))
        _remote_resume_attempts = 0
        _set_local_controls_visible(False)
        if not same_loaded_remote:
            _reset_seek_ui()
        _set_caption_controls_state(
            has_target=bool(_current_target_subtitle_relpath),
            has_reference=bool(_current_reference_subtitle_relpath),
            use_local_player=False,
        )
        if same_loaded_remote:
            if _last_known_position > 0:
                _remote_resume_target = 0.0
                _remote_resume_attempts = 0
                _position_lock_card_id = int(card_id)
                _position_lock_sec = float(_last_known_position)
                _position_lock_until = time.monotonic() + 8.0
                _set_seek_ui(_last_known_position, None)
            _video_dock.show()
            _video_dock.raise_()
            _start_video_timer()
            return
        if _remote_resume_target > 0:
            _set_seek_ui(_remote_resume_target, None)

        local_player = getattr(_video_dock, "_local_player", None)
        if local_player is not None:
            try:
                local_player.stop()
            except Exception:
                pass
        media_stack = getattr(_video_dock, "_media_stack", None)
        web_index = getattr(_video_dock, "_web_index", None)
        if media_stack is not None and web_index is not None:
            media_stack.setCurrentIndex(web_index)

        _video_dock.show()
        _video_dock.raise_()
        _video_dock._view.load(url)
        _start_video_timer()
        return

    tooltip("Incremento: This video card has no valid video URL.")
    _set_caption_controls_state(
        has_target=bool(_current_target_subtitle_relpath),
        has_reference=bool(_current_reference_subtitle_relpath),
        use_local_player=False,
    )
    print(f"[Incremento] Invalid video URL for card {card_id}: {video_url!r}")


def _stored_video_position_for_card(card_id: int | None) -> float:
    if card_id is None:
        return 0.0
    try:
        return float(get_video_position(_ADDON_DIR, _active_profile(), int(card_id)) or 0.0)
    except Exception:
        return 0.0


def _best_protected_video_position(card_id: int | None, fallback_sec: float = 0.0) -> float:
    target = max(0.0, float(fallback_sec or 0.0), _stored_video_position_for_card(card_id))
    try:
        if card_id is not None and _current_video_card_id is not None and int(card_id) == int(_current_video_card_id):
            target = max(target, float(_last_known_position or 0.0))
    except Exception:
        pass
    try:
        if card_id is not None and _position_lock_card_id is not None and int(card_id) == int(_position_lock_card_id):
            target = max(target, float(_position_lock_sec or 0.0))
    except Exception:
        pass
    return target


def _arm_video_extract_position_protection(
    card_id: int | None,
    position_sec: float = 0.0,
    *,
    ttl_sec: float = 60.0,
) -> float:
    global _last_known_position
    global _position_lock_card_id, _position_lock_until, _position_lock_sec
    global _recent_video_extract_source_card_id
    global _recent_video_extract_until, _recent_video_extract_position_sec
    if card_id is None:
        return 0.0
    try:
        source_card_id = int(card_id)
    except Exception:
        return 0.0
    target = _best_protected_video_position(source_card_id, position_sec)
    if target <= 0.0:
        return 0.0
    _recent_video_extract_source_card_id = source_card_id
    _recent_video_extract_position_sec = float(target)
    _recent_video_extract_until = time.monotonic() + max(1.0, float(ttl_sec))
    _last_known_position = max(float(_last_known_position or 0.0), float(target))
    _position_lock_card_id = source_card_id
    _position_lock_sec = float(target)
    _position_lock_until = time.monotonic() + max(1.0, float(ttl_sec))
    try:
        set_video_position(_ADDON_DIR, _active_profile(), source_card_id, float(target))
    except Exception:
        pass
    return float(target)


def _video_note_payload_for_card(card_id: int) -> tuple[str, dict]:
    try:
        card = mw.col.get_card(int(card_id))
        note = mw.col.get_note(card.nid)
    except Exception:
        return "", {}
    try:
        video_url = str(note["YouTube_URL"] or "").strip()
    except Exception:
        video_url = ""
    try:
        media = get_video_note_media(note)
    except Exception:
        media = {}
    return video_url, media


def _restore_video_extract_position(
    card_id: int | None = None,
    position_sec: float = 0.0,
    *,
    ttl_sec: float = 60.0,
) -> bool:
    raw_card_id = card_id if card_id is not None else _recent_video_extract_source_card_id
    try:
        source_card_id = int(raw_card_id)
    except Exception:
        return False
    target = _arm_video_extract_position_protection(
        source_card_id,
        max(float(position_sec or 0.0), float(_recent_video_extract_position_sec or 0.0)),
        ttl_sec=ttl_sec,
    )
    if target <= 0.0:
        return False

    same_current = False
    try:
        same_current = _current_video_card_id is not None and int(_current_video_card_id) == source_card_id
    except Exception:
        same_current = False
    if same_current and _video_dock is not None:
        try:
            _video_dock.show()
            _video_dock.raise_()
        except Exception:
            pass
        _seek_to_seconds(target)
        _set_seek_ui(target, _last_known_duration if _last_known_duration > 0 else None)
        return True

    video_url, media = _video_note_payload_for_card(source_card_id)
    local_video_file = str((media or {}).get("local_video_file") or "")
    if not video_url and not local_video_file:
        return False
    show_video_in_dock(
        source_card_id,
        video_url,
        target,
        local_video_file,
        target_subtitle_file=str((media or {}).get("target_subtitle_file") or ""),
        target_subtitle_label=str((media or {}).get("target_subtitle_label") or ""),
        reference_subtitle_file=str((media or {}).get("reference_subtitle_file") or ""),
        reference_subtitle_label=str((media or {}).get("reference_subtitle_label") or ""),
        preserve_loaded=True,
    )
    return True


def _schedule_video_extract_position_restores(
    card_id: int | None,
    position_sec: float,
    *,
    ttl_sec: float = 60.0,
) -> None:
    for delay_ms in (0, 250, 900, 1800, 3500):
        try:
            QTimer.singleShot(
                delay_ms,
                lambda cid=card_id, sec=position_sec, ttl=ttl_sec: _restore_video_extract_position(
                    cid,
                    sec,
                    ttl_sec=ttl,
                ),
            )
        except Exception:
            pass


def _should_preserve_for_recent_video_extract(non_video_card_id: int | None) -> bool:
    if time.monotonic() >= float(_recent_video_extract_until or 0.0):
        return False
    try:
        card_id = int(non_video_card_id) if non_video_card_id is not None else None
    except Exception:
        card_id = None
    if card_id is not None and card_id in _recent_video_extract_child_card_ids:
        return True
    if _recent_video_extract_child_card_ids:
        return False
    try:
        return (
            _current_video_card_id is not None
            and _recent_video_extract_source_card_id is not None
            and int(_current_video_card_id) == int(_recent_video_extract_source_card_id)
        )
    except Exception:
        return False


def on_video_extract_note_added(source_card_id, created_card_ids=None) -> None:
    global _recent_video_extract_child_card_ids
    try:
        source_id = int(source_card_id)
    except Exception:
        return
    children = set(_recent_video_extract_child_card_ids or set())
    for raw_card_id in list(created_card_ids or []):
        try:
            children.add(int(raw_card_id))
        except Exception:
            pass
    _recent_video_extract_child_card_ids = children
    target = _arm_video_extract_position_protection(
        source_id,
        float(_recent_video_extract_position_sec or _last_known_position or 0.0),
        ttl_sec=60.0,
    )
    if target > 0.0:
        _schedule_video_extract_position_restores(source_id, target, ttl_sec=60.0)


def _start_video_timer() -> None:
    global _video_timer, _video_tick_count
    _video_tick_count = 0
    if _video_timer is not None:
        try:
            _video_timer.stop()
        except RuntimeError:
            pass
    _video_timer = QTimer()
    _video_timer.setInterval(1000)
    _video_timer.timeout.connect(_video_timer_tick)
    _video_timer.start()


def _video_timer_tick() -> None:
    global _local_resume_attempts, _remote_resume_attempts
    if _video_dock is None or _current_video_card_id is None:
        return
    if _using_local_qt_player:
        player = getattr(_video_dock, "_local_player", None)
        if player is not None:
            try:
                pos_ms = int(player.position())
                if _local_resume_pending and pos_ms <= 0 and _local_resume_ms > 0:
                    if _local_resume_attempts < 12:
                        try:
                            player.setPosition(_local_resume_ms)
                            player.pause()
                        except Exception:
                            pass
                        _local_resume_attempts += 1
                dur_ms = 0
                try:
                    dur_ms = int(player.duration())
                except Exception:
                    dur_ms = 0
                _on_video_time(
                    {
                        "currentTime": float(pos_ms) / 1000.0,
                        "duration": (float(dur_ms) / 1000.0) if dur_ms > 0 else None,
                        "hasVideo": True,
                        "readyState": 4,
                        "networkState": 1,
                        "errorCode": 0,
                    }
                )
            except Exception:
                pass
            return
    if _remote_resume_target > 0.0 and _remote_resume_attempts < 12:
        # Force resume for web players that ignore initial URL timestamp.
        try:
            _seek_to_seconds(_remote_resume_target)
        except Exception:
            pass
        _remote_resume_attempts += 1
    try:
        _video_dock._view.page().runJavaScript(_PLAYBACK_STATUS_JS, _on_video_time)
    except (RuntimeError, AttributeError):
        pass


def _on_video_time(t) -> None:
    global _video_tick_count, _local_fallback_done, _last_known_position
    global _local_resume_pending, _local_resume_attempts, _browser_sync_pending
    global _last_known_duration, _position_lock_card_id
    global _position_lock_until, _position_lock_sec
    global _remote_resume_target, _remote_resume_attempts
    if _video_dock is None:
        return
    status = t if isinstance(t, dict) else {}
    current_time = status.get("currentTime", t if not isinstance(t, dict) else 0)
    try:
        t = float(current_time or 0)
    except Exception:
        t = 0.0
    if (
        _position_lock_card_id is not None
        and _current_video_card_id == _position_lock_card_id
        and time.monotonic() < float(_position_lock_until or 0.0)
    ):
        lock_sec = max(0.0, float(_position_lock_sec or 0.0))
        if t + 1.0 < lock_sec:
            try:
                _seek_to_seconds(lock_sec)
            except Exception:
                pass
            t = lock_sec
        else:
            _position_lock_card_id = None
            _position_lock_until = 0.0
            _position_lock_sec = 0.0
    if t > 0:
        _last_known_position = t
    if _remote_resume_target > 0.0 and t >= (_remote_resume_target - 1.0):
        _remote_resume_target = 0.0
        _remote_resume_attempts = 0
    if _using_local_qt_player and _local_resume_pending and t > 0:
        _local_resume_pending = False
        _local_resume_attempts = 0
    err_code = int(status.get("errorCode", 0) or 0)
    ready_state = int(status.get("readyState", 0) or 0)
    network_state = int(status.get("networkState", 0) or 0)
    has_video = bool(status.get("hasVideo", True))
    raw_dur = status.get("duration", None)
    try:
        dur = float(raw_dur) if raw_dur is not None else 0.0
    except Exception:
        dur = 0.0
    if dur > 0 and math.isfinite(dur):
        _last_known_duration = dur
    duration_for_ui = _last_known_duration if _last_known_duration > 0 else None

    if _current_local_relpath and not _local_fallback_done and not _using_local_qt_player:
        # Explicit media failure only.
        # HTMLMediaElement.networkState == 3 means NETWORK_NO_SOURCE.
        failed_decode = err_code > 0 or (has_video and ready_state == 0 and network_state == 3)
        if failed_decode:
            _local_fallback_done = True
            if is_supported_video_url(_current_video_url):
                tooltip("Incremento: local video failed to decode, falling back to URL stream.")
                show_video_in_dock(_current_video_card_id, _current_video_url, t, "")
                return
            tooltip(
                "Incremento: local video failed to decode in Anki. "
                "Re-download with ffmpeg for H.264 compatibility."
            )

    disp_t = t
    if _using_local_qt_player and _local_resume_pending and t <= 0.0 and _local_resume_ms > 0:
        disp_t = float(_local_resume_ms) / 1000.0
    elif (not _using_local_qt_player) and t <= 0.0 and _last_known_position > 0.0:
        # Keep UI stable while remote/web player initializes currentTime reporting.
        disp_t = float(_last_known_position)
    _set_seek_ui(disp_t, duration_for_ui)
    _video_tick_count += 1
    if _video_tick_count >= 5 and _current_video_card_id:
        _video_tick_count = 0
        if _browser_sync_pending:
            return
        if _using_local_qt_player and _local_resume_pending and t <= 0.0:
            return
        if _current_local_relpath and t <= 0.0:
            return
        persist_t = t if t > 0.0 else float(_last_known_position or 0.0)
        if persist_t <= 0.0:
            return
        try:
            set_video_position(_ADDON_DIR, _active_profile(), _current_video_card_id, persist_t)
        except Exception:
            pass


def _video_add_card_at_point() -> None:
    if _video_dock is None or _current_video_card_id is None:
        return
    if _using_local_qt_player:
        player = getattr(_video_dock, "_local_player", None)
        if player is not None:
            try:
                _do_video_add_card(float(player.position()) / 1000.0)
                return
            except Exception:
                pass
    try:
        _video_dock._view.page().runJavaScript(_CURRENT_TIME_JS, _do_video_add_card)
    except (RuntimeError, AttributeError):
        pass


def _on_local_player_error(*_args) -> None:
    global _local_fallback_done
    if _video_dock is None or _current_video_card_id is None:
        return
    if not _current_local_relpath or _local_fallback_done:
        return
    _local_fallback_done = True
    player = getattr(_video_dock, "_local_player", None)
    t = 0.0
    if player is not None:
        try:
            t = float(player.position()) / 1000.0
        except Exception:
            t = 0.0
    tooltip("Incremento: local video failed to play in Anki Qt player.")


_USER_TIME_HMS_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def _parse_user_time_seconds(text: str) -> int | None:
    raw = (text or "").strip().lower()
    if not raw:
        return None
    raw = raw.replace(" ", "")
    if raw.isdigit():
        return max(0, int(raw))
    if raw.endswith("s") and raw[:-1].isdigit():
        return max(0, int(raw[:-1]))
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            return int(parts[0]) * 60 + int(parts[1])
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return None
    m = _USER_TIME_HMS_RE.fullmatch(raw)
    if m and any(m.groups()):
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        return h * 3600 + mi * 60 + s
    return None


def _split_hms(total_seconds: int) -> tuple[int, int, int]:
    t = max(0, int(total_seconds or 0))
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return h, m, s


def _show_browser_stop_time_dialog(default_sec: int) -> tuple[bool, int]:
    dlg = QDialog(mw)
    dlg.setWindowTitle("Sync Browser Stop Time")
    layout = QVBoxLayout(dlg)

    prompt = QLabel("Where did you stop in browser?")
    layout.addWidget(prompt)

    raw_row = QHBoxLayout()
    raw_edit = QLineEdit(fmt_time(float(default_sec)))
    raw_edit.setPlaceholderText("12:34 or 1h2m3s")
    raw_apply = QPushButton("Apply")
    raw_row.addWidget(raw_edit, 1)
    raw_row.addWidget(raw_apply)
    layout.addLayout(raw_row)

    h, m, s = _split_hms(default_sec)
    h_spin = QSpinBox()
    h_spin.setRange(0, 999)
    h_spin.setValue(h)
    h_spin.setSuffix(" h")
    m_spin = QSpinBox()
    m_spin.setRange(0, 59)
    m_spin.setValue(m)
    m_spin.setSuffix(" m")
    s_spin = QSpinBox()
    s_spin.setRange(0, 59)
    s_spin.setValue(s)
    s_spin.setSuffix(" s")

    hms_row = QHBoxLayout()
    hms_row.addWidget(h_spin)
    hms_row.addWidget(m_spin)
    hms_row.addWidget(s_spin)
    hms_row.addStretch()
    layout.addLayout(hms_row)

    quick_row = QHBoxLayout()
    minus_10 = QPushButton("−10s")
    plus_10 = QPushButton("+10s")
    plus_1m = QPushButton("+1m")
    plus_5m = QPushButton("+5m")
    quick_row.addWidget(minus_10)
    quick_row.addWidget(plus_10)
    quick_row.addWidget(plus_1m)
    quick_row.addWidget(plus_5m)
    quick_row.addStretch()
    layout.addLayout(quick_row)

    status_lbl = QLabel("")
    layout.addWidget(status_lbl)

    def _total_from_spins() -> int:
        return int(h_spin.value()) * 3600 + int(m_spin.value()) * 60 + int(s_spin.value())

    def _set_from_total(total: int, update_raw: bool = True) -> None:
        hh, mm, ss = _split_hms(total)
        h_spin.setValue(hh)
        m_spin.setValue(mm)
        s_spin.setValue(ss)
        if update_raw:
            raw_edit.setText(fmt_time(float(total)))
        status_lbl.setText(f"Result: {fmt_time(float(total))} ({int(total)}s)")

    def _apply_raw_text() -> None:
        parsed = _parse_user_time_seconds(raw_edit.text())
        if parsed is None:
            status_lbl.setText("Invalid format. Use 12:34, 1:02:03, 1h2m3s, or seconds.")
            return
        _set_from_total(parsed, update_raw=True)

    def _nudge(delta: int) -> None:
        _set_from_total(max(0, _total_from_spins() + int(delta)), update_raw=True)

    qconnect(raw_apply.clicked, _apply_raw_text)
    qconnect(raw_edit.returnPressed, _apply_raw_text)
    qconnect(minus_10.clicked, lambda: _nudge(-10))
    qconnect(plus_10.clicked, lambda: _nudge(10))
    qconnect(plus_1m.clicked, lambda: _nudge(60))
    qconnect(plus_5m.clicked, lambda: _nudge(300))
    qconnect(h_spin.valueChanged, lambda _v: _set_from_total(_total_from_spins(), update_raw=False))
    qconnect(m_spin.valueChanged, lambda _v: _set_from_total(_total_from_spins(), update_raw=False))
    qconnect(s_spin.valueChanged, lambda _v: _set_from_total(_total_from_spins(), update_raw=False))

    _set_from_total(default_sec, update_raw=True)

    button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    qconnect(button_box.accepted, dlg.accept)
    qconnect(button_box.rejected, dlg.reject)
    layout.addWidget(button_box)

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False, int(default_sec)
    parsed = _parse_user_time_seconds(raw_edit.text())
    if parsed is not None:
        return True, int(parsed)
    return True, _total_from_spins()


def _open_video_in_browser() -> None:
    if _video_dock is None or _current_video_card_id is None:
        return
    if _using_local_qt_player:
        player = getattr(_video_dock, "_local_player", None)
        sec = 0.0
        if player is not None:
            try:
                sec = float(player.position()) / 1000.0
            except Exception:
                sec = 0.0
        _open_video_in_browser_at_seconds(sec)
        return
    try:
        _video_dock._view.page().runJavaScript(_CURRENT_TIME_JS, _open_video_in_browser_at_seconds)
    except Exception:
        _open_video_in_browser_at_seconds(_last_known_position)


def _open_video_in_browser_at_seconds(seconds) -> None:
    global _browser_sync_pending, _browser_sync_wait_bg
    global _browser_sync_card_id, _browser_sync_seed_sec, _last_known_position

    if _current_video_card_id is None:
        return
    try:
        sec = max(0, int(float(seconds or 0.0)))
    except Exception:
        sec = max(0, int(float(_last_known_position or 0.0)))
    watch_url = build_remote_video_watch_url(
        _current_video_url,
        start_sec=sec,
        card_id=int(_current_video_card_id),
    )
    if not watch_url:
        tooltip("Incremento: no remote URL is available for browser fallback.")
        return
    try:
        set_video_position(_ADDON_DIR, _active_profile(), _current_video_card_id, float(sec))
    except Exception:
        pass
    _last_known_position = float(sec)

    try:
        ok = bool(QDesktopServices.openUrl(QUrl(watch_url)))
    except Exception:
        ok = False
    if not ok:
        tooltip("Incremento: failed to open system browser.")
        return

    _browser_sync_pending = True
    _browser_sync_wait_bg = True
    _browser_sync_card_id = int(_current_video_card_id)
    _browser_sync_seed_sec = sec


class _VideoCaptionDialog(QDialog):
    def __init__(self, *, parent=None):
        super().__init__(parent or mw)
        self.setWindowTitle("Video Captions")
        self.setMinimumWidth(520)
        self._tracks: list[dict] = []

        note = _current_video_note()
        media = get_video_note_media(note) if note is not None else {}
        self._video_url = ""
        if note is not None:
            try:
                self._video_url = str(note["YouTube_URL"] or "").strip()
            except Exception:
                self._video_url = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        intro = QLabel(
            "Choose target and reference subtitles for this video card. "
            "Remote subtitles can be fetched with yt-dlp; manual .srt/.vtt files are also supported."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._current_target = QLabel("")
        self._current_reference = QLabel("")
        self._current_target.setWordWrap(True)
        self._current_reference.setWordWrap(True)
        layout.addWidget(self._current_target)
        layout.addWidget(self._current_reference)

        remote_row = QHBoxLayout()
        remote_row.addWidget(QLabel("Available remote tracks:"))
        self._refresh_btn = QPushButton("Refresh")
        remote_row.addStretch()
        remote_row.addWidget(self._refresh_btn)
        layout.addLayout(remote_row)

        self._remote_hint = QLabel("")
        self._remote_hint.setWordWrap(True)
        self._remote_hint.setStyleSheet("font-size: 11px; color: #9aa0a6;")
        layout.addWidget(self._remote_hint)

        self._target_combo = QComboBox()
        self._reference_combo = QComboBox()
        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target track:"))
        target_row.addWidget(self._target_combo, 1)
        self._download_target_btn = QPushButton("Download To Target")
        target_row.addWidget(self._download_target_btn)
        layout.addLayout(target_row)

        reference_row = QHBoxLayout()
        reference_row.addWidget(QLabel("Reference track:"))
        reference_row.addWidget(self._reference_combo, 1)
        self._download_reference_btn = QPushButton("Download To Reference")
        reference_row.addWidget(self._download_reference_btn)
        layout.addLayout(reference_row)

        manual_row = QHBoxLayout()
        self._import_target_btn = QPushButton("Import Target File…")
        self._import_reference_btn = QPushButton("Import Reference File…")
        self._clear_target_btn = QPushButton("Clear Target")
        self._clear_reference_btn = QPushButton("Clear Reference")
        manual_row.addWidget(self._import_target_btn)
        manual_row.addWidget(self._import_reference_btn)
        manual_row.addWidget(self._clear_target_btn)
        manual_row.addWidget(self._clear_reference_btn)
        layout.addLayout(manual_row)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        qconnect(close_box.rejected, self.reject)
        qconnect(close_box.accepted, self.accept)
        layout.addWidget(close_box)

        qconnect(self._refresh_btn.clicked, self._refresh_tracks)
        qconnect(self._download_target_btn.clicked, lambda: self._download_track("target"))
        qconnect(self._download_reference_btn.clicked, lambda: self._download_track("reference"))
        qconnect(self._import_target_btn.clicked, lambda: self._import_manual("target"))
        qconnect(self._import_reference_btn.clicked, lambda: self._import_manual("reference"))
        qconnect(self._clear_target_btn.clicked, lambda: self._clear_slot("target"))
        qconnect(self._clear_reference_btn.clicked, lambda: self._clear_slot("reference"))

        self._refresh_current_labels(media)
        self._populate_track_combos([])
        self._refresh_tracks()

    def _refresh_current_labels(self, media: dict | None = None) -> None:
        current = media or get_video_note_media(_current_video_note())
        target_label = str(current.get("target_subtitle_label") or "").strip()
        target_file = str(current.get("target_subtitle_file") or "").strip()
        reference_label = str(current.get("reference_subtitle_label") or "").strip()
        reference_file = str(current.get("reference_subtitle_file") or "").strip()
        self._current_target.setText(
            f"Target: {target_label or 'Not set'}"
            + (f"  [{target_file}]" if target_file else "")
        )
        self._current_reference.setText(
            f"Reference: {reference_label or 'Not set'}"
            + (f"  [{reference_file}]" if reference_file else "")
        )

    def _populate_track_combos(self, tracks: list[dict]) -> None:
        self._tracks = list(tracks or [])
        for combo in (self._target_combo, self._reference_combo):
            combo.clear()
            combo.addItem("Select a track…", "")
            for track in self._tracks:
                combo.addItem(str(track.get("label") or ""), str(track.get("track_id") or ""))
        has_tracks = bool(self._tracks)
        self._download_target_btn.setEnabled(has_tracks)
        self._download_reference_btn.setEnabled(has_tracks)

    def _track_for_combo(self, combo: QComboBox) -> dict | None:
        track_id = str(combo.currentData() or "").strip()
        if not track_id:
            return None
        for track in self._tracks:
            if str(track.get("track_id") or "") == track_id:
                return dict(track)
        return None

    def _refresh_tracks(self) -> None:
        if not self._video_url or not is_supported_video_url(self._video_url):
            self._remote_hint.setText(
                "This card has no supported remote URL. You can still attach manual subtitle files."
            )
            self._populate_track_combos([])
            return

        self._refresh_btn.setEnabled(False)
        self._remote_hint.setText("Loading remote subtitle tracks…")

        def _task():
            return list_available_video_subtitles(_ADDON_DIR, _active_profile(), self._video_url)

        def _on_done(fut) -> None:
            self._refresh_btn.setEnabled(True)
            try:
                tracks = fut.result()
            except Exception as exc:
                self._populate_track_combos([])
                self._remote_hint.setText(f"Could not load subtitles: {exc}")
                return
            self._populate_track_combos(tracks)
            if tracks:
                self._remote_hint.setText(
                    f"Found {len(tracks)} remote subtitle track(s). Download one into target or reference."
                )
            else:
                self._remote_hint.setText(
                    "No remote subtitle tracks were found. You can still import manual subtitle files."
                )

        mw.taskman.run_in_background(_task, _on_done)

    def _apply_slot(self, slot: str, *, relpath: str, label: str) -> None:
        slot_name = str(slot or "").strip().lower()
        updates = {}
        if slot_name == "target":
            updates = {
                "target_subtitle_file": relpath,
                "target_subtitle_label": label,
            }
        elif slot_name == "reference":
            updates = {
                "reference_subtitle_file": relpath,
                "reference_subtitle_label": label,
            }
        if not updates:
            return
        if _persist_current_video_note_media(**updates):
            self._refresh_current_labels()
            _reload_current_video_card()

    def _download_track(self, slot: str) -> None:
        combo = self._target_combo if slot == "target" else self._reference_combo
        track = self._track_for_combo(combo)
        if track is None:
            tooltip("Incremento: select a subtitle track first.")
            return
        if not self._video_url:
            tooltip("Incremento: this video card has no remote URL.")
            return
        label = str(track.get("label") or "").strip()
        language = str(track.get("language") or "").strip()
        automatic = bool(track.get("automatic"))
        self._remote_hint.setText(f"Downloading {label}…")

        note = _current_video_note()
        preferred_stem = ""
        if note is not None:
            try:
                preferred_stem = str(note["Title"] or "").strip()
            except Exception:
                preferred_stem = ""

        def _task():
            return download_video_subtitle(
                _ADDON_DIR,
                _active_profile(),
                self._video_url,
                language=language,
                automatic=automatic,
            )

        def _on_done(fut) -> None:
            try:
                result = fut.result()
            except Exception as exc:
                self._remote_hint.setText(f"Subtitle download failed: {exc}")
                return
            relpath = str(result.get("relpath") or "").strip()
            applied_label = str(result.get("label") or label or language).strip()
            self._apply_slot(slot, relpath=relpath, label=applied_label)
            self._remote_hint.setText(f"Saved {applied_label} to {slot}.")

        mw.taskman.run_in_background(_task, _on_done)

    def _import_manual(self, slot: str) -> None:
        exts = supported_subtitle_extensions()
        patterns = " ".join(f"*{ext}" for ext in exts)
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Choose {slot.title()} Subtitle",
            "",
            f"Subtitle files ({patterns});;All files (*)",
        )
        if not path:
            return
        note = _current_video_note()
        preferred_stem = ""
        if note is not None:
            try:
                preferred_stem = str(note["Title"] or "").strip()
            except Exception:
                preferred_stem = ""
        try:
            relpath = import_local_subtitle_file(
                _ADDON_DIR,
                _active_profile(),
                path,
                preferred_stem=f"{preferred_stem or 'video'}-{slot}",
            )
        except Exception as exc:
            tooltip(f"Incremento: could not import subtitle file ({exc}).")
            return
        label = os.path.basename(path)
        self._apply_slot(slot, relpath=relpath, label=label)
        self._remote_hint.setText(f"Imported {label} into {slot}.")

    def _clear_slot(self, slot: str) -> None:
        self._apply_slot(slot, relpath="", label="")
        self._remote_hint.setText(f"Cleared {slot} subtitles.")


def _reload_current_video_card() -> None:
    card = _current_video_card()
    note = _current_video_note()
    if card is None or note is None:
        return
    media = get_video_note_media(note)
    try:
        youtube_url = str(note["YouTube_URL"] or "").strip()
    except Exception:
        youtube_url = ""
    show_video_in_dock(
        int(card.id),
        youtube_url,
        float(_last_known_position or 0.0),
        media.get("local_video_file") or "",
        target_subtitle_file=media.get("target_subtitle_file") or "",
        target_subtitle_label=media.get("target_subtitle_label") or "",
        reference_subtitle_file=media.get("reference_subtitle_file") or "",
        reference_subtitle_label=media.get("reference_subtitle_label") or "",
    )


def configure_current_video_captions() -> None:
    note = _current_video_note()
    if note is None:
        tooltip("Incremento: no active video card.")
        return
    dlg = _VideoCaptionDialog(parent=mw)
    dlg.exec()


def download_current_video_locally() -> None:
    note = _current_video_note()
    if note is None:
        tooltip("Incremento: no active video card.")
        return
    try:
        video_url = str(note["YouTube_URL"] or "").strip()
    except Exception:
        video_url = ""
    if not is_supported_video_url(video_url):
        tooltip("Incremento: this video card has no supported remote URL.")
        return

    current_media = get_video_note_media(note)
    has_existing_local = bool(current_media.get("local_video_file"))
    _set_download_button_enabled(False, has_local_copy=has_existing_local)

    try:
        mw.progress.start(
            label=(
                "Re-downloading local video copy…"
                if has_existing_local
                else "Downloading local video copy…"
            ),
            immediate=True,
            value=0,
            max=100,
        )
    except TypeError:
        mw.progress.start(
            label=(
                "Re-downloading local video copy…"
                if has_existing_local
                else "Downloading local video copy…"
            ),
            immediate=True,
        )

    def _progress_main(percent: int, label: str) -> None:
        try:
            mw.progress.update(label=label, value=int(percent), max=100)
        except TypeError:
            mw.progress.update(label=label)

    def _progress_cb(percent: int, label: str) -> None:
        mw.taskman.run_on_main(lambda p=percent, l=label: _progress_main(p, l))

    def _task():
        return download_and_compress_video(
            _ADDON_DIR,
            _active_profile(),
            video_url,
            progress_cb=_progress_cb,
        )

    def _on_done(fut) -> None:
        mw.progress.finish()
        _set_download_button_enabled(True, has_local_copy=has_existing_local)
        try:
            local_relpath = fut.result()
        except Exception as exc:
            tooltip(f"Incremento: local download failed ({exc}).")
            return
        if not _persist_current_video_note_media(local_video_file=local_relpath):
            tooltip("Incremento: video downloaded, but the card could not be updated.")
            return
        tooltip("Incremento: local video copy is ready.")
        _reload_current_video_card()

    mw.taskman.run_in_background(_task, _on_done)


def _on_application_state_changed(state) -> None:
    global _browser_sync_wait_bg
    if not _browser_sync_pending:
        return
    if state != Qt.ApplicationState.ApplicationActive:
        _browser_sync_wait_bg = False
        return
    if _browser_sync_wait_bg:
        return
    _prompt_browser_stop_time()


def _prompt_browser_stop_time() -> None:
    global _browser_sync_pending, _browser_sync_card_id, _browser_sync_seed_sec
    global _last_known_position
    global _position_lock_card_id, _position_lock_until, _position_lock_sec
    if not _browser_sync_pending:
        return

    raw_card_id = _browser_sync_card_id
    raw_seed = _browser_sync_seed_sec
    _browser_sync_pending = False
    _browser_sync_card_id = None
    _browser_sync_seed_sec = 0

    if raw_card_id is None:
        return
    try:
        card_id = int(raw_card_id)
    except Exception:
        return

    ok, sec = _show_browser_stop_time_dialog(int(raw_seed or 0))
    if not ok:
        return
    try:
        set_video_position(_ADDON_DIR, _active_profile(), card_id, float(sec))
    except Exception:
        return
    if _current_video_card_id == card_id:
        _last_known_position = float(sec)
        _position_lock_card_id = int(card_id)
        _position_lock_sec = float(sec)
        _position_lock_until = time.monotonic() + 8.0
        _seek_to_seconds(float(sec))
        _set_seek_ui(float(sec), _last_known_duration if _last_known_duration > 0 else None)
    tooltip(f"Incremento: saved browser stop time at {fmt_time(float(sec))}.")


def _do_video_add_card(t) -> None:
    global _last_known_position
    global _position_lock_card_id, _position_lock_until, _position_lock_sec

    raw_t = float(t or 0)
    persisted_t = 0.0
    if _current_video_card_id is not None:
        try:
            persisted_t = float(
                get_video_position(_ADDON_DIR, _active_profile(), _current_video_card_id) or 0.0
            )
        except Exception:
            persisted_t = 0.0

    if raw_t > 0:
        _last_known_position = raw_t
    t = max(raw_t, float(_last_known_position or 0.0), persisted_t)
    if _current_video_card_id is None:
        return
    if t > 0:
        _last_known_position = t
        _position_lock_card_id = int(_current_video_card_id)
        _position_lock_sec = float(t)
        _position_lock_until = time.monotonic() + 8.0
        _set_seek_ui(t, _last_known_duration if _last_known_duration > 0 else None)
        _arm_video_extract_position_protection(
            int(_current_video_card_id),
            t,
            ttl_sec=60.0,
        )
        _schedule_video_extract_position_restores(
            int(_current_video_card_id),
            t,
            ttl_sec=60.0,
        )
    ts = fmt_time(t)
    try:
        note = mw.col.get_card(_current_video_card_id).note()
        title = note.fields[0][:60].strip() if note.fields else ""
    except Exception:
        title = ""
    label = f"&#9654; {ts}" + (f" \u2013 {title}" if title else "")
    link = (
        f'<a href="#" onclick="pycmd(\'incremento_open_video:{_current_video_card_id}:{t}\')" '
        f'style="color:#4a90d9;">{label}</a>'
    )
    try:
        from .add_card_dock import (
            fill_dock_field,
            set_pending_extract_options,
            source_relative_extract_priority_for_source,
        )
    except Exception:
        from add_card_dock import (  # type: ignore
            fill_dock_field,
            set_pending_extract_options,
            source_relative_extract_priority_for_source,
        )

    fill_dock_field(0, link, include_pdf_citation=False, source_link_kind="video")
    set_pending_extract_options(
        priority=source_relative_extract_priority_for_source("video"),
        mark_topic=False,
        source="video",
        source_card_id=_current_video_card_id,
    )


def on_video_question_shown(card) -> None:
    global _video_dock, _video_timer, _current_local_relpath, _current_video_url
    global _local_fallback_done, _using_local_qt_player, _current_video_card_id
    global _local_resume_pending, _local_resume_ms, _local_resume_attempts
    global _last_known_position
    global _last_known_duration, _browser_sync_pending, _browser_sync_wait_bg
    global _browser_sync_card_id, _browser_sync_seed_sec
    global _position_lock_card_id, _position_lock_until, _position_lock_sec
    global _remote_resume_target, _remote_resume_attempts
    global _using_local_web_player
    global _current_target_subtitle_relpath, _current_target_subtitle_label
    global _current_reference_subtitle_relpath, _current_reference_subtitle_label
    try:
        if card is None:
            return
        try:
            note  = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != VIDEO_NOTE_TYPE:
            if _should_preserve_for_recent_video_extract(getattr(card, "id", None)):
                _restore_video_extract_position(
                    _recent_video_extract_source_card_id,
                    _recent_video_extract_position_sec,
                    ttl_sec=60.0,
                )
                return
            _persist_position_now()
            _current_local_relpath = ""
            _current_video_url = ""
            _local_fallback_done = False
            _using_local_qt_player = False
            _using_local_web_player = False
            _local_resume_pending = False
            _local_resume_ms = 0
            _local_resume_attempts = 0
            _last_known_duration = 0.0
            _current_video_card_id = None
            _browser_sync_pending = False
            _browser_sync_wait_bg = False
            _browser_sync_card_id = None
            _browser_sync_seed_sec = 0
            _position_lock_card_id = None
            _position_lock_until = 0.0
            _position_lock_sec = 0.0
            _remote_resume_target = 0.0
            _remote_resume_attempts = 0
            _current_target_subtitle_relpath = ""
            _current_target_subtitle_label = ""
            _current_reference_subtitle_relpath = ""
            _current_reference_subtitle_label = ""
            _set_local_controls_visible(False)
            _set_browser_button_enabled(False)
            _set_download_button_enabled(False, has_local_copy=False)
            _set_captions_button_enabled(False)
            _set_caption_controls_state(
                has_target=False,
                has_reference=False,
                use_local_player=False,
            )
            _reset_seek_ui()
            if _video_dock is not None:
                local_player = getattr(_video_dock, "_local_player", None)
                if local_player is not None:
                    try:
                        local_player.stop()
                    except Exception:
                        pass
                try:
                    _video_dock.hide()
                except RuntimeError:
                    _video_dock = None
            if _video_timer is not None:
                try:
                    _video_timer.stop()
                except RuntimeError:
                    pass
            return
        try:
            youtube_url = (note["YouTube_URL"] or "").strip()
        except (KeyError, TypeError):
            return
        try:
            media = get_video_note_media(note)
            local_video_file = str(media.get("local_video_file") or "").strip()
        except Exception:
            media = {}
            local_video_file = ""
        # Fallback for malformed cards where URL was accidentally saved in Title.
        # Skip this when local video exists: local playback does not need the URL.
        if not youtube_url and not local_video_file:
            try:
                title_text = (note["Title"] or "").strip()
            except Exception:
                title_text = ""
            if is_supported_video_url(title_text):
                youtube_url = title_text
            else:
                if _video_dock is not None:
                    try:
                        _video_dock.hide()
                    except RuntimeError:
                        _video_dock = None
                return
        position = float(get_video_position(_ADDON_DIR, _active_profile(), card.id) or 0.0)
        preserve_loaded = (
            _current_video_card_id is not None
            and int(card.id) == int(_current_video_card_id)
        )
        if preserve_loaded:
            position = max(position, float(_last_known_position or 0.0))
            if (
                _position_lock_card_id is not None
                and int(_position_lock_card_id) == int(card.id)
                and time.monotonic() < float(_position_lock_until or 0.0)
            ):
                position = max(position, float(_position_lock_sec or 0.0))
        try:
            url_position = float(extract_start_seconds(youtube_url) or 0.0)
        except Exception:
            url_position = 0.0
        # If URL timestamp was externally updated (e.g., browser extension via
        # AnkiConnect), honor it and sync DB so resume is deterministic.
        if url_position > 0.0 and abs(url_position - position) >= 1.0:
            position = url_position
            try:
                set_video_position(_ADDON_DIR, _active_profile(), card.id, position)
            except Exception:
                pass
        show_video_in_dock(
            card.id,
            youtube_url,
            position,
            local_video_file,
            target_subtitle_file=str(media.get("target_subtitle_file") or ""),
            target_subtitle_label=str(media.get("target_subtitle_label") or ""),
            reference_subtitle_file=str(media.get("reference_subtitle_file") or ""),
            reference_subtitle_label=str(media.get("reference_subtitle_label") or ""),
            preserve_loaded=preserve_loaded,
        )
    except Exception as e:
        print(f"[Incremento] on_video_question_shown error: {e}")


def on_video_reviewer_will_end() -> None:
    global _video_dock, _video_timer, _current_local_relpath, _current_video_url
    global _local_fallback_done, _using_local_qt_player, _current_video_card_id
    global _local_resume_pending, _local_resume_ms, _local_resume_attempts
    global _last_known_duration, _browser_sync_pending, _browser_sync_wait_bg
    global _browser_sync_card_id, _browser_sync_seed_sec
    global _position_lock_card_id, _position_lock_until, _position_lock_sec
    global _remote_resume_target, _remote_resume_attempts
    global _using_local_web_player
    global _current_target_subtitle_relpath, _current_target_subtitle_label
    global _current_reference_subtitle_relpath, _current_reference_subtitle_label
    _persist_position_now()
    _current_local_relpath = ""
    _current_video_url = ""
    _local_fallback_done = False
    _using_local_qt_player = False
    _using_local_web_player = False
    _local_resume_pending = False
    _local_resume_ms = 0
    _local_resume_attempts = 0
    _last_known_duration = 0.0
    _current_video_card_id = None
    _browser_sync_pending = False
    _browser_sync_wait_bg = False
    _browser_sync_card_id = None
    _browser_sync_seed_sec = 0
    _position_lock_card_id = None
    _position_lock_until = 0.0
    _position_lock_sec = 0.0
    _remote_resume_target = 0.0
    _remote_resume_attempts = 0
    _current_target_subtitle_relpath = ""
    _current_target_subtitle_label = ""
    _current_reference_subtitle_relpath = ""
    _current_reference_subtitle_label = ""
    _set_local_controls_visible(False)
    _set_browser_button_enabled(False)
    _set_download_button_enabled(False, has_local_copy=False)
    _set_captions_button_enabled(False)
    _set_caption_controls_state(
        has_target=False,
        has_reference=False,
        use_local_player=False,
    )
    _reset_seek_ui()
    if _video_timer is not None:
        try:
            _video_timer.stop()
        except RuntimeError:
            pass
        _video_timer = None
    if _video_dock is not None:
        local_player = getattr(_video_dock, "_local_player", None)
        if local_player is not None:
            try:
                local_player.stop()
            except Exception:
                pass
        try:
            _video_dock.hide()
        except RuntimeError:
            _video_dock = None


def sync_video_note_type() -> None:
    try:
        ensure_video_note_type(mw.col)
    except Exception:
        pass


def flush_video_progress(*_args, **_kwargs) -> None:
    """Best-effort save hook for app/profile shutdown."""
    try:
        _persist_position_now()
    except Exception:
        pass
