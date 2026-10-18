"""Daily memory grades come from Anki, including repeated answers and Undo."""

import sqlite3
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from backend import statistics


@pytest.fixture
def review_collection(monkeypatch):
    monkeypatch.setattr(statistics, "_logical_day_bounds_ms", lambda _cutoff: (1000, 2000))
    monkeypatch.setattr(statistics, "_effective_date", lambda _cutoff: "2026-10-13")
    database = sqlite3.connect(":memory:")
    database.execute("CREATE TABLE revlog(id INTEGER PRIMARY KEY, cid, type, ease)")
    collection = SimpleNamespace(
        db=SimpleNamespace(all=lambda sql, *args: database.execute(sql, args).fetchall()),
        get_card=lambda cid: SimpleNamespace(id=cid),
    )
    yield database, collection
    database.close()


def _load(collection, **kwargs):
    return statistics.daily_learning_outcomes_from_collection(
        collection,
        classifier=object(),
        topic_predicate=lambda card, **_kwargs: card.id == 99,
        **kwargs,
    )


def test_daily_outcomes_count_repeated_memory_grades_by_answer_stage(review_collection):
    db, collection = review_collection
    db.executemany("INSERT INTO revlog VALUES (?, ?, ?, ?)", [
        (999, 1, 1, 1),  # Before the logical day.
        (1000, 1, 0, 1), (1001, 1, 0, 1), (1002, 1, 0, 3),
        (1003, 2, 1, 2), (1004, 2, 1, 4), (1005, 3, 2, 3),
        (1006, 99, 1, 3),  # A topic frequency choice is not recall.
        (1007, 4, 3, 1), (1008, 4, 4, 1), (1009, 4, 5, 1),
        (1010, 4, 1, 0), (1011, 4, 1, 5),  # Invalid/manual ratings.
        (2000, 1, 1, 1),  # The next logical day.
    ])

    result = _load(collection)

    assert result == {
        "date": "2026-10-13",
        "cards": 3,
        "failed_cards": 1,
        "stages": {
            "learning": {"again": 2, "hard": 0, "good": 1, "easy": 0},
            "review": {"again": 0, "hard": 1, "good": 0, "easy": 1},
            "relearning": {"again": 0, "hard": 0, "good": 1, "easy": 0},
        },
    }


def test_daily_outcomes_follow_undo_and_redo_without_duplicate_counters(review_collection):
    db, collection = review_collection
    row = (1100, 1, 1, 1)
    db.execute("INSERT INTO revlog VALUES (?, ?, ?, ?)", row)
    first = _load(collection)
    db.execute("DELETE FROM revlog WHERE id = 1100")
    undone = _load(collection)
    db.execute("INSERT INTO revlog VALUES (?, ?, ?, ?)", row)

    assert first["failed_cards"] == 1
    assert undone["cards"] == 0
    assert undone["stages"]["review"]["again"] == 0
    assert _load(collection) == first


def test_daily_outcomes_do_not_truncate_a_large_day(review_collection):
    db, collection = review_collection
    db.executemany("INSERT INTO revlog VALUES (?, ?, ?, ?)", [
        (1000 + index, index + 100, 1, 3) for index in range(600)
    ])

    result = _load(collection)

    assert result["cards"] == 600
    assert result["stages"]["review"]["good"] == 600


def test_daily_outcomes_report_unavailable_or_cancelled_as_unknown(review_collection):
    _db, collection = review_collection
    assert _load(None) is None
    assert _load(collection, should_cancel=lambda: True) is None
    collection.db.all = lambda *_args: (_ for _ in ()).throw(sqlite3.OperationalError())
    assert _load(collection) is None


