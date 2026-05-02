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
            "youtube": 4,
            "items": 5,
        }
    )

    assert items == [
        ("Topics", 2.0),
        ("Items", 5.0),
        ("PDFs", 3.0),
        ("Videos", 4.0),
        ("Web pages", 1.0),
    ]


def test_ordered_type_items_keeps_unknown_types_visible():
    assert _mod._ordered_type_items({"writing_card": 2}) == [("Writing Card", 2.0)]
