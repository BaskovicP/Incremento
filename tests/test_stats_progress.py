"""Progress graphs must preserve daily totals, quiet days and honest comparisons."""

from copy import deepcopy
from datetime import date, timedelta

import pytest


def row(day, *, pdf=0, epub=0, cards=0, seconds=0):
    return {
        "date": day,
        "reading": {"pdf_pages": pdf, "epub_pages": epub},
        "counts": {"type": {"items": cards}},
        "seconds": {"type": {"pdf": seconds}},
    }


def test_progress_keeps_zero_days_and_cumulative_reading_separate_from_cards():
    from frontend.stats_progress import progress_model

    history = [row("2026-10-11", pdf=4, seconds=120),
               row("2026-10-13", epub=2), row("2026-10-14", pdf=3, epub=1)]
    original = deepcopy(history)
    model = progress_model(history, end_date="2026-10-14", days=4)

    assert [item["pages"] for item in model["daily"]] == [4, 0, 2, 4]
    assert model["cumulative"]["pages"] == [4, 4, 6, 10]
    assert model["cumulative"]["cards"] == [0, 0, 0, 0]
    assert model["totals"] == {"pages": 10, "cards": 0, "minutes": 2, "pdf_pages": 7, "epub_pages": 3}
    assert model["reading_days"] == 3
    assert model["active_days"] == 3
    assert model["reading_streak"] == 2
    assert history == original


@pytest.mark.parametrize("today, yesterday, expected", [(0, 2, 2), (1, 2, 3), (0, 0, 0)])
def test_reading_streak_allows_today_to_be_unfinished_but_not_a_missed_yesterday(today, yesterday, expected):
    from frontend.stats_progress import progress_model

    history = [row("2026-10-12", pdf=5), row("2026-10-13", epub=yesterday),
               row("2026-10-14", pdf=today, cards=15, seconds=600)]
    assert progress_model(history, end_date="2026-10-14", days=7)["reading_streak"] == expected


def test_comparison_uses_equal_calendar_windows_and_has_no_invented_percentage():
    from frontend.stats_progress import progress_model

    model = progress_model([row("2026-10-10", pdf=8), row("2026-10-14", epub=12)],
                           end_date="2026-10-14", days=4)
    assert model["comparison"]["pages"] == {"previous": 8, "delta": 4, "percent": 50}
    assert model["comparison"]["cards"] == {"previous": 0, "delta": 0, "percent": None}


def test_year_graph_groups_weeks_without_losing_first_last_or_zero_days():
    from frontend.stats_progress import progress_model

    start = date(2025, 10, 15)
    history = [row((start + timedelta(days=index)).isoformat(), pdf=1, epub=2, seconds=60)
               for index in range(365)]
    model = progress_model(history, end_date="2026-10-14", days=365)
    assert len(model["buckets"]) == 53
    assert model["buckets"][0]["start"] == "2025-10-15"
    assert model["buckets"][-1]["end"] == "2026-10-14"
    assert [item["days"] for item in model["buckets"]][-2:] == [7, 1]
    assert model["cumulative"]["pages"][-1] == 1095
    assert sum(item["minutes"] for item in model["buckets"]) == 365


def test_empty_dirty_and_future_rows_do_not_inflate_progress():
    from frontend.stats_progress import progress_model

    history = [None, {}, row("not-a-date", pdf=100), row("2026-10-15", pdf=99),
               row("2026-10-14", pdf=float("nan"), epub=-2, seconds=float("inf"))]
    model = progress_model(history, end_date="2026-10-14", days=7)
    assert model["totals"] == {"pages": 0, "cards": 0, "minutes": 0, "pdf_pages": 0, "epub_pages": 0}
    assert model["reading_days"] == model["reading_streak"] == 0
    assert len(model["daily"]) == 7
    assert model["cumulative"]["pages"] == [0] * 7


def test_time_only_day_is_active_without_inventing_a_reading_day():
    from frontend.stats_progress import progress_model

    model = progress_model([row("2026-10-14", seconds=600)], end_date="2026-10-14", days=7)
    assert model["reading_days"] == 0
    assert model["active_days"] == 1
