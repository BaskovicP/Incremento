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
