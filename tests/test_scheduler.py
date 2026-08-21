from unittest.mock import patch, MagicMock
import scheduler
import cards as card_utils

NO_TAGS_KEY = scheduler.NO_TAGS_KEY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_soft_pick(card_type="items", tag="health", mode="priority", use_tags=True):
    """Stub soft_pick to return deterministic decisions in order: type, mode, [tag]."""
    side_effect = [card_type, mode, tag] if use_tags else [card_type, mode]
    return patch("scheduler.soft_pick", side_effect=side_effect)


def _mock_card_utils(tag_topic=None, tag_item=None, all_topic=None, all_item=None):
    """Patch all four card fetch functions on scheduler.card_utils."""
    tag_topic = [] if tag_topic is None else tag_topic
    tag_item = [] if tag_item is None else tag_item
    all_topic = [] if all_topic is None else all_topic
    all_item = [] if all_item is None else all_item
    return patch.multiple(
        "scheduler.card_utils",
        get_topic_cards_by_tag=lambda tag, **kw: tag_topic,
        get_item_cards_by_tag=lambda tag, **kw: tag_item,
        get_all_topic_cards=lambda **kw: all_topic,
        get_all_item_cards=lambda **kw: all_item,
    )


# ---------------------------------------------------------------------------
# soft_pick
# ---------------------------------------------------------------------------


class TestSoftPick:
    def test_returns_a_key_from_weights(self):
        result = scheduler.soft_pick({"a": 0.5, "b": 0.5}, {})
        assert result in ("a", "b")

    def test_single_option_always_returned(self):
        for _ in range(20):
            assert scheduler.soft_pick({"only": 1.0}, {}) == "only"

    def test_zero_weight_option_is_never_selected(self):
        with patch("scheduler.random.random", return_value=0.0):
            for _ in range(20):
                assert scheduler.soft_pick({"disabled": 0.0, "enabled": 1.0}, {}) == "enabled"

    def test_zero_weight_option_stays_disabled_with_historical_counts(self):
        with patch("scheduler.random.random", return_value=0.0):
            assert scheduler.soft_pick(
                {"topics": 1.0, "items": 0.0},
                {"topics": 20, "items": 2000},
            ) == "topics"

    def test_higher_weight_selected_more_often(self):
        # With n=0 (empty counts), alpha dominates and all items are equal.
        # Seed counts so n > 0, letting weights drive the distribution.
        weights = {"rare": 0.1, "common": 0.9}
        counts = {"rare": 5, "common": 5}  # n=10, equal history
        selections = [scheduler.soft_pick(weights, counts) for _ in range(500)]
        assert selections.count("common") > selections.count("rare")

    def test_overrepresented_key_selected_less(self):
        """A key with many past counts should be selected less than a fresh one."""
        weights = {"a": 0.5, "b": 0.5}
        counts = {"a": 100}  # "a" heavily overrepresented
        selections = [scheduler.soft_pick(weights, counts) for _ in range(100)]
        assert selections.count("b") > selections.count("a")

    # --- deterministic tests (mocked random) ---
    # With {"a": 0.5, "b": 0.5}, counts={}, alpha=0.2:
    #   n=0 → probs = {"a": 0.2, "b": 0.2}, total=0.4 → each has 50% share
    #   r=0.1 → r -= 0.5 = -0.4 ≤ 0 → "a"
    #   r=0.9 → r -= 0.5 = 0.4 > 0; r -= 0.5 = -0.1 ≤ 0 → "b"

    def test_selects_first_key_with_small_random(self):
        with patch("scheduler.random.random", return_value=0.1):
            result = scheduler.soft_pick({"a": 0.5, "b": 0.5}, {})
        assert result == "a"

    def test_selects_second_key_with_large_random(self):
        with patch("scheduler.random.random", return_value=0.9):
            result = scheduler.soft_pick({"a": 0.5, "b": 0.5}, {})
        assert result == "b"

    def test_selects_third_of_three_keys(self):
        # {"a": 1/3, "b": 1/3, "c": 1/3}, counts={} → equal 1/3 shares
        # r=0.9 → r -= 1/3 ≈ 0.567 > 0; r -= 1/3 ≈ 0.234 > 0; r -= 1/3 ≈ -0.1 ≤ 0 → "c"
        with patch("scheduler.random.random", return_value=0.9):
            result = scheduler.soft_pick({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}, {})
        assert result == "c"

    # --- alpha smoothing ---

    def test_empty_counts_gives_equal_probability_regardless_of_weights(self):
        """With n=0, alpha dominates: prob = alpha for all keys regardless of weight."""
        weights = {"rare": 0.1, "common": 0.9}
        selections = [scheduler.soft_pick(weights, {}) for _ in range(1000)]
        ratio = selections.count("common") / 1000
        assert 0.4 < ratio < 0.6  # ~50/50, NOT 90/10

    # --- epsilon floor ---
    # With counts={"a": 1000}, weights={"a": 0.5, "b": 0.5}:
    #   n=1000 → probs["a"] = max(500 - 1000 + 0.2, 0.05) = 0.05  (epsilon floor)
    #            probs["b"] = max(500 - 0    + 0.2, 0.05) = 500.2
    #   p_a/total ≈ 0.0001 → r=0.0 triggers "a" first

    def test_epsilon_floor_keeps_overrepresented_key_selectable(self):
        """A key far over its budget is still selectable via the epsilon floor."""
        with patch("scheduler.random.random", return_value=0.0):
            result = scheduler.soft_pick({"a": 0.5, "b": 0.5}, {"a": 1000})
        assert result == "a"

    def test_custom_epsilon_raises_floor(self):
        """A larger epsilon gives a bigger minimum share to overrepresented keys."""
        # default epsilon=0.05 → probs["a"] = 0.05
        # custom epsilon=0.5  → probs["a"] = 0.5 (larger floor)
        counts = {"a": 1000}
        weights = {"a": 0.5, "b": 0.5}
        default_share = 0.05 / (0.05 + 500.2)
        larger_share = 0.5 / (0.5 + 500.2)
        assert larger_share > default_share

    # --- debt / catch-up ---
    # counts={"a": 10}, weights={"a": 0.5, "b": 0.5}:
    #   n=10 → probs["a"] = max(5 - 10 + 0.2, 0.05) = 0.05
    #          probs["b"] = max(5 -  0 + 0.2, 0.05) = 5.2
    #   p_b/total ≈ 0.99 → r=0.5 skips "a" and lands on "b"

    def test_underrepresented_key_dominates(self):
        with patch("scheduler.random.random", return_value=0.5):
            result = scheduler.soft_pick({"a": 0.5, "b": 0.5}, {"a": 10})
        assert result == "b"

    def test_underrepresented_key_selected_far_more_often(self):
        weights = {"a": 0.5, "b": 0.5}
        counts = {"a": 8, "b": 2}  # n=10: probs["a"]≈0.05, probs["b"]≈3.2
        selections = [scheduler.soft_pick(weights, counts) for _ in range(200)]
        assert selections.count("b") > selections.count("a") * 10


