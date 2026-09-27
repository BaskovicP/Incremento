import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault("session", MagicMock())
import aqt

import epub_dock


@pytest.mark.parametrize('model', ['Incremento Writing', 'Basic'])
def test_markdown_editor_is_unavailable_for_non_document_notes_even_with_matching_metadata(monkeypatch, model):
    class Note(dict):
        def note_type(self):
            return {'name': model}
    note = Note(Incremento_Source_Type='Markdown', EPUB_Filename='managed.epub')
    col = types.SimpleNamespace(get_card=lambda cid: types.SimpleNamespace(note=lambda: note))
    monkeypatch.setattr(epub_dock, 'mw', types.SimpleNamespace(col=col))
    monkeypatch.setattr(epub_dock, '_current_epub_card_id', 41)
    monkeypatch.setattr(epub_dock, '_current_epub_filename', 'managed.epub')
    assert epub_dock.is_current_markdown_document() is False


def test_markdown_editor_is_unavailable_when_the_open_card_was_deleted(monkeypatch):
    def deleted(cid):
        raise LookupError('Deleted card')
    monkeypatch.setattr(epub_dock, 'mw', types.SimpleNamespace(col=types.SimpleNamespace(get_card=deleted)))
    monkeypatch.setattr(epub_dock, '_current_epub_card_id', 41)
    monkeypatch.setattr(epub_dock, '_current_epub_filename', 'managed.epub')
    assert epub_dock.is_current_markdown_document() is False


def test_epub_custom_hex_color_is_selected_without_falling_back_to_yellow(monkeypatch):
    monkeypatch.setattr(epub_dock, '_epub_dock', None)
    monkeypatch.setattr(epub_dock, '_current_epub_highlight_color', 'yellow')
    epub_dock._select_epub_highlight_color('#123ABC')
    assert epub_dock._current_epub_highlight_color == '#123abc'


def test_epub_toolbar_is_refreshed_after_locale_initialization(monkeypatch):
    monkeypatch.setattr(epub_dock, "_EPUB_CONTROL_GROUPS", epub_dock._EPUB_CONTROL_GROUPS)
    monkeypatch.setattr(epub_dock, "_EPUB_TOOLBAR_TEXT", epub_dock._EPUB_TOOLBAR_TEXT)
    monkeypatch.setattr(epub_dock, "reader_toolbar_clone_spec", lambda _kind: (("navigation", "Navigacija", ()),))
    monkeypatch.setattr(epub_dock, "reader_toolbar_action_text", lambda _kind: {"previous_page": "← Prethodna"})

    epub_dock._refresh_epub_toolbar_text()

    assert epub_dock._EPUB_CONTROL_GROUPS == (("navigation", "Navigacija"),)
    assert epub_dock._EPUB_TOOLBAR_TEXT["previous_page"] == "← Prethodna"


def test_epub_link_back_history_is_bounded_and_returns_newest_location():
    history = []
    for section_index in range(40):
        history = epub_dock._push_epub_link_back_history(
            history,
            {
                "card_id": 7,
                "filename": "book.epub",
                "section_index": section_index,
                "scroll_ratio": 0.25,
            },
        )

    assert len(history) == epub_dock._MAX_EPUB_LINK_BACK_HISTORY
    assert history[0]["section_index"] == 8

    location, remaining = epub_dock._take_epub_link_back_history(history)

    assert location["section_index"] == 39
    assert len(remaining) == epub_dock._MAX_EPUB_LINK_BACK_HISTORY - 1
    assert len(history) == epub_dock._MAX_EPUB_LINK_BACK_HISTORY


def test_epub_controls_collapse_to_pdf_style_compact_bar(monkeypatch):
    class _Widget:
        def __init__(self):
            self.visible = None

        def setVisible(self, value):
            self.visible = bool(value)

    expanded = _Widget()
    compact = _Widget()
    dock = types.SimpleNamespace(
        _controls_expanded=expanded,
        _controls_compact=compact,
        _controls_collapsed=False,
    )
    monkeypatch.setattr(epub_dock, "_epub_dock", dock)

    epub_dock._set_epub_controls_collapsed(True)

    assert dock._controls_collapsed is True
    assert expanded.visible is False
    assert compact.visible is True


def test_epub_read_progress_state_uses_saved_section_and_ten_segments():
    state = epub_dock._epub_read_progress_state(read_section_index=4, section_count=8)

    assert state == {
        "read_count": 5,
        "percent": 63,
        "filled_segments": 6,
        "range_text": "s.1–5",
    }


def test_epub_read_to_here_toggles_progress_and_clears_exact_anchor(monkeypatch):
    saved = []
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 7)
    monkeypatch.setattr(epub_dock, "_current_epub_section_index", 3)
    monkeypatch.setattr(epub_dock, "_current_epub_read_anchor", {"sectionIndex": 2})
    monkeypatch.setattr(epub_dock, "_active_profile", lambda: "Profile")
    monkeypatch.setattr(epub_dock, "get_read_section_index", lambda *_args: 1)
    monkeypatch.setattr(
        epub_dock,
        "set_read_section_index",
        lambda *args: saved.append(args),
    )
    monkeypatch.setattr(epub_dock, "_push_epub_read_anchor", lambda: None)
    monkeypatch.setattr(epub_dock, "_update_title_and_buttons", lambda: None)
    monkeypatch.setattr(epub_dock, "tooltip", lambda _message: None)

    epub_dock._mark_epub_read_to_here()

    assert saved == [(epub_dock._ADDON_DIR, "Profile", 7, 3, None)]
    assert epub_dock._current_epub_read_anchor is None


