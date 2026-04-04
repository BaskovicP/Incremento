"""Tests for pdf_highlights functions in backend/pdf_highlights.py."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "_incremento_pdf_highlights",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "pdf_highlights.py")),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

load_highlights = _mod.load_highlights
add_highlight = _mod.add_highlight
remove_highlight = _mod.remove_highlight


def make_hl(hl_id="hl-1", page=1, color="yellow", text="hello", rects=None):
    return {"id": hl_id, "page": page, "color": color, "text": text, "rects": rects or []}


class TestLoadHighlights:
    def test_empty_when_none_added(self, tmp_path):
        assert load_highlights(str(tmp_path), "TestProfile", 1) == []

    def test_returns_added_highlight(self, tmp_path):
        hl = make_hl()
        add_highlight(str(tmp_path), "TestProfile", 1, hl)
        result = load_highlights(str(tmp_path), "TestProfile", 1)
        assert len(result) == 1
        assert result[0]["id"] == "hl-1"
        assert result[0]["text"] == "hello"
        assert result[0]["color"] == "yellow"
        assert result[0]["page"] == 1
        assert result[0]["rects"] == []

    def test_rects_deserialized_from_json(self, tmp_path):
        hl = make_hl(rects=[{"x": 10, "y": 20, "w": 30, "h": 5}])
        add_highlight(str(tmp_path), "TestProfile", 1, hl)
        result = load_highlights(str(tmp_path), "TestProfile", 1)
        assert result[0]["rects"] == [{"x": 10, "y": 20, "w": 30, "h": 5}]

    def test_only_returns_highlights_for_card(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-a"))
        add_highlight(str(tmp_path), "TestProfile", 2, make_hl("hl-b"))
        result1 = load_highlights(str(tmp_path), "TestProfile", 1)
        result2 = load_highlights(str(tmp_path), "TestProfile", 2)
        assert len(result1) == 1
        assert result1[0]["id"] == "hl-a"
        assert len(result2) == 1
        assert result2[0]["id"] == "hl-b"


class TestAddHighlight:
    def test_adds_multiple_highlights(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-1"))
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-2", page=2, color="blue"))
        result = load_highlights(str(tmp_path), "TestProfile", 1)
        assert len(result) == 2

    def test_replace_on_duplicate_id(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-1", text="old"))
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-1", text="new"))
        result = load_highlights(str(tmp_path), "TestProfile", 1)
        assert len(result) == 1
        assert result[0]["text"] == "new"

    def test_defaults_for_missing_fields(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 5, {"id": "hl-x"})
        result = load_highlights(str(tmp_path), "TestProfile", 5)
        assert result[0]["page"] == 1
        assert result[0]["color"] == "yellow"
        assert result[0]["text"] == ""
        assert result[0]["rects"] == []


class TestRemoveHighlight:
    def test_removes_specific_highlight(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-1"))
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-2"))
        remove_highlight(str(tmp_path), "TestProfile", 1, "hl-1")
        result = load_highlights(str(tmp_path), "TestProfile", 1)
        assert len(result) == 1
        assert result[0]["id"] == "hl-2"

    def test_remove_nonexistent_is_noop(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-1"))
        remove_highlight(str(tmp_path), "TestProfile", 1, "nonexistent")
        assert len(load_highlights(str(tmp_path), "TestProfile", 1)) == 1

    def test_does_not_remove_other_cards_highlight(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 1, make_hl("hl-1"))
        add_highlight(str(tmp_path), "TestProfile", 2, make_hl("hl-1"))
        remove_highlight(str(tmp_path), "TestProfile", 1, "hl-1")
        assert load_highlights(str(tmp_path), "TestProfile", 1) == []
        assert len(load_highlights(str(tmp_path), "TestProfile", 2)) == 1

    def test_remove_all_leaves_empty(self, tmp_path):
        add_highlight(str(tmp_path), "TestProfile", 3, make_hl("hl-a"))
        remove_highlight(str(tmp_path), "TestProfile", 3, "hl-a")
        assert load_highlights(str(tmp_path), "TestProfile", 3) == []
