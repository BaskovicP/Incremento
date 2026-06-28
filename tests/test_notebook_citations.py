import importlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.modules.setdefault("PyQt6", MagicMock())
sys.modules.setdefault("PyQt6.QtPdf", MagicMock())

import db  # noqa: E402

sys.modules.setdefault("db", db)

import notebook_citations  # noqa: E402

notebook_citations = importlib.reload(notebook_citations)

from pdf_highlights import load_highlights  # noqa: E402


def _word(x0, y0, x1, y1, text, block=0, line=0, word_no=0):
    return (x0, y0, x1, y1, text, block, line, word_no)


class _FakePage:
    def __init__(self, words):
        self._words = list(words)

    def get_text(self, mode, sort=True):
        assert mode == "words"
        assert sort is True
        return list(self._words)


class _FakeDoc:
    def __init__(self, pages):
        self._pages = [_FakePage(page_words) for page_words in pages]

    def __len__(self):
        return len(self._pages)

    def load_page(self, index):
        return self._pages[index]

    def close(self):
        return None


def _selected_card():
    return [{"card_id": 11, "title": "Test PDF", "stored_filename": "stored.pdf"}]


def _pdf_path(tmp_path):
    path = tmp_path / "stored.pdf"
    path.write_bytes(b"%PDF-1.4 test")
    return path


def _notebook_path(tmp_path):
    path = tmp_path / "Notebook.html"
    path.write_text("<html></html>", encoding="utf-8")
    return path


def _named_notebook_path(tmp_path, name, contents):
    path = tmp_path / name
    path.write_text(contents, encoding="utf-8")
    return path


def test_parse_notebook_html_extracts_sections_metadata_and_text():
    html = """
    <div class="sectionHeading">Chapter&nbsp;1 &amp; “Warm-up”</div>
    <div class="noteHeading">Highlight (Blue) - Location 123</div>
    <div class="noteText">“Quoted”  line &amp; text</div>
    <div class="noteHeading">Highlight (Green) - Page 17</div>
    <div class="noteText">Second<br>highlight</div>
    <div class="noteHeading">Note - Page 17</div>
    <div class="noteText">Margin&nbsp;note</div>
    """

    entries = notebook_citations.parse_notebook_html(html)

    assert entries == [
        {
            "section": 'Chapter 1 & “Warm-up”',
            "kind": "highlight",
            "color": "blue",
            "page": None,
            "location": 123,
            "text": '“Quoted” line & text',
            "ordinal": 1,
        },
        {
            "section": 'Chapter 1 & “Warm-up”',
            "kind": "highlight",
            "color": "green",
            "page": 17,
            "location": None,
            "text": "Second highlight",
            "ordinal": 2,
        },
        {
            "section": 'Chapter 1 & “Warm-up”',
            "kind": "note",
            "color": "",
            "page": 17,
            "location": None,
            "text": "Margin note",
            "ordinal": 3,
        },
    ]


