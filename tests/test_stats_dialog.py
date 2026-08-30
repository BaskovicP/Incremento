import importlib.util
import os
import sys


_ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_spec = importlib.util.spec_from_file_location(
    "_incremento_stats_dialog",
    os.path.join(_ADDON_ROOT, "frontend", "stats_dialog.py"),
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_incremento_stats_dialog"] = _mod
_spec.loader.exec_module(_mod)


def test_ordered_type_items_includes_document_and_web_types():
    items = _mod._ordered_type_items(
        {
            "webpage": 1,
            "topics": 2,
            "pdf": 3,
            "epub": 6,
            "youtube": 4,
            "items": 5,
        }
    )

    assert items == [
        ("Topics", 2.0),
        ("Items", 5.0),
        ("PDFs", 3.0),
        ("EPUBs", 6.0),
        ("Videos", 4.0),
        ("Web pages", 1.0),
    ]


def test_ordered_type_items_keeps_unknown_types_visible():
    assert _mod._ordered_type_items({"writing_card": 2}) == [("Writing Card", 2.0)]


def test_summary_metrics_calculates_core_values():
    metrics = dict(
        _mod._summary_metrics(
            {
                "type": {"topics": 2, "epub": 1},
                "tags": {"math": 1, "reading": 2},
                "mode": {"random": 2, "priority": 1},
            },
            {"type": {"topics": 30.0, "epub": 60.0}, "tags": {}},
        )
    )

    assert metrics["Cards studied"] == "3"
    assert metrics["Review time"] == "1m 30s"
    assert metrics["Avg/card"] == "30s"
    assert metrics["Top type/tag"] == "Topics / reading"


def test_summary_metrics_tolerates_malformed_blocks():
    metrics = dict(
        _mod._summary_metrics(
            {"type": {"topics": "2", "items": -1}, "tags": {"__no_tags__": 5}},
            {"type": {"pdf": "bad"}, "tags": {"read": "15"}},
        )
    )

    assert metrics["Cards studied"] == "2"
    assert metrics["Review time"] == "15s"
    assert metrics["Top type/tag"] == "Topics / None"


def test_tag_items_filters_internal_synthetic_tags():
    assert _mod._tag_items({"__no_tags__": 10, "science": 2, "math": "3"}) == [
        ("math", 3.0),
        ("science", 2.0),
    ]


def test_ordered_mode_items_includes_unknown_modes_without_crashing():
    assert _mod._ordered_mode_items({"priority": 1, "custom_mode": 2}) == [
        ("Priority", 1.0),
        ("Custom Mode", 2.0),
    ]


def _history_fixture():
    return [
        {
            "date": "2026-04-21",
            "counts": {
                "type": {"topics": 2, "items": 1, "writing": 1},
                "tags": {},
                "mode": {},
            },
            "seconds": {"type": {"topics": 60.0, "items": 30.0}, "tags": {}},
            "reading": {"pdf_pages": 2, "epub_pages": 1, "pages": 3},
        },
        {
            "date": "2026-04-22",
            "counts": {"type": {}, "tags": {}, "mode": {}},
            "seconds": {"type": {}, "tags": {}},
            "reading": {"pdf_pages": 0, "epub_pages": 0, "pages": 0},
        },
        {
            "date": "2026-04-23",
            "counts": {"type": {"topics": 1, "items": 3}, "tags": {}, "mode": {}},
            "seconds": {"type": {"topics": 120.0}, "tags": {}},
            "reading": {"pdf_pages": 1, "epub_pages": 3, "pages": 4},
        },
    ]


def test_history_summary_metrics_reports_cards_pages_time_and_active_days():
    assert _mod._history_summary_metrics(_history_fixture()) == [
        ("Cards studied", "8"),
        ("Pages read", "7"),
        ("Study time", "3m 30s"),
        ("Active days", "2 / 3"),
    ]


def test_history_chart_series_keeps_topics_items_other_pdf_and_epub_separate():
    series = _mod._history_chart_series(_history_fixture())

    assert series["labels"] == ["4/21", "4/22", "4/23"]
    assert series["cards"] == [
        ("Topics", [2.0, 0.0, 1.0]),
        ("Items", [1.0, 0.0, 3.0]),
        ("Other", [1.0, 0.0, 0.0]),
    ]
    assert series["pages"] == [
        ("PDF", [2.0, 0.0, 1.0]),
        ("EPUB", [1.0, 0.0, 3.0]),
    ]
    assert series["minutes"] == [("Minutes", [1.5, 0.0, 2.0])]


def test_history_insight_reports_streak_and_active_day_averages():
    assert _mod._history_insight(_history_fixture()) == (
        "Current streak: 1 day · Active-day average: 4 cards and 3.5 pages"
    )
