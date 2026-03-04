from unittest.mock import patch
import scheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_soft_pick(card_type="items", tag="health", mode="priority"):
    """Stub soft_pick to return deterministic decisions in order: type, tag, mode."""
    return patch("scheduler.soft_pick", side_effect=[card_type, tag, mode])


def _mock_card_utils(tag_topic=None, tag_item=None, all_topic=None, all_item=None):
    """Patch all four card fetch functions on scheduler.card_utils."""
    tag_topic = [] if tag_topic is None else tag_topic
    tag_item  = [] if tag_item  is None else tag_item
    all_topic = [] if all_topic is None else all_topic
    all_item  = [] if all_item  is None else all_item
    return patch.multiple(
        "scheduler.card_utils",
        get_topic_cards_by_tag=lambda tag: tag_topic,
        get_item_cards_by_tag=lambda tag: tag_item,
        get_all_topic_cards=lambda: all_topic,
        get_all_item_cards=lambda: all_item,
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
            result = scheduler.soft_pick({"a": 1/3, "b": 1/3, "c": 1/3}, {})
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
        larger_share  = 0.5  / (0.5  + 500.2)
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
                result = scheduler.get_card_from_scheduler()
        assert result in [101, 102]

    def test_items_fetches_from_item_function(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201, 202]):
                result = scheduler.get_card_from_scheduler()
        assert result in [201, 202]


# ---------------------------------------------------------------------------
# Mode selection (priority vs random)
# ---------------------------------------------------------------------------

class TestModeSelection:
    def test_priority_returns_first_card(self):
        with _patch_soft_pick(card_type="items", mode="priority"):
            with _mock_card_utils(tag_item=[501, 502, 503]):
                result = scheduler.get_card_from_scheduler()
        assert result == 501

    def test_random_calls_random_choice(self):
        with _patch_soft_pick(card_type="items", mode="random"):
            with _mock_card_utils(tag_item=[601, 602, 603]):
                with patch("scheduler.random.choice", return_value=602) as mock_choice:
                    result = scheduler.get_card_from_scheduler()
        mock_choice.assert_called_once_with([601, 602, 603])
        assert result == 602


# ---------------------------------------------------------------------------
# Tag fallback
# ---------------------------------------------------------------------------

class TestTagFallback:
    def test_falls_back_to_all_items_when_tag_empty(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[], all_item=[201, 202]):
                result = scheduler.get_card_from_scheduler()
        assert result in [201, 202]

    def test_falls_back_to_all_topics_when_tag_empty(self):
        with _patch_soft_pick(card_type="topics", tag="health", mode="priority"):
            with _mock_card_utils(tag_topic=[], all_topic=[101, 102]):
                result = scheduler.get_card_from_scheduler()
        assert result in [101, 102]

    def test_falls_back_to_other_type_when_selected_type_empty(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[], all_item=[], all_topic=[101, 102]):
                result = scheduler.get_card_from_scheduler()
        assert result in [101, 102]

    def test_falls_back_to_items_when_topics_empty(self):
        with _patch_soft_pick(card_type="topics", tag="health", mode="priority"):
            with _mock_card_utils(tag_topic=[], all_topic=[], all_item=[201, 202]):
                result = scheduler.get_card_from_scheduler()
        assert result in [201, 202]

    def test_returns_none_when_all_sources_empty(self):
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[], all_item=[], all_topic=[]):
                result = scheduler.get_card_from_scheduler()
        assert result is None

    def test_does_not_use_fallback_when_tag_has_cards(self):
        """Fallback (get_all_item_cards) must NOT be called when tag returns results."""
        calls = []
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with patch.multiple(
                "scheduler.card_utils",
                get_item_cards_by_tag=lambda tag: [201],
                get_all_item_cards=lambda: calls.append(1) or [999],
                get_topic_cards_by_tag=lambda tag: [],
                get_all_topic_cards=lambda: [],
            ):
                result = scheduler.get_card_from_scheduler()
        assert result == 201
        assert calls == [], "fallback should not have been called"


# ---------------------------------------------------------------------------
# Counts tracking
# ---------------------------------------------------------------------------

class TestCountsTracking:
    def test_counts_updated_after_call(self):
        counts = {"type": {}, "tags": {}, "mode": {}}
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201]):
                scheduler.get_card_from_scheduler(counts=counts)
        assert counts["type"]["items"] == 1
        assert counts["tags"]["health"] == 1
        assert counts["mode"]["priority"] == 1

    def test_counts_accumulate_across_calls(self):
        counts = {"type": {}, "tags": {}, "mode": {}}
        with _mock_card_utils(tag_item=[201]):
            for _ in range(3):
                with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
                    scheduler.get_card_from_scheduler(counts=counts)
        assert counts["type"]["items"] == 3

    def test_default_counts_do_not_persist_between_calls(self):
        """Each call with counts=None should start fresh."""
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201]):
                r1 = scheduler.get_card_from_scheduler()
        with _patch_soft_pick(card_type="items", tag="health", mode="priority"):
            with _mock_card_utils(tag_item=[201]):
                r2 = scheduler.get_card_from_scheduler()
        assert r1 == r2  # both get the same first card; no carry-over state


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_card_returned(self):
        with _patch_soft_pick(card_type="items", mode="priority"):
            with _mock_card_utils(tag_item=[999]):
                result = scheduler.get_card_from_scheduler()
        assert result == 999
