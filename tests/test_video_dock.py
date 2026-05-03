import sys
import types
from unittest.mock import MagicMock
import time

sys.modules.setdefault("session", MagicMock())

import video_dock


class _FakeNote:
    def __init__(self):
        self.fields = ["Source Video Title"]
        self._values = {
            "YouTube_URL": "",
            "Title": "Source Video Title",
        }

    def __getitem__(self, key):
        return self._values[key]


class _FakeCard:
    def __init__(self, card_id=321, nid=99):
        self.id = card_id
        self.nid = nid

    def note(self):
        return _FakeNote()


def test_do_video_add_card_primes_video_extract_context(monkeypatch):
    fill_calls = []
    pending_calls = []
    position_calls = []

    monkeypatch.setattr(video_dock, "_current_video_card_id", 321)
    monkeypatch.setattr(video_dock, "_last_known_position", 0.0)
    monkeypatch.setattr(video_dock, "set_video_position", lambda *args, **kwargs: position_calls.append((args, dict(kwargs))))
    monkeypatch.setattr(video_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(video_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        video_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(get_card=lambda card_id: _FakeCard())
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "add_card_dock",
        types.SimpleNamespace(
            fill_dock_field=lambda *args, **kwargs: fill_calls.append((args, dict(kwargs))),
            set_pending_extract_options=lambda **kwargs: pending_calls.append(dict(kwargs)),
            source_relative_extract_priority_for_source=lambda source: 42.5 if source == "video" else 50.0,
        ),
    )

    video_dock._do_video_add_card(73.0)

    assert fill_calls
    assert fill_calls[0][0][0] == 0
    assert "incremento_open_video:321:73.0" in fill_calls[0][0][1]
    assert fill_calls[0][1]["include_pdf_citation"] is False
    assert fill_calls[0][1]["source_link_kind"] == "video"
    assert position_calls == [
        (
            ("/tmp/addon", "TestProfile", 321, 73.0),
            {},
        )
    ]
    assert pending_calls == [
        {
            "priority": 42.5,
            "mark_topic": False,
            "source": "video",
            "source_card_id": 321,
        }
    ]


def test_do_video_add_card_uses_last_known_position_when_player_reports_zero(monkeypatch):
    fill_calls = []
    position_calls = []

    monkeypatch.setattr(video_dock, "_current_video_card_id", 321)
    monkeypatch.setattr(video_dock, "_last_known_position", 91.0)
    monkeypatch.setattr(video_dock, "set_video_position", lambda *args, **kwargs: position_calls.append((args, dict(kwargs))))
    monkeypatch.setattr(video_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(video_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        video_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(get_card=lambda card_id: _FakeCard())
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "add_card_dock",
        types.SimpleNamespace(
            fill_dock_field=lambda *args, **kwargs: fill_calls.append((args, dict(kwargs))),
            set_pending_extract_options=lambda **kwargs: None,
            source_relative_extract_priority_for_source=lambda source: 42.5,
        ),
    )

    video_dock._do_video_add_card(0.0)

    assert "incremento_open_video:321:91.0" in fill_calls[0][0][1]
    assert position_calls == [
        (
            ("/tmp/addon", "TestProfile", 321, 91.0),
            {},
        )
    ]


def test_on_video_question_shown_preserves_live_position_for_same_active_card(monkeypatch):
    shown = []
    fake_note = _FakeNote()
    fake_note.mid = 7
    fake_card = _FakeCard(card_id=321, nid=99)

    monkeypatch.setattr(video_dock, "_current_video_card_id", 321)
    monkeypatch.setattr(video_dock, "_last_known_position", 84.0)
    monkeypatch.setattr(video_dock, "_position_lock_card_id", 321)
    monkeypatch.setattr(video_dock, "_position_lock_sec", 84.0)
    monkeypatch.setattr(video_dock, "_position_lock_until", time.monotonic() + 30.0)
    monkeypatch.setattr(video_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(video_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(video_dock, "get_video_position", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr(video_dock, "get_video_note_media", lambda note: {})
    monkeypatch.setattr(video_dock, "extract_start_seconds", lambda url: 0.0)
    monkeypatch.setattr(video_dock, "is_supported_video_url", lambda url: True)
    monkeypatch.setattr(video_dock, "show_video_in_dock", lambda *args, **kwargs: shown.append((args, dict(kwargs))))
    monkeypatch.setattr(
        video_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                get_note=lambda nid: fake_note,
                models=types.SimpleNamespace(get=lambda mid: {"name": video_dock.VIDEO_NOTE_TYPE}),
            )
        ),
    )

    video_dock.on_video_question_shown(fake_card)

    assert shown == [
        (
            (321, "Source Video Title", 84.0, ""),
            {
                "target_subtitle_file": "",
                "target_subtitle_label": "",
                "reference_subtitle_file": "",
                "reference_subtitle_label": "",
                "preserve_loaded": True,
            },
        )
    ]


def test_show_video_in_dock_preserves_loaded_remote_player_for_same_card(monkeypatch):
    load_calls = []
    reset_calls = []
    seek_ui_calls = []
    timer_calls = []

    class _FakePage:
        def runJavaScript(self, *_args, **_kwargs):
            pass

    class _FakeView:
        def page(self):
            return _FakePage()

        def load(self, url):
            load_calls.append(url)

    class _FakeDock:
        _view = _FakeView()
        _local_player = None

        def widget(self):
            return object()

        def show(self):
            pass

        def raise_(self):
            pass

    monkeypatch.setattr(video_dock, "_video_dock", _FakeDock())
    monkeypatch.setattr(video_dock, "_current_video_card_id", 321)
    monkeypatch.setattr(video_dock, "_current_video_url", "https://youtu.be/abc")
    monkeypatch.setattr(video_dock, "_current_local_relpath", "")
    monkeypatch.setattr(video_dock, "_using_local_qt_player", False)
    monkeypatch.setattr(video_dock, "_using_local_web_player", False)
    monkeypatch.setattr(video_dock, "_last_known_position", 84.0)
    monkeypatch.setattr(video_dock, "_last_known_duration", 120.0)
    monkeypatch.setattr(video_dock, "detect_video_provider", lambda url: "youtube")
    monkeypatch.setattr(
        video_dock,
        "build_remote_video_watch_url",
        lambda url, start_sec=0: f"https://www.youtube.com/watch?v=abc&t={int(start_sec)}s&autoplay=0",
    )
    monkeypatch.setattr(video_dock, "is_supported_video_url", lambda url: True)
    monkeypatch.setattr(video_dock, "_set_browser_button_enabled", lambda enabled: None)
    monkeypatch.setattr(video_dock, "_set_download_button_enabled", lambda *args, **kwargs: None)
    monkeypatch.setattr(video_dock, "_set_captions_button_enabled", lambda enabled: None)
    monkeypatch.setattr(video_dock, "_refresh_video_bookmarks_panel", lambda: None)
    monkeypatch.setattr(video_dock, "_set_local_controls_visible", lambda visible: None)
    monkeypatch.setattr(video_dock, "_set_caption_controls_state", lambda **kwargs: None)
    monkeypatch.setattr(video_dock, "_reset_seek_ui", lambda: reset_calls.append(True))
    monkeypatch.setattr(video_dock, "_set_seek_ui", lambda *args: seek_ui_calls.append(args))
    monkeypatch.setattr(video_dock, "_start_video_timer", lambda: timer_calls.append(True))

    video_dock.show_video_in_dock(
        321,
        "https://youtu.be/abc",
        84.0,
        "",
        preserve_loaded=True,
    )

    assert load_calls == []
    assert reset_calls == []
    assert seek_ui_calls == [(84.0, None)]
    assert timer_calls == [True]
    assert video_dock._remote_resume_target == 0.0
    assert video_dock._position_lock_card_id == 321


def test_position_lock_seeks_back_when_remote_player_reports_zero(monkeypatch):
    seek_calls = []
    seek_ui_calls = []

    monkeypatch.setattr(video_dock, "_video_dock", object())
    monkeypatch.setattr(video_dock, "_current_video_card_id", 321)
    monkeypatch.setattr(video_dock, "_position_lock_card_id", 321)
    monkeypatch.setattr(video_dock, "_position_lock_sec", 84.0)
    monkeypatch.setattr(video_dock, "_position_lock_until", time.monotonic() + 30.0)
    monkeypatch.setattr(video_dock, "_last_known_position", 84.0)
    monkeypatch.setattr(video_dock, "_last_known_duration", 0.0)
    monkeypatch.setattr(video_dock, "_using_local_qt_player", False)
    monkeypatch.setattr(video_dock, "_current_local_relpath", "")
    monkeypatch.setattr(video_dock, "_browser_sync_pending", False)
    monkeypatch.setattr(video_dock, "_video_tick_count", 0)
    monkeypatch.setattr(video_dock, "_seek_to_seconds", lambda sec: seek_calls.append(sec))
    monkeypatch.setattr(video_dock, "_set_seek_ui", lambda *args: seek_ui_calls.append(args))

    video_dock._on_video_time(
        {
            "currentTime": 0.0,
            "duration": None,
            "hasVideo": True,
            "readyState": 4,
            "networkState": 1,
            "errorCode": 0,
        }
    )

    assert seek_calls == [84.0]
    assert seek_ui_calls == [(84.0, None)]


def test_recent_video_extract_child_does_not_clear_source_video(monkeypatch):
    restore_calls = []
    persist_calls = []
    fake_note = _FakeNote()
    fake_note.mid = 7
    child_card = _FakeCard(card_id=701, nid=100)

    monkeypatch.setattr(video_dock, "_current_video_card_id", 321)
    monkeypatch.setattr(video_dock, "_current_video_url", "https://youtu.be/abc")
    monkeypatch.setattr(video_dock, "_recent_video_extract_source_card_id", 321)
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_card_ids", {701})
    monkeypatch.setattr(video_dock, "_recent_video_extract_position_sec", 84.0)
    monkeypatch.setattr(video_dock, "_recent_video_extract_until", time.monotonic() + 30.0)
    monkeypatch.setattr(video_dock, "_persist_position_now", lambda: persist_calls.append(True))
    monkeypatch.setattr(
        video_dock,
        "_restore_video_extract_position",
        lambda *args, **kwargs: restore_calls.append((args, dict(kwargs))) or True,
    )
    monkeypatch.setattr(
        video_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                get_note=lambda nid: fake_note,
                models=types.SimpleNamespace(get=lambda mid: {"name": "Basic"}),
            )
        ),
    )

    video_dock.on_video_question_shown(child_card)

    assert restore_calls == [((321, 84.0), {"ttl_sec": 60.0})]
    assert persist_calls == []
    assert video_dock._current_video_card_id == 321
    assert video_dock._current_video_url == "https://youtu.be/abc"