def test_epub_highlight_color_selection_updates_page_before_highlighting(monkeypatch):
    scripts = []
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: object()))
    monkeypatch.setattr(epub_dock, "_epub_dock", dock)
    monkeypatch.setattr(
        epub_dock,
        "_run_epub_javascript",
        lambda _page, script, *args: scripts.append(script),
    )

    epub_dock._select_epub_highlight_color("purple", create_highlight=True)

    assert epub_dock._current_epub_highlight_color == "purple"
    assert "incrementoSetEpubHighlightColor" in scripts[0]
    assert "incrementoAddEpubHighlight" in scripts[0]
    assert scripts[0].index("incrementoSetEpubHighlightColor") < scripts[0].index(
        "incrementoAddEpubHighlight"
    )


def test_open_current_epub_page_cards_uses_only_current_section(monkeypatch):
    browsed = []
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 7)
    monkeypatch.setattr(epub_dock, "_current_epub_section_index", 2)
    monkeypatch.setattr(epub_dock, "_active_profile", lambda: "Profile")
    monkeypatch.setattr(
        epub_dock,
        "get_epub_card_sources",
        lambda *_args: [{"note_id": 11}, {"note_id": 12}, {"note_id": 11}],
    )
    monkeypatch.setattr(
        epub_dock,
        "_browse_note_ids_in_browser",
        lambda note_ids, **kwargs: browsed.append((note_ids, kwargs)) or True,
    )

    assert epub_dock._open_current_epub_page_cards_in_browser() is True
    assert browsed == [([11, 12, 11], {"empty_message": "No cards created from this EPUB page yet."})]


def test_epub_page_script_supports_absolute_page_jump_and_all_pdf_highlight_colors(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "One"}, {"text": "Two"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)

    script = epub_dock._build_page_script(
        card_id=7,
        section_index=0,
        scroll_ratio=0.0,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[],
        bridge_nonce="private-token",
        highlight_color="aqua",
    )

    assert '"highlightColor": "aqua"' in script
    assert "incrementoSetEpubHighlightColor" in script
    assert "incrementoGoToEpubPage" in script
    for color in ("yellow", "green", "blue", "pink", "aqua", "orange", "red", "purple"):
        assert color in script
        assert f'span.incremento-epub-highlight[data-color="{color}"]' in script
    assert "if (targetSection === STATE.sectionIndex)" not in script


def test_epub_page_script_sets_selected_locale_and_translates_generated_controls(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "中文"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)
    monkeypatch.setattr(epub_dock, "get_locale", lambda: "zh-Hans", raising=False)
    monkeypatch.setattr(epub_dock, "t", lambda key, **_values: {"reader_read_marker": "已读至此"}.get(key, key), raising=False)

    script = epub_dock._build_page_script(
        card_id=7, section_index=0, scroll_ratio=0.0, text_scale=1.0,
        read_anchor=None, focus_offset=-1, search_query="", highlights=[],
        bridge_nonce="private-token",
    )

    assert '"locale": "zh-Hans"' in script
    assert f'"readMarker": {json.dumps("已读至此")}' in script
    assert "document.documentElement.lang = STATE.locale" in script


def test_epub_limit_summary_uses_translated_mode_code(monkeypatch):
    messages = {
        "reader_epub_limit_summary": "Danas: {used}/{limit} stranica, preostaje {remaining}. Način: {mode}.",
        "reader_limit_soft_lock": "Meko zaključavanje",
    }
    monkeypatch.setattr(epub_dock, "t", lambda key, **values: messages[key].format(**values))

    summary = epub_dock._epub_limit_summary_text({
        "enabled": True,
        "daily_page_limit": 5,
        "pages_used": 2,
        "pages_remaining": 3,
        "enforcement_mode": "soft_lock",
    })

    assert summary == "Danas: 2/5 stranica, preostaje 3. Način: Meko zaključavanje."


def test_epub_control_customization_hides_only_selected_groups(monkeypatch):
    class _Widget:
        def __init__(self):
            self.visible = None

        def setVisible(self, value):
            self.visible = bool(value)

    class _Layout:
        def __init__(self):
            self.invalidated = False

        def invalidate(self):
            self.invalidated = True

    groups = {
        group_id: _Widget()
        for group_id, _label in epub_dock._EPUB_CONTROL_GROUPS
    }
    group_layout = _Layout()
    dock = types.SimpleNamespace(
        _control_groups=groups,
        _control_groups_layout=group_layout,
    )
    monkeypatch.setattr(epub_dock, "_epub_dock", dock)

    epub_dock._apply_epub_control_visibility({"annotation": False})

    assert groups["annotation"].visible is False
    assert all(
        widget.visible is True
        for group_id, widget in groups.items()
        if group_id != "annotation"
    )
    assert dock._epub_control_visibility["annotation"] is False
    assert group_layout.invalidated is True