# ---------------------------------------------------------------------------
# Card type selection (topics vs items)
# ---------------------------------------------------------------------------


class TestCardTypeSelection:
    def test_topics_fetches_from_topic_function(self):
        with _patch_soft_pick(card_type="topics", tag="health", mode="priority"):
            with _mock_card_utils(tag_topic=[101, 102]):
                result = scheduler.get_card_from_scheduler(use_tags=True)
        assert result.card in [101, 102]
        assert result.card_type == "topics"

    def test_items_fetches_from_item_function(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201, 202]):
                result = scheduler.get_card_from_scheduler(use_tags=True)
        assert result.card in [201, 202]
        assert result.card_type == "items"


# ---------------------------------------------------------------------------
# Mode selection (priority vs random)
# ---------------------------------------------------------------------------


class TestModeSelection:
    def test_priority_returns_first_card(self):
        with _patch_soft_pick(card_type="items", mode="priority"):
            with _mock_card_utils(tag_item=[501, 502, 503]):
                result = scheduler.get_card_from_scheduler(use_tags=True)
        assert result.card == 501
        assert result.mode == "priority"

    def test_random_calls_random_choice(self):
        with _patch_soft_pick(card_type="items", mode="random"):
            with _mock_card_utils(tag_item=[601, 602, 603]):
                with patch("scheduler.random.choice", return_value=602) as mock_choice:
                    result = scheduler.get_card_from_scheduler(use_tags=True)
        mock_choice.assert_called_once_with([601, 602, 603])
        assert result.card == 602
        assert result.mode == "random"


# ---------------------------------------------------------------------------
# Tag fallback
# ---------------------------------------------------------------------------


