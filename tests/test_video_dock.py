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


def test_on_video_question_shown_ignores_older_url_timestamp_than_saved_progress(monkeypatch):
    shown = []
    persisted = []
    fake_note = _FakeNote()
    fake_note.mid = 7
    fake_note._values["YouTube_URL"] = "https://www.youtube.com/watch?v=abc&t=45s"
    fake_card = _FakeCard(card_id=321, nid=99)

    monkeypatch.setattr(video_dock, "_current_video_card_id", None)
    monkeypatch.setattr(video_dock, "_last_known_position", 0.0)
    monkeypatch.setattr(video_dock, "_position_lock_card_id", None)
    monkeypatch.setattr(video_dock, "_position_lock_sec", 0.0)
    monkeypatch.setattr(video_dock, "_position_lock_until", 0.0)
    monkeypatch.setattr(video_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(video_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(video_dock, "get_video_position", lambda *args, **kwargs: 120.0)
    monkeypatch.setattr(video_dock, "set_video_position", lambda *args, **kwargs: persisted.append((args, dict(kwargs))))
    monkeypatch.setattr(video_dock, "get_video_note_media", lambda note: {})
    monkeypatch.setattr(video_dock, "extract_start_seconds", lambda url: 45.0)
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
            (321, "https://www.youtube.com/watch?v=abc&t=45s", 120.0, ""),
            {
                "target_subtitle_file": "",
                "target_subtitle_label": "",
                "reference_subtitle_file": "",
                "reference_subtitle_label": "",
                "preserve_loaded": False,
            },
        )
    ]
    assert persisted == []


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


def test_refresh_video_bookmarks_panel_renders_comment_actions(monkeypatch):
    html_calls = []
    label_calls = []

    class _FakePanel:
        def setHtml(self, html):
            html_calls.append(html)

    class _FakeButton:
        def setText(self, text):
            label_calls.append(text)

    monkeypatch.setattr(
        video_dock,
        "_video_bookmarks",
        lambda: [
            {"id": "bm-1", "label": "1:05", "comment_text": "", "location": {"seconds": 65.0}},
            {"id": "bm-2", "label": "2:30", "comment_text": "Why this matters", "location": {"seconds": 150.0}},
        ],
    )
    monkeypatch.setattr(
        video_dock,
        "_video_dock",
        types.SimpleNamespace(_bookmarks_btn=_FakeButton(), _bookmarks_panel=_FakePanel()),
    )

    video_dock._refresh_video_bookmarks_panel()

    assert label_calls == ["Bookmarks 2"]
    assert "Add comment" in html_calls[0]
    assert "Edit comment" in html_calls[0]
    assert "Why this matters" in html_calls[0]
    assert "inc://video-bookmark-comment/bm-2" in html_calls[0]


