"""Tests for backend/topic_scheduler.py — pure logic + mocked-mw functions."""
import pytest
from unittest.mock import MagicMock, patch

# topic_scheduler imports `from aqt import mw` at module level.
# The conftest already registers aqt as a MagicMock, so it resolves fine.
import topic_scheduler

_next_interval_and_afactor = topic_scheduler._next_interval_and_afactor
_topics_deck_name = topic_scheduler._topics_deck_name
is_topic_card = topic_scheduler.is_topic_card
_A_MIN = topic_scheduler._A_MIN
_A_MAX = topic_scheduler._A_MAX


class TestNextIntervalAndAfactor:
    """Tests for the SuperMemo A-factor interval calculation."""

    # ── ease == 1 (Again) ─────────────────────────────────────────────────

    def test_again_resets_interval_to_one(self):
        interval, _ = _next_interval_and_afactor(10, 3.5, 1)
        assert interval == 1

    def test_again_leaves_afactor_unchanged(self):
        _, afactor = _next_interval_and_afactor(10, 3.5, 1)
        assert afactor == 3.5

    def test_again_leaves_custom_afactor_unchanged(self):
        _, afactor = _next_interval_and_afactor(5, 2.0, 1)
        assert afactor == 2.0

    # ── ease == 2 (Hard) ──────────────────────────────────────────────────

    def test_hard_reduces_afactor(self):
        _, afactor = _next_interval_and_afactor(10, 3.5, 2)
        assert afactor < 3.5

    def test_hard_afactor_is_09_times_original(self):
        _, afactor = _next_interval_and_afactor(10, 3.5, 2)
        assert afactor == pytest.approx(round(3.5 * 0.9, 3))

    def test_hard_afactor_clamped_to_a_min(self):
        """A-factor cannot go below _A_MIN even with Hard."""
        _, afactor = _next_interval_and_afactor(10, _A_MIN, 2)
        assert afactor == _A_MIN

    def test_hard_uses_normal_interval(self):
        interval, _ = _next_interval_and_afactor(10, 3.5, 2)
        assert interval == max(1, round(10 * 3.5))

    # ── ease == 3 (Good) ──────────────────────────────────────────────────

    def test_good_afactor_unchanged(self):
        _, afactor = _next_interval_and_afactor(10, 3.5, 3)
        assert afactor == 3.5

    def test_good_interval_is_last_times_afactor(self):
        interval, _ = _next_interval_and_afactor(10, 2.0, 3)
        assert interval == max(1, round(10 * 2.0))

    def test_good_minimum_interval_is_one(self):
        interval, _ = _next_interval_and_afactor(0, 3.5, 3)
        assert interval >= 1

    # ── ease == 4 (Easy) ──────────────────────────────────────────────────

    def test_easy_increases_afactor(self):
        _, afactor = _next_interval_and_afactor(10, 3.5, 4)
        assert afactor > 3.5

    def test_easy_afactor_is_11_times_original(self):
        _, afactor = _next_interval_and_afactor(10, 3.5, 4)
        assert afactor == pytest.approx(round(3.5 * 1.1, 3))

    def test_easy_afactor_clamped_to_a_max(self):
        """A-factor cannot exceed _A_MAX even with Easy."""
        _, afactor = _next_interval_and_afactor(10, _A_MAX, 4)
        assert afactor == _A_MAX

    def test_easy_uses_normal_interval(self):
        interval, _ = _next_interval_and_afactor(10, 3.5, 4)
        assert interval == max(1, round(10 * 3.5))

    # ── boundary / cumulative ─────────────────────────────────────────────

    def test_interval_grows_with_repeated_good_reviews(self):
        """Multiple Good answers should compound the interval via A-factor."""
        interval = 1
        a = 3.5
        for _ in range(5):
            interval, a = _next_interval_and_afactor(interval, a, 3)
        assert interval > 1

    def test_small_interval_never_goes_below_one(self):
        for ease in (1, 2, 3, 4):
            interval, _ = _next_interval_and_afactor(1, _A_MIN, ease)
            assert interval >= 1


# ── _topics_deck_name ─────────────────────────────────────────────────────────


