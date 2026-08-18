import types
import sys
import tempfile
from unittest.mock import MagicMock

sys.modules.setdefault("session", MagicMock())
sys.modules.setdefault("PyQt6", MagicMock())
sys.modules.setdefault("PyQt6.QtPdf", MagicMock())
sys.modules.setdefault("PyQt6.QtWebEngineWidgets", MagicMock())
sys.modules.setdefault("PyQt6.QtWebEngineCore", MagicMock())
sys.modules.setdefault("PyQt6.QtCore", MagicMock())
import aqt

import pdf_dock
from pdf_highlight_bulk_dialog import (
    can_create_pdf_highlight_bulk_rows,
    normalize_pdf_highlight_bulk_row,
    remap_pdf_highlight_bulk_row_fields,
)


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


class _BatchPdfNote:
    def __init__(self, field_names):
        self.id = 0
        self.fields = ["" for _ in field_names]
        self._field_names = list(field_names)
        self._field_map = {name: index for index, name in enumerate(field_names)}
        self._note_type = {
            "name": "Basic",
            "flds": [{"name": name} for name in field_names],
        }

    def note_type(self):
        return self._note_type

    def __getitem__(self, key):
        return self.fields[self._field_map[key]]

    def __setitem__(self, key, value):
        self.fields[self._field_map[key]] = value


class _BatchPdfModels:
    def __init__(self, model):
        self._model = model

    def by_name(self, name):
        return self._model if self._model.get("name") == name else None


class _BatchPdfDecks:
    def __init__(self, deck_name="Topics", deck_id=99):
        self._deck = {"name": deck_name, "id": deck_id}

    def by_name(self, name):
        return self._deck if self._deck["name"] == name else None

    def get(self, deck_id):
        return self._deck if int(deck_id) == self._deck["id"] else None

    def add_normal_deck_with_name(self, name):
        self._deck = {"name": name, "id": self._deck["id"]}
        return types.SimpleNamespace(id=self._deck["id"])


class _BatchPdfCollection:
    def __init__(self, model, add_results=None, deck_name="Topics", deck_id=99):
        self.models = _BatchPdfModels(model)
        self.decks = _BatchPdfDecks(deck_name=deck_name, deck_id=deck_id)
        self.created_notes = []
        self._add_results = list(add_results or [])

    def new_note(self, model):
        note = _BatchPdfNote([field["name"] for field in model["flds"]])
        note._note_type = model
        self.created_notes.append(note)
        return note

    def add_note(self, note, deck_id):
        if self._add_results:
            result = self._add_results.pop(0)
        else:
            result = 1
        if not result:
            return 0
        note.id = len([created for created in self.created_notes if created.id > 0]) + 1
        note.note_type()["did"] = deck_id
        return 1


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

    html = pdf_dock.pdf_citation('Quoted "excerpt"<br>line', highlight_id="hl-7", page=42)

    assert 'onclick="pycmd(&quot;incremento_open_pdf_ref:' in html
    assert "writer&#x27;s-guide.pdf" in html
    assert "Writer &quot;First&quot; &amp; &lt;Best&gt;" in html
    assert 'card_id\\&quot;: 55' in html
    assert 'highlight_id\\&quot;: \\&quot;hl-7\\&quot;' in html
    assert 'excerpt\\&quot;:' in html
    assert 'Quoted' in html
    assert 'line' in html
    assert '=""' not in html


def test_missing_pdf_html_uses_plain_repair_message_for_pycmd():
    html = pdf_dock._missing_pdf_html(
        "writer's-guide.pdf",
        r"C:\Users\paulo\pdfs\writer's-guide.pdf",
    )

    assert 'onclick="pycmd(&quot;incremento_pdf_repair_missing:&quot;); return false;"' in html
    assert pdf_dock._PYCMD_BRIDGE not in html
    assert "writer&#x27;s-guide.pdf" in html
    assert r"C:\Users\paulo\pdfs\writer&#x27;s-guide.pdf" in html


def test_open_or_create_pdf_highlight_card_previews_existing_link(monkeypatch):
    previews = []
    monkeypatch.setattr(pdf_dock, "current_pdf_card_id", lambda: 55)
    monkeypatch.setattr(
        pdf_dock,
        "_current_pdf_highlight_by_id",
        lambda hl_id: {"id": hl_id, "page": 3, "text": "Excerpt"},
    )
    monkeypatch.setattr(
        pdf_dock,
        "get_pdf_card_source_for_highlight",
        lambda *args, **kwargs: {"note_id": 321},
    )
    monkeypatch.setattr(pdf_dock, "_note_exists", lambda note_id: True)
    monkeypatch.setattr(pdf_dock, "show_pdf_page_card_preview", lambda note_id: previews.append(note_id))

    pdf_dock._open_or_create_pdf_highlight_card("hl-1")

    assert previews == [321]


