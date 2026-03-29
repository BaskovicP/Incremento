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
                    QSpinBox, QDialogButtonBox)
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
    from ..backend.video_manager import (
        VIDEO_NOTE_TYPE,
        build_remote_video_watch_url,
        detect_video_provider,
        resolve_video_url_for_embed,
        is_supported_video_url,
        fmt_time,
        get_video_position,
        set_video_position,
        ensure_video_note_type,
        local_video_abspath,
    )
except ImportError:
    from video_manager import (
        VIDEO_NOTE_TYPE,
        build_remote_video_watch_url,
        detect_video_provider,
        resolve_video_url_for_embed,
        is_supported_video_url,
        fmt_time,
        get_video_position,
        set_video_position,
        ensure_video_note_type,
        local_video_abspath,
    )

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
_remote_resume_target  = 0.0
_remote_resume_attempts = 0

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
        _video_profile.setPersistentStoragePath(
            os.path.join(_ADDON_DIR, "user_files", "video_profile")
        )
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
    browser_btn = QPushButton("Open in Browser")
    browser_btn.setEnabled(False)
    ctrl_layout.addWidget(browser_btn)
    vbox.addWidget(ctrl)

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
    qconnect(add_btn.clicked, _video_add_card_at_point)
    qconnect(browser_btn.clicked, _open_video_in_browser)
    qconnect(seek_slider.sliderPressed, _on_seek_slider_pressed)
    qconnect(seek_slider.sliderReleased, _on_seek_slider_released)
    qconnect(seek_slider.valueChanged, _on_seek_slider_value_changed)
    qconnect(back_btn.clicked, lambda: _local_seek(-10))
    qconnect(play_btn.clicked, _toggle_local_playback)
    qconnect(fwd_btn.clicked, lambda: _local_seek(10))
    qconnect(rate_combo.currentTextChanged, _set_local_rate)
    qconnect(vol_slider.valueChanged, _set_local_volume)
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


def _local_video_html(video_src: str, mime_type: str, start_sec: int) -> str:
    src = html.escape(video_src, quote=True)
    mime = html.escape(mime_type or "video/mp4", quote=True)
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {{ margin:0; padding:0; background:#000; width:100%; height:100%; overflow:hidden; }}
#player {{ width:100vw; height:100vh; background:#000; }}
</style>
</head>
<body>
<video id="player" controls playsinline>
  <source src="{src}" type="{mime}">
</video>
<script>
const startSec = {max(0, int(start_sec))};
const v = document.getElementById("player");
v.addEventListener("loadedmetadata", () => {{
  if (startSec > 0) {{
    try {{ v.currentTime = startSec; }} catch (_e) {{}}
  }}
}});
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
            set_video_position(_ADDON_DIR, _current_video_card_id, target)
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
        set_video_position(_ADDON_DIR, _current_video_card_id, t)
    except Exception:
        pass


def show_video_in_dock(
    card_id: int,
    video_url: str,
    position: float = 0.0,
    local_video_file: str = "",
) -> None:
    global _video_dock, _current_video_card_id, _current_video_url
    global _current_local_relpath, _local_fallback_done, _using_local_qt_player
    global _last_known_position, _local_resume_pending, _local_resume_ms
    global _local_resume_attempts, _last_known_duration
    global _position_lock_card_id, _position_lock_until, _position_lock_sec
    global _remote_resume_target, _remote_resume_attempts

    normalized_url = (video_url or "").strip()
    if detect_video_provider(normalized_url) == "vimeo":
        try:
            normalized_url = resolve_video_url_for_embed(normalized_url, timeout_sec=1.5)
        except Exception:
            pass

    _current_video_card_id = card_id
    _current_video_url = normalized_url
    _last_known_position = max(0.0, float(position or 0.0))
    _last_known_duration = 0.0
    _remote_resume_target = 0.0
    _remote_resume_attempts = 0
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
    _set_browser_button_enabled(bool(build_remote_video_watch_url(_current_video_url, start_sec=0)))

    local_relpath = (local_video_file or "").strip()
    start_sec = int(position)
    if local_relpath:
        local_abs = local_video_abspath(_ADDON_DIR, local_relpath)
        if os.path.exists(local_abs):
            local_path = Path(local_abs)
            _current_local_relpath = local_relpath
            _local_fallback_done = False
            _video_dock.show()
            _video_dock.raise_()
            local_player = getattr(_video_dock, "_local_player", None)
            local_index = getattr(_video_dock, "_local_index", None)
            media_stack = getattr(_video_dock, "_media_stack", None)
            if local_player is not None and local_index is not None and media_stack is not None:
                _using_local_qt_player = True
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
            _start_video_timer()
            if _using_local_qt_player:
                return
        print(f"[Incremento] Local video missing for card {card_id}: {local_relpath!r}")

    remote_watch_url = build_remote_video_watch_url(_current_video_url, start_sec=start_sec)
    if remote_watch_url:
        url = QUrl(remote_watch_url)
        _current_local_relpath = ""
        _local_fallback_done = False
        _using_local_qt_player = False
        _local_resume_pending = False
        _local_resume_ms = 0
        _local_resume_attempts = 0
        _last_known_duration = 0.0
        _remote_resume_target = max(0.0, float(start_sec))
        _remote_resume_attempts = 0
        _set_local_controls_visible(False)
        _reset_seek_ui()
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
    print(f"[Incremento] Invalid video URL for card {card_id}: {video_url!r}")


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
            set_video_position(_ADDON_DIR, _current_video_card_id, persist_t)
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
    watch_url = build_remote_video_watch_url(_current_video_url, start_sec=sec)
    if not watch_url:
        tooltip("Incremento: no remote URL is available for browser fallback.")
        return
    try:
        set_video_position(_ADDON_DIR, _current_video_card_id, float(sec))
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
        set_video_position(_ADDON_DIR, card_id, float(sec))
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
    t = float(t or 0)
    if t > 0:
        _last_known_position = t
    if _current_video_card_id is None:
        return
    try:
        set_video_position(_ADDON_DIR, _current_video_card_id, t)
    except Exception:
        pass
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
    from .add_card_dock import fill_dock_field
    fill_dock_field(0, link)


def on_video_question_shown(card) -> None:
    global _video_dock, _video_timer, _current_local_relpath, _current_video_url
    global _local_fallback_done, _using_local_qt_player, _current_video_card_id
    global _local_resume_pending, _local_resume_ms, _local_resume_attempts
    global _last_known_duration, _browser_sync_pending, _browser_sync_wait_bg
    global _browser_sync_card_id, _browser_sync_seed_sec
    global _position_lock_card_id, _position_lock_until, _position_lock_sec
    global _remote_resume_target, _remote_resume_attempts
    try:
        if card is None:
            return
        try:
            note  = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != VIDEO_NOTE_TYPE:
            _persist_position_now()
            _current_local_relpath = ""
            _current_video_url = ""
            _local_fallback_done = False
            _using_local_qt_player = False
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
            _set_local_controls_visible(False)
            _set_browser_button_enabled(False)
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
            local_video_file = (note["Local_Video_File"] or "").strip()
        except Exception:
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
        position = get_video_position(_ADDON_DIR, card.id)
        show_video_in_dock(card.id, youtube_url, position, local_video_file)
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
    _persist_position_now()
    _current_local_relpath = ""
    _current_video_url = ""
    _local_fallback_done = False
    _using_local_qt_player = False
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
    _set_local_controls_visible(False)
    _set_browser_button_enabled(False)
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
