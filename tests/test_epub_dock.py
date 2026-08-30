import sys
import types
from unittest.mock import MagicMock

sys.modules.setdefault("session", MagicMock())
import aqt

import epub_dock


def test_due_review_details_escape_card_content():
    rendered = epub_dock._epub_due_review_details_html(
        [
            {
                "card_id": 7,
                "section_index": 2,
                "title": "<img src=x onerror=alert(1)>",
                "excerpt": "<script>alert(1)</script>",
                "due_state": "<b>due</b>",
            }
        ]
    )

    assert "<img" not in rendered
    assert "<script" not in rendered
    assert "&lt;img" in rendered
    assert "&lt;script&gt;" in rendered


def test_browse_note_ids_in_browser_builds_deduplicated_query(monkeypatch):
    searches = []

    class _FakeBrowser:
        def search_for(self, query):
            searches.append(query)

    fake_dialogs = types.SimpleNamespace(open=lambda name, parent: _FakeBrowser())
    monkeypatch.setitem(sys.modules, "aqt.dialogs", fake_dialogs)
    monkeypatch.setattr(aqt, "dialogs", fake_dialogs, raising=False)

    assert epub_dock._browse_note_ids_in_browser([21, 22, 21, 0, -1]) is True
    assert searches == ["nid:21 OR nid:22"]


def test_browse_note_ids_in_browser_shows_empty_tooltip(monkeypatch):
    tooltips = []
    monkeypatch.setattr(epub_dock, "tooltip", lambda message: tooltips.append(message))

    assert epub_dock._browse_note_ids_in_browser([], empty_message="No cards yet.") is False
    assert tooltips == ["No cards yet."]


def test_add_card_source_for_new_note_prefers_pending_extract_source(monkeypatch):
    fake_add_card_dock = types.SimpleNamespace(
        pending_extract_options=lambda: {"source": "reviewer"},
        recent_fill_source=lambda: "epub",
    )
    monkeypatch.setitem(sys.modules, "add_card_dock", fake_add_card_dock)

    assert epub_dock._add_card_source_for_new_note() == "reviewer"


def test_on_add_cards_did_add_note_ignores_reviewer_extract(monkeypatch):
    calls = []
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 55)
    monkeypatch.setattr(epub_dock, "_add_card_source_for_new_note", lambda: "reviewer")
    monkeypatch.setattr(
        epub_dock,
        "add_epub_card_source",
        lambda *args, **kwargs: calls.append(args),
    )

    epub_dock.on_add_cards_did_add_note(types.SimpleNamespace(id=123, fields=["Front"]))

    assert calls == []


def test_regenerate_epub_cover_reloads_active_reviewer_card_in_place(monkeypatch):
    tooltips = []
    shown = []
    resets = []

    class _FakeReviewerCard:
        def __init__(self):
            self.id = 66
            self.timer_started = 456.0
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
    monkeypatch.setattr(epub_dock, "mw", types.SimpleNamespace(col=fake_col, reviewer=reviewer))
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 66)
    monkeypatch.setattr(epub_dock, "regenerate_epub_card_cover", lambda addon_dir, col, card_id: "cover.png")
    monkeypatch.setattr(epub_dock, "tooltip", lambda message: tooltips.append(message))

    epub_dock._regenerate_epub_cover()

    assert resets == [True]
    assert reviewer.card is current_card
    assert current_card.load_calls == 1
    assert current_card.timer_started == 456.0
    assert shown == [True]
    assert tooltips == ["EPUB cover regenerated from book metadata."]


def test_build_page_script_includes_highlight_note_action_menu(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "Example section"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: True)

    script = epub_dock._build_page_script(
        card_id=7,
        section_index=1,
        scroll_ratio=0.2,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[{"id": "hl-1", "startOffset": 0, "endOffset": 7, "text": "Example"}],
        bridge_nonce="private-token",
    )

    assert "incremento_epub_hl_note:" in script
    assert "incremento-epub-highlight-actions" in script
    assert "incrementoUpdateEpubHighlightNote" in script
    assert "private-token" in script
    assert "if (!event.isTrusted) return" in script


def test_epub_javascript_runs_in_application_world():
    calls = []

    class _FakePage:
        def runJavaScript(self, *args):
            calls.append(args)

    epub_dock._run_epub_javascript(_FakePage(), "window.test = true;")

    assert calls == [
        (
            "window.test = true;",
            int(epub_dock.QWebEngineScript.ScriptWorldId.ApplicationWorld.value),
        )
    ]