def test_open_or_create_pdf_highlight_card_prefills_configured_field(monkeypatch):
    fills = []
    monkeypatch.setattr(pdf_dock, "current_pdf_card_id", lambda: 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "source.pdf")
    monkeypatch.setattr(
        pdf_dock,
        "_current_pdf_highlight_by_id",
        lambda hl_id: {"id": hl_id, "page": 4, "text": "Excerpt text"},
    )
    monkeypatch.setattr(pdf_dock, "get_pdf_card_source_for_highlight", lambda *args, **kwargs: None)
    monkeypatch.setattr(pdf_dock, "configured_pdf_highlight_extract_field", lambda *args, **kwargs: 3)
    monkeypatch.setattr(pdf_dock, "_cb_open_add_card_dock", lambda: None)
    monkeypatch.setattr(
        pdf_dock,
        "_cb_fill_dock_field",
        lambda *args, **kwargs: fills.append((args, kwargs)),
    )
    monkeypatch.setattr(pdf_dock, "tooltip", lambda _message: None)

    pdf_dock._open_or_create_pdf_highlight_card("hl-9")

    assert fills[0][0] == (2, "Excerpt text")
    assert fills[0][1]["source_link_kind"] == "pdf"
    assert "highlight_id" in fills[0][1]["citation_html"]


def test_pdf_highlight_bulk_row_defaults_to_checked_and_validates_target_text():
    normalized = normalize_pdf_highlight_bulk_row(
        {
            "highlight_id": "hl-1",
            "page": 2,
            "text": "Excerpt",
            "fields": {"Back": "Excerpt<br>Citation", "Front": ""},
        },
        visible_fields=["Front", "Back"],
        target_field="Back",
    )

    assert normalized["create"] is True
    assert normalized["valid"] is True
    assert normalized["fields"]["Back"] == "Excerpt<br>Citation"

    edited = normalize_pdf_highlight_bulk_row(
        dict(normalized, fields={"Front": "", "Back": ""}),
        visible_fields=["Front", "Back"],
        target_field="Back",
    )
    assert edited["valid"] is False
    assert "Back is empty" in edited["error"]

    recovered = normalize_pdf_highlight_bulk_row(
        dict(edited, fields={"Front": "", "Back": "Recovered"}),
        visible_fields=["Front", "Back"],
        target_field="Back",
    )
    assert recovered["valid"] is True
    assert recovered["error"] == ""


def test_pdf_highlight_bulk_row_remap_preserves_hidden_field_edits():
    original = normalize_pdf_highlight_bulk_row(
        {
            "highlight_id": "hl-1",
            "page": 2,
            "text": "Excerpt",
            "generated_text": "Generated citation",
            "fields": {"Back": "Edited back", "Front": "Edited front"},
        },
        visible_fields=["Front", "Back"],
        target_field="Back",
    )

    switched = remap_pdf_highlight_bulk_row_fields(
        original,
        visible_fields=["Front", "Extra"],
        target_field="Extra",
    )
    assert switched["fields"]["Front"] == "Edited front"
    assert switched["fields"]["Extra"] == "Generated citation"

    restored = remap_pdf_highlight_bulk_row_fields(
        switched,
        visible_fields=["Front", "Back"],
        target_field="Back",
    )
    assert restored["fields"]["Back"] == "Edited back"
    assert restored["fields"]["Front"] == "Edited front"


def test_pdf_highlight_bulk_create_state_requires_checked_valid_rows():
    assert can_create_pdf_highlight_bulk_rows(
        [{"create": True, "valid": True}, {"create": False, "valid": False}]
    )
    assert not can_create_pdf_highlight_bulk_rows(
        [{"create": False, "valid": True}, {"create": True, "valid": False}]
    )