def test_epub_links_toggle_stays_synchronized_in_full_and_compact_controls(monkeypatch):
    class _Button:
        def __init__(self):
            self.checked = False
            self.text = ""
            self.tooltip = ""
            self.description = ""

        def blockSignals(self, _value):
            return None

        def setChecked(self, value):
            self.checked = bool(value)

        def setText(self, value):
            self.text = value

        def setToolTip(self, value):
            self.tooltip = value

        def setAccessibleDescription(self, value):
            self.description = value

    full = _Button()
    compact = _Button()
    dock = types.SimpleNamespace(
        _links_btn=full,
        _compact_links_btn=compact,
        _view=types.SimpleNamespace(page=lambda: object()),
    )
    scripts = []
    monkeypatch.setattr(epub_dock, "_epub_dock", dock)
    monkeypatch.setattr(
        epub_dock,
        "_run_epub_javascript",
        lambda page, script, *args: scripts.append(script),
    )

    epub_dock._toggle_epub_clickable_links(True)

    assert full.checked is True
    assert compact.checked is True
    assert full.text == compact.text == "Links On"
    assert "true" in scripts[0]


def test_internal_epub_link_records_exact_source_location_for_jump_back(monkeypatch):
    scripts = []
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: object()))
    monkeypatch.setattr(epub_dock, "_epub_dock", dock)
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 7)
    monkeypatch.setattr(epub_dock, "_current_epub_filename", "book.epub")
    monkeypatch.setattr(epub_dock, "_current_epub_section_index", 0)
    monkeypatch.setattr(epub_dock, "_current_epub_scroll_ratio", 0.1)
    monkeypatch.setattr(epub_dock, "_epub_link_back_history", [])
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"title": "One"}])
    monkeypatch.setattr(
        epub_dock,
        "get_epub_section_path",
        lambda addon_dir, filename, index: "/safe/book/one.xhtml",
    )
    monkeypatch.setattr(
        epub_dock,
        "get_epub_extract_dir",
        lambda filename, profile: "/safe/book",
    )
    monkeypatch.setattr(epub_dock, "_active_profile", lambda: "Profile")
    monkeypatch.setattr(
        epub_dock,
        "_run_epub_javascript",
        lambda page, script, *args: scripts.append(script),
    )
    monkeypatch.setattr(epub_dock, "_sync_epub_link_back_buttons", lambda: None)

    assert epub_dock._open_epub_reader_link(
        "#destination",
        source_scroll_ratio=0.625,
    ) is True

    assert epub_dock._epub_link_back_history == [
        {
            "card_id": 7,
            "filename": "book.epub",
            "section_index": 0,
            "scroll_ratio": 0.625,
        }
    ]
    assert "incrementoOpenEpubAnchor" in scripts[0]