def test_import_matches_highlight_across_line_breaks(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(
        open=lambda _path: _FakeDoc(
            [[
                _word(10, 10, 30, 20, "Blessed", line=0, word_no=0),
                _word(35, 10, 50, 20, "are", line=0, word_no=1),
                _word(10, 24, 35, 34, "those", line=1, word_no=0),
                _word(40, 24, 55, 34, "who", line=1, word_no=1),
            ]]
        )
    )
    entries = [{
        "section": "S",
        "kind": "highlight",
        "color": "blue",
        "page": 1,
        "location": None,
        "text": "Blessed are those who",
        "ordinal": 1,
    }]

    report = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert report["pdfs"][0]["created"] == 1
    assert rows[0]["page"] == 1
    assert rows[0]["color"] == "blue"
    assert len(rows[0]["rects"]) == 2


def test_import_prefers_parsed_page_when_same_text_exists_multiple_times(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    repeated = [
        _word(10, 10, 30, 20, "repeat", line=0, word_no=0),
        _word(35, 10, 55, 20, "quote", line=0, word_no=1),
    ]
    fitz = SimpleNamespace(open=lambda _path: _FakeDoc([repeated, repeated]))
    entries = [{
        "section": "S",
        "kind": "highlight",
        "color": "yellow",
        "page": 2,
        "location": None,
        "text": "repeat quote",
        "ordinal": 1,
    }]

    notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert rows[0]["page"] == 2


def test_import_scans_all_pages_for_location_only_entries(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(
        open=lambda _path: _FakeDoc(
            [
                [_word(10, 10, 20, 20, "other", line=0, word_no=0)],
                [_word(10, 10, 30, 20, "target", line=0, word_no=0)],
            ]
        )
    )
    entries = [{
        "section": "S",
        "kind": "highlight",
        "color": "green",
        "page": None,
        "location": 42,
        "text": "target",
        "ordinal": 1,
    }]

    notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert rows[0]["page"] == 2


def test_import_matches_quote_across_page_boundary(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(
        open=lambda _path: _FakeDoc(
            [
                [
                    _word(10, 10, 40, 20, "These", line=0, word_no=0),
                    _word(45, 10, 80, 20, "virtues", line=0, word_no=1),
                    _word(85, 10, 110, 20, "are", line=0, word_no=2),
                ],
                [
                    _word(10, 10, 35, 20, "the", line=0, word_no=0),
                    _word(40, 10, 95, 20, "foundation", line=0, word_no=1),
                ],
            ]
        )
    )
    entries = [{
        "section": "S",
        "kind": "highlight",
        "color": "pink",
        "page": 1,
        "location": None,
        "text": "These virtues are the foundation",
        "ordinal": 1,
    }]

    report = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert report["pdfs"][0]["created"] == 1
    assert report["pdfs"][0]["unmatched_highlights"] == 0
    assert rows[0]["page"] == 1
    assert rows[0]["rects"]


def test_import_uses_deterministic_ids_on_reimport(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(
        open=lambda _path: _FakeDoc(
            [[_word(10, 10, 30, 20, "repeat", line=0, word_no=0)]]
        )
    )
    entries = [{
        "section": "S",
        "kind": "highlight",
        "color": "yellow",
        "page": 1,
        "location": None,
        "text": "repeat",
        "ordinal": 1,
    }]

    first = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )
    second = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert first["pdfs"][0]["created"] == 1
    assert second["pdfs"][0]["updated"] == 1
    assert len(rows) == 1


def test_import_dedupes_old_entries_from_fresh_notebook_export(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(
        open=lambda _path: _FakeDoc(
            [[_word(10, 10, 30, 20, "repeat", line=0, word_no=0)]]
        )
    )
    entries = [{
        "section": "Section A",
        "kind": "highlight",
        "color": "yellow",
        "page": 1,
        "location": None,
        "text": "repeat",
        "ordinal": 1,
    }]

    first_path = _named_notebook_path(tmp_path, "Notebook-old.html", "<html>old export</html>")
    second_path = _named_notebook_path(tmp_path, "Notebook-new.html", "<html>fresh export with more entries</html>")

    first = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(first_path),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )
    second = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(second_path),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert first["pdfs"][0]["created"] == 1
    assert second["pdfs"][0]["updated"] == 1
    assert len(rows) == 1


def test_import_falls_back_to_yellow_for_unknown_color(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(
        open=lambda _path: _FakeDoc(
            [[_word(10, 10, 30, 20, "color", line=0, word_no=0)]]
        )
    )
    entries = [{
        "section": "S",
        "kind": "highlight",
        "color": "magenta",
        "page": 1,
        "location": None,
        "text": "color",
        "ordinal": 1,
    }]

    notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert rows[0]["color"] == "yellow"


def test_import_attaches_page_notes_to_same_page_imported_highlights(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(
        open=lambda _path: _FakeDoc(
            [[], [], [_word(10, 10, 30, 20, "anchor", line=0, word_no=0)]]
        )
    )
    entries = [
        {
            "section": "S",
            "kind": "highlight",
            "color": "orange",
            "page": 3,
            "location": None,
            "text": "anchor",
            "ordinal": 1,
        },
        {
            "section": "S",
            "kind": "note",
            "color": "",
            "page": 3,
            "location": None,
            "text": "Margin note",
            "ordinal": 2,
        },
    ]

    report = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    rows = load_highlights(str(tmp_path), "TestProfile", 11)
    assert report["pdfs"][0]["notes_attached"] == 1
    assert rows[0]["note"] == "Margin note"
    assert rows[0]["color"] == "orange"


def test_import_reports_unmatched_highlights_and_unattached_notes(tmp_path, monkeypatch):
    pdf_path = _pdf_path(tmp_path)
    monkeypatch.setattr(notebook_citations, "pdf_storage_abspath", lambda _: str(pdf_path))
    fitz = SimpleNamespace(open=lambda _path: _FakeDoc([[ _word(10, 10, 20, 20, "present") ]]))
    entries = [
        {
            "section": "S",
            "kind": "highlight",
            "color": "red",
            "page": 1,
            "location": None,
            "text": "missing quote",
            "ordinal": 1,
        },
        {
            "section": "S",
            "kind": "note",
            "color": "",
            "page": 1,
            "location": None,
            "text": "Detached note",
            "ordinal": 2,
        },
    ]

    report = notebook_citations.import_notebook_citations(
        str(tmp_path),
        "TestProfile",
        str(_notebook_path(tmp_path)),
        _selected_card(),
        entries=entries,
        fitz_module=fitz,
    )

    assert report["pdfs"][0]["unmatched_highlights"] == 1
    assert report["pdfs"][0]["unattached_notes"] == 1
    assert report["pdfs"][0]["unmatched_highlight_entries"] == [
        {
            "ordinal": 1,
            "section": "S",
            "page": 1,
            "location": None,
            "text": "missing quote",
        }
    ]
    assert report["pdfs"][0]["unattached_note_entries"] == [
        {
            "ordinal": 2,
            "section": "S",
            "page": 1,
            "location": None,
            "text": "Detached note",
        }
    ]
