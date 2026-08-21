"""Tests for backend/topic_scheduler.py — pure logic + mocked-mw functions."""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# topic_scheduler imports `from aqt import mw` at module level.
# The conftest already registers aqt as a MagicMock, so it resolves fine.
import topic_scheduler

_next_interval_and_afactor = topic_scheduler._next_interval_and_afactor
_topics_deck_name = topic_scheduler._topics_deck_name
configured_topic_card_tags = topic_scheduler.configured_topic_card_tags
configured_topic_card_types = topic_scheduler.configured_topic_card_types
configured_default_topic_a_factor = topic_scheduler.configured_default_topic_a_factor
configured_topic_more_adjustment_percent = topic_scheduler.configured_topic_more_adjustment_percent
configured_topic_less_adjustment_percent = topic_scheduler.configured_topic_less_adjustment_percent
configured_topic_maximum_interval_days = topic_scheduler.configured_topic_maximum_interval_days
effective_topic_maximum_interval_days = topic_scheduler.effective_topic_maximum_interval_days
is_topic_card = topic_scheduler.is_topic_card
consume_pending_topic_choice = topic_scheduler.consume_pending_topic_choice
prepare_topic_answer = topic_scheduler.prepare_topic_answer
sync_card_review_interval = topic_scheduler.sync_card_review_interval
topic_choice_for_button = topic_scheduler.topic_choice_for_button
topic_due_label = topic_scheduler.topic_due_label
_A_MIN = topic_scheduler._A_MIN
_A_MAX = topic_scheduler._A_MAX


class TestNextIntervalAndAfactor:
    """Tests for the SuperMemo A-factor interval calculation."""

    def test_more_reduces_afactor(self):
        _, afactor, _ = _next_interval_and_afactor(10, 3.5, "more")
        assert afactor < 3.5

    def test_more_afactor_is_09_times_original(self):
        _, afactor, _ = _next_interval_and_afactor(10, 3.5, "more")
        assert afactor == pytest.approx(round(3.5 * 0.9, 3))

    def test_more_afactor_clamped_to_a_min(self):
        _, afactor, _ = _next_interval_and_afactor(10, _A_MIN, "more")
        assert afactor == _A_MIN

    def test_more_shortens_immediate_interval(self):
        interval, _, precise = _next_interval_and_afactor(10, 3.5, "more")
        assert interval == max(1, round(10 * 3.5 * 0.9))
        assert precise == pytest.approx(10 * 3.5 * 0.9)

    def test_more_uses_configured_adjustment_strength(self):
        interval, afactor, precise = _next_interval_and_afactor(
            10,
            3.5,
            "more",
            more_adjustment_percent=20,
        )
        assert interval == 28
        assert afactor == pytest.approx(2.8)
        assert precise == pytest.approx(28.0)

    def test_same_afactor_unchanged(self):
        _, afactor, _ = _next_interval_and_afactor(10, 3.5, "same")
        assert afactor == 3.5

    def test_same_interval_is_last_times_afactor(self):
        interval, _, precise = _next_interval_and_afactor(10, 2.0, "same")
        assert interval == max(1, round(10 * 2.0))
        assert precise == pytest.approx(20.0)

    def test_same_minimum_interval_is_one(self):
        interval, _, precise = _next_interval_and_afactor(0, 3.5, "same")
        assert interval >= 1
        assert precise >= 1.0

    def test_same_accumulates_precise_interval_even_when_rounded_interval_stalls(self):
        interval = 1.0
        for _ in range(2):
            rounded, _a_factor, interval = _next_interval_and_afactor(interval, 1.25, "same")
        assert rounded == 2
        assert interval == pytest.approx(1.5625)

    def test_less_increases_afactor(self):
        _, afactor, _ = _next_interval_and_afactor(10, 3.5, "less")
        assert afactor > 3.5

    def test_less_afactor_is_11_times_original(self):
        _, afactor, _ = _next_interval_and_afactor(10, 3.5, "less")
        assert afactor == pytest.approx(round(3.5 * 1.1, 3))

    def test_less_afactor_clamped_to_a_max(self):
        _, afactor, _ = _next_interval_and_afactor(10, _A_MAX, "less")
        assert afactor == _A_MAX

    def test_less_lengthens_immediate_interval(self):
        interval, _, precise = _next_interval_and_afactor(10, 3.5, "less")
        assert interval == max(1, round(10 * 3.5 * 1.1))
        assert precise == pytest.approx(10 * 3.5 * 1.1)

    def test_less_uses_configured_adjustment_strength(self):
        interval, afactor, precise = _next_interval_and_afactor(
            10,
            3.5,
            "less",
            less_adjustment_percent=25,
        )
        assert interval == 44
        assert afactor == pytest.approx(4.375)
        assert precise == pytest.approx(43.75)

    # ── boundary / cumulative ─────────────────────────────────────────────

    def test_interval_grows_with_repeated_same_choices(self):
        interval = 1.0
        a = 3.5
        for _ in range(5):
            rounded, a, interval = _next_interval_and_afactor(interval, a, "same")
        assert rounded > 1
        assert interval > 1.0

    def test_small_interval_never_goes_below_one(self):
        for choice in ("more", "same", "less"):
            interval, _, precise = _next_interval_and_afactor(1, _A_MIN, choice)
            assert interval >= 1
            assert precise >= 1.0

    def test_interval_is_clamped_to_maximum(self):
        interval, _a_factor, precise = _next_interval_and_afactor(
            100,
            10,
            "less",
            maximum_interval_days=90,
        )
        assert interval == 90
        assert precise == 90.0

    def test_more_adjustment_is_applied_before_maximum_cap(self):
        interval, _a_factor, precise = _next_interval_and_afactor(
            100,
            10,
            "more",
            maximum_interval_days=90,
        )
        assert interval == 90
        assert precise == 90.0


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