def test_missing_pdf_highlight_card_rows_excludes_linked_and_empty(monkeypatch):
    monkeypatch.setattr(
        pdf_dock,
        "_pdf_highlights_payload",
        lambda card_id: [
            {"id": "hl-1", "page": 1, "text": "First", "note": "", "linked_note_id": 0},
            {"id": "hl-2", "page": 2, "text": "Already linked", "note": "", "linked_note_id": 77},
            {"id": "hl-3", "page": 3, "text": "   ", "note": "", "linked_note_id": 0},
        ],
    )
    monkeypatch.setattr(pdf_dock, "_add_card_dock_module", lambda: types.SimpleNamespace(should_add_extract_source_link=lambda kind: False))

    rows = pdf_dock._missing_pdf_highlight_card_rows(
        55,
        {
            "visible_fields": ["Front", "Back"],
            "target_field": "Back",
        },
    )

    assert len(rows) == 1
    assert rows[0]["highlight_id"] == "hl-1"
    assert rows[0]["fields"]["Back"] == "First"


def test_pdf_highlight_bulk_snapshot_uses_first_compatible_note_type(monkeypatch):
    fake_add_card_dock = types.SimpleNamespace(
        prepare_pending_extract_from_source_fill=lambda source: None,
        snapshot_add_card_target_state=lambda min_visible_fields=1: {
            "note_type_name": "Incompatible",
            "note_type_model": {
                "name": "Incompatible",
                "flds": [{"name": "Only"}],
            },
            "deck_name": "Topics",
            "visible_fields": ["Only"],
            "extract_options": {},
            "extract_context": {},
        },
    )
    monkeypatch.setattr(pdf_dock, "_add_card_dock_module", lambda: fake_add_card_dock)
    monkeypatch.setattr(pdf_dock, "_cb_open_add_card_dock", lambda: None)
    monkeypatch.setattr(pdf_dock, "_resolve_pdf_highlight_extract_field_index", lambda config=None: 1)
    monkeypatch.setattr(pdf_dock, "visible_field_names", lambda names: list(names))
    monkeypatch.setattr(
        pdf_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                models=types.SimpleNamespace(
                    all=lambda: [
                        {"name": "Incompatible", "flds": [{"name": "Only"}]},
                        {"name": "Compatible", "flds": [{"name": "Front"}, {"name": "Back"}]},
                    ]
                ),
                decks=types.SimpleNamespace(
                    all_names_and_ids=lambda: [types.SimpleNamespace(name="Topics")]
                ),
            )
        ),
    )

    snapshot = pdf_dock._pdf_highlight_bulk_snapshot()

    assert snapshot["note_type_name"] == "Compatible"
    assert snapshot["visible_fields"] == ["Front", "Back"]
    assert snapshot["target_field"] == "Back"
    assert snapshot["note_type_options"][0]["name"] == "Compatible"


def test_pdf_highlights_payload_prunes_stale_link_and_makes_highlight_creatable(monkeypatch):
    deleted = []
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        pdf_dock,
        "load_highlights",
        lambda addon_dir, profile, card_id: [{"id": "hl-stale", "page": 4, "text": "Recovered", "note": ""}],
    )
    monkeypatch.setattr(
        pdf_dock,
        "get_pdf_card_sources_for_highlights",
        lambda *args, **kwargs: {
            "hl-stale": {"note_id": 123, "highlight_id": "hl-stale", "page": 4, "excerpt": "Recovered"}
        },
    )
    monkeypatch.setattr(pdf_dock, "_note_exists", lambda note_id: False)
    monkeypatch.setattr(
        pdf_dock,
        "delete_pdf_card_sources_for_note_ids",
        lambda addon_dir, profile, pdf_card_id, note_ids: deleted.append(sorted(note_ids)),
    )
    monkeypatch.setattr(
        pdf_dock,
        "count_pdf_card_sources_for_highlight",
        lambda *args, **kwargs: 0,
    )

    payload = pdf_dock._pdf_highlights_payload(88)
    rows = pdf_dock._missing_pdf_highlight_card_rows(
        88,
        {"visible_fields": ["Front"], "target_field": "Front"},
    )

    assert deleted == [[123], [123]]
    assert payload[0]["linked_note_id"] == 0
    assert rows[0]["highlight_id"] == "hl-stale"


