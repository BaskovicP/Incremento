import types
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("session", MagicMock())
import aqt

import pdf_dock


class _FakeNote:
    def __init__(self):
        self.tags = ["alpha", "beta"]
        self._fields = {
            "Front": "Main title\nSecond line",
            "Back": "Answer text",
            "Incremento_Source_Title": "Hidden source",
            "Empty": "   ",
        }

    def note_type(self):
        return {
            "flds": [
                {"name": "Front"},
                {"name": "Back"},
                {"name": "Incremento_Source_Title"},
                {"name": "Empty"},
            ]
        }

    def __getitem__(self, key):
        return self._fields[key]

    def cards(self):
        return [object(), object()]


def test_load_pdf_page_note_preview_filters_hidden_and_empty_fields(monkeypatch):
    fake_mw = types.SimpleNamespace(
        col=types.SimpleNamespace(get_note=lambda note_id: _FakeNote())
    )
    monkeypatch.setattr(pdf_dock, "mw", fake_mw)

    payload = pdf_dock._load_pdf_page_note_preview(123)

    assert payload is not None
    assert payload["note_id"] == 123
    assert payload["title"] == "Main title"
    assert payload["tags"] == ["alpha", "beta"]
    assert payload["card_count"] == 2
    assert payload["fields"] == [
        {"name": "Front", "value": "Main title\nSecond line"},
        {"name": "Back", "value": "Answer text"},
    ]


def test_render_pdf_page_note_preview_html_shows_tags_and_card_count():
    html = pdf_dock._render_pdf_page_note_preview_html(
        {
            "note_id": 123,
            "title": "Main title",
            "fields": [{"name": "Front", "value": "Line 1\nLine 2"}],
            "tags": ["alpha", "beta"],
            "card_count": 2,
        }
    )

    assert "PDF Page Card" not in html
    assert "Note ID 123" in html
    assert "2 cards" in html
    assert "alpha, beta" in html
    assert "Line 1<br>Line 2" in html


def test_browse_note_ids_in_browser_builds_deduplicated_query(monkeypatch):
    searches = []

    class _FakeBrowser:
        def search_for(self, query):
            searches.append(query)

    fake_dialogs = types.SimpleNamespace(open=lambda name, parent: _FakeBrowser())
    monkeypatch.setitem(sys.modules, "aqt.dialogs", fake_dialogs)
    monkeypatch.setattr(aqt, "dialogs", fake_dialogs, raising=False)

    assert pdf_dock._browse_note_ids_in_browser([11, 12, 11, 0, -1]) is True
    assert searches == ["nid:11 OR nid:12"]


def test_browse_note_ids_in_browser_shows_empty_tooltip(monkeypatch):
    tooltips = []
    monkeypatch.setattr(pdf_dock, "tooltip", lambda message: tooltips.append(message))

    assert pdf_dock._browse_note_ids_in_browser([], empty_message="No cards yet.") is False
    assert tooltips == ["No cards yet."]


def test_reconcile_pdf_page_sources_prunes_missing_notes(monkeypatch):
    deleted = []
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        pdf_dock,
        "get_pdf_card_sources",
        lambda addon_dir, profile, pdf_card_id, page: [
            {"note_id": 11, "excerpt": "live"},
            {"note_id": 12, "excerpt": "stale"},
        ],
    )
    monkeypatch.setattr(
        pdf_dock,
        "get_pdf_page_card_counts",
        lambda addon_dir, profile, pdf_card_id: {3: 1},
    )
    monkeypatch.setattr(
        pdf_dock,
        "delete_pdf_card_sources_for_note_ids",
        lambda addon_dir, profile, pdf_card_id, note_ids: deleted.append(
            (addon_dir, profile, pdf_card_id, sorted(note_ids))
        ),
    )
    monkeypatch.setattr(
        pdf_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                get_note=lambda note_id: object() if note_id == 11 else (_ for _ in ()).throw(Exception("missing"))
            )
        ),
    )

    cards, counts = pdf_dock._reconcile_pdf_page_sources(5, 3)

    assert cards == [{"note_id": 11, "excerpt": "live"}]
    assert counts == {3: 1}
    assert deleted == [("/tmp/addon", "TestProfile", 5, [12])]