def test_epub_jump_back_restores_latest_internal_link_source(monkeypatch):
    calls = []
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 7)
    monkeypatch.setattr(epub_dock, "_current_epub_filename", "book.epub")
    monkeypatch.setattr(
        epub_dock,
        "_epub_link_back_history",
        [
            {
                "card_id": 7,
                "filename": "book.epub",
                "section_index": 3,
                "scroll_ratio": 0.375,
            }
        ],
    )
    monkeypatch.setattr(
        epub_dock,
        "show_epub_in_dock",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr(epub_dock, "_sync_epub_link_back_buttons", lambda: None)

    assert epub_dock._jump_back_from_epub_link() is True

    assert calls == [
        (
            (7, "book.epub"),
            {
                "section_index": 3,
                "scroll_ratio": 0.375,
                "offer_due_review_prompt": False,
                "preserve_link_history": True,
            },
        )
    ]
    assert epub_dock._epub_link_back_history == []


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


def test_build_page_script_supports_dragging_both_highlight_endpoints(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "Example section text"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)

    script = epub_dock._build_page_script(
        card_id=7,
        section_index=0,
        scroll_ratio=0.0,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[{"id": "hl-1", "startOffset": 0, "endOffset": 7, "text": "Example"}],
        bridge_nonce="private-token",
    )

    assert "incremento-epub-highlight-resize-btn" in script
    assert "incremento-epub-resize-handle" in script
    assert "data-endpoint" in script
    assert "setPointerCapture" in script
    assert "pointermove" in script
    assert "pointerup" in script
    assert "incremento_epub_hl_add:" in script
    assert "resizeHighlightRange" in script
    assert "highlight: session.highlight" in script
    assert "id: String(target.dataset.id || '')" in script
    assert "if (endOffset <= startOffset) return null" in script
    assert "opacity: 0;\n            pointer-events: none;" in script
    assert "#incremento-epub-highlight-actions:hover #incremento-epub-highlight-resize-btn" in script
    finish_resize = script[
        script.index("      function finishHighlightResize"):
        script.index("      function cancelHighlightResize")
    ]
    cancel_resize = script[
        script.index("      function cancelHighlightResize"):
        script.index("      function beginHighlightResize")
    ]
    assert "removeHighlightResizeHandles();" in finish_resize
    assert "removeHighlightResizeHandles();" in cancel_resize
    update_resize = script[
        script.index("      function updateHighlightResize"):
        script.index("      function finishHighlightResize")
    ]
    assert "const caret = preciseCaretAtPoint(session" in update_resize
    click_handler = script[
        script.index("window._incrementoEpubClickListener = function(event)"):
        script.index("document.addEventListener('click'", script.index("window._incrementoEpubClickListener"))
    ]
    assert "resizeHighlightRange(target);" in click_handler
    assert "openHighlightActionMenu(target);" in click_handler


def test_build_page_script_shows_draggable_handles_on_live_epub_selection(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "Example section text"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)

    script = epub_dock._build_page_script(
        card_id=7,
        section_index=0,
        scroll_ratio=0.0,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[],
        bridge_nonce="private-token",
    )

    assert "incremento-epub-selection-resize-handle" in script
    assert "renderSelectionResizeHandles(meta)" in script
    assert "moveSelectionResizeEndpoint" in script
    assert "selection.removeAllRanges()" in script
    assert "selection.addRange(next)" in script
    assert "pointercancel" in script
    assert "window._incrementoEpubPreciseSelectionStart = beginPreciseSelectionDrag" in script
    assert "const preciseStartEvent = preciseUsesPointerEvents ? 'pointerdown' : 'mousedown'" in script
    assert "document.addEventListener(preciseMoveEvent, window._incrementoEpubPreciseSelectionMove, true)" in script
    assert "document.addEventListener('selectstart', window._incrementoEpubPreciseSelectionBlocker, true)" in script
    assert "incremento-epub-selection-loupe" not in script
    assert "preciseStickyRow" in script
    assert "preciseMagneticWordCaret" in script
    assert "if (!window._incrementoEpubSelectionHandlesRequested)" in script
    assert "window._incrementoEpubSelectionHandlesRequested = true;" in script
    assert "window._incrementoEpubSelectionHandlesRequested = false;" in script
    click_handler = script[script.index("window._incrementoEpubClickListener = function(event)") :]
    assert click_handler.index("removeHighlightResizeHandles();") < click_handler.index(
        "const target = event.target && event.target.closest"
    )


def test_epub_end_handle_stays_on_its_row_in_the_right_margin(monkeypatch):
    import json
    import subprocess

    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "Example section text"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)
    script = epub_dock._build_page_script(
        card_id=7,
        section_index=0,
        scroll_ratio=0.0,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[],
        bridge_nonce="private-token",
    )
    resize_drag = script[
        script.index("      function preciseSelectionRange"):
        script.index("      function cancelSelectionResize")
    ]
    program = r"""
        const fs = require('node:fs');
        const code = JSON.parse(fs.readFileSync(0, 'utf8')).code;
        const textNode = {nodeType: 3, nodeValue: 'hello world again'};
        const selected = [];
        const visualTop = offset => offset <= 5 ? 20 : (offset <= 11 ? 40 : 200);
        const makeRange = (start = 0, end = start) => ({
          startContainer: textNode,
          endContainer: textNode,
          startOffset: start,
          endOffset: end,
          commonAncestorContainer: textNode,
          get collapsed() { return this.startOffset === this.endOffset; },
          setStart(node, offset) { this.startContainer = node; this.startOffset = offset; },
          setEnd(node, offset) { this.endContainer = node; this.endOffset = offset; },
          collapse() { this.endContainer = this.startContainer; this.endOffset = this.startOffset; },
          cloneRange() { return makeRange(this.startOffset, this.endOffset); },
          selectNodeContents(node) { this.selectedNode = node; },
          getClientRects() {
            if (!this.selectedNode) return [];
            return [20, 40].map(top => ({left: 0, right: 10, top, bottom: top + 18, width: 10, height: 18}));
          },
          getBoundingClientRect() {
            return {left: this.startOffset, right: this.startOffset, top: visualTop(this.startOffset), height: 18};
          },
        });
        let currentRange = makeRange(0, 3);
        const selection = {
          isCollapsed: false,
          rangeCount: 1,
          getRangeAt: () => currentRange,
          removeAllRanges: () => selected.splice(0),
          addRange: range => { selected.push(range); currentRange = range; },
        };
        const document = {createRange: () => makeRange()};
        const window = {getSelection: () => selection};
        const textNodes = () => [textNode];
        const caretRangeAtPoint = (x, y) => {
          const offset = x > 10 ? 15 : (x >= 9 ? (y < 40 ? 5 : 11) : Math.trunc(x));
          return makeRange(offset, offset);
        };
        const selectionMeta = () => null;
        eval(code);
        const handle = {
          dataset: {endpoint: 'end'},
          setPointerCapture() {},
        };
        beginSelectionResize({
          currentTarget: handle, pointerId: 12,
          preventDefault() {}, stopPropagation() {},
        });
        moveSelectionResizeEndpoint({pointerId: 12, clientX: 50, clientY: 30});
        const sameRow = selected[0].endOffset;
        moveSelectionResizeEndpoint({pointerId: 12, clientX: 50, clientY: 39});
        const boundary = selected[0].endOffset;
        moveSelectionResizeEndpoint({pointerId: 12, clientX: 50, clientY: 45});
        const nextRow = selected[0].endOffset;
        process.stdout.write(JSON.stringify({sameRow, boundary, nextRow}));
    """
    result = subprocess.run(
        ["node", "-e", program],
        input=json.dumps({"code": resize_drag}),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"sameRow": 5, "boundary": 5, "nextRow": 11}


