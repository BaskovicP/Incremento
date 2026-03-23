"""Integration tests for the learnFunction picking loop and _on_card_answered logic.

These tests exercise the behaviors of the session machinery without requiring the
full Anki UI by reproducing the key logic using the public API of scheduler.py and
statistics.py with lightweight mocks.
"""

import copy
import types
from unittest.mock import MagicMock, patch

import scheduler as sched
from scheduler import NO_TAGS_KEY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stats_mock():
    """Return a mock StatsManager with an in-memory counts dict."""
    stats = MagicMock()
    stats.session  = {"type": {}, "tags": {}, "mode": {}}
    stats.counts_for.side_effect = lambda scope: stats.session
    return stats


def _simulate_pick(get_card_fn, selected_ids, added_to_filtered, picked_meta, stats, scope):
    """Replicate one iteration of the _pick() inner function from learnFunction."""
    counts = stats.counts_for(scope)
    result = get_card_fn(exclude_ids=added_to_filtered)
    if result.card is None:
        return False
    counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
    counts["mode"][result.mode]      = counts["mode"].get(result.mode, 0) + 1
    if result.tag:
        counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1
    picked_meta[result.card] = {
        "card_type": result.card_type,
        "tag":       result.tag,
        "mode":      result.mode,
    }
    added_to_filtered.add(result.card)
    selected_ids.append(result.card)
    return True


def _simulate_on_card_answered(cid, picked_meta, reviewed_ids, stats, scope):
    """Replicate _on_card_answered from learnFunction."""
    if cid not in picked_meta or cid in reviewed_ids:
        return
    reviewed_ids.add(cid)
    meta = picked_meta[cid]
    tag = None if meta["tag"] == NO_TAGS_KEY else meta["tag"]
    fake = types.SimpleNamespace(
        card=cid, card_type=meta["card_type"], tag=tag, mode=meta["mode"]
    )
    stats.record(fake, scope)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPickLoopDeduplication:
    """_pick excludes cards already selected via added_to_filtered."""

    def test_second_call_excludes_first_card(self):
        """A card returned twice by the scheduler is only added once."""
        call_count = [0]
        CARD_A = 101

        def fake_get(exclude_ids):
            call_count[0] += 1
            if CARD_A not in exclude_ids:
                return types.SimpleNamespace(card=CARD_A, card_type="items", tag=None, mode="random")
            return types.SimpleNamespace(card=None, card_type=None, tag=None, mode=None)

        stats     = _make_stats_mock()
        selected  = []
        excluded  = set()
        meta      = {}

        _simulate_pick(fake_get, selected, excluded, meta, stats, "session")
        _simulate_pick(fake_get, selected, excluded, meta, stats, "session")

        assert selected == [CARD_A], "Card should appear exactly once in selected_ids"
        assert call_count[0] == 2, "Scheduler was called twice"


class TestOnCardAnsweredDeduplication:
    """_on_card_answered only records a card once even if called repeatedly."""

    def test_second_answer_for_same_card_not_recorded(self):
        picked_meta   = {42: {"card_type": "items", "tag": None, "mode": "random"}}
        reviewed_ids  = set()
        stats         = _make_stats_mock()

        _simulate_on_card_answered(42, picked_meta, reviewed_ids, stats, "session")
        _simulate_on_card_answered(42, picked_meta, reviewed_ids, stats, "session")

        assert stats.record.call_count == 1


class TestOnCardAnsweredIgnoresUnpickedCards:
    """_on_card_answered is a no-op for cards not in picked_meta."""

    def test_card_not_in_picked_meta_not_recorded(self):
        picked_meta  = {}   # card 99 was never scheduled
        reviewed_ids = set()
        stats        = _make_stats_mock()

        _simulate_on_card_answered(99, picked_meta, reviewed_ids, stats, "session")

        stats.record.assert_not_called()


class TestNoTagsKeyNotPersisted:
    """NO_TAGS_KEY is synthetic — it must never reach stats.record as a real tag."""

    def test_no_tags_key_becomes_none(self):
        picked_meta  = {7: {"card_type": "topics", "tag": NO_TAGS_KEY, "mode": "priority"}}
        reviewed_ids = set()
        stats        = _make_stats_mock()

        _simulate_on_card_answered(7, picked_meta, reviewed_ids, stats, "session")

        call_args = stats.record.call_args
        result_ns = call_args[0][0]      # first positional arg is the fake SchedulerResult
        assert result_ns.tag is None, "NO_TAGS_KEY should be converted to None before recording"


class TestSessionCountsSnapshot:
    """Session counts accumulate correctly across multiple picks."""

    def test_type_counts_increment_per_pick(self):
        results_queue = [
            types.SimpleNamespace(card=1, card_type="topics", tag=None, mode="random"),
            types.SimpleNamespace(card=2, card_type="items",  tag=None, mode="random"),
            types.SimpleNamespace(card=3, card_type="topics", tag=None, mode="priority"),
        ]
        queue_iter = iter(results_queue)

        def fake_get(exclude_ids):
            return next(queue_iter)

        stats    = _make_stats_mock()
        selected = []
        excluded = set()
        meta     = {}

        for _ in range(3):
            _simulate_pick(fake_get, selected, excluded, meta, stats, "session")

        session_copy = copy.deepcopy(stats.session)
        assert session_copy["type"]["topics"] == 2
        assert session_copy["type"]["items"]  == 1
        assert session_copy["mode"]["random"]   == 2
        assert session_copy["mode"]["priority"] == 1