def test_create_pdf_highlight_batch_notes_creates_notes_and_records_highlight_ids(monkeypatch):
    model = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    collection = _BatchPdfCollection(model)
    source_calls = []
    apply_calls = []

    fake_add_card_dock = types.SimpleNamespace(
        _ensure_incremento_metadata_fields_saved=lambda models, current_model: False,
        apply_extract_options_to_note=lambda note, options: apply_calls.append((note["Back"], dict(options))) or dict(options),
        apply_extract_context_to_note=lambda note, options=None, context=None: {"metadata_saved": True},
        mark_reviewer_extract_note_added=lambda options: None,
        _notify_video_extract_note_added=lambda note, options: None,
    )

    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=collection))
    monkeypatch.setattr(pdf_dock, "_add_card_dock_module", lambda: fake_add_card_dock)
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "get_pdf_card_source_for_highlight", lambda *args, **kwargs: None)
    monkeypatch.setattr(pdf_dock, "_note_exists", lambda note_id: False)
    monkeypatch.setattr(
        pdf_dock,
        "add_pdf_card_source",
        lambda *args, **kwargs: source_calls.append((args, kwargs)),
    )

    summary = pdf_dock.create_pdf_highlight_batch_notes(
        pdf_card_id=55,
        pdf_filename="source.pdf",
        snapshot={
            "note_type_name": "Basic",
            "deck_name": "Topics",
            "deck_id": 99,
            "visible_fields": ["Front", "Back"],
            "target_field": "Back",
            "extract_options": {"priority": 33.0, "source": "pdf", "source_card_id": 55},
            "extract_context": {"parent_card_id": 55},
        },
        rows=[
            {
                "highlight_id": "hl-1",
                "page": 7,
                "text": "Excerpt",
                "fields": {"Front": "", "Back": "Excerpt<br>Citation"},
            }
        ],
    )

    assert summary == {
        "created": 1,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "created_note_ids": [1],
    }
    assert collection.created_notes[0]["Back"] == "Excerpt<br>Citation"
    assert apply_calls == [("Excerpt<br>Citation", {"priority": 33.0, "source": "pdf", "source_card_id": 55})]
    assert source_calls[0][1]["highlight_id"] == "hl-1"


def test_create_pdf_highlight_batch_notes_prefers_selected_deck_name_over_stale_id(monkeypatch):
    model = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    collection = _BatchPdfCollection(model, deck_name="New Deck", deck_id=7)
    fake_add_card_dock = types.SimpleNamespace(
        _ensure_incremento_metadata_fields_saved=lambda models, current_model: False,
        apply_extract_options_to_note=lambda note, options: dict(options),
        apply_extract_context_to_note=lambda note, options=None, context=None: {"metadata_saved": True},
        mark_reviewer_extract_note_added=lambda options: None,
        _notify_video_extract_note_added=lambda note, options: None,
    )

    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=collection))
    monkeypatch.setattr(pdf_dock, "_add_card_dock_module", lambda: fake_add_card_dock)
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "get_pdf_card_source_for_highlight", lambda *args, **kwargs: None)
    monkeypatch.setattr(pdf_dock, "_note_exists", lambda note_id: False)
    monkeypatch.setattr(pdf_dock, "add_pdf_card_source", lambda *args, **kwargs: None)

    summary = pdf_dock.create_pdf_highlight_batch_notes(
        pdf_card_id=55,
        pdf_filename="source.pdf",
        snapshot={
            "note_type_name": "Basic",
            "deck_name": "New Deck",
            "deck_id": None,
            "visible_fields": ["Front", "Back"],
            "target_field": "Back",
            "extract_options": {"source": "pdf"},
            "extract_context": {},
        },
        rows=[
            {
                "highlight_id": "hl-1",
                "page": 7,
                "text": "Excerpt",
                "fields": {"Front": "", "Back": "Excerpt"},
            }
        ],
    )

    assert summary["created"] == 1
    assert collection.created_notes[0].note_type()["did"] == 7