def test_initial_epub_trackpad_drag_tracks_each_character_in_both_directions(monkeypatch):
    import json
    import subprocess

    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "Example section text"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)
    script = epub_dock._build_page_script(
        card_id=7,
        section_index=0,
        scroll_ratio=0.0,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[],
        bridge_nonce="private-token",
    )
    smooth_drag = script[
        script.index("      function preciseSelectionRange"):
        script.index("      function removeSelectionResizeHandles")
    ]
    program = r"""
        const fs = require('node:fs');
        const code = JSON.parse(fs.readFileSync(0, 'utf8')).code;
        const textNode = {nodeType: 3, nodeValue: 'hello world'};
        const foreignNode = {};
        let caretNode = textNode;
        const selected = [];
        const visualTop = offset => ({1: 10, 2: 20, 3: 20, 4: 40, 5: 60, 9: 260}[offset] ?? 20);
        const makeRange = (start = 0, end = start) => ({
          startContainer: textNode,
          endContainer: textNode,
          startOffset: start,
          endOffset: end,
          commonAncestorContainer: textNode,
          get collapsed() { return this.startOffset === this.endOffset; },
          setStart(node, offset) { this.startContainer = node; this.startOffset = offset; },
          setEnd(node, offset) { this.endContainer = node; this.endOffset = offset; },
          collapse() { this.endContainer = this.startContainer; this.endOffset = this.startOffset; },
          cloneRange() { return makeRange(this.startOffset, this.endOffset); },
          compareBoundaryPoints(_how, source) { return this.startOffset - source.startOffset; },
          selectNodeContents(node) { this.selectedNode = node; },
          getClientRects() {
            if (!this.selectedNode) return [];
            return [20, 40, 60].map(top => ({left: 0, right: 10, top, bottom: top + 18, width: 10, height: 18}));
          },
          getBoundingClientRect() {
            return {left: this.startOffset, top: visualTop(this.startOffset), width: 0, height: 18};
          },
        });
        const document = { createRange: () => makeRange() };
        const window = {
          PointerEvent: function PointerEvent() {},
          getSelection: () => ({
            removeAllRanges: () => selected.splice(0),
            addRange: range => selected.push(range),
          }),
        };
        let capturedPointer = null;
        const dragTarget = {
          closest: () => null,
          setPointerCapture: pointerId => { capturedPointer = pointerId; },
          releasePointerCapture: pointerId => {
            if (pointerId !== capturedPointer) throw new Error('released the wrong pointer');
            capturedPointer = null;
          },
        };
        const textNodes = () => [textNode];
        const caretRangeAtPoint = (x, y) => {
          let offset = Math.trunc(x);
          if (x === 9 && y === 57) offset = 4;
          if (x === 8 && y === 55) offset = 3;
          if (x === 9 && y === 21) offset = 3;
          if (x === 1 && y === 21) offset = 0;
          const range = makeRange(offset, offset);
          range.startContainer = caretNode;
          range.endContainer = caretNode;
          range.commonAncestorContainer = caretNode;
          return range;
        };
        const reportSelection = () => {};
        const event = (x, buttons = 1, y = 10) => ({
          button: 0, buttons, isPrimary: true, pointerId: 12,
          clientX: x, clientY: y, target: dragTarget,
          preventDefault() { this.defaultPrevented = true; },
        });
        eval(code);
        const down = event(2, 1, 20);
        beginPreciseSelectionDrag(down);
        const nativeSelection = event(2);
        blockNativeSelectionDuringPreciseDrag(nativeSelection);
        const first = event(3, 1, 20);
        updatePreciseSelectionDrag(first);
        const forward = [selected[0].startOffset, selected[0].endOffset];
        updatePreciseSelectionDrag(event(5, 1, 60));
        const later = [selected[0].startOffset, selected[0].endOffset];
        updatePreciseSelectionDrag(event(9, 1, 59));
        const interline = [selected[0].startOffset, selected[0].endOffset];
        updatePreciseSelectionDrag(event(8, 1, 55));
        const changedRow = [selected[0].startOffset, selected[0].endOffset];
        updatePreciseSelectionDrag(event(9, 1, 55));
        const rejectedJump = [selected[0].startOffset, selected[0].endOffset];
        updatePreciseSelectionDrag(event(1, 1, 10));
        const backward = [selected[0].startOffset, selected[0].endOffset];
        caretNode = foreignNode;
        updatePreciseSelectionDrag(event(9));
        const outside = [selected[0].startOffset, selected[0].endOffset];
        finishPreciseSelectionDrag(event(1, 0, 10));
        const afterRelease = event(1, 0);
        blockNativeSelectionDuringPreciseDrag(afterRelease);
        caretNode = textNode;
        beginPreciseSelectionDrag(event(50, 1, 20));
        finishPreciseSelectionDrag(event(50, 0, 20));
        const blankRight = [selected[0].startOffset, selected[0].endOffset];
        beginPreciseSelectionDrag(event(-50, 1, 20));
        finishPreciseSelectionDrag(event(-50, 0, 20));
        const blankLeft = [selected[0].startOffset, selected[0].endOffset];
        beginPreciseSelectionDrag(event(4.9, 1, 20));
        finishPreciseSelectionDrag(event(4.9, 0, 20));
        const magneticWordEnd = [selected[0].startOffset, selected[0].endOffset];
        process.stdout.write(JSON.stringify({
          downPrevented: !!down.defaultPrevented,
          nativeSelectionPrevented: !!nativeSelection.defaultPrevented,
          afterReleasePrevented: !!afterRelease.defaultPrevented,
          pointerReleased: capturedPointer === null,
          movePrevented: !!first.defaultPrevented,
          forward, later, interline, changedRow, rejectedJump, backward, outside,
          blankRight, blankLeft, magneticWordEnd,
        }));
    """
    result = subprocess.run(
        ["node", "-e", program],
        input=json.dumps({"code": smooth_drag}),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "downPrevented": True,
        "nativeSelectionPrevented": True,
        "afterReleasePrevented": False,
        "pointerReleased": True,
        "movePrevented": True,
        "forward": [2, 3],
        "later": [2, 5],
        "interline": [2, 5],
        "changedRow": [2, 3],
        "rejectedJump": [2, 3],
        "backward": [0, 2],
        "outside": [0, 2],
        "blankRight": [3, 3],
        "blankLeft": [0, 0],
        "magneticWordEnd": [5, 5],
    }