def test_learning_history_zero_fills_days_and_uses_the_same_memory_grade_rules(review_collection):
    db, collection = review_collection

    def stamp(day, hour=4, minute=0):
        return int(datetime(2026, 10, day, hour, minute).timestamp() * 1000)

    db.executemany("INSERT INTO revlog VALUES (?, ?, ?, ?)", [
        (stamp(7) - 1, 1, 1, 1),  # Before the seven-day window.
        (stamp(7), 1, 0, 1), (stamp(7) + 1, 1, 0, 3),
        (stamp(9) - 1, 2, 1, 2), (stamp(9), 2, 1, 4),
        (stamp(13) - 1, 1, 2, 1), (stamp(13), 1, 2, 3),
        (stamp(13) + 1, 99, 1, 3),  # Topic choice.
        (stamp(13) + 2, 3, 3, 1), (stamp(13) + 3, 3, 4, 1),
        (stamp(14), 1, 1, 1),  # After today's logical day.
    ])

    history = statistics.learning_outcome_history_from_collection(
        collection, days=7, classifier=object(),
        topic_predicate=lambda card, **_: card.id == 99,
    )

    assert [row["date"] for row in history] == [f"2026-10-{day:02}" for day in range(7, 14)]
    assert [row["cards"] for row in history] == [1, 1, 1, 0, 0, 1, 1]
    assert [row["failed_cards"] for row in history] == [1, 0, 0, 0, 0, 1, 0]
    assert history[0]["stages"]["learning"] == {"again": 1, "hard": 0, "good": 1, "easy": 0}
    assert history[1]["stages"]["review"]["hard"] == 1
    assert history[-1]["stages"]["relearning"]["good"] == 1


@pytest.mark.parametrize("days", [7, 30, 60])
def test_learning_history_returns_exact_window_and_reflects_deleted_answers(review_collection, days):
    db, collection = review_collection
    start = date(2026, 10, 13) - timedelta(days=days - 1)
    stamp = int(datetime.combine(start, datetime.min.time()).replace(hour=4).timestamp() * 1000)
    db.execute("INSERT INTO revlog VALUES (?, ?, ?, ?)", (stamp, 1, 1, 1))
    kwargs = dict(days=days, classifier=object(), topic_predicate=lambda *_args, **_kw: False)
    first = statistics.learning_outcome_history_from_collection(collection, **kwargs)
    assert len(first) == days
    assert first[0]["date"] == start.isoformat()
    assert first[0]["stages"]["review"]["again"] == 1
    db.execute("DELETE FROM revlog")
    undone = statistics.learning_outcome_history_from_collection(collection, **kwargs)
    assert sum(row["failed_cards"] for row in undone) == 0


def test_learning_history_is_bounded_and_distinguishes_unavailable_from_empty(review_collection):
    _db, collection = review_collection
    kwargs = dict(classifier=object(), topic_predicate=lambda *_args, **_kw: False)
    assert len(statistics.learning_outcome_history_from_collection(collection, days=100_000, **kwargs)) == 60
    assert statistics.learning_outcome_history_from_collection(None, **kwargs) is None
    assert statistics.learning_outcome_history_from_collection(collection, should_cancel=lambda: True, **kwargs) is None


def test_learning_history_pages_card_day_groups_without_skipping_or_duplicating(review_collection):
    db, collection = review_collection
    db.executemany("INSERT INTO revlog VALUES (?, ?, ?, ?)", [
        (int(datetime(2026, 10, day, 4).timestamp() * 1000) + index, 100 + index, 1, 3)
        for day in (11, 12, 13) for index in range(501)
    ])
    history = statistics.learning_outcome_history_from_collection(
        collection, days=7, classifier=object(), topic_predicate=lambda *_args, **_kw: False,
    )
    assert [row["cards"] for row in history] == [0, 0, 0, 0, 501, 501, 501]
    assert [row["stages"]["review"]["good"] for row in history] == [0, 0, 0, 0, 501, 501, 501]


def test_learning_history_uses_calendar_cutoffs_across_a_25_hour_day(review_collection, monkeypatch):
    db, collection = review_collection
    monkeypatch.setattr(statistics, "_effective_date", lambda _cutoff: "2026-10-26")
    try:
        with monkeypatch.context() as timezone:
            timezone.setenv("TZ", "Europe/Zagreb")
            time.tzset()
            boundary = int(datetime(2026, 10, 25, 5, 30).timestamp() * 1000)
            db.executemany("INSERT INTO revlog VALUES (?, ?, ?, ?)", [
                (boundary - 1, 1, 1, 1), (boundary, 1, 1, 3),
            ])
            history = statistics.learning_outcome_history_from_collection(
                collection, "05:30", days=3, classifier=object(),
                topic_predicate=lambda *_args, **_kw: False,
            )
            assert [row["date"] for row in history] == ["2026-10-24", "2026-10-25", "2026-10-26"]
            assert history[0]["stages"]["review"]["again"] == 1
            assert history[1]["stages"]["review"]["good"] == 1
            start, end = statistics._logical_date_bounds_ms(date(2026, 10, 24), "05:30")
            assert end - start == 25 * 60 * 60 * 1000
    finally:
        time.tzset()