def test_create_pdf_highlight_batch_notes_skips_duplicates_and_reports_failures(monkeypatch):
    model = {
        "name": "Basic",
        "flds": [{"name": "Front"}, {"name": "Back"}],
    }
    collection = _BatchPdfCollection(model, add_results=[1, 0])
    fake_add_card_dock = types.SimpleNamespace(
        _ensure_incremento_metadata_fields_saved=lambda models, current_model: False,
        apply_extract_options_to_note=lambda note, options: dict(options),
        apply_extract_context_to_note=lambda note, options=None, context=None: {"metadata_saved": True},
        mark_reviewer_extract_note_added=lambda options: None,
        _notify_video_extract_note_added=lambda note, options: None,
    )

    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=collection))
    monkeypatch.setattr(pdf_dock, "_add_card_dock_module", lambda: fake_add_card_dock)
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_note_exists", lambda note_id: note_id == 88)
    monkeypatch.setattr(
        pdf_dock,
        "get_pdf_card_source_for_highlight",
        lambda addon_dir, profile, pdf_card_id, highlight_id: {"note_id": 88} if highlight_id == "hl-linked" else None,
    )
    monkeypatch.setattr(pdf_dock, "add_pdf_card_source", lambda *args, **kwargs: None)

    summary = pdf_dock.create_pdf_highlight_batch_notes(
        pdf_card_id=55,
        pdf_filename="source.pdf",
        snapshot={
            "note_type_name": "Basic",
            "deck_name": "Topics",
            "deck_id": 99,
            "visible_fields": ["Front", "Back"],
            "target_field": "Back",
            "extract_options": {"source": "pdf"},
            "extract_context": {},
        },
        rows=[
            {
                "highlight_id": "hl-linked",
                "page": 3,
                "text": "Existing",
                "fields": {"Front": "", "Back": "Existing"},
            },
            {
                "highlight_id": "hl-new",
                "page": 4,
                "text": "First create",
                "fields": {"Front": "", "Back": "First create"},
            },
            {
                "highlight_id": "hl-fail",
                "page": 5,
                "text": "Will fail",
                "fields": {"Front": "", "Back": "Will fail"},
            },
        ],
    )

    assert summary["created"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 1
    assert summary["created_note_ids"] == [1]
    assert "hl-fail" in summary["errors"][0]


def test_pdf_storage_path_rejects_traversal(monkeypatch):
    monkeypatch.setattr(pdf_dock, "pdf_storage_abspath", lambda _filename: "")

    assert pdf_dock._pdf_storage_path("../../../etc/passwd") == ""


def test_show_pdf_in_dock_reloads_viewer_after_missing_screen(monkeypatch):
    events = []
    js_calls = []
    load_calls = []

    class _FakeUrl:
        def toString(self):
            return pdf_dock._DOCK_HTML

    class _FakePage:
        def runJavaScript(self, js):
            js_calls.append(js)

    class _FakeSignal:
        def __init__(self):
            self.callback = None

        def connect(self, callback):
            self.callback = callback

        def disconnect(self, callback):
            if self.callback == callback:
                self.callback = None

    class _FakeView:
        def __init__(self):
            self._page = _FakePage()
            self.loadFinished = _FakeSignal()

        def url(self):
            return _FakeUrl()

        def page(self):
            return self._page

        def load(self, url):
            load_calls.append(url)
            callback = self.loadFinished.callback
            if callback is not None:
                callback(True)

    fake_dock = types.SimpleNamespace(
        show=lambda: None,
        raise_=lambda: None,
        widget=lambda: object(),
        _view=_FakeView(),
    )
    fake_note = {"PDF_Filename": "new-file.pdf"}
    fake_card = types.SimpleNamespace(nid=321)
    fake_mw = types.SimpleNamespace(
        col=types.SimpleNamespace(
            get_card=lambda card_id: fake_card,
            get_note=lambda note_id: fake_note,
        )
    )

    class _FakeQUrl:
        def __init__(self, path):
            self.path = path

        @staticmethod
        def fromLocalFile(path):
            return types.SimpleNamespace(toString=lambda: path)

    monkeypatch.setattr(pdf_dock, "_pdf_dock", fake_dock)
    monkeypatch.setattr(pdf_dock, "_pdf_showing_missing_screen", True)
    monkeypatch.setattr(pdf_dock, "_build_pdf_dock", lambda: (_ for _ in ()).throw(AssertionError("unexpected build")))
    monkeypatch.setattr(pdf_dock, "mw", fake_mw)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_pdf_highlights_payload", lambda card_id: [])
    monkeypatch.setattr(pdf_dock, "_pdf_bookmarks_payload", lambda card_id: [])
    monkeypatch.setattr(pdf_dock, "_current_pdf_limit_status", lambda *args, **kwargs: {"enabled": False})
    monkeypatch.setattr(pdf_dock, "get_read_anchor", lambda *args, **kwargs: None)
    monkeypatch.setattr(pdf_dock, "get_scroll_ratio", lambda *args, **kwargs: 0.42)
    monkeypatch.setattr(pdf_dock, "configured_highlight_when_extracting", lambda *args, **kwargs: False)
    monkeypatch.setattr(pdf_dock, "configured_scroll_to_top_on_page_change", lambda *args, **kwargs: False)
    monkeypatch.setattr(pdf_dock, "_consume_due_review_prompt_suppression", lambda card_id: False)
    monkeypatch.setattr(pdf_dock, "_show_missing_pdf_screen", lambda filename: events.append(("missing", filename)))
    monkeypatch.setattr(pdf_dock, "tooltip", lambda message: events.append(("tooltip", message)))
    monkeypatch.setattr(
        pdf_dock,
        "QUrl",
        _FakeQUrl,
    )
    monkeypatch.setattr(
        pdf_dock,
        "repair_pdf_card_filename",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("repair should not run")),
    )
    monkeypatch.setattr(
        pdf_dock,
        "_pdf_storage_path",
        lambda filename: f"/tmp/{filename}" if filename == "new-file.pdf" else "",
    )
    monkeypatch.setattr(pdf_dock.os.path, "exists", lambda path: path == "/tmp/new-file.pdf")

    pdf_dock.show_pdf_in_dock(77, "old-file.pdf", 3, offer_due_review_prompt=False)

    assert pdf_dock._current_pdf_filename == "new-file.pdf"
    assert pdf_dock._pdf_showing_missing_screen is False
    assert events == []
    assert len(load_calls) == 1
    assert js_calls
    assert '"new-file.pdf"' in js_calls[0]
    assert "scrollRatio: 0.42" in js_calls[0]
    assert "scrollToTopOnPageChange: false" in js_calls[0]
    assert '"old-file.pdf"' not in js_calls[0]


