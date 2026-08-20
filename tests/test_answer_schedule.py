from types import SimpleNamespace
from unittest.mock import MagicMock

import answer_schedule


def _collection_with_existing(existing_ids):
    col = MagicMock()
    col.db.list.side_effect = lambda _sql, *ids: [
        value for value in ids if value in existing_ids
    ]
    return col


def test_new_answer_revlog_rejects_the_pre_answer_row():
    col = MagicMock()
    col.db.scalar.return_value = 100
    assert answer_schedule.new_answer_revlog_id(
        42,
        100,
        collection=col,
    ) == 0
    col.db.scalar.return_value = 101
    assert answer_schedule.new_answer_revlog_id(
        42,
        100,
        collection=col,
    ) == 101


def test_new_answer_revlog_rejects_an_older_surviving_row():
    col = MagicMock()
    col.db.scalar.return_value = 99

    assert answer_schedule.new_answer_revlog_id(
        42,
        100,
        collection=col,
    ) == 0


def test_revlog_query_failure_is_distinct_from_an_empty_history():
    col = MagicMock()
    col.db.scalar.side_effect = RuntimeError("db unavailable")
    assert answer_schedule.answer_revlog_snapshot(
        42,
        collection=col,
    ) == (False, 0)
    assert answer_schedule.new_answer_revlog_id(
        42,
        0,
        collection=col,
    ) == 0


def test_detects_only_filtered_decks_with_rescheduling_disabled():
    card = SimpleNamespace(did=9, odid=1)
    col = MagicMock()
    col.decks.get.return_value = {"dyn": 1, "resched": False}

    assert answer_schedule.is_nonrescheduling_filtered_card(
        card,
        collection=col,
    ) is True

    col.decks.get.return_value = {"dyn": 1, "resched": True}
    assert answer_schedule.is_nonrescheduling_filtered_card(
        card,
        collection=col,
    ) is False
    card.odid = 0
    assert answer_schedule.is_nonrescheduling_filtered_card(
        card,
        collection=col,
    ) is False


def test_tracker_accepts_undo_then_only_the_matching_redo():
    tracker = answer_schedule.ReviewRevlogTracker()
    tracker.track("Profile A", 42, 100)
    existing = set()
    col = _collection_with_existing(existing)

    undo = list(
        tracker.transitions(
            SimpleNamespace(can_redo=True),
            collection=col,
        )
    )
    assert undo == [("Profile A", 42, frozenset(), frozenset({100}))]

    existing.add(100)
    redo = list(
        tracker.transitions(
            SimpleNamespace(can_redo=False),
            collection=col,
        )
    )
    assert redo == [("Profile A", 42, frozenset({100}), frozenset())]


def test_tracker_retires_redo_candidate_when_anki_clears_redo_stack():
    tracker = answer_schedule.ReviewRevlogTracker()
    tracker.track("Profile A", 42, 100)
    existing = set()
    col = _collection_with_existing(existing)

    assert list(
        tracker.transitions(
            SimpleNamespace(can_redo=True),
            collection=col,
        )
    ) == [("Profile A", 42, frozenset(), frozenset({100}))]

    # A different Anki operation clears Redo without restoring the revlog.
    assert list(
        tracker.transitions(
            SimpleNamespace(can_redo=False),
            collection=col,
        )
    ) == []

    # A later sync/reimport of that id must not be mistaken for Redo.
    existing.add(100)
    assert list(
        tracker.transitions(
            SimpleNamespace(can_redo=False),
            collection=col,
        )
    ) == []


def test_tracker_does_not_treat_history_deletion_as_undo_or_later_sync_as_redo():
    tracker = answer_schedule.ReviewRevlogTracker()
    tracker.track("Profile A", 42, 100)
    existing = set()
    col = _collection_with_existing(existing)

    assert list(
        tracker.transitions(
            SimpleNamespace(can_redo=False),
            collection=col,
        )
    ) == []

    existing.add(100)
    assert list(
        tracker.transitions(
            SimpleNamespace(can_redo=False),
            collection=col,
        )
    ) == []


def test_tracker_is_profile_scoped_and_clear_discards_all_state():
    tracker = answer_schedule.ReviewRevlogTracker()
    tracker.track("Profile A", 42, 100)
    tracker.track("Profile B", 42, 200)
    tracker.clear()

    col = _collection_with_existing(set())
    assert list(tracker.transitions(None, collection=col)) == []