def test_epub_bridge_rejects_static_prefix_and_wrong_card(monkeypatch):
    fills = []
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 42)
    monkeypatch.setattr(
        epub_dock,
        "_on_epub_selection",
        lambda idx, text, start, end: fills.append((idx, text, start, end)),
    )
    page = types.SimpleNamespace(_bridge_nonce="private-token")
    payload = '{"cardId":42,"idx":1,"text":"selected","startOffset":2,"endOffset":10}'

    epub_dock._EpubDockPage.javaScriptConsoleMessage(
        page,
        0,
        epub_dock._PYCMD_BRIDGE + epub_dock._MSG_FILL_FIELD + payload,
        0,
        "book.xhtml",
    )
    epub_dock._EpubDockPage.javaScriptConsoleMessage(
        page,
        0,
        epub_dock._PYCMD_BRIDGE
        + "private-token:"
        + epub_dock._MSG_FILL_FIELD
        + payload.replace('"cardId":42', '"cardId":99'),
        0,
        "book.xhtml",
    )

    assert fills == []

    epub_dock._EpubDockPage.javaScriptConsoleMessage(
        page,
        0,
        epub_dock._PYCMD_BRIDGE
        + "private-token:"
        + epub_dock._MSG_FILL_FIELD
        + payload,
        0,
        "book.xhtml",
    )

    assert fills == [(1, "selected", 2, 10)]


def test_epub_file_request_path_must_stay_under_book_root(tmp_path):
    root = tmp_path / "book"
    root.mkdir()
    assert epub_dock._path_is_within_root(root, root / "chapter.xhtml") is True
    assert epub_dock._path_is_within_root(root, tmp_path / "outside.txt") is False


def test_epub_page_allows_only_the_prepared_main_document(tmp_path):
    root = tmp_path / "book"
    root.mkdir()
    chapter = root / "chapter.xhtml"
    appendix = root / "appendix.html"
    chapter.write_text("chapter", encoding="utf-8")
    appendix.write_text("appendix", encoding="utf-8")

    page = types.SimpleNamespace(
        _interceptor=types.SimpleNamespace(set_allowed_root=lambda _root: None),
        _bridge_nonce="",
        _main_document=None,
    )
    epub_dock._EpubDockPage.prepare_document_load(page, root, chapter)

    assert page._main_document == chapter.resolve()
    assert epub_dock._EpubDockPage.acceptNavigationRequest(
        page,
        epub_dock.QUrl.fromLocalFile(str(appendix)),
        None,
        True,
    ) is False
    assert epub_dock._EpubDockPage.acceptNavigationRequest(
        page,
        epub_dock.QUrl("https://example.test/remote"),
        None,
        True,
    ) is False