class TestTopicConfigHelpers:
    def test_configured_topic_card_types_uses_defaults(self):
        assert configured_topic_card_types({}) == {
            "pdf_epub": True,
            "video": True,
            "writing": True,
            "web": False,
        }

    def test_configured_topic_card_types_merges_overrides(self):
        cfg = {"topic_card_types": {"video": False, "web": True}}
        assert configured_topic_card_types(cfg) == {
            "pdf_epub": True,
            "video": False,
            "writing": True,
            "web": True,
        }

    def test_configured_topic_card_tags_parses_string_and_deduplicates(self):
        cfg = {"topic_card_tags": "Topic, topic,  reading "}
        assert configured_topic_card_tags(cfg) == ["Topic", "reading"]

    def test_configured_topic_card_tags_accepts_list(self):
        cfg = {"topic_card_tags": ["Topic", "reading", "Topic"]}
        assert configured_topic_card_tags(cfg) == ["Topic", "reading"]

    def test_configured_default_topic_a_factor_uses_default(self):
        assert configured_default_topic_a_factor({}) == 3.5

    def test_configured_default_topic_a_factor_clamps_and_rounds(self):
        assert configured_default_topic_a_factor({"default_topic_a_factor": 1000}) == 100.0
        assert configured_default_topic_a_factor({"default_topic_a_factor": 1.0001}) == 1.1
        assert configured_default_topic_a_factor({"default_topic_a_factor": 2.34567}) == 2.346

    def test_topic_adjustment_percentages_default_to_ten(self):
        assert configured_topic_more_adjustment_percent({}) == 10.0
        assert configured_topic_less_adjustment_percent({}) == 10.0

    def test_topic_adjustment_percentages_read_clamp_and_round_config(self):
        cfg = {
            "topic_more_adjustment_percent": 17.4567,
            "topic_less_adjustment_percent": 250,
        }
        assert configured_topic_more_adjustment_percent(cfg) == 17.457
        assert configured_topic_less_adjustment_percent(cfg) == 100.0
        assert configured_topic_more_adjustment_percent(
            {"topic_more_adjustment_percent": -4}
        ) == 0.0

    def test_topic_maximum_interval_defaults_and_clamps(self):
        assert configured_topic_maximum_interval_days({}) == 36500
        assert configured_topic_maximum_interval_days(
            {"topic_maximum_interval_days": 30}
        ) == 30
        assert configured_topic_maximum_interval_days(
            {"topic_maximum_interval_days": 99999}
        ) == 36500

    def test_effective_maximum_uses_stricter_deck_preset_cap(self):
        card = SimpleNamespace(did=7, odid=0)
        fake_decks = MagicMock()
        fake_decks.config_dict_for_deck_id.return_value = {"rev": {"maxIvl": 45}}
        fake_mw = SimpleNamespace(col=SimpleNamespace(decks=fake_decks))
        with patch.object(topic_scheduler, "mw", fake_mw):
            assert effective_topic_maximum_interval_days(
                card,
                {"topic_maximum_interval_days": 90},
            ) == 45