def test_current_card_pdf_search_hits_orders_pages_and_builds_snippets(monkeypatch):
    monkeypatch.setattr(
        pdf_dock,
        "search_pdf_text_index_for_card",
        lambda addon_dir, profile, card_id, query, limit=250: [
            (2, "Second page mentions the target phrase"),
            (5, "Fifth page also mentions the target phrase"),
        ],
    )
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")

    hits = pdf_dock.current_card_pdf_search_hits(77, "target phrase")

    assert [hit["page"] for hit in hits] == [2, 5]
    assert "target phrase" in hits[0]["snippet"].lower()
    assert "excerpt" in hits[0]


def test_current_pdf_search_context_uses_filename_label(monkeypatch):
    class _VisibleDock:
        def isVisible(self):
            return True

    monkeypatch.setattr(pdf_dock, "_pdf_dock", _VisibleDock())
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "paper_name.pdf")
    monkeypatch.setattr(pdf_dock, "_current_pdf_search_query", "target phrase")
    monkeypatch.setattr(pdf_dock, "_current_pdf_search_hits", [{"page": 4, "snippet": "hit"}])
    monkeypatch.setattr(
        pdf_dock,
        "pdf_display_label_from_filename",
        lambda filename, fallback="PDF": "Paper Name",
    )

    context = pdf_dock.current_pdf_search_context()

    assert context["documentKind"] == "pdf"
    assert context["documentLabel"] == "Paper Name"
    assert context["cardId"] == 42
    assert context["query"] == "target phrase"
    assert context["hits"][0]["page"] == 4


def test_pdf_scroll_bridge_persists_updates(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_pdf_preserve_history", False)
    monkeypatch.setattr(
        pdf_dock,
        "set_scroll_ratio",
        lambda addon_dir, profile, card_id, scroll_ratio: calls.append(
            (addon_dir, profile, card_id, scroll_ratio)
        ),
    )

    pdf_dock._handle_pdf_js_message('incremento_pdf_scroll:{"cardId":55,"scrollRatio":0.63}')

    assert calls == [("/tmp/addon", "TestProfile", 55, 0.63)]


def test_pdf_nav_resets_saved_scroll_ratio_for_new_page(monkeypatch):
    import db as _db

    _db.close_connection()
    addon_dir = tempfile.mkdtemp()
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", addon_dir)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_pdf_via_link", False)
    monkeypatch.setattr(pdf_dock, "_pdf_preserve_history", False)
    monkeypatch.setattr(pdf_dock, "_current_pdf_limit_status", lambda *args, **kwargs: {"enabled": False})
    monkeypatch.setattr(pdf_dock, "_push_pdf_limit_status", lambda status: None)
    monkeypatch.setattr(pdf_dock, "_timer_mod", types.SimpleNamespace(record_pdf_page_read=lambda *args, **kwargs: None))

    try:
        pdf_dock.set_page(addon_dir, "TestProfile", 77, 3)
        pdf_dock.set_scroll_ratio(addon_dir, "TestProfile", 77, 0.58)

        pdf_dock._handle_pdf_js_message("incremento_pdf_nav:77:4")

        assert pdf_dock.get_page(addon_dir, "TestProfile", 77) == 4
        assert pdf_dock.get_scroll_ratio(addon_dir, "TestProfile", 77) == 0.0
    finally:
        _db.close_connection()


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