def test_build_page_script_installs_opt_in_trusted_link_bridge(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "Example"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)

    script = epub_dock._build_page_script(
        card_id=7,
        section_index=0,
        scroll_ratio=0.0,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[],
        bridge_nonce="private-token",
        clickable_links=True,
        link_fragment="chapter-part",
    )

    assert '"clickableLinks": true' in script
    assert '"linkFragment": "chapter-part"' in script
    assert "incremento_epub_open_link:" in script
    assert "sourceScrollRatio" in script
    assert "incrementoSetEpubClickableLinks" in script
    assert "incrementoOpenEpubAnchor" in script
    assert "if (!event.isTrusted) return" in script
    assert "window.open(" not in script


def test_epub_page_script_exposes_exact_right_click_anchor(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: [{"text": "Example section"}])
    monkeypatch.setattr(epub_dock, "configured_highlight_when_extracting", lambda: False)

    script = epub_dock._build_page_script(
        card_id=7,
        section_index=0,
        scroll_ratio=0.0,
        text_scale=1.0,
        read_anchor=None,
        focus_offset=-1,
        search_query="",
        highlights=[],
        bridge_nonce="private-token",
    )

    assert "incrementoEpubAnchorAtPoint" in script
    assert "caretRangeFromPoint" in script
    dock_source = Path(epub_dock.__file__).read_text(encoding="utf-8")
    assert "customContextMenuRequested" in dock_source
    assert 'action_label=t("reader_copy_link_to_place")' in dock_source
    assert epub_dock.t("reader_copy_link_to_place") == "Copy Link to This Place"


def test_epub_context_anchor_builds_clickable_card_link_and_rejects_stale_card(monkeypatch):
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 77)
    monkeypatch.setattr(epub_dock, "_current_epub_filename", "my-book.epub")
    monkeypatch.setattr(epub_dock, "_current_epub_section_index", 3)
    monkeypatch.setattr(
        epub_dock,
        "_current_sections",
        lambda: [
            {"title": "One", "text": "a"},
            {"title": "Two", "text": "b"},
            {"title": "Three", "text": "c"},
            {"title": "Chapter <Four>", "text": "abcdefghij"},
        ],
    )

    anchor = epub_dock._normalize_epub_context_anchor(
        {
            "cardId": 77,
            "sectionIndex": 3,
            "focusOffset": 8,
            "scrollRatio": 0.375,
        }
    )
    html = epub_dock.epub_anchor_link_html(**anchor, label="Chapter <Four>")

    assert anchor == {
        "card_id": 77,
        "section_index": 3,
        "focus_offset": 8,
        "scroll_ratio": 0.375,
    }
    assert "incremento_open_epub:77:3:8:0.375" in html
    assert "Chapter &lt;Four&gt;" in html
    assert epub_dock._normalize_epub_context_anchor(
        {"cardId": 88, "sectionIndex": 3, "focusOffset": 8, "scrollRatio": 0.2}
    ) is None
    assert epub_dock.epub_anchor_link_html(
        card_id="invalid",
        section_index=3,
        focus_offset=8,
        scroll_ratio=0.2,
        label="Chapter",
    ) == ""