class TestTopicAnswerSeparation:
    def test_visible_buttons_map_to_frequency_choices(self):
        assert topic_choice_for_button(1) == "more"
        assert topic_choice_for_button(2) == "same"
        assert topic_choice_for_button(3) == "less"

    @pytest.mark.parametrize("button_ease", [1, 2, 3])
    @pytest.mark.parametrize(
        ("card_type", "queue"),
        [(0, 0), (1, 1), (3, 3), (2, 2)],
        ids=["new", "learning", "relearning", "review"],
    )
    def test_every_topic_choice_submits_good_in_every_card_state(
        self,
        button_ease,
        card_type,
        queue,
    ):
        card = SimpleNamespace(id=1000 + card_type * 10 + button_ease, type=card_type, queue=queue)
        assert prepare_topic_answer(card, button_ease) == 3
        consume_pending_topic_choice(card)

    @pytest.mark.parametrize(
        ("button_ease", "expected_choice"),
        [(1, "more"), (2, "same"), (3, "less")],
    )
    def test_original_choice_survives_until_post_answer_hook(
        self,
        button_ease,
        expected_choice,
    ):
        card = SimpleNamespace(id=2000 + button_ease)
        prepare_topic_answer(card, button_ease)
        assert consume_pending_topic_choice(card) == expected_choice
        assert consume_pending_topic_choice(card) == "same"

    def test_profile_reset_discards_pending_and_tracked_topic_state(self):
        card = SimpleNamespace(id=2999, ivl=7)
        with patch("topic_scheduler._answer_revlog_snapshot", return_value=(True, 100)):
            prepare_topic_answer(card, 2)
        topic_scheduler._HANDLED_TOPIC_ANSWER_IDS.add(card.id)
        topic_scheduler._TOPIC_REVLOG_TRACKER.track("OldProfile", card.id, 101)

        topic_scheduler.reset_topic_answer_runtime_state()

        assert topic_scheduler._PENDING_TOPIC_CHOICES == {}
        assert topic_scheduler._HANDLED_TOPIC_ANSWER_IDS == set()
        assert topic_scheduler._TOPIC_REVLOG_TRACKER._cards == {}


# ── is_topic_card ─────────────────────────────────────────────────────────────