def test_edit_current_epub_highlight_note_updates_live_view(monkeypatch):
    js_calls = []
    updates = []
    tooltips = []

    class _FakeDialog:
        def __init__(self, parent, *, title, excerpt, current_note):
            assert parent is epub_dock.mw
            assert title == "EPUB Highlight Note"
            assert excerpt == "Quoted text"
            assert current_note == ""

        def exec(self):
            return True

        def note_text(self):
            return "New note"

    class _FakePage:
        def runJavaScript(self, js):
            js_calls.append(js)

    class _FakeView:
        def page(self):
            return _FakePage()

    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 42)
    monkeypatch.setattr(epub_dock, "_current_epub_section_index", 3)
    monkeypatch.setattr(
        epub_dock,
        "load_highlights",
        lambda addon_dir, profile, card_id: [
            {"id": "hl-1", "sectionIndex": 3, "text": "Quoted text", "note": ""}
        ],
    )
    monkeypatch.setattr(epub_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(epub_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(epub_dock, "HighlightNoteDialog", _FakeDialog)
    monkeypatch.setattr(
        epub_dock,
        "update_highlight_note",
        lambda addon_dir, profile, card_id, hl_id, note: (
            updates.append((addon_dir, profile, card_id, hl_id, note)) or
            {"id": hl_id, "note": note}
        ),
    )
    monkeypatch.setattr(epub_dock, "_update_sources_panel", lambda: js_calls.append("sources"))
    monkeypatch.setattr(epub_dock, "tooltip", lambda message: tooltips.append(message))
    monkeypatch.setattr(epub_dock, "mw", object())
    monkeypatch.setattr(epub_dock, "_epub_dock", types.SimpleNamespace(_view=_FakeView()))

    epub_dock._edit_current_epub_highlight_note("hl-1")

    assert updates == [("/tmp/addon", "TestProfile", 42, "hl-1", "New note")]
    assert any("incrementoUpdateEpubHighlightNote" in js for js in js_calls if isinstance(js, str))
    assert "sources" in js_calls
    assert tooltips == ["EPUB highlight note saved."]


def test_current_card_epub_search_hits_use_section_title_fallback(monkeypatch):
    monkeypatch.setattr(
        epub_dock,
        "search_epub_text_index_for_card",
        lambda addon_dir, profile, card_id, query, limit=250: [
            (0, "Chapter One", "The phrase appears here."),
            (1, "", "Another phrase appears in untitled text."),
        ],
    )
    monkeypatch.setattr(epub_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(epub_dock, "_active_profile", lambda: "TestProfile")

    hits = epub_dock.current_card_epub_search_hits(9, "phrase")

    assert hits[0]["sectionTitle"] == "Chapter One"
    assert hits[1]["sectionTitle"] == "Section 2"
    assert hits[0]["focusOffset"] >= 0


def test_on_epub_question_shown_never_opens_automatic_due_prompt(monkeypatch):
    shown = []

    class _FakeEpubNote(dict):
        mid = 1

    fake_note = _FakeEpubNote(
        **{epub_dock.EPUB_FILE_FIELD: "book.epub"}
    )
    fake_col = types.SimpleNamespace(
        get_note=lambda _note_id: fake_note,
        models=types.SimpleNamespace(
            get=lambda _mid: {"name": epub_dock.EPUB_NOTE_TYPE}
        ),
    )
    monkeypatch.setattr(epub_dock, "mw", types.SimpleNamespace(col=fake_col))
    monkeypatch.setattr(
        epub_dock,
        "get_epub_progress",
        lambda *_args: (4, 0.35, False),
    )
    monkeypatch.setattr(
        epub_dock,
        "show_epub_in_dock",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )

    epub_dock.on_epub_question_shown(types.SimpleNamespace(id=66, nid=123))

    assert shown == [
        (
            (66, "book.epub"),
            {
                "section_index": 4,
                "scroll_ratio": 0.35,
                "offer_due_review_prompt": False,
            },
        )
    ]


def test_current_epub_search_context_uses_current_title(monkeypatch):
    class _VisibleDock:
        def isVisible(self):
            return True

    monkeypatch.setattr(epub_dock, "_epub_dock", _VisibleDock())
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 15)
    monkeypatch.setattr(epub_dock, "_current_epub_filename", "My Book.epub")
    monkeypatch.setattr(epub_dock, "_current_epub_search_query", "topic")
    monkeypatch.setattr(
        epub_dock,
        "_current_epub_search_hits",
        [{"sectionIndex": 2, "sectionTitle": "Chapter 3", "snippet": "topic appears"}],
    )

    context = epub_dock.current_epub_search_context()

    assert context["documentKind"] == "epub"
    assert context["documentLabel"] == "My Book"
    assert context["cardId"] == 15
    assert context["query"] == "topic"
    assert context["hits"][0]["sectionIndex"] == 2


def test_start_all_epub_review_passes_reader_context_and_restores_reader(monkeypatch):
    starts = []
    selected_decks = []
    restored = []
    read_markers = []
    fake_note = {epub_dock.EPUB_FILE_FIELD: "book.epub"}
    fake_col = types.SimpleNamespace(
        get_card=lambda card_id: types.SimpleNamespace(nid=9),
        get_note=lambda note_id: fake_note,
        decks=types.SimpleNamespace(
            current=lambda: {"id": 33},
            select=lambda deck_id: selected_decks.append(deck_id),
        ),
    )
    fake_launcher = types.SimpleNamespace(
        start_attached_media_review=lambda **kwargs: starts.append(kwargs) or True,
    )
    monkeypatch.setitem(sys.modules, "media_review_dialog", fake_launcher)
    monkeypatch.setattr(epub_dock, "mw", types.SimpleNamespace(col=fake_col))
    monkeypatch.setattr(epub_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(epub_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(epub_dock, "_current_epub_section_index", 4)
    monkeypatch.setattr(epub_dock, "_current_epub_scroll_ratio", 0.35)
    monkeypatch.setattr(epub_dock, "get_read_section_index", lambda *_args: 3)
    monkeypatch.setattr(
        epub_dock,
        "set_read_section_index",
        lambda *args: read_markers.append(args),
    )
    monkeypatch.setattr(
        epub_dock,
        "show_epub_in_dock",
        lambda *args, **kwargs: restored.append((args, kwargs)),
    )
    monkeypatch.setattr(
        epub_dock,
        "QTimer",
        types.SimpleNamespace(singleShot=lambda _ms, callback: callback()),
    )

    assert epub_dock._start_all_epub_review(66) is True
    assert starts[0]["source_card_id"] == 66
    assert starts[0]["media_label"] == "EPUB"
    assert starts[0]["media_kind"] == "epub"
    assert starts[0]["current_position"] == 4
    assert starts[0]["deck_name"] == epub_dock.INCREMENTO_EPUB_REVIEW_DECK

    starts[0]["on_finished"]()
    assert selected_decks == [33]
    assert restored == [
        (
            (66, "book.epub"),
            {
                "section_index": 4,
                "scroll_ratio": 0.35,
                "offer_due_review_prompt": False,
            },
        )
    ]
    assert read_markers == [("/tmp/addon", "TestProfile", 66, 3)]
