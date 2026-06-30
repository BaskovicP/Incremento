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


def test_pdf_storage_path_rejects_traversal(monkeypatch):
    monkeypatch.setattr(pdf_dock, "pdf_storage_abspath", lambda _filename: "")

    assert pdf_dock._pdf_storage_path("../../../etc/passwd") == ""


def test_show_pdf_in_dock_prefers_current_note_filename_over_stale_argument(monkeypatch):
    events = []
    js_calls = []

    class _FakeUrl:
        def toString(self):
            return pdf_dock._DOCK_HTML

    class _FakePage:
        def runJavaScript(self, js):
            js_calls.append(js)

    class _FakeView:
        def __init__(self):
            self._page = _FakePage()

        def url(self):
            return _FakeUrl()

        def page(self):
            return self._page

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

    monkeypatch.setattr(pdf_dock, "_pdf_dock", fake_dock)
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
        types.SimpleNamespace(fromLocalFile=lambda path: types.SimpleNamespace(toString=lambda: path)),
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
    assert events == []
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