class TestIsTopicCard:
    def _make_card(self, did, odid=0, note_type_name="", tags=None):
        card = MagicMock()
        card.did = did
        card.odid = odid
        if note_type_name or tags is not None:
            note = MagicMock()
            note.note_type.return_value = {"name": note_type_name}
            note.tags = list(tags or [])
            card.note.return_value = note
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

    def test_returns_true_for_enabled_pdf_epub_type(self):
        card = self._make_card(did=2, note_type_name="Incremento PDF")
        with patch("topic_scheduler.configured_topic_card_types", return_value={
            "pdf_epub": True,
            "video": False,
            "writing": False,
            "web": False,
        }), patch("topic_scheduler.configured_effective_topic_tags", return_value=[]), \
             patch("topic_scheduler._card_in_topics_deck", return_value=False):
            result = is_topic_card(card)
        assert result is True

    def test_returns_true_for_matching_topic_tag(self):
        card = self._make_card(did=2, note_type_name="Basic", tags=["reading"])
        with patch("topic_scheduler.configured_topic_card_types", return_value={
            "pdf_epub": False,
            "video": False,
            "writing": False,
            "web": False,
        }), patch("topic_scheduler.configured_effective_topic_tags", return_value=["Reading"]), \
             patch("topic_scheduler._card_in_topics_deck", return_value=False):
            result = is_topic_card(card)
        assert result is True

    def test_returns_true_for_add_card_topic_tag_from_t_button(self):
        card = self._make_card(did=2, note_type_name="Basic", tags=["topic"])
        with patch("topic_scheduler.configured_topic_card_types", return_value={
            "pdf_epub": False,
            "video": False,
            "writing": False,
            "web": False,
        }), patch("topic_scheduler.configured_effective_topic_tags", return_value=["topic"]), \
             patch("topic_scheduler._card_in_topics_deck", return_value=False):
            result = is_topic_card(card)
        assert result is True

    def test_item_tag_overrides_topic_note_type(self):
        card = self._make_card(did=2, note_type_name="Incremento PDF", tags=["item"])
        with patch("topic_scheduler.configured_topic_card_types", return_value={
            "pdf_epub": True,
            "video": False,
            "writing": False,
            "web": False,
        }), patch("topic_scheduler.configured_effective_topic_tags", return_value=["topic"]), \
             patch("topic_scheduler.configured_effective_item_tags", return_value=["item"]), \
             patch("topic_scheduler._card_in_topics_deck", return_value=False):
            result = is_topic_card(card)
        assert result is False

    def test_item_tag_overrides_topics_deck_membership(self):
        card = self._make_card(did=2, note_type_name="Basic", tags=["item"])
        with patch("topic_scheduler.configured_topic_card_types", return_value={
            "pdf_epub": False,
            "video": False,
            "writing": False,
            "web": False,
        }), patch("topic_scheduler.configured_effective_topic_tags", return_value=["topic"]), \
             patch("topic_scheduler.configured_effective_item_tags", return_value=["item"]), \
             patch("topic_scheduler._card_in_topics_deck", return_value=True):
            result = is_topic_card(card)
        assert result is False

    def test_resolved_classifier_fetches_note_once_and_uses_explicit_collection(self):
        note = MagicMock()
        note.note_type.return_value = {"name": "Basic"}
        note.tags = []
        card = MagicMock(did=9, odid=0)
        card.did = 9
        card.odid = 0
        card.note.return_value = note
        collection = MagicMock()
        collection.decks.get.return_value = {"name": "Topics"}
        classifier = topic_scheduler.TopicCardClassifier(
            enabled_note_type_names=frozenset(),
            topic_tags=frozenset({"topic"}),
            item_tags=frozenset({"item"}),
            topics_deck_name="Topics",
        )

        assert is_topic_card(card, classifier=classifier, col=collection) is True
        card.note.assert_called_once_with()
        collection.decks.get.assert_called_once_with(9)

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


class TestTopicDueLabel:
    def test_preview_mode_does_not_promise_an_incremento_interval(self):
        card = SimpleNamespace(id=42, did=9, odid=1, ivl=10)
        fake_col = MagicMock()
        fake_col.decks.get.return_value = {"dyn": 1, "resched": False}
        with patch("topic_scheduler.mw", SimpleNamespace(col=fake_col)), \
             patch("topic_scheduler.get_topic_schedule_state") as get_state:
            assert topic_due_label(card, 2) == ""
        get_state.assert_not_called()

    def test_topic_buttons_show_distinct_immediate_intervals(self):
        card = MagicMock()
        card.id = 42
        with patch("topic_scheduler.get_topic_schedule_state", return_value=(3.5, 7.0, 7)), \
             patch("topic_scheduler.get_custom_schedule_rule", return_value=None), \
             patch("topic_scheduler.configured_default_topic_a_factor", return_value=4.2):
            assert topic_due_label(card, 1) == "22d"
            assert topic_due_label(card, 2) == "24d"
            assert topic_due_label(card, 3) == "27d"

    def test_uses_configured_adjustments_in_displayed_intervals(self):
        card = MagicMock()
        card.id = 42
        with patch("topic_scheduler.get_topic_schedule_state", return_value=(3.5, 10.0, 10)), \
             patch("topic_scheduler.get_custom_schedule_rule", return_value=None), \
             patch("topic_scheduler.configured_default_topic_a_factor", return_value=3.5), \
             patch("topic_scheduler.configured_topic_more_adjustment_percent", return_value=20.0), \
             patch("topic_scheduler.configured_topic_less_adjustment_percent", return_value=25.0):
            assert topic_due_label(card, 1) == "28d"
            assert topic_due_label(card, 2) == "35d"
            assert topic_due_label(card, 3) == "44d"

    def test_passes_configured_default_for_unseen_topic_cards(self):
        card = MagicMock()
        card.id = 42
        with patch("topic_scheduler.get_topic_schedule_state", return_value=(4.2, 1.0, 1)) as mock_get, \
             patch("topic_scheduler.get_custom_schedule_rule", return_value=None), \
             patch("topic_scheduler.configured_default_topic_a_factor", return_value=4.2):
            assert topic_due_label(card, 2) == "4d"
        assert mock_get.call_args.kwargs["default_a_factor"] == 4.2