def test_add_card_source_for_new_note_prefers_pending_extract_source(monkeypatch):
    fake_add_card_dock = types.SimpleNamespace(
        pending_extract_options=lambda: {"source": "reviewer"},
        recent_fill_source=lambda: "pdf",
    )
    monkeypatch.setitem(sys.modules, "add_card_dock", fake_add_card_dock)

    assert pdf_dock._add_card_source_for_new_note() == "reviewer"


def test_pdf_citation_escapes_onclick_payload_and_label(monkeypatch):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer's-guide.pdf")
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "get_page", lambda addon_dir, profile, card_id: 42)
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda filename: 'Writer "First" & <Best>')

    html = pdf_dock.pdf_citation()

    assert 'onclick="pycmd(&quot;incremento_open_pdf_ref:' in html
    assert "writer&#x27;s-guide.pdf" in html
    assert "Writer &quot;First&quot; &amp; &lt;Best&gt;" in html
    assert 'card_id\\&quot;: 55' in html
    assert '=""' not in html


def test_repair_legacy_pdf_reference_links_html_fixes_broken_anchor():
    html = (
        'Before <a onclick="pycmd(" incremento_open_pdf_ref:{\\"card_id\\":="" 1776888912488,="" '
        '\\"filename\\":="" \\"write-a-must-read.pdf\\",="" \\"page\\":="" 42}");="" return="" false;"="" '
        'style="cursor:pointer; color:#4a90d9; text-decoration:none;">Page 42. of write a must read</a> After'
    )

    repaired = pdf_dock.repair_legacy_pdf_reference_links_html(html)

    assert 'onclick="pycmd(&quot;incremento_open_pdf_ref:' in repaired
    assert "write-a-must-read.pdf" in repaired
    assert "Page 42. of write a must read</a>" in repaired
    assert '=""' not in repaired
    assert repaired.startswith("Before ")


def test_on_add_cards_did_add_note_ignores_reviewer_extract(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_add_card_source_for_new_note", lambda: "reviewer")
    monkeypatch.setattr(
        pdf_dock,
        "get_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("not a PDF add")),
    )
    monkeypatch.setattr(
        pdf_dock,
        "add_pdf_card_source",
        lambda *args, **kwargs: calls.append(args),
    )

    pdf_dock.on_add_cards_did_add_note(types.SimpleNamespace(id=123, fields=["Front"]))

    assert calls == []


def test_due_review_prompt_suppression_is_one_shot_and_card_scoped(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(pdf_dock.time, "monotonic", lambda: now[0])

    pdf_dock._suppress_next_due_review_prompt_for_pdf_add(55)

    assert pdf_dock._consume_due_review_prompt_suppression(56) is False
    assert pdf_dock._consume_due_review_prompt_suppression(55) is True
    assert pdf_dock._consume_due_review_prompt_suppression(55) is False

    pdf_dock._suppress_next_due_review_prompt_for_pdf_add(55)
    now[0] += pdf_dock._PDF_ADD_PROMPT_SUPPRESSION_SECONDS + 0.1

    assert pdf_dock._consume_due_review_prompt_suppression(55) is False


def test_on_add_cards_did_add_note_suppresses_next_pdf_due_prompt(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "source.pdf")
    monkeypatch.setattr(pdf_dock, "_pdf_dock", None)
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_add_card_source_for_new_note", lambda: "pdf")
    monkeypatch.setattr(pdf_dock, "get_page", lambda addon_dir, profile, card_id: 7)
    monkeypatch.setattr(
        pdf_dock,
        "add_pdf_card_source",
        lambda *args, **kwargs: calls.append(args),
    )

    pdf_dock.on_add_cards_did_add_note(types.SimpleNamespace(id=123, fields=["Front"]))

    assert calls
    assert pdf_dock._consume_due_review_prompt_suppression(55) is True