class TestTagFallback:
    def test_falls_back_to_all_items_when_tag_empty(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[], all_item=[201, 202]):
                result = scheduler.get_card_from_scheduler()
        assert result.card in [201, 202]
        assert result.tag is None  # tag was ignored

    def test_falls_back_to_all_topics_when_tag_empty(self):
        with _patch_soft_pick(card_type="topics", tag="health", mode="priority"):
            with _mock_card_utils(tag_topic=[], all_topic=[101, 102]):
                result = scheduler.get_card_from_scheduler()
        assert result.card in [101, 102]
        assert result.tag is None

    def test_falls_back_to_other_type_when_selected_type_empty(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[], all_item=[], all_topic=[101, 102]):
                result = scheduler.get_card_from_scheduler()
        assert result.card in [101, 102]
        assert result.card_type == "topics"  # fell back to other type

    def test_falls_back_to_items_when_topics_empty(self):
        with _patch_soft_pick(card_type="topics", tag="health", mode="priority"):
            with _mock_card_utils(tag_topic=[], all_topic=[], all_item=[201, 202]):
                result = scheduler.get_card_from_scheduler()
        assert result.card in [201, 202]
        assert result.card_type == "items"

    def test_returns_none_card_when_all_sources_empty(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[], all_item=[], all_topic=[]):
                result = scheduler.get_card_from_scheduler()
        assert result.card is None

    def test_does_not_use_fallback_when_tag_has_cards(self):
        """Fallback (get_all_item_cards) must NOT be called when tag returns results."""
        calls = []
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with patch.multiple(
                "scheduler.card_utils",
                get_item_cards_by_tag=lambda tag, **kw: [201],
                get_all_item_cards=lambda **kw: calls.append(1) or [999],
                get_topic_cards_by_tag=lambda tag, **kw: [],
                get_all_topic_cards=lambda **kw: [],
            ):
                result = scheduler.get_card_from_scheduler(use_tags=True)
        assert result.card == 201
        assert result.tag == "health"  # tag was used successfully
        assert calls == [], "fallback should not have been called"


# ---------------------------------------------------------------------------
# use_tags=False
# ---------------------------------------------------------------------------


class TestUseTagsFalse:
    def test_skips_tag_fetch_and_uses_all_cards(self):
        tag_fetch_calls = []
        with _patch_soft_pick(card_type="items", mode="priority", use_tags=False):
            with patch.multiple(
                "scheduler.card_utils",
                get_item_cards_by_tag=lambda tag, **kw: tag_fetch_calls.append(tag)
                or [],
                get_all_item_cards=lambda **kw: [201, 202],
                get_topic_cards_by_tag=lambda tag, **kw: [],
                get_all_topic_cards=lambda **kw: [],
            ):
                result = scheduler.get_card_from_scheduler(use_tags=False)
        assert result.card in [201, 202]
        assert result.tag is None
        assert tag_fetch_calls == [], "tag-based fetch should not be called"

    def test_tag_is_none_in_result(self):
        with _patch_soft_pick(card_type="items", mode="priority", use_tags=False):
            with _mock_card_utils(all_item=[201]):
                result = scheduler.get_card_from_scheduler(use_tags=False)
        assert result.tag is None

    def test_tag_counts_not_updated(self):
        counts = {"type": {}, "tags": {}, "mode": {}}
        with _patch_soft_pick(card_type="items", mode="priority", use_tags=False):
            with _mock_card_utils(all_item=[201]):
                scheduler.get_card_from_scheduler(use_tags=False, counts=counts)
        assert counts["tags"] == {}

    def test_use_tags_true_still_calls_tag_fetch(self):
        tag_fetch_calls = []
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with patch.multiple(
                "scheduler.card_utils",
                get_item_cards_by_tag=lambda tag, **kw: tag_fetch_calls.append(tag)
                or [201],
                get_all_item_cards=lambda **kw: [],
                get_topic_cards_by_tag=lambda tag, **kw: [],
                get_all_topic_cards=lambda **kw: [],
            ):
                result = scheduler.get_card_from_scheduler(use_tags=True)
        assert tag_fetch_calls == ["health"]
        assert result.tag == "health"


# ---------------------------------------------------------------------------
# Counts tracking
# ---------------------------------------------------------------------------