def test_edit_video_bookmark_comment_updates_panel(monkeypatch):
    updates = []
    refresh_calls = []
    tooltips = []
    visibility = []

    class _FakeDialog:
        def __init__(self, parent, *, title, context_label, current_comment):
            assert parent is video_dock.mw
            assert title == "Video Bookmark Comment"
            assert context_label == "1:05"
            assert current_comment == ""

        def exec(self):
            return True

        def comment_text(self):
            return "Reason to revisit"

    class _FakePanel:
        def setVisible(self, value):
            visibility.append(value)

    monkeypatch.setattr(video_dock, "_current_video_card_id", 42)
    monkeypatch.setattr(video_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(video_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        video_dock,
        "_video_bookmarks",
        lambda: [{"id": "bm-1", "label": "1:05", "comment_text": "", "location": {"seconds": 65.0}}],
    )
    monkeypatch.setattr(video_dock, "BookmarkCommentDialog", _FakeDialog)
    monkeypatch.setattr(
        video_dock,
        "update_reader_bookmark_comment",
        lambda addon_dir, profile, card_id, reader_type, bookmark_id, comment_text: (
            updates.append((addon_dir, profile, card_id, reader_type, bookmark_id, comment_text)) or
            {"id": bookmark_id, "comment_text": comment_text}
        ),
    )
    monkeypatch.setattr(video_dock, "_refresh_video_bookmarks_panel", lambda: refresh_calls.append(True))
    monkeypatch.setattr(video_dock, "tooltip", lambda message: tooltips.append(message))
    monkeypatch.setattr(video_dock, "mw", object())
    monkeypatch.setattr(video_dock, "_video_dock", types.SimpleNamespace(_bookmarks_panel=_FakePanel()))

    video_dock._edit_video_bookmark_comment("bm-1")

    assert updates == [("/tmp/addon", "TestProfile", 42, "video", "bm-1", "Reason to revisit")]
    assert refresh_calls == [True]
    assert visibility == [True]
    assert tooltips == ["Video bookmark comment saved."]


def test_start_all_video_review_preserves_position_and_restores_video(monkeypatch):
    starts = []
    selected_decks = []
    restored = []
    persisted = []
    fake_launcher = types.SimpleNamespace(
        start_attached_media_review=lambda **kwargs: starts.append(kwargs) or True,
    )
    monkeypatch.setitem(sys.modules, "media_review_dialog", fake_launcher)
    monkeypatch.setattr(video_dock, "_current_video_card_id", 321)
    monkeypatch.setattr(video_dock, "_last_known_position", 72.0)
    monkeypatch.setattr(video_dock, "_recent_video_extract_source_card_id", 321)
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_card_ids", {701})
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_positions", {701: 45.0})
    monkeypatch.setattr(video_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(video_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(video_dock, "_persist_position_now", lambda: persisted.append(True))
    monkeypatch.setattr(video_dock, "get_video_position", lambda *_args: 75.0)
    monkeypatch.setattr(
        video_dock,
        "_video_note_payload_for_card",
        lambda card_id: (
            "https://youtu.be/example",
            {
                "local_video_file": "clip.mp4",
                "target_subtitle_file": "target.vtt",
                "target_subtitle_label": "Target",
                "reference_subtitle_file": "reference.vtt",
                "reference_subtitle_label": "Reference",
            },
        ),
    )
    monkeypatch.setattr(
        video_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                decks=types.SimpleNamespace(
                    current=lambda: {"id": 88},
                    select=lambda deck_id: selected_decks.append(deck_id),
                )
            )
        ),
    )
    monkeypatch.setattr(
        video_dock,
        "show_video_in_dock",
        lambda *args, **kwargs: restored.append((args, kwargs)),
    )
    monkeypatch.setattr(
        video_dock,
        "QTimer",
        types.SimpleNamespace(singleShot=lambda _ms, callback: callback()),
    )

    assert video_dock._start_all_video_review() is True
    assert persisted == [True]
    assert starts[0]["source_card_id"] == 321
    assert starts[0]["media_label"] == "video"
    assert starts[0]["media_kind"] == "video"
    assert starts[0]["current_position"] == 75.0
    assert starts[0]["linked_card_ids"] == [701]
    assert starts[0]["linked_card_positions"] == {701: 45.0}
    assert starts[0]["deck_name"] == sys.modules["session"].INCREMENTO_VIDEO_REVIEW_DECK

    starts[0]["on_finished"]()
    assert selected_decks == [88]
    assert restored == [
        (
            (321, "https://youtu.be/example", 75.0, "clip.mp4"),
            {
                "target_subtitle_file": "target.vtt",
                "target_subtitle_label": "Target",
                "reference_subtitle_file": "reference.vtt",
                "reference_subtitle_label": "Reference",
                "preserve_loaded": False,
            },
        )
    ]


def test_switching_video_source_clears_recent_child_position_cache(monkeypatch):
    monkeypatch.setattr(video_dock, "_recent_video_extract_source_card_id", 111)
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_card_ids", {701})
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_positions", {701: 12.0})
    monkeypatch.setattr(
        video_dock,
        "_best_protected_video_position",
        lambda *_args: 30.0,
    )
    monkeypatch.setattr(video_dock, "set_video_position", lambda *_args: None)

    assert video_dock._arm_video_extract_position_protection(222, 30.0) == 30.0
    assert video_dock._recent_video_extract_source_card_id == 222
    assert video_dock._recent_video_extract_child_card_ids == set()
    assert video_dock._recent_video_extract_child_positions == {}


def test_video_extract_records_position_for_each_created_child(monkeypatch):
    monkeypatch.setattr(video_dock, "_recent_video_extract_source_card_id", 321)
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_card_ids", {701})
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_positions", {701: 40.0})
    monkeypatch.setattr(
        video_dock,
        "_arm_video_extract_position_protection",
        lambda *_args, **_kwargs: 84.0,
    )
    monkeypatch.setattr(
        video_dock,
        "_schedule_video_extract_position_restores",
        lambda *_args, **_kwargs: None,
    )

    video_dock.on_video_extract_note_added(321, [702])

    assert video_dock._recent_video_extract_child_card_ids == {701, 702}
    assert video_dock._recent_video_extract_child_positions == {
        701: 40.0,
        702: 84.0,
    }


def test_profile_switch_clears_recent_video_extract_links(monkeypatch):
    dock_calls = []
    fake_dock = types.SimpleNamespace(
        hide=lambda: dock_calls.append("hide"),
        deleteLater=lambda: dock_calls.append("delete"),
    )
    monkeypatch.setattr(video_dock, "_video_profile", object())
    monkeypatch.setattr(video_dock, "_video_dock", fake_dock)
    monkeypatch.setattr(video_dock, "_recent_video_extract_source_card_id", 321)
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_card_ids", {701})
    monkeypatch.setattr(video_dock, "_recent_video_extract_child_positions", {701: 40.0})
    monkeypatch.setattr(video_dock, "_recent_video_extract_until", 99.0)
    monkeypatch.setattr(video_dock, "_recent_video_extract_position_sec", 40.0)

    video_dock.reset_for_profile_switch()

    assert video_dock._video_profile is None
    assert video_dock._video_dock is None
    assert video_dock._recent_video_extract_source_card_id is None
    assert video_dock._recent_video_extract_child_card_ids == set()
    assert video_dock._recent_video_extract_child_positions == {}
    assert video_dock._recent_video_extract_until == 0.0
    assert video_dock._recent_video_extract_position_sec == 0.0
    assert dock_calls == ["hide", "delete"]