def test_epub_anchor_command_parser_supports_exact_and_legacy_links():
    assert epub_dock.parse_epub_anchor_command(
        "incremento_open_epub:77:3:8:0.375"
    ) == {
        "card_id": 77,
        "section_index": 3,
        "focus_offset": 8,
        "scroll_ratio": 0.375,
    }
    assert epub_dock.parse_epub_anchor_command(
        "incremento_open_epub:77:3:8"
    ) == {
        "card_id": 77,
        "section_index": 3,
        "focus_offset": 8,
        "scroll_ratio": None,
    }
    for unsafe in (
        "incremento_open_epub:0:3:8:0.5",
        "incremento_open_epub:77:-1:8:0.5",
        "incremento_open_epub:77:3:-2:0.5",
        "incremento_open_epub:77:3:8:nan",
        "incremento_open_epub:77:3:8:0.5:extra",
    ):
        assert epub_dock.parse_epub_anchor_command(unsafe) is None


def test_epub_link_target_resolver_allows_book_sections_and_https_only(tmp_path):
    root = tmp_path / "book"
    chapter_one = root / "Text" / "one.xhtml"
    chapter_two = root / "Text" / "two.xhtml"
    chapter_one.parent.mkdir(parents=True)
    chapter_one.write_text("one", encoding="utf-8")
    chapter_two.write_text("two", encoding="utf-8")

    kwargs = {
        "content_root": root,
        "current_section_path": chapter_one,
        "section_paths": [chapter_one, chapter_two],
    }
    assert epub_dock._resolve_epub_reader_link("two.xhtml#part", **kwargs) == {
        "kind": "internal",
        "section_index": 1,
        "fragment": "part",
    }
    assert epub_dock._resolve_epub_reader_link("#local", **kwargs) == {
        "kind": "internal",
        "section_index": 0,
        "fragment": "local",
    }
    assert epub_dock._resolve_epub_reader_link(
        "https://docs.example.test/reference", **kwargs
    ) == {
        "kind": "external",
        "url": "https://docs.example.test/reference",
    }
    for unsafe in (
        "javascript:alert(1)",
        "file:///etc/passwd",
        "mailto:user@example.test",
        "../../../outside.xhtml",
        r"..\\outside.xhtml",
        "missing.xhtml",
    ):
        assert epub_dock._resolve_epub_reader_link(unsafe, **kwargs) is None


def test_epub_link_bridge_requires_current_card(monkeypatch):
    opened = []
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 42)
    monkeypatch.setattr(
        epub_dock,
        "_open_epub_reader_link",
        lambda href: opened.append(href),
    )
    page = types.SimpleNamespace(_bridge_nonce="private-token")

    for card_id in (99, 42):
        payload = '{"cardId":%d,"href":"https://example.test/docs"}' % card_id
        epub_dock._EpubDockPage.javaScriptConsoleMessage(
            page,
            0,
            epub_dock._PYCMD_BRIDGE
            + "private-token:"
            + epub_dock._MSG_OPEN_LINK
            + payload,
            0,
            "book.xhtml",
        )

    assert opened == ["https://example.test/docs"]


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


@pytest.mark.parametrize("locale,label", [("en", "Section 2"), ("hr", "Odjeljak 2"), ("zh-Hans", "第 2 章节")])
def test_untitled_epub_section_is_localized_in_search_navigation_and_citation(monkeypatch, locale, label):
    from backend.i18n import Translator

    sections = [{"title": "Original Chapter"}, {"title": ""}]
    monkeypatch.setattr(epub_dock, "t", Translator(locale).t)
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 9)
    monkeypatch.setattr(epub_dock, "_current_epub_filename", "book.epub")
    monkeypatch.setattr(epub_dock, "_current_epub_section_index", 1)
    monkeypatch.setattr(epub_dock, "_current_epub_scroll_ratio", 0.25)
    monkeypatch.setattr(epub_dock, "_last_selection_meta", {})
    monkeypatch.setattr(epub_dock, "_current_sections", lambda: sections)
    monkeypatch.setattr(epub_dock, "load_epub_metadata", lambda *args: {"sections": sections})
    monkeypatch.setattr(epub_dock, "search_epub_text_index_for_card", lambda *args, **kwargs: [(1, "", "A phrase")])

    assert epub_dock.current_card_epub_search_hits(9, "phrase")[0]["sectionTitle"] == label
    assert epub_dock._current_epub_section_title() == label
    assert f">{label}</a>" in epub_dock.epub_citation()
    assert sections == [{"title": "Original Chapter"}, {"title": ""}]


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