class TestCountsTracking:
    def test_counts_passed_to_scheduler_not_modified(self):
        """Scheduler uses counts for soft_pick decisions but does not modify the dict.
        The caller (_pick in __init__.py) is responsible for updating counts from the result."""
        counts = {"type": {}, "tags": {}, "mode": {}}
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201]):
                result = scheduler.get_card_from_scheduler(counts=counts, use_tags=True)
        assert result.card_type == "items"
        assert result.tag == "health"
        assert result.mode == "priority"
        assert counts == {"type": {}, "tags": {}, "mode": {}}  # unchanged by scheduler

    def test_scheduler_called_repeatedly_with_same_counts(self):
        """Scheduler can be called multiple times with the same counts dict."""
        counts = {"type": {}, "tags": {}, "mode": {}}
        with _mock_card_utils(tag_item=[201]):
            for _ in range(3):
                with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
                    result = scheduler.get_card_from_scheduler(
                        counts=counts, use_tags=True
                    )
        assert result.card == 201

    def test_default_counts_do_not_persist_between_calls(self):
        """Each call with counts=None should start fresh."""
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201]):
                r1 = scheduler.get_card_from_scheduler()
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201]):
                r2 = scheduler.get_card_from_scheduler()
        assert r1.card == r2.card  # no carry-over state


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_card_returned(self):
        with _patch_soft_pick(card_type="items", mode="priority"):
            with _mock_card_utils(tag_item=[999]):
                result = scheduler.get_card_from_scheduler(use_tags=True)
        assert result.card == 999


# ---------------------------------------------------------------------------
# "Other cards" remainder — partial tag weights
# ---------------------------------------------------------------------------


class TestOtherCardsRemainder:
    """When tag weights sum to < 1.0, the remainder is offered as NO_TAGS_KEY."""

    def test_full_weight_no_remainder_added(self):
        """sum(tag_weights) == 1.0 → NO_TAGS_KEY not added to extended weights."""
        calls = []
        # Capture the weights passed to soft_pick
        original_sp = scheduler.soft_pick

        def capturing_sp(weights, counts, *a, **kw):
            calls.append(dict(weights))
            return list(weights.keys())[0]  # always return first key

        with patch("scheduler.soft_pick", side_effect=capturing_sp):
            with _mock_card_utils(tag_item=[201]):
                scheduler.get_card_from_scheduler(
                    use_tags=True,
                    tag_weights={"health": 0.5, "psych": 0.5},  # sum = 1.0
                )
        # Third call is the tag soft_pick — NO_TAGS_KEY must NOT be present
        tag_weights_call = calls[2]
        assert NO_TAGS_KEY not in tag_weights_call

    def test_partial_weight_adds_remainder_key(self):
        """sum(tag_weights) == 0.20 → NO_TAGS_KEY with weight 0.80 is added."""
        calls = []

        def capturing_sp(weights, counts, *a, **kw):
            calls.append(dict(weights))
            return list(weights.keys())[0]

        with patch("scheduler.soft_pick", side_effect=capturing_sp):
            with _mock_card_utils(all_item=[201]):
                scheduler.get_card_from_scheduler(
                    use_tags=True,
                    tag_weights={"statistics": 0.20},  # sum = 0.20
                )
        tag_weights_call = calls[2]
        assert NO_TAGS_KEY in tag_weights_call
        assert abs(tag_weights_call[NO_TAGS_KEY] - 0.80) < 1e-6

    def test_include_rest_false_does_not_add_remainder_key(self):
        calls = []

        def capturing_sp(weights, counts, *a, **kw):
            calls.append(dict(weights))
            return list(weights.keys())[0]

        with patch("scheduler.soft_pick", side_effect=capturing_sp):
            with _mock_card_utils(tag_item=[201]):
                scheduler.get_card_from_scheduler(
                    use_tags=True,
                    include_rest=False,
                    tag_weights={"statistics": 0.20},
                )

        tag_weights_call = calls[2]
        assert NO_TAGS_KEY not in tag_weights_call

    def test_no_tags_key_selection_uses_general_pool(self):
        """When soft_pick returns NO_TAGS_KEY, the general pool is used."""
        tag_fetch_calls = []
        with patch(
            "scheduler.soft_pick", side_effect=["items", "priority", NO_TAGS_KEY]
        ):
            with patch.multiple(
                "scheduler.card_utils",
                get_item_cards_by_tag=lambda tag, **kw: tag_fetch_calls.append(tag)
                or [],
                get_all_item_cards=lambda **kw: [501, 502],
                get_topic_cards_by_tag=lambda tag, **kw: [],
                get_all_topic_cards=lambda **kw: [],
            ):
                result = scheduler.get_card_from_scheduler(
                    use_tags=True,
                    tag_weights={"statistics": 0.20},
                )
        assert result.card in [501, 502]
        assert result.tag == NO_TAGS_KEY  # sentinel returned for debt tracking
        assert tag_fetch_calls == [], (
            "tag-based fetch must not be called for NO_TAGS_KEY"
        )

    def test_no_tags_key_result_has_correct_type(self):
        """An 'other' pick correctly reports its actual card type."""
        with patch(
            "scheduler.soft_pick", side_effect=["topics", "priority", NO_TAGS_KEY]
        ):
            with _mock_card_utils(all_topic=[101]):
                result = scheduler.get_card_from_scheduler(
                    use_tags=True,
                    tag_weights={"statistics": 0.20},
                )
        assert result.card == 101
        assert result.card_type == "topics"
        assert result.tag == NO_TAGS_KEY


