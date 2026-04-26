"""Tests for epub_highlights helpers."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "_incremento_epub_highlights",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "epub_highlights.py")),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

load_highlights = _mod.load_highlights
add_highlight = _mod.add_highlight
remove_highlight = _mod.remove_highlight


def make_hl(
    hl_id="hl-1",
    section_index=0,
    color="yellow",
    text="hello",
    note="",
    start_offset=10,
    end_offset=20,
):
    return {
        "id": hl_id,
        "sectionIndex": section_index,
        "color": color,
        "text": text,
        "note": note,
        "startOffset": start_offset,
        "endOffset": end_offset,
    }


class TestEpubHighlights:
    def test_empty_when_none_added(self, tmp_path):
        assert load_highlights(str(tmp_path), "TestProfile", 1) == []

    def test_round_trips_note_text(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl(note="Context note"))
        result = load_highlights(str(tmp_path), "TestProfile", 1)
        assert result == [
            {
                "id": "hl-1",
                "sectionIndex": 0,
                "color": "yellow",
                "text": "hello",
                "note": "Context note",
                "startOffset": 10,
                "endOffset": 20,
            }
        ]

    def test_defaults_for_missing_fields(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 2, {"id": "hl-x"})
        result = load_highlights(str(tmp_path), "TestProfile", 2)
        assert result[0]["color"] == "yellow"
        assert result[0]["text"] == ""
        assert result[0]["note"] == ""
        assert result[0]["startOffset"] == 0
        assert result[0]["endOffset"] == 0

    def test_remove_highlight(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 3, make_hl("hl-a"))
        remove_highlight(str(tmp_path), "TestProfile", 3, "hl-a")
        assert load_highlights(str(tmp_path), "TestProfile", 3) == []