class TestTopicsDeckName:
    def test_returns_topics_from_deck_filter(self):
        mock_cfg = MagicMock()
        mock_cfg.topics_filter = "deck:Topics"
        with patch("topic_scheduler.load_scheduler_config", return_value=mock_cfg):
            result = _topics_deck_name()
        assert result == "Topics"

    def test_returns_topics_from_complex_filter(self):
        """Only the deck: prefix part is extracted."""
        mock_cfg = MagicMock()
        mock_cfg.topics_filter = "deck:MyDeck"
        with patch("topic_scheduler.load_scheduler_config", return_value=mock_cfg):
            result = _topics_deck_name()
        assert result == "MyDeck"

    def test_returns_default_when_filter_has_no_deck_prefix(self):
        mock_cfg = MagicMock()
        mock_cfg.topics_filter = "tag:Incremento"
        with patch("topic_scheduler.load_scheduler_config", return_value=mock_cfg):
            result = _topics_deck_name()
        assert result == "Topics"

    def test_returns_default_when_load_config_raises(self):
        with patch("topic_scheduler.load_scheduler_config", side_effect=Exception("fail")):
            result = _topics_deck_name()
        assert result == "Topics"


# ── is_topic_card ─────────────────────────────────────────────────────────────


class TestIsTopicCard:
    def _make_card(self, did, odid=0):
        card = MagicMock()
        card.did = did
        card.odid = odid
        return card

    def test_returns_true_for_card_in_topics_deck(self):
        card = self._make_card(did=1, odid=0)
        with patch("topic_scheduler.mw") as mock_mw, \
             patch("topic_scheduler.load_scheduler_config") as mock_cfg:
            mock_cfg.return_value.topics_filter = "deck:Topics"
            mock_mw.col.decks.get.return_value = {"name": "Topics"}
            result = is_topic_card(card)
        assert result is True

    def test_returns_false_for_card_in_other_deck(self):
        card = self._make_card(did=2, odid=0)
        with patch("topic_scheduler.mw") as mock_mw, \
             patch("topic_scheduler.load_scheduler_config") as mock_cfg:
            mock_cfg.return_value.topics_filter = "deck:Topics"
            mock_mw.col.decks.get.return_value = {"name": "Default"}
            result = is_topic_card(card)
        assert result is False

    def test_uses_odid_when_in_filtered_deck(self):
        """When odid != 0, use odid (original deck) instead of did."""
        card = self._make_card(did=999, odid=1)
        with patch("topic_scheduler.mw") as mock_mw, \
             patch("topic_scheduler.load_scheduler_config") as mock_cfg:
            mock_cfg.return_value.topics_filter = "deck:Topics"
            mock_mw.col.decks.get.return_value = {"name": "Topics"}
            result = is_topic_card(card)
        assert result is True
        # Should have queried odid=1, not did=999
        mock_mw.col.decks.get.assert_called_with(1)

    def test_returns_false_when_deck_is_none(self):
        card = self._make_card(did=1)
        with patch("topic_scheduler.mw") as mock_mw, \
             patch("topic_scheduler.load_scheduler_config") as mock_cfg:
            mock_cfg.return_value.topics_filter = "deck:Topics"
            mock_mw.col.decks.get.return_value = None
            result = is_topic_card(card)
        assert result is False

    def test_returns_false_on_exception(self):
        card = self._make_card(did=1)
        with patch("topic_scheduler.mw") as mock_mw:
            mock_mw.col.decks.get.side_effect = Exception("db error")
            result = is_topic_card(card)
        assert result is False


# ── on_topic_card_answered ────────────────────────────────────────────────────

on_topic_card_answered = topic_scheduler.on_topic_card_answered


class TestOnTopicCardAnswered:
    def _make_card(self, did=1, odid=0):
        card = MagicMock()
        card.id = 42
        card.did = did
        card.odid = odid
        return card

    def test_skips_non_topic_card(self):
        card = self._make_card()
        with patch("topic_scheduler.is_topic_card", return_value=False), \
             patch("topic_scheduler.get_topic_schedule") as mock_get:
            on_topic_card_answered(MagicMock(), card, ease=3)
        mock_get.assert_not_called()

    def test_schedules_topic_card_with_good(self):
        card = self._make_card()
        with patch("topic_scheduler.is_topic_card", return_value=True), \
             patch("topic_scheduler.get_topic_schedule", return_value=(3.5, 7)), \
             patch("topic_scheduler.set_topic_schedule") as mock_set, \
             patch("topic_scheduler.mw") as mock_mw:
            on_topic_card_answered(MagicMock(), card, ease=3)
        mock_set.assert_called_once()
        mock_mw.col.sched.set_due_date.assert_called_once()

    def test_handles_exception_gracefully(self):
        card = self._make_card()
        with patch("topic_scheduler.is_topic_card", return_value=True), \
             patch("topic_scheduler.get_topic_schedule", side_effect=Exception("db error")):
            # Should not raise
            on_topic_card_answered(MagicMock(), card, ease=3)