def test_open_epub_location_prefers_explicit_anchor_scroll_fallback(monkeypatch):
    shown = []
    monkeypatch.setattr(
        epub_dock,
        "mw",
        types.SimpleNamespace(
            col=types.SimpleNamespace(
                get_card=lambda card_id: types.SimpleNamespace(nid=9),
                get_note=lambda note_id: {epub_dock.EPUB_FILE_FIELD: "book.epub"},
            )
        ),
    )
    monkeypatch.setattr(epub_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(epub_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(epub_dock, "get_epub_progress", lambda *_args: (1, 0.2, False))
    monkeypatch.setattr(
        epub_dock,
        "show_epub_in_dock",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )

    epub_dock.open_epub_location(
        77,
        3,
        focus_offset=8,
        scroll_ratio_override=0.625,
    )

    assert shown == [
        (
            (77, "book.epub"),
            {
                "section_index": 3,
                "scroll_ratio": 0.625,
                "focus_offset": 8,
                "search_query": "",
            },
        )
    ]


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


@pytest.mark.parametrize('switch_context', [False, True], ids=['current-section', 'section-changed'])
def test_epub_picker_remembers_selection_and_drops_result_after_navigation(monkeypatch, switch_context):
    scripts, callbacks, picks = [], [], []
    page = types.SimpleNamespace(bridge_nonce=lambda: 'current-nonce')
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: page))
    monkeypatch.setattr(epub_dock, '_epub_dock', dock)
    monkeypatch.setattr(epub_dock, '_current_epub_card_id', 42)
    monkeypatch.setattr(epub_dock, '_current_epub_filename', 'book.epub')
    monkeypatch.setattr(epub_dock, '_current_epub_section_index', 0)
    monkeypatch.setattr(epub_dock, '_current_epub_highlight_color', 'yellow')
    monkeypatch.setattr(epub_dock, '_active_profile', lambda: 'Profile A')
    def run(_page, script, callback=None):
        scripts.append(script)
        if callback:
            callbacks.append(callback)
    monkeypatch.setattr(epub_dock, '_run_epub_javascript', run)
    def choose(parent, current, *, addon_dir, profile):
        picks.append((parent, current, addon_dir, profile))
        if switch_context:
            monkeypatch.setattr(epub_dock, '_current_epub_section_index', 1)
        return '#123abc'
    monkeypatch.setitem(sys.modules, 'highlight_color_dialog', types.SimpleNamespace(choose_highlight_color=choose))
    epub_dock._choose_epub_highlight_color()
    assert len(scripts) == 1 and 'incrementoRememberEpubHighlightSelection' in scripts[0]
    assert not picks
    callbacks.pop()(None)
    assert picks == [(dock, 'yellow', epub_dock._ADDON_DIR, 'Profile A')]
    if switch_context:
        assert len(scripts) == 1
        assert epub_dock._current_epub_highlight_color == 'yellow'
    else:
        assert epub_dock._current_epub_highlight_color == '#123abc'
        assert 'incrementoPickEpubHighlightColor("#123abc")' in scripts[-1]


@pytest.mark.parametrize('accepted', [True, False], ids=['hex-selected', 'cancelled'])
def test_epub_hex_selection_survives_picker_and_paints_selected_text(monkeypatch, accepted):
    import json
    import subprocess
    monkeypatch.setattr(epub_dock, '_current_sections', lambda: [{'text': 'Selected passage'}])
    monkeypatch.setattr(epub_dock, 'configured_highlight_when_extracting', lambda: False)
    script = epub_dock._build_page_script(card_id=42, section_index=0, scroll_ratio=0,
        text_scale=1, read_anchor=None, focus_offset=-1, search_query='', highlights=[],
        bridge_nonce='test-nonce', highlight_color='yellow')
    normalize = script[script.index('      const HIGHLIGHT_COLORS'):script.index('      function send')]
    paint = script[script.index('      function applyHighlight'):script.index('      function selectionMeta')]
    set_color = script[script.index('      window.incrementoSetEpubHighlightColor'):script.index('      window.incrementoSetEpubReadAnchor')]
    picker = script[script.index('      let pendingHighlightSelection'):script.index('      window.incrementoSnapshotEpubSelection')]
    program = '''
        const fs = require('node:fs');
        const input = JSON.parse(fs.readFileSync(0, 'utf8'));
        const STATE = { cardId: 42, sectionIndex: 0, highlightColor: 'yellow' };
        const window = {}, rows = [], wrappers = [];
        let selection = { text: 'Selected passage', startOffset: 2, endOffset: 18 };
        const selectionMeta = () => selection;
        const clearSelection = () => { selection = null; };
        const pointFromOffset = offset => ({ node: {nodeValue: 'Selected passage longer'}, offset });
        const updateHighlightNodeNote = () => {};
        const resizeHighlightRange = () => true;
        const send = command => rows.push(JSON.parse(command.slice('incremento_epub_hl_add:'.length)).highlight);
        const document = {
            createRange: () => ({setStart(){}, setEnd(){}, collapsed: false,
                extractContents(){ return {}; }, insertNode(){} }),
            createElement: () => { const node = {dataset: {}, style: {}, appendChild(){}}; wrappers.push(node); return node; },
        };
        eval(input.code);
        window.incrementoRememberEpubHighlightSelection();
        selection = null;
        window.incrementoPickEpubHighlightColor(input.accepted ? '#123ABC' : null);
        window.incrementoPickEpubHighlightColor('#654321');
        process.stdout.write(JSON.stringify({rows, wrappers}));
    '''
    result = subprocess.run(['node', '-e', program], input=json.dumps({
        'code': normalize + paint + set_color + picker, 'accepted': accepted}),
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    state = json.loads(result.stdout)
    if not accepted:
        assert state == {'rows': [], 'wrappers': []}
    else:
        assert len(state['rows']) == 1
        assert state['rows'][0]['color'] == '#123abc'
        assert state['rows'][0]['text'] == 'Selected passage'
        assert state['rows'][0]['startOffset'] == 2 and state['rows'][0]['endOffset'] == 18
        assert state['wrappers'][0]['style']['backgroundColor'] == 'rgba(18,58,188,0.42)'
