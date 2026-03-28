"""
video_dock.py — YouTube video dock (QWebEngineView + position tracking).

Displays YouTube videos in a right-side dock that persists across card reviews.
Position is polled every second and saved every 5 ticks to pdf_progress storage.

Public API:
    show_video_in_dock(card_id, youtube_url, position)
    on_video_question_shown(card)
    on_video_reviewer_will_end()
    sync_video_note_type()
"""

import os

from aqt import mw
from aqt.utils import tooltip
from aqt.qt import (QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
                    QPushButton, QLabel, QTimer, Qt, qconnect)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

try:
    from ..backend.video_manager import (VIDEO_NOTE_TYPE, extract_video_id, fmt_time,
                                         get_video_position, set_video_position,
                                         ensure_video_note_type)
except ImportError:
    from video_manager import (VIDEO_NOTE_TYPE, extract_video_id, fmt_time,
                                get_video_position, set_video_position,
                                ensure_video_note_type)

_ADDON_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_video_dock            = None
_current_video_card_id = None
_video_timer           = None
_video_tick_count      = 0
_video_profile         = None  # module-level singleton — avoids use-after-free on exit

_YT_CURRENT_TIME_JS = (
    "(function(){"
    "var v=document.querySelector('video');"
    "return v ? v.currentTime : 0;"
    "})()"
)


def _build_video_dock():
    global _video_dock, _video_profile

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

    view = QWebEngineView(container)

    # Module-level profile with no parent — avoids use-after-free segfault on exit
    # that occurs when the profile is parented to the view and both get destroyed.
    # Persistent named profile so YouTube login cookies survive across restarts.
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

    _page = _WEPage(_video_profile)  # no parent — profile must outlive page
    view.setPage(_page)

    vbox.addWidget(view, 1)

    ctrl = QWidget(container)
    ctrl_layout = QHBoxLayout(ctrl)
    ctrl_layout.setContentsMargins(8, 4, 8, 4)

    ts_lbl = QLabel("\u25b6  0:00")
    ts_lbl.setStyleSheet("font-family: monospace; font-size: 12px;")
    ctrl_layout.addWidget(ts_lbl)
    ctrl_layout.addStretch()

    add_btn = QPushButton("+ Add Card at this point")
    ctrl_layout.addWidget(add_btn)
    vbox.addWidget(ctrl)

    dock.setWidget(container)
    mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    dock._view   = view
    dock._ts_lbl = ts_lbl
    qconnect(add_btn.clicked, _video_add_card_at_point)

    _video_dock = dock
    return dock


def show_video_in_dock(card_id: int, youtube_url: str, position: float = 0.0) -> None:
    global _video_dock, _current_video_card_id

    _current_video_card_id = card_id

    if _video_dock is None:
        _build_video_dock()
    else:
        try:
            _video_dock.widget()
        except RuntimeError:
            _video_dock = None
            _build_video_dock()

    video_id = extract_video_id((youtube_url or "").strip())
    if not video_id:
        tooltip("Incremento: This video card has no valid YouTube URL.")
        print(f"[Incremento] Invalid YouTube URL for card {card_id}: {youtube_url!r}")
        return

    # Load the full YouTube watch page — this avoids all embed-level restrictions
    # (Error 152/153) that occur when using the IFrame API from a non-browser origin.
    start_sec = int(position)
    url = QUrl(f"https://www.youtube.com/watch?v={video_id}&t={start_sec}s&autoplay=1")

    _video_dock.show()
    _video_dock.raise_()
    _video_dock._view.load(url)
    _start_video_timer()


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
    if _video_dock is None or _current_video_card_id is None:
        return
    try:
        _video_dock._view.page().runJavaScript(_YT_CURRENT_TIME_JS, _on_video_time)
    except (RuntimeError, AttributeError):
        pass


def _on_video_time(t) -> None:
    global _video_tick_count
    if _video_dock is None:
        return
    t = float(t or 0)
    try:
        _video_dock._ts_lbl.setText(f"\u25b6  {fmt_time(t)}")
    except (RuntimeError, AttributeError):
        return
    _video_tick_count += 1
    if _video_tick_count >= 5 and _current_video_card_id:
        _video_tick_count = 0
        try:
            set_video_position(_ADDON_DIR, _current_video_card_id, t)
        except Exception:
            pass


def _video_add_card_at_point() -> None:
    if _video_dock is None or _current_video_card_id is None:
        return
    try:
        _video_dock._view.page().runJavaScript(_YT_CURRENT_TIME_JS, _do_video_add_card)
    except (RuntimeError, AttributeError):
        pass


def _do_video_add_card(t) -> None:
    t = float(t or 0)
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
    global _video_dock, _video_timer
    try:
        if card is None:
            return
        try:
            note  = mw.col.get_note(card.nid)
            model = mw.col.models.get(note.mid)
        except Exception:
            return
        if model is None or model.get("name") != VIDEO_NOTE_TYPE:
            if _video_dock is not None:
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
        # Fallback for malformed cards where URL was accidentally saved in Title.
        if not youtube_url:
            try:
                title_text = (note["Title"] or "").strip()
            except Exception:
                title_text = ""
            if extract_video_id(title_text):
                youtube_url = title_text
            else:
                if _video_dock is not None:
                    try:
                        _video_dock.hide()
                    except RuntimeError:
                        _video_dock = None
                return
        position = get_video_position(_ADDON_DIR, card.id)
        show_video_in_dock(card.id, youtube_url, position)
    except Exception as e:
        print(f"[Incremento] on_video_question_shown error: {e}")


def on_video_reviewer_will_end() -> None:
    global _video_dock, _video_timer
    if _video_timer is not None:
        try:
            _video_timer.stop()
        except RuntimeError:
            pass
        _video_timer = None
    if _video_dock is not None:
        try:
            _video_dock.hide()
        except RuntimeError:
            _video_dock = None


def sync_video_note_type() -> None:
    try:
        ensure_video_note_type(mw.col)
    except Exception:
        pass