# ---------------------------------------------------------------------------
# Forced dimensions (force_card_type / force_mode)
# ---------------------------------------------------------------------------


class TestForcedDimensions:
    def test_force_card_type_topics(self):
        """force_card_type bypasses soft_pick and pins the type."""
        with patch("scheduler.soft_pick", side_effect=["priority"]) as mock_sp:
            with _mock_card_utils(all_topic=[101]):
                result = scheduler.get_card_from_scheduler(
                    force_card_type="topics", use_tags=False
                )
        assert result.card == 101
        assert result.card_type == "topics"
        # soft_pick called only once (for mode, not for type)
        assert mock_sp.call_count == 1

    def test_force_card_type_items(self):
        with patch("scheduler.soft_pick", side_effect=["priority"]):
            with _mock_card_utils(all_item=[201]):
                result = scheduler.get_card_from_scheduler(
                    force_card_type="items", use_tags=False
                )
        assert result.card == 201
        assert result.card_type == "items"

    def test_forced_topic_does_not_consume_an_item_when_topic_pool_is_empty(self):
        with patch("scheduler.soft_pick", return_value="priority"):
            with _mock_card_utils(all_topic=[], all_item=[201]):
                result = scheduler.get_card_from_scheduler(
                    force_card_type="topics",
                    use_tags=False,
                )

        assert result.card is None
        assert result.card_type == "topics"

    def test_force_mode_priority(self):
        """force_mode bypasses soft_pick and pins the mode."""
        with patch("scheduler.soft_pick", side_effect=["items"]) as mock_sp:
            with _mock_card_utils(all_item=[201, 202, 203]):
                result = scheduler.get_card_from_scheduler(
                    force_mode="priority", use_tags=False
                )
        assert result.card == 201  # priority → first card
        assert result.mode == "priority"
        assert mock_sp.call_count == 1  # only type was soft-picked

    def test_force_both_skips_all_soft_picks(self):
        """When both are forced, soft_pick is never called."""
        with patch("scheduler.soft_pick") as mock_sp:
            with _mock_card_utils(all_topic=[101]):
                result = scheduler.get_card_from_scheduler(
                    force_card_type="topics", force_mode="priority", use_tags=False
                )
        mock_sp.assert_not_called()
        assert result.card == 101
        assert result.card_type == "topics"
        assert result.mode == "priority"


# ---------------------------------------------------------------------------
# Priority mode — sort by due date
# ---------------------------------------------------------------------------