def test_on_add_cards_did_add_note_ignores_unknown_source_on_non_pdf_reviewer_card(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_add_card_source_for_new_note", lambda: "")
    monkeypatch.setattr(
        pdf_dock,
        "mw",
        types.SimpleNamespace(reviewer=types.SimpleNamespace(card=types.SimpleNamespace(id=88))),
    )
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


def test_on_pdf_question_shown_clears_context_for_non_pdf_card(monkeypatch):
    stopped = []

    class _FakeDock:
        def __init__(self):
            self.hidden = False

        def hide(self):
            self.hidden = True

    fake_dock = _FakeDock()
    fake_note = types.SimpleNamespace(mid=1)
    fake_col = types.SimpleNamespace(
        get_note=lambda note_id: fake_note,
        models=types.SimpleNamespace(get=lambda mid: {"name": "Basic"}),
    )

    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=fake_col))
    monkeypatch.setattr(pdf_dock, "_pdf_dock", fake_dock)
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "source.pdf")
    monkeypatch.setattr(
        pdf_dock,
        "_cb_pdf_view_stopped",
        lambda card_id: stopped.append(card_id),
    )

    pdf_dock.on_pdf_question_shown(types.SimpleNamespace(id=88, nid=123))

    assert fake_dock.hidden is True
    assert pdf_dock.current_pdf_card_id() is None
    assert pdf_dock._current_pdf_filename is None
    assert stopped == [55]


def test_non_pdf_transition_prevents_stale_pdf_restore_on_later_add(monkeypatch):
    class _FakeDock:
        def __init__(self):
            self.hidden = False
            self.shown = False

        def hide(self):
            self.hidden = True

        def isVisible(self):
            return False

        def show(self):
            self.shown = True

    fake_dock = _FakeDock()
    fake_note = types.SimpleNamespace(mid=1)
    fake_col = types.SimpleNamespace(
        get_note=lambda note_id: fake_note,
        models=types.SimpleNamespace(get=lambda mid: {"name": "Basic"}),
    )

    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=fake_col))
    monkeypatch.setattr(pdf_dock, "_pdf_dock", fake_dock)
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "source.pdf")
    monkeypatch.setattr(pdf_dock, "_cb_pdf_view_stopped", lambda card_id: None)

    pdf_dock.on_pdf_question_shown(types.SimpleNamespace(id=88, nid=123))

    monkeypatch.setattr(pdf_dock, "_add_card_source_for_new_note", lambda: "pdf")
    monkeypatch.setattr(
        pdf_dock,
        "get_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale PDF add")),
    )

    pdf_dock.on_add_cards_did_add_note(types.SimpleNamespace(id=123, fields=["Front"]))

    assert fake_dock.hidden is True
    assert fake_dock.shown is False
    assert pdf_dock.current_pdf_card_id() is None


def test_on_add_cards_did_add_note_restores_confirmed_pdf_source_after_context_clear(
    monkeypatch,
):
    starts = []
    sources = []

    class _FakePage:
        def runJavaScript(self, js):
            pass

    class _FakeView:
        def page(self):
            return _FakePage()

    class _FakeDock:
        def __init__(self):
            self.visible = False
            self.show_count = 0
            self._view = _FakeView()

        def isVisible(self):
            return self.visible

        def show(self):
            self.visible = True
            self.show_count += 1

    def _single_shot(_delay, callback):
        pdf_dock._clear_current_pdf_context()
        callback()

    fake_dock = _FakeDock()
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "source.pdf")
    monkeypatch.setattr(pdf_dock, "_pdf_dock", fake_dock)
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_add_card_source_for_new_note", lambda: "pdf")
    monkeypatch.setattr(
        pdf_dock,
        "_cb_pdf_view_started",
        lambda card_id: starts.append(card_id),
    )
    monkeypatch.setattr(pdf_dock, "get_page", lambda addon_dir, profile, card_id: 7)
    monkeypatch.setattr(
        pdf_dock,
        "add_pdf_card_source",
        lambda *args, **kwargs: sources.append((args, kwargs)),
    )
    monkeypatch.setattr(
        pdf_dock,
        "_reconcile_pdf_page_sources",
        lambda card_id, page: ([], {}),
    )
    monkeypatch.setattr(pdf_dock.QTimer, "singleShot", _single_shot, raising=False)

    pdf_dock.on_add_cards_did_add_note(types.SimpleNamespace(id=123, fields=["Front"]))

    assert sources
    assert sources[0][1]["highlight_id"] == ""
    assert fake_dock.show_count == 1
    assert pdf_dock.current_pdf_card_id() == 55
    assert pdf_dock._current_pdf_filename == "source.pdf"
    assert starts == [55]


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