class TestSyncCardReviewInterval:
    def test_updates_stale_anki_interval_after_manual_due_date(self):
        fake_card = SimpleNamespace(id=42, ivl=3)
        fake_col = MagicMock()
        fake_col.get_card.return_value = fake_card
        fake_mw = SimpleNamespace(col=fake_col)

        with patch("topic_scheduler.mw", fake_mw):
            sync_card_review_interval(42, 24)

        assert fake_card.ivl == 24
        fake_col.update_card.assert_called_once_with(fake_card)

    def test_skips_update_when_interval_is_already_aligned(self):
        fake_card = SimpleNamespace(id=42, ivl=24)
        fake_col = MagicMock()
        fake_col.get_card.return_value = fake_card
        fake_mw = SimpleNamespace(col=fake_col)

        with patch("topic_scheduler.mw", fake_mw):
            sync_card_review_interval(42, 24)

        fake_col.update_card.assert_not_called()


class TestApplyTopicIntervalToAnkiCard:
    def test_updates_review_fields_and_merges_into_answer_undo_step(self):
        fake_card = SimpleNamespace(
            id=42,
            did=999,
            odid=7,
            odue=123,
            type=3,
            queue=1,
            due=123,
            ivl=9,
            left=2002,
        )
        fake_col = MagicMock()
        fake_col.get_card.return_value = fake_card
        fake_col.sched.today = 500
        fake_mw = SimpleNamespace(col=fake_col)

        with patch.object(topic_scheduler, "mw", fake_mw):
            topic_scheduler._apply_topic_interval_to_anki_card(
                42,
                12,
                answer_undo_step=77,
            )

        assert fake_card.did == 7
        assert fake_card.odid == 0
        assert fake_card.odue == 0
        assert fake_card.type == 2
        assert fake_card.queue == 2
        assert fake_card.due == 512
        assert fake_card.ivl == 12
        assert fake_card.left == 0
        fake_col.update_card.assert_called_once_with(fake_card)
        fake_col.merge_undo_entries.assert_called_once_with(77)


# ── on_topic_card_answered ────────────────────────────────────────────────────

on_topic_card_answered = topic_scheduler.on_topic_card_answered