class TestPriorityModeSort:
    """Verify that priority mode returns the most overdue card (lowest due value)."""

    def _make_db_mock(self, due_map: dict) -> MagicMock:
        """Build a mock_mw whose col.db.all returns rows for the given {cid: due}."""
        mock_mw = MagicMock()
        rows = list(due_map.items())  # [(cid, due), ...]
        mock_mw.col.find_cards.return_value = list(due_map.keys())
        mock_mw.col.db.all.return_value = rows
        return mock_mw

    def test_priority_returns_most_overdue_card_no_tags(self):
        """cards[0] after sort should be the card with the smallest due value."""
        with patch("cards.mw", self._make_db_mock({201: 10, 202: 1, 203: 5})):
            with patch("scheduler.soft_pick", side_effect=["items", "priority"]):
                result = scheduler.get_card_from_scheduler(use_tags=False)
        assert result.card == 202  # due=1, most overdue
        assert result.mode == "priority"

    def test_priority_returns_most_overdue_card_with_tags(self):
        with patch("cards.mw", self._make_db_mock({101: 3, 102: 1, 103: 8})):
            with _patch_soft_pick(card_type="topics", tag="health", mode="priority"):
                result = scheduler.get_card_from_scheduler(use_tags=True)
        assert result.card == 102  # due=1, most overdue
        assert result.mode == "priority"

    def test_priority_already_sorted_returns_first(self):
        """If cards are already in due order, cards[0] is still most overdue."""
        with patch("cards.mw", self._make_db_mock({301: 1, 302: 5, 303: 10})):
            with patch("scheduler.soft_pick", side_effect=["items", "priority"]):
                result = scheduler.get_card_from_scheduler(use_tags=False)
        assert result.card == 301  # due=1, already first

    def test_large_shared_priority_pool_is_sorted_only_once(self):
        card_ids = list(range(1, 1001))
        pool_cache = {}
        excluded = set()
        get_items = MagicMock(return_value=card_ids)

        with patch.multiple(
            "scheduler.card_utils",
            get_all_item_cards=get_items,
            get_all_topic_cards=MagicMock(return_value=[]),
            sort_cards_for_priority_mode=MagicMock(
                side_effect=lambda ids, **_kwargs: list(reversed(ids))
            ),
        ) as _unused:
            sort_cards = scheduler.card_utils.sort_cards_for_priority_mode
            picked = []
            for _ in card_ids:
                result = scheduler.get_card_from_scheduler(
                    force_card_type="items",
                    force_mode="priority",
                    use_tags=False,
                    exclude_ids=excluded,
                    pool_cache=pool_cache,
                )
                picked.append(result.card)
                excluded.add(result.card)

        assert picked == list(reversed(card_ids))
        get_items.assert_called_once()
        sort_cards.assert_called_once()

    def test_large_shared_random_pool_is_queried_and_shuffled_only_once(self):
        card_ids = list(range(1, 1001))
        pool_cache = {}
        excluded = set()
        get_items = MagicMock(return_value=card_ids)

        with patch.multiple(
            "scheduler.card_utils",
            get_all_item_cards=get_items,
            get_all_topic_cards=MagicMock(return_value=[]),
        ), patch(
            "scheduler.random.shuffle",
            side_effect=lambda values: values.reverse(),
        ) as shuffle, patch(
            "scheduler.random.choice", side_effect=lambda values: values[0]
        ):
            picked = []
            for _ in card_ids:
                result = scheduler.get_card_from_scheduler(
                    force_card_type="items",
                    force_mode="random",
                    use_tags=False,
                    exclude_ids=excluded,
                    pool_cache=pool_cache,
                )
                picked.append(result.card)
                excluded.add(result.card)

        assert picked == list(reversed(card_ids))
        get_items.assert_called_once()
        shuffle.assert_called_once()

    def test_random_mode_uses_choice_not_first_sorted(self):
        """Random mode calls random.choice, not the sorted first card."""
        with patch("cards.mw", self._make_db_mock({401: 10, 402: 1, 403: 5})):
            with patch("scheduler.soft_pick", side_effect=["items", "random"]):
                with patch("scheduler.random.choice", return_value=403) as mock_choice:
                    result = scheduler.get_card_from_scheduler(use_tags=False)
        mock_choice.assert_called_once()
        assert result.card == 403  # random.choice result, not most overdue (402)
        assert result.mode == "random"

    def test_priority_mode_prefers_lower_numeric_priority_when_configured(self):
        with patch("cards.mw", self._make_db_mock({201: 10, 202: 1, 203: 5})), patch(
            "cards.get_all_priorities",
            return_value={201: 5.0, 202: 90.0, 203: 5.0},
        ):
            with patch("scheduler.soft_pick", side_effect=["items", "priority"]):
                result = scheduler.get_card_from_scheduler(
                    use_tags=False,
                    addon_dir="/tmp/unused",
                    priority_lower_is_more_important=True,
                )
        assert result.card == 203  # lowest priority value wins, due breaks the tie
        assert result.mode == "priority"

    def test_priority_mode_prefers_higher_numeric_priority_when_configured(self):
        with patch("cards.mw", self._make_db_mock({201: 10, 202: 1, 203: 5})), patch(
            "cards.get_all_priorities",
            return_value={201: 95.0, 202: 20.0, 203: 95.0},
        ):
            with patch("scheduler.soft_pick", side_effect=["items", "priority"]):
                result = scheduler.get_card_from_scheduler(
                    use_tags=False,
                    addon_dir="/tmp/unused",
                    priority_lower_is_more_important=False,
                )
        assert result.card == 203  # highest priority value wins, due breaks the tie
        assert result.mode == "priority"