def test_regenerate_pdf_cover_reloads_active_reviewer_card_in_place(monkeypatch):
    tooltips = []
    shown = []
    resets = []

    class _FakeReviewerCard:
        def __init__(self):
            self.id = 55
            self.timer_started = 123.0
            self.load_calls = 0

        def load(self):
            self.load_calls += 1

    current_card = _FakeReviewerCard()
    reviewer = types.SimpleNamespace(
        card=current_card,
        _showQuestion=lambda: shown.append(True),
    )
    fake_col = types.SimpleNamespace(
        reset=lambda: resets.append(True),
        get_card=lambda card_id: (_ for _ in ()).throw(
            AssertionError("reviewer card should be reloaded in place")
        ),
    )
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=fake_col, reviewer=reviewer))
    monkeypatch.setattr(pdf_dock, "current_pdf_card_id", lambda: 55)
    monkeypatch.setattr(pdf_dock, "regenerate_pdf_card_cover", lambda addon_dir, col, card_id: "cover.png")
    monkeypatch.setattr(pdf_dock, "tooltip", lambda message: tooltips.append(message))

    pdf_dock._regenerate_pdf_cover()

    assert resets == [True]
    assert reviewer.card is current_card
    assert current_card.load_calls == 1
    assert current_card.timer_started == 123.0
    assert shown == [True]
    assert tooltips == ["PDF cover regenerated from page 1."]


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
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    pdf_dock.on_add_cards_did_add_note(types.SimpleNamespace(id=123, fields=["Front"]))

    assert calls
    assert calls[0][1]["highlight_id"] == ""
    assert pdf_dock._consume_due_review_prompt_suppression(55) is True


def test_on_add_cards_did_add_note_records_exact_highlight_id(monkeypatch):
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
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    note = types.SimpleNamespace(
        id=123,
        fields=[
            'Front <a onclick="pycmd(&quot;incremento_open_pdf_ref:{\\"card_id\\": 55, \\"filename\\": \\"source.pdf\\", \\"page\\": 7, \\"highlight_id\\": \\"hl-22\\"}&quot;); return false;">Page 7. of source</a>'
        ],
    )

    pdf_dock.on_add_cards_did_add_note(note)

    assert calls[0][1]["highlight_id"] == "hl-22"
    assert calls[0][0][3] == 7


def test_on_add_cards_did_add_note_uses_highlight_citation_page(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "source.pdf")
    monkeypatch.setattr(pdf_dock, "_pdf_dock", None)
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_add_card_source_for_new_note", lambda: "pdf")
    monkeypatch.setattr(pdf_dock, "get_page", lambda addon_dir, profile, card_id: 2)
    monkeypatch.setattr(
        pdf_dock,
        "add_pdf_card_source",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    note = types.SimpleNamespace(
        id=123,
        fields=[
            'Front <a onclick="pycmd(&quot;incremento_open_pdf_ref:{\\"card_id\\": 55, \\"filename\\": \\"source.pdf\\", \\"page\\": 9, \\"highlight_id\\": \\"hl-9\\"}&quot;); return false;">Page 9. of source</a>'
        ],
    )

    pdf_dock.on_add_cards_did_add_note(note)

    assert calls[0][0][3] == 9
    assert calls[0][1]["highlight_id"] == "hl-9"


def test_pdf_highlight_delete_prunes_exact_source(monkeypatch):
    removed = []
    deleted = []
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        pdf_dock,
        "remove_highlight",
        lambda addon_dir, profile, card_id, highlight_id: removed.append(
            (addon_dir, profile, card_id, highlight_id)
        ),
    )
    monkeypatch.setattr(
        pdf_dock,
        "delete_pdf_card_source_for_highlight",
        lambda addon_dir, profile, card_id, highlight_id: deleted.append(
            (addon_dir, profile, card_id, highlight_id)
        ),
    )

    pdf_dock._handle_pdf_js_message('incremento_pdf_hl_del:{"cardId":55,"id":"hl-9"}')

    assert removed == [("/tmp/addon", "TestProfile", 55, "hl-9")]
    assert deleted == [("/tmp/addon", "TestProfile", 55, "hl-9")]