class TestOnTopicCardAnswered:
    def _make_card(self, did=1, odid=0):
        card = MagicMock()
        card.id = 42
        card.did = did
        card.odid = odid
        card.ivl = 7
        return card

    def _run_answer(
        self,
        card,
        button_ease,
        *,
        state=(3.5, 7.0, 7),
        schedule_exists=True,
        custom_rule=None,
    ):
        latest_card = SimpleNamespace(
            id=42,
            did=1,
            odid=0,
            odue=0,
            type=2,
            queue=2,
            due=100,
            ivl=7,
            left=0,
        )
        fake_mw = MagicMock()
        fake_mw.col.get_card.return_value = latest_card
        with patch("topic_scheduler.is_topic_card", return_value=True), \
             patch("topic_scheduler.topic_schedule_exists", return_value=schedule_exists), \
             patch("topic_scheduler.get_topic_schedule_state", return_value=state) as get_state, \
             patch("topic_scheduler.get_custom_schedule_rule", return_value=custom_rule), \
             patch("topic_scheduler._current_answer_undo_step", return_value=77), \
             patch("topic_scheduler._apply_topic_interval_to_anki_card") as apply_interval, \
             patch("topic_scheduler._answer_revlog_snapshot", return_value=(True, 122)), \
             patch("topic_scheduler._new_answer_revlog_id", return_value=123), \
             patch("topic_scheduler._track_topic_review_state"), \
             patch("topic_scheduler.commit_topic_review") as commit_review, \
             patch("topic_scheduler.mw", fake_mw), \
             patch("topic_scheduler.configured_default_topic_a_factor", return_value=4.2):
            assert prepare_topic_answer(card, button_ease) == 3
            on_topic_card_answered(MagicMock(), card, ease=3)
        return get_state, apply_interval, commit_review

    def test_skips_non_topic_card(self):
        card = self._make_card()
        with patch("topic_scheduler.is_topic_card", return_value=False), \
             patch("topic_scheduler.get_topic_schedule_state") as mock_get:
            on_topic_card_answered(MagicMock(), card, ease=3)
        mock_get.assert_not_called()

    def test_preview_answer_does_not_change_incremento_schedule_or_history(self):
        card = self._make_card(did=9, odid=1)
        fake_col = MagicMock()
        fake_col.decks.get.return_value = {"dyn": 1, "resched": False}
        with patch("topic_scheduler.mw", SimpleNamespace(col=fake_col)), \
             patch("topic_scheduler._answer_revlog_snapshot", return_value=(True, 100)), \
             patch("topic_scheduler.is_topic_card", return_value=True), \
             patch("topic_scheduler.get_topic_schedule_state") as get_state, \
             patch("topic_scheduler._apply_topic_interval_to_anki_card") as apply_interval, \
             patch("topic_scheduler.commit_topic_review") as commit_review:
            assert prepare_topic_answer(card, 1) == 3
            on_topic_card_answered(MagicMock(), card, ease=3)

        get_state.assert_not_called()
        apply_interval.assert_not_called()
        commit_review.assert_not_called()
        assert topic_scheduler.consume_handled_topic_answer(card.id) is True

    def test_schedules_topic_card_with_same(self):
        card = self._make_card()
        _get_state, apply_interval, commit_review = self._run_answer(card, 2)
        assert apply_interval.call_args.args[1] == 24
        assert commit_review.call_args.args[3] == "same"
        assert commit_review.call_args.kwargs["anki_ease"] == 3
        assert commit_review.call_args.kwargs["new_precise_interval"] == pytest.approx(24.5)

    def test_uses_configured_default_for_unseen_topic_cards(self):
        card = self._make_card()
        card.ivl = 18
        get_state, apply_interval, commit_review = self._run_answer(
            card,
            2,
            state=(4.2, 18.0, 18),
            schedule_exists=False,
        )
        assert get_state.call_args.kwargs["default_a_factor"] == 4.2
        assert get_state.call_args.kwargs["default_interval"] == 18.0
        assert apply_interval.call_args.args[1] == 76
        assert commit_review.call_args.kwargs["previous_schedule_exists"] is False

    def test_more_choice_changes_only_incremento_schedule_after_anki_good(self):
        card = self._make_card()
        _get_state, apply_interval, commit_review = self._run_answer(card, 1)
        assert apply_interval.call_args.args[1] == 22
        assert commit_review.call_args.args[3] == "more"
        assert commit_review.call_args.kwargs["new_a_factor"] == pytest.approx(3.15)
        assert commit_review.call_args.kwargs["new_precise_interval"] == pytest.approx(22.05)

    def test_less_choice_changes_only_incremento_schedule_after_anki_good(self):
        card = self._make_card()
        _get_state, apply_interval, commit_review = self._run_answer(card, 3)
        assert apply_interval.call_args.args[1] == 27
        assert commit_review.call_args.args[3] == "less"
        assert commit_review.call_args.kwargs["new_a_factor"] == pytest.approx(3.85)
        assert commit_review.call_args.kwargs["new_precise_interval"] == pytest.approx(26.95)

    def test_one_time_custom_rule_is_resolved_in_same_commit(self):
        card = self._make_card()
        rule = {
            "card_id": 42,
            "enabled": True,
            "mode": "one_time",
            "interval_value": 2,
            "interval_unit": "days",
        }
        _get_state, apply_interval, commit_review = self._run_answer(
            card,
            2,
            custom_rule=rule,
        )
        assert apply_interval.call_args.args[1] == 2
        assert commit_review.call_args.kwargs["scheduled_interval"] == 2
        assert commit_review.call_args.kwargs["new_precise_interval"] == 2.0
        assert commit_review.call_args.kwargs["consumed_one_time"] is True

    def test_handles_exception_gracefully(self):
        card = self._make_card()
        with patch("topic_scheduler.is_topic_card", return_value=True), \
             patch("topic_scheduler.get_topic_schedule_state", side_effect=Exception("db error")):
            # Should not raise
            on_topic_card_answered(MagicMock(), card, ease=3)