# ---------------------------------------------------------------------------
# PDF rate paths
# ---------------------------------------------------------------------------


def _mock_card_utils_with_pdf(
    tag_topic=None,
    tag_item=None,
    all_topic=None,
    all_item=None,
    pdf_cards=None,
    pdf_tag_cards=None,
):
    tag_topic = [] if tag_topic is None else tag_topic
    tag_item = [] if tag_item is None else tag_item
    all_topic = [] if all_topic is None else all_topic
    all_item = [] if all_item is None else all_item
    pdf_cards = [] if pdf_cards is None else pdf_cards
    pdf_tag_cards = [] if pdf_tag_cards is None else pdf_tag_cards
    return patch.multiple(
        "scheduler.card_utils",
        get_topic_cards_by_tag=lambda tag, **kw: tag_topic,
        get_item_cards_by_tag=lambda tag, **kw: tag_item,
        get_all_topic_cards=lambda **kw: all_topic,
        get_all_item_cards=lambda **kw: all_item,
        get_all_pdf_cards=lambda **kw: pdf_cards,
        get_pdf_cards_by_tag=lambda tag, **kw: pdf_tag_cards,
    )


class TestPdfRatePaths:
    def test_pdf_type_returns_pdf_card_priority_mode(self):
        """When card_type=='pdf', a PDF card is returned in priority mode (index 0)."""
        with patch("scheduler.soft_pick", side_effect=["pdf", "priority"]):
            with _mock_card_utils_with_pdf(pdf_cards=[301, 302, 303]):
                result = scheduler.get_card_from_scheduler(pdf_rate=0.2, use_tags=False)
        assert result.card == 301
        assert result.card_type == "pdf"
        assert result.mode == "priority"

    def test_pdf_type_returns_pdf_card_random_mode(self):
        with patch("scheduler.soft_pick", side_effect=["pdf", "random"]):
            with _mock_card_utils_with_pdf(pdf_cards=[301, 302, 303]):
                with patch("scheduler.random.choice", return_value=302):
                    result = scheduler.get_card_from_scheduler(pdf_rate=0.2, use_tags=False)
        assert result.card == 302
        assert result.card_type == "pdf"

    def test_document_pick_preserves_epub_card_type(self):
        with patch("scheduler.soft_pick", side_effect=["pdf", "priority"]):
            with _mock_card_utils_with_pdf(pdf_cards=[301]):
                with patch("scheduler.card_utils.get_document_card_type", return_value="epub"):
                    result = scheduler.get_card_from_scheduler(pdf_rate=0.2, use_tags=False)

        assert result.card == 301
        assert result.card_type == "epub"

    def test_pdf_type_falls_back_to_topics_when_no_pdf_cards(self):
        """When pdf_cards is empty, fall back to topics (topics_rate >= 0.5)."""
        with patch("scheduler.soft_pick", side_effect=["pdf", "priority"]):
            with _mock_card_utils_with_pdf(pdf_cards=[], all_topic=[101]):
                result = scheduler.get_card_from_scheduler(
                    pdf_rate=0.2, topics_rate=0.7, use_tags=False
                )
        assert result.card == 101
        assert result.card_type == "topics"

    def test_forced_pdf_does_not_consume_a_topic_when_pdf_pool_is_empty(self):
        with patch("scheduler.soft_pick", return_value="priority"):
            with _mock_card_utils_with_pdf(pdf_cards=[], all_topic=[101]):
                result = scheduler.get_card_from_scheduler(
                    force_card_type="pdf",
                    topics_rate=0.7,
                    use_tags=False,
                )

        assert result.card is None
        assert result.card_type == "pdf"

    def test_shared_pool_cache_avoids_requerying_the_same_document_pool(self):
        cache = {}
        get_all_pdf_cards = MagicMock(return_value=[301, 302])
        with patch("scheduler.soft_pick", return_value="priority"), patch.multiple(
            "scheduler.card_utils",
            get_all_pdf_cards=get_all_pdf_cards,
            get_pdf_cards_by_tag=MagicMock(return_value=[]),
            get_document_card_type=MagicMock(return_value="pdf"),
        ):
            first = scheduler.get_card_from_scheduler(
                force_card_type="pdf",
                use_tags=False,
                pool_cache=cache,
            )
            second = scheduler.get_card_from_scheduler(
                force_card_type="pdf",
                use_tags=False,
                exclude_ids={first.card},
                pool_cache=cache,
            )

        assert (first.card, second.card) == (301, 302)
        get_all_pdf_cards.assert_called_once()

    def test_pdf_soft_pick_uses_three_way_weights(self):
        """With pdf_rate > 0, soft_pick receives a 3-key weights dict."""
        captured = []
        original_sp = scheduler.soft_pick

        def capturing_sp(weights, counts, *a, **kw):
            captured.append(dict(weights))
            return list(weights.keys())[0]

        with patch("scheduler.soft_pick", side_effect=capturing_sp):
            with _mock_card_utils_with_pdf(pdf_cards=[301]):
                scheduler.get_card_from_scheduler(pdf_rate=0.1, use_tags=False)

        type_weights = captured[0]
        assert "pdf" in type_weights
        assert "topics" in type_weights
        assert "items" in type_weights

    def test_pdf_tag_miss_does_not_fall_back_to_all_pdfs_by_default(self):
        with patch(
            "scheduler.soft_pick",
            side_effect=["pdf", "priority", "statistics", "statistics"],
        ):
            with _mock_card_utils_with_pdf(
                pdf_cards=[301],
                pdf_tag_cards=[],
                tag_topic=[101],
            ):
                result = scheduler.get_card_from_scheduler(
                    pdf_rate=0.2,
                    topics_rate=0.7,
                    use_tags=True,
                    tag_weights={"statistics": 1.0},
                )

        assert result.card == 101
        assert result.card_type == "topics"
        assert result.tag == "statistics"

    def test_pdf_tag_miss_can_use_legacy_full_pool_fallback_when_enabled(self):
        with patch("scheduler.soft_pick", side_effect=["pdf", "priority", "statistics"]):
            with _mock_card_utils_with_pdf(pdf_cards=[301], pdf_tag_cards=[]):
                result = scheduler.get_card_from_scheduler(
                    pdf_rate=0.2,
                    use_tags=True,
                    tag_weights={"statistics": 1.0},
                    allow_content_tag_fallback=True,
                )

        assert result.card == 301
        assert result.card_type == "pdf"
        assert result.tag is None


