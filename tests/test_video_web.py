"""Tests for video_manager and web_manager backend functions."""
import importlib.util
import os

import pytest

# ── Load modules by path to avoid Qt dependency ──────────────────────────────

def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_vm = _load("_incremento_video_manager", "backend/video_manager.py")
_wm = _load("_incremento_web_manager", "backend/web_manager.py")

extract_video_id = _vm.extract_video_id
fmt_time = _vm.fmt_time
get_video_position = _vm.get_video_position
set_video_position = _vm.set_video_position

get_web_url = _wm.get_web_url
set_web_url = _wm.set_web_url


# ── extract_video_id ──────────────────────────────────────────────────────────

class TestExtractVideoId:
    def test_standard_watch_url(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url(self):
        assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ?feature=share") == "dQw4w9WgXcQ"

    def test_url_with_extra_params(self):
        assert extract_video_id("https://youtube.com/watch?v=abcdefghijk&t=30") == "abcdefghijk"

    def test_plain_video_id(self):
        assert extract_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_encoded_wrapper(self):
        url = "https://www.youtube.com/attribution_link?a=1&u=%2Fwatch%3Fv%3DdQw4w9WgXcQ%26feature%3Dshare"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_returns_none_for_invalid_url(self):
        assert extract_video_id("https://example.com/video") is None

    def test_returns_none_for_empty_string(self):
        assert extract_video_id("") is None


# ── fmt_time ──────────────────────────────────────────────────────────────────

class TestFmtTime:
    def test_zero(self):
        assert fmt_time(0) == "0:00"

    def test_seconds_only(self):
        assert fmt_time(45) == "0:45"

    def test_one_minute(self):
        assert fmt_time(60) == "1:00"

    def test_minutes_and_seconds(self):
        assert fmt_time(90) == "1:30"

    def test_one_hour(self):
        assert fmt_time(3600) == "1:00:00"

    def test_hours_minutes_seconds(self):
        assert fmt_time(3723) == "1:02:03"

    def test_truncates_fractional_seconds(self):
        assert fmt_time(61.9) == "1:01"


# ── get/set_video_position ────────────────────────────────────────────────────

class TestVideoPosition:
    def test_default_when_not_set(self, tmp_path):
        assert get_video_position(str(tmp_path), 1) == 0.0

    def test_stores_and_retrieves_position(self, tmp_path):
        set_video_position(str(tmp_path), 1, 123.4)
        assert get_video_position(str(tmp_path), 1) == pytest.approx(123.4)

    def test_overwrites_existing(self, tmp_path):
        set_video_position(str(tmp_path), 1, 10.0)
        set_video_position(str(tmp_path), 1, 99.9)
        assert get_video_position(str(tmp_path), 1) == pytest.approx(99.9)

    def test_rounds_to_one_decimal(self, tmp_path):
        set_video_position(str(tmp_path), 2, 55.555)
        assert get_video_position(str(tmp_path), 2) == pytest.approx(round(55.555, 1))

    def test_different_cards_independent(self, tmp_path):
        set_video_position(str(tmp_path), 1, 10.0)
        set_video_position(str(tmp_path), 2, 20.0)
        assert get_video_position(str(tmp_path), 1) == pytest.approx(10.0)
        assert get_video_position(str(tmp_path), 2) == pytest.approx(20.0)


# ── get/set_web_url ───────────────────────────────────────────────────────────

class TestWebUrl:
    def test_default_when_not_set(self, tmp_path):
        assert get_web_url(str(tmp_path), 1) == ""

    def test_stores_and_retrieves_url(self, tmp_path):
        set_web_url(str(tmp_path), 1, "https://example.com")
        assert get_web_url(str(tmp_path), 1) == "https://example.com"

    def test_overwrites_existing(self, tmp_path):
        set_web_url(str(tmp_path), 1, "https://old.com")
        set_web_url(str(tmp_path), 1, "https://new.com")
        assert get_web_url(str(tmp_path), 1) == "https://new.com"

    def test_different_cards_independent(self, tmp_path):
        set_web_url(str(tmp_path), 1, "https://a.com")
        set_web_url(str(tmp_path), 2, "https://b.com")
        assert get_web_url(str(tmp_path), 1) == "https://a.com"
        assert get_web_url(str(tmp_path), 2) == "https://b.com"

    def test_empty_string_stored(self, tmp_path):
        set_web_url(str(tmp_path), 1, "https://example.com")
        set_web_url(str(tmp_path), 1, "")
        assert get_web_url(str(tmp_path), 1) == ""


# ── ensure_video_note_type ────────────────────────────────────────────────────

ensure_video_note_type = _vm.ensure_video_note_type
ensure_web_note_type = _wm.ensure_web_note_type


def _make_mock_col(note_type_exists=False, template_matches=True):
    """Build a minimal mock collection for note type tests."""
    from unittest.mock import MagicMock
    col = MagicMock()
    if not note_type_exists:
        col.models.by_name.return_value = None
    else:
        m = MagicMock()
        if template_matches:
            m.__getitem__ = lambda self, key: (
                [{"qfmt": _vm.CARD_TEMPLATE_FRONT, "afmt": _vm.CARD_TEMPLATE_BACK}]
                if key == "tmpls" else MagicMock()
            )
        else:
            m.__getitem__ = lambda self, key: (
                [{"qfmt": "old front", "afmt": "old back"}]
                if key == "tmpls" else MagicMock()
            )
        col.models.by_name.return_value = m
    return col


class TestEnsureVideoNoteType:
    def test_creates_new_note_type_when_absent(self):
        col = _make_mock_col(note_type_exists=False)
        ensure_video_note_type(col)
        col.models.add.assert_called_once()

    def test_does_not_create_when_already_exists_with_matching_template(self):
        col = _make_mock_col(note_type_exists=True, template_matches=True)
        ensure_video_note_type(col)
        col.models.add.assert_not_called()

    def test_updates_template_when_stale(self):
        col = _make_mock_col(note_type_exists=True, template_matches=False)
        ensure_video_note_type(col)
        col.models.update_dict.assert_called_once()


class TestEnsureWebNoteType:
    def test_creates_new_note_type_when_absent(self):
        col = _make_mock_col(note_type_exists=False)
        # patch CARD_TEMPLATE_FRONT/BACK on web_manager
        ensure_web_note_type(col)
        col.models.add.assert_called_once()

    def test_does_not_create_when_already_exists_with_matching_template(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        m = MagicMock()
        m.__getitem__ = lambda self, key: (
            [{"qfmt": _wm.CARD_TEMPLATE_FRONT, "afmt": _wm.CARD_TEMPLATE_BACK}]
            if key == "tmpls" else MagicMock()
        )
        col.models.by_name.return_value = m
        ensure_web_note_type(col)
        col.models.add.assert_not_called()

    def test_updates_template_when_stale(self):
        from unittest.mock import MagicMock
        col = MagicMock()
        m = MagicMock()
        m.__getitem__ = lambda self, key: (
            [{"qfmt": "old", "afmt": "old"}]
            if key == "tmpls" else MagicMock()
        )
        col.models.by_name.return_value = m
        ensure_web_note_type(col)
        col.models.update_dict.assert_called_once()


# ── add_video_card / add_web_card ─────────────────────────────────────────────

add_video_card = _vm.add_video_card
add_web_card = _wm.add_web_card


def _make_mock_col_for_add(deck_exists=True):
    from unittest.mock import MagicMock
    col = MagicMock()
    col.models.by_name.return_value = None  # note type doesn't exist yet → create
    note = MagicMock()
    note.id = 999
    col.new_note.return_value = note
    col.find_cards.return_value = [12345]
    if deck_exists:
        col.decks.by_name.return_value = {"id": 1}
    else:
        col.decks.by_name.return_value = None
        col.decks.add_normal_deck_with_name.return_value.id = 1
    return col


class TestAddVideoCard:
    def test_returns_card_id(self):
        col = _make_mock_col_for_add()
        result = add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")
        assert result == 12345

    def test_creates_deck_when_absent(self):
        col = _make_mock_col_for_add(deck_exists=False)
        add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")
        col.decks.add_normal_deck_with_name.assert_called_once()

    def test_uses_existing_deck(self):
        col = _make_mock_col_for_add(deck_exists=True)
        add_video_card(col, "https://youtube.com/watch?v=abc", "My Video")
        col.decks.add_normal_deck_with_name.assert_not_called()


class TestAddWebCard:
    def test_returns_card_id(self):
        col = _make_mock_col_for_add()
        result = add_web_card(col, "https://example.com", "My Web Page")
        assert result == 12345

    def test_creates_deck_when_absent(self):
        col = _make_mock_col_for_add(deck_exists=False)
        add_web_card(col, "https://example.com", "Page")
        col.decks.add_normal_deck_with_name.assert_called_once()

    def test_uses_existing_deck(self):
        col = _make_mock_col_for_add(deck_exists=True)
        add_web_card(col, "https://example.com", "Page")
        col.decks.add_normal_deck_with_name.assert_not_called()


# ── Tag handling edge cases ───────────────────────────────────────────────────


class TestVideoTagEdgeCases:
    def test_add_card_with_extra_tags(self):
        """Provide extra tags to exercise the tag loop."""
        col = _make_mock_col_for_add()
        result = add_video_card(
            col, "https://youtube.com/watch?v=abc", "Test", tags=["science", "physics"]
        )
        assert result == 12345


class TestWebTagEdgeCases:
    def test_add_card_with_extra_tags(self):
        """Provide extra tags to exercise the tag loop."""
        col = _make_mock_col_for_add()
        result = add_web_card(col, "https://example.com", "Test", tags=["health"])
        assert result == 12345