# ---------------------------------------------------------------------------
# NO_TAGS_KEY fallback when general pool is also empty
# ---------------------------------------------------------------------------


class TestNoTagsKeyEmptyFallback:
    def test_no_tags_key_falls_back_to_other_type_when_empty(self):
        """When NO_TAGS_KEY is selected and the primary type has no cards,
        fall back to the other type."""
        with patch("scheduler.soft_pick", side_effect=["topics", "priority", NO_TAGS_KEY]):
            with patch.multiple(
                "scheduler.card_utils",
                get_all_topic_cards=lambda **kw: [],
                get_all_item_cards=lambda **kw: [501, 502],
                get_topic_cards_by_tag=lambda tag, **kw: [],
                get_item_cards_by_tag=lambda tag, **kw: [],
            ):
                result = scheduler.get_card_from_scheduler(
                    use_tags=True,
                    tag_weights={"health": 0.2},
                )
        assert result.card in [501, 502]
        assert result.card_type == "items"

    def test_no_tags_key_returns_none_when_both_pools_empty(self):
        """When NO_TAGS_KEY selected and both topic and item pools are empty."""
        with patch("scheduler.soft_pick", side_effect=["topics", "priority", NO_TAGS_KEY]):
            with _mock_card_utils(all_topic=[], all_item=[]):
                result = scheduler.get_card_from_scheduler(
                    use_tags=True,
                    tag_weights={"health": 0.2},
                )
        assert result.card is None

    def test_tag_items_falls_back_to_topics_by_tag(self):
        """When items-by-tag is empty, try topics-by-tag as fallback."""
        with patch("scheduler.soft_pick", side_effect=["items", "priority", "health"]):
            with patch.multiple(
                "scheduler.card_utils",
                get_item_cards_by_tag=lambda tag, **kw: [],
                get_topic_cards_by_tag=lambda tag, **kw: [101, 102],
                get_all_topic_cards=lambda **kw: [],
                get_all_item_cards=lambda **kw: [],
            ):
                result = scheduler.get_card_from_scheduler(
                    use_tags=True,
                    tag_weights={"health": 1.0},
                )
        assert result.card in [101, 102]
        assert result.card_type == "topics"
