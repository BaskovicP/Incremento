import json
import types
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def test_visible_page_link_bridge_jumps_in_main_reader_and_retires_on_document_change(monkeypatch):
    controllers, opened = [], []
    class Bridge:
        def __init__(self, **options):
            self.options = options
            controllers.append(self)
        def current(self): return self.options['is_current']()
        def close(self): pass
        def handle(self, payload): return payload['operation'] == 'list'
    monkeypatch.setitem(sys.modules, 'pdf_page_links', types.SimpleNamespace(PdfPageLinksBridge=Bridge))
    page = types.SimpleNamespace(runJavaScript=lambda *a: None)
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: page))
    monkeypatch.setattr(pdf_dock, '_pdf_dock', dock)
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, '_current_pdf_filename', 'first.pdf')
    monkeypatch.setattr(pdf_dock, '_active_profile', lambda: 'A')
    monkeypatch.setattr(pdf_dock, 'show_pdf_in_dock', lambda *a, **kw: opened.append((a, kw)))
    assert pdf_dock._handle_pdf_page_links({'cardId': 42, 'operation': 'list'})
    options = controllers[0].options
    options['open_pdf']({'card_id': 43, 'filename': 'second.pdf'},
                        {'target_page': 8, 'target_scroll': .3, 'target_y': .65})
    assert opened[0][0][:3] == (43, 'second.pdf', 8)
    assert opened[0][1]['preserve_history'] is True
    assert opened[0][1]['scroll_ratio_override'] == .3
    assert opened[0][1]['page_y_override'] == .65
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 44)
    assert not options['is_current']()


def test_linked_pdf_actions_capture_source_and_reject_stale_reader(monkeypatch):
    opened = []
    ui = types.SimpleNamespace(show_links=lambda *a, **kw: opened.append((a, kw)), link_pdf=lambda *a, **kw: None)
    monkeypatch.setitem(sys.modules, "document_link_ui", ui)
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "book.pdf")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "A")
    monkeypatch.setattr(pdf_dock, "_pdf_dock", object())
    assert not pdf_dock._open_pdf_document_links({"cardId": 99, "page": 3}, create=False)
    assert pdf_dock._open_pdf_document_links({"cardId": 42, "page": 3}, create=False)
    source = opened[0][0][0]
    assert source == {"card_id": 42, "kind": "pdf", "page": 3, "quote": ""}
    guard = opened[0][1]["is_current"]
    assert guard()
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 43)
    assert not guard()


def test_annotation_refresh_preserves_live_reference_navigation_without_changing_saved_progress(monkeypatch):
    opened, saved = [], []
    location = {'profile': 'A', 'card_id': 42, 'filename': 'book.pdf', 'page': 3,
                'zoom': 1, 'scroll_ratio': .3, 'page_y': .65}
    monkeypatch.setattr(pdf_dock, '_pdf_dock', types.SimpleNamespace(_reader_location=location))
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, '_current_pdf_filename', 'book.pdf')
    monkeypatch.setattr(pdf_dock, '_active_profile', lambda: 'A')
    monkeypatch.setattr(pdf_dock, '_pdf_preserve_history', True)
    monkeypatch.setattr(pdf_dock, '_pdf_via_link', True)
    monkeypatch.setattr(pdf_dock, 'get_page', lambda *a: 1)
    monkeypatch.setattr(pdf_dock, '_current_pdf_limit_status', lambda *a, **kw: {})
    monkeypatch.setattr(pdf_dock, '_push_pdf_limit_status', lambda *a: None)
    monkeypatch.setattr(pdf_dock, '_timer_mod', types.SimpleNamespace(record_pdf_page_read=lambda *a: None))
    for name in ('set_page', 'set_zoom', 'set_scroll_ratio'):
        monkeypatch.setattr(pdf_dock, name, lambda *a: saved.append(a))
    monkeypatch.setattr(pdf_dock, 'show_pdf_in_dock', lambda *a, **kw: opened.append((a, kw)))
    pdf_dock._handle_pdf_js_message('incremento_pdf_nav:42:8')
    pdf_dock._handle_pdf_js_message('incremento_pdf_zoom:42:1.5')
    pdf_dock._handle_pdf_js_message('incremento_pdf_scroll:' + json.dumps({'cardId': 42, 'scrollRatio': .6}))
    pdf_dock._reload_current_pdf_annotations({'reader_path': '/unused/prepared.pdf'})
    assert opened[0][0][:4] == (42, 'book.pdf', 8, 1.5)
    assert opened[0][1]['scroll_ratio_override'] == .6
    assert opened[0][1]['page_y_override'] is None
    assert saved == []


@pytest.mark.parametrize('focus_on,modal,popup,expected', [
    ('primary', False, False, 'primary'), ('reference', False, False, 'reference'),
    ('editor', False, False, None), ('primary', True, False, None),
    ('reference', False, True, None),
])
def test_pdf_extraction_shortcuts_only_target_the_focused_reader(monkeypatch, focus_on, modal, popup, expected):
    focus = object()
    primary = types.SimpleNamespace(isAncestorOf=lambda widget: focus_on == 'primary')
    reference = types.SimpleNamespace(view=object())
    monkeypatch.setattr(pdf_dock, 'QApplication', types.SimpleNamespace(
        activeModalWidget=lambda: object() if modal else None,
        activePopupWidget=lambda: object() if popup else None, focusWidget=lambda: focus))
    monkeypatch.setitem(sys.modules, 'pdf_reference_workspace', types.SimpleNamespace(
        focused_reference=lambda: reference if focus_on == 'reference' else None))
    monkeypatch.setattr(pdf_dock, '_pdf_dock', types.SimpleNamespace(_view=primary, isVisible=lambda: True))
    actual = pdf_dock._focused_pdf_extraction_view()
    assert actual is {'primary': primary, 'reference': reference.view, None: None}[expected]


def test_contents_popup_targets_and_saved_places_are_bound_to_the_current_pdf_and_profile(monkeypatch):
    scripts, saved, popups = [], [], []
    active_profile = ["A"]
    page = types.SimpleNamespace(_bridge_nonce="one", runJavaScript=scripts.append)
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: page), isVisible=lambda: True)

    class Popup:
        def __init__(self, parent, **options):
            self.options = options
            popups.append(self)
        def show_at(self, anchor):
            pass

    monkeypatch.setitem(sys.modules, "reader_contents_popup", types.SimpleNamespace(ReaderContentsPopup=Popup))
    monkeypatch.setattr(pdf_dock, "_pdf_dock", dock)
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: active_profile[0])
    monkeypatch.setattr(pdf_dock, "_pdf_bookmarks_payload", lambda cid: [])
    monkeypatch.setattr(pdf_dock, "_push_pdf_bookmarks", lambda cid: None)
    monkeypatch.setattr(pdf_dock, "tooltip", lambda text: None)
    monkeypatch.setattr(pdf_dock, "add_reader_bookmark", lambda *args, **kwargs: saved.append((args, kwargs)))
    payload = {"cardId": 42, "totalPages": 20, "token": 3, "location": {"page": 2, "scrollRatio": .625},
               "entries": [{"title": "Chapter", "page": 10, "id": 0}, {"title": "Invalid", "page": 21}]}
    assert pdf_dock._open_pdf_contents(payload)
    options = popups[0].options
    assert options["entries"] == [{"title": "Chapter", "depth": 0, "page": 10, "id": 0}]
    options["open_entry"](options["entries"][0])
    assert 'incrementoPdfContentsJump' in scripts[0]
    options["save_place"]("Contents page")
    assert saved[0][0][1:5] == ("A", 42, "pdf", {"page": 2, "scroll_ratio": .625})
    assert saved[0][1] == {"label": "Contents page", "replace_label": True}
    active_profile[0] = "B"
    options["open_entry"](options["entries"][0])
    options["save_place"]("Wrong profile")
    assert len(scripts) == len(saved) == 1


@pytest.mark.parametrize("changes", [
    {"cardId": 99}, {"totalPages": 0}, {"token": -1},
    {"location": {"page": 21, "scrollRatio": .5}},
    {"location": {"page": 1, "scrollRatio": float("nan")}},
])
def test_invalid_contents_bridge_request_cannot_open_a_popup(monkeypatch, changes):
    monkeypatch.setattr(pdf_dock, "_pdf_dock", object())
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    payload = {"cardId": 42, "totalPages": 20, "token": 3, "location": {"page": 2, "scrollRatio": .5}}
    assert not pdf_dock._open_pdf_contents({**payload, **changes})

_dependency_names = (
    "session", "PyQt6", "PyQt6.QtPdf", "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebEngineCore", "PyQt6.QtCore",
)
_original_dependencies = {name: sys.modules.get(name) for name in _dependency_names}
try:
    for _name in _dependency_names:
        sys.modules.setdefault(_name, MagicMock())
    import aqt

    import pdf_dock
    from pdf_highlight_bulk_dialog import (
        can_create_pdf_highlight_bulk_rows,
        normalize_pdf_highlight_bulk_row,
        remap_pdf_highlight_bulk_row_fields,
    )
finally:
    # These stubs belong to the PDF import only. In particular, leaving the
    # WebEngine stub installed turns EPUB's page subclass into a MagicMock.
    for _name, _original in _original_dependencies.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def test_due_review_details_escape_card_content():
    rendered = pdf_dock._pdf_due_review_details_html(
        [
            {
                "card_id": 7,
                "page": 3,
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


def test_pdf_extract_renders_emphasis_and_paragraphs_without_trusting_markup():
    payload = {
        "text": "The goal: The goal explains why.\n\nThe process: <img src=x>",
        "runs": [
            {"text": "The goal:", "bold": True},
            {"text": " The ", "bold": False},
            {"text": "goal", "italic": True},
            {"text": " explains why.\n\n"},
            {"text": "The process:", "bold": True},
            {"text": " <img src=x>"},
        ],
    }

    assert pdf_dock._pdf_extract_html(payload) == (
        "<strong>The goal:</strong> The <em>goal</em> explains why.<br><br>"
        "<strong>The process:</strong> &lt;img src=x&gt;"
    )


def test_pdf_extract_rejects_mismatched_formatting_payload():
    assert pdf_dock._pdf_extract_html({
        "text": "Safe text",
        "runs": [{"text": "<script>unsafe</script>", "bold": True}],
    }) == "Safe text"


def test_pdf_extract_bridge_fills_field_with_safe_rich_html(monkeypatch):
    fills = []
    monkeypatch.setattr(
        pdf_dock,
        "_cb_fill_dock_field",
        lambda idx, html, **options: fills.append((idx, html, options)),
    )

    pdf_dock._handle_pdf_js_message(pdf_dock._MSG_FILL_FIELD + json.dumps({
        "idx": 0,
        "text": "The goal: <unsafe>",
        "runs": [
            {"text": "The goal:", "bold": True, "italic": False},
            {"text": " <unsafe>", "bold": False, "italic": False},
        ],
    }))

    assert fills == [(0, "<strong>The goal:</strong> &lt;unsafe&gt;", {"mark_topic": True})]


@pytest.mark.parametrize("field_index", [0, 3])
def test_pdf_shortcut_marks_extracted_note_as_topic_immediately(monkeypatch, field_index):
    fills = []
    monkeypatch.setattr(
        pdf_dock,
        "_cb_fill_dock_field",
        lambda idx, html, **options: fills.append((idx, html, options)),
    )

    pdf_dock._handle_pdf_js_message(pdf_dock._MSG_FILL_FIELD + json.dumps({
        "idx": field_index,
        "text": "Selected passage",
    }))

    assert fills == [(field_index, "Selected passage", {"mark_topic": True})]


def test_pdf_command_one_fallback_marks_extracted_note_as_topic_immediately(monkeypatch):
    fills = []
    monkeypatch.setattr(
        pdf_dock,
        "_cb_fill_dock_field",
        lambda idx, html, **options: fills.append((idx, html, options)),
    )
    monkeypatch.setattr(pdf_dock.QTimer, "singleShot", lambda _delay, callback: callback())

    pdf_dock._handle_pdf_js_message(pdf_dock._MSG_CMD1 + "Selected passage")

    assert fills == [(0, "Selected passage", {"mark_topic": True})]


def test_pdf_citation_excerpt_does_not_add_spaces_at_emphasis_boundaries():
    assert pdf_dock._normalize_pdf_reference_excerpt(
        "<strong>The</strong>goal<br><em>matters</em>."
    ) == "Thegoal matters."


def test_pdf_limit_summary_uses_translated_mode_code(monkeypatch):
    messages = {
        "reader_pdf_limit_summary": "Danas: {used}/{limit} stranica, preostaje {remaining}. Način: {mode}.",
        "reader_limit_hard_stop": "Strogo zaustavljanje",
    }
    monkeypatch.setattr(pdf_dock, "t", lambda key, **values: messages[key].format(**values), raising=False)

    summary = pdf_dock._pdf_limit_summary_text({
        "enabled": True, "daily_page_limit": 10, "pages_used": 7,
        "pages_remaining": 3, "enforcement_mode": "hard_stop",
    })

    assert summary == "Danas: 7/10 stranica, preostaje 3. Način: Strogo zaustavljanje."


def test_missing_pdf_screen_uses_selected_language_and_escapes_filename(monkeypatch):
    monkeypatch.setattr(pdf_dock, "get_locale", lambda: "zh-Hans")
    monkeypatch.setattr(pdf_dock, "t", lambda key, **_values: {
        "reader_pdf_missing_title": "PDF 文件丢失",
    }.get(key, key), raising=False)

    html = pdf_dock._missing_pdf_html("<x>.pdf", "/tmp/<x>.pdf")

    assert '<html lang="zh-Hans">' in html
    assert "PDF 文件丢失" in html
    assert "&lt;x&gt;.pdf" in html
    assert "<x>.pdf" not in html


def test_pdf_bridge_rejects_static_prefix_and_stale_card(monkeypatch):
    messages = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(
        pdf_dock,
        "_handle_pdf_js_message",
        lambda message: messages.append(message),
    )
    page = types.SimpleNamespace(
        _bridge_nonce="private-token",
        _bridge_card_id=42,
    )

    pdf_dock._dispatch_pdf_bridge_message(
        page,
        pdf_dock._PYCMD_BRIDGE + pdf_dock._MSG_OPEN_ADD_CARD,
    )
    page._bridge_card_id = 99
    pdf_dock._dispatch_pdf_bridge_message(
        page,
        pdf_dock._PYCMD_BRIDGE + "private-token:" + pdf_dock._MSG_OPEN_ADD_CARD,
    )
    assert messages == []

    page._bridge_card_id = 42
    pdf_dock._dispatch_pdf_bridge_message(
        page,
        pdf_dock._PYCMD_BRIDGE + "private-token:" + pdf_dock._MSG_OPEN_ADD_CARD,
    )
    assert messages == [pdf_dock._MSG_OPEN_ADD_CARD]


def test_pdf_appearance_policy_uses_saved_mode_unless_force_is_enabled():
    assert pdf_dock.resolve_pdf_appearance_mode(
        "night",
        {"pdf_default_appearance": "dark", "pdf_force_default_appearance": False},
    ) == "night"
    assert pdf_dock.resolve_pdf_appearance_mode(
        None,
        {"pdf_default_appearance": "dark", "pdf_force_default_appearance": False},
    ) == "dark"
    assert pdf_dock.resolve_pdf_appearance_mode(
        "night",
        {"pdf_default_appearance": "original", "pdf_force_default_appearance": True},
    ) == "original"


def test_pdf_snapshot_remembered_field_resolves_by_note_type_and_name():
    config = {
        "pdf_snapshot_auto_field_enabled": True,
        "pdf_snapshot_auto_fields": {"Basic": "Back"},
    }

    assert pdf_dock.resolve_pdf_snapshot_field_index(
        "Basic", ["Front", "Back"], config
    ) == 1
    assert pdf_dock.resolve_pdf_snapshot_field_index(
        "Cloze", ["Text", "Back"], config
    ) == -1
    assert pdf_dock.resolve_pdf_snapshot_field_index(
        "Basic", ["Front", "Extra"], config
    ) == -1
    assert pdf_dock.resolve_pdf_snapshot_field_index(
        "Basic",
        ["Front", "Back"],
        {**config, "pdf_snapshot_auto_field_enabled": False},
    ) == -1
    assert pdf_dock.resolve_pdf_snapshot_field_index(
        "Basic",
        ["Front", "Back"],
        {**config, "pdf_snapshot_auto_field_enabled": "false"},
    ) == -1


def test_remember_pdf_snapshot_field_preserves_other_config(monkeypatch):
    saved = []
    monkeypatch.setattr(
        pdf_dock,
        "_config",
        lambda config=None: {
            "future_setting": {"keep": True},
            "pdf_snapshot_auto_fields": {"Cloze": "Text"},
        },
    )
    monkeypatch.setattr(
        pdf_dock,
        "save_addon_config",
        lambda manager, package, config: saved.append(dict(config)),
    )

    pdf_dock._remember_pdf_snapshot_field("Basic", "Back")

    assert saved == [
        {
            "future_setting": {"keep": True},
            "pdf_snapshot_auto_field_enabled": True,
            "pdf_snapshot_auto_fields": {"Cloze": "Text", "Basic": "Back"},
        }
    ]


def test_pdf_snapshot_selection_skips_picker_for_valid_remembered_field(monkeypatch):
    monkeypatch.setattr(
        pdf_dock,
        "resolve_pdf_snapshot_field_index",
        lambda note_type_name, field_names, config=None: 1,
    )
    monkeypatch.setattr(
        pdf_dock,
        "_show_pdf_snapshot_field_picker",
        lambda *args, **kwargs: pytest.fail("remembered field should skip the picker"),
        raising=False,
    )

    assert pdf_dock._select_pdf_snapshot_field(
        "Basic", ["Front", "Back"], object()
    ) == 1


def test_pdf_snapshot_selection_remembers_checked_picker_choice(monkeypatch):
    remembered = []
    monkeypatch.setattr(
        pdf_dock,
        "resolve_pdf_snapshot_field_index",
        lambda note_type_name, field_names, config=None: -1,
    )
    monkeypatch.setattr(
        pdf_dock,
        "_show_pdf_snapshot_field_picker",
        lambda field_names, preview: (1, True),
        raising=False,
    )
    monkeypatch.setattr(
        pdf_dock,
        "_remember_pdf_snapshot_field",
        lambda note_type_name, field_name: remembered.append(
            (note_type_name, field_name)
        ),
        raising=False,
    )

    assert pdf_dock._select_pdf_snapshot_field(
        "Basic", ["Front", "Back"], object()
    ) == 1
    assert remembered == [("Basic", "Back")]


def test_pdf_snapshot_field_context_keeps_note_type_and_field_names(monkeypatch):
    note = types.SimpleNamespace(
        note_type=lambda: {
            "name": "Basic",
            "flds": [{"name": "Front"}, {"name": "Back"}],
        }
    )
    dock = types.SimpleNamespace(
        widget=lambda: types.SimpleNamespace(
            editor=types.SimpleNamespace(note=note),
        )
    )
    monkeypatch.setattr(pdf_dock, "_cb_get_add_card_dock", lambda: dock)

    assert pdf_dock._pdf_snapshot_add_card_fields() == (
        "Basic",
        ["Front", "Back"],
    )


def test_pdf_snapshot_picker_places_remember_checkbox_with_field_buttons(monkeypatch):
    checkbox = MagicMock()
    checkbox_type = MagicMock(return_value=checkbox)
    dialog = MagicMock()
    dialog.exec.return_value = False
    monkeypatch.setattr(pdf_dock, "QDialog", MagicMock(return_value=dialog))
    monkeypatch.setattr(pdf_dock, "QVBoxLayout", MagicMock())
    monkeypatch.setattr(pdf_dock, "QLabel", MagicMock())
    monkeypatch.setattr(pdf_dock, "QPushButton", MagicMock())
    monkeypatch.setattr(pdf_dock, "QCheckBox", checkbox_type)
    monkeypatch.setattr(pdf_dock, "t", lambda key, **values: key)

    assert pdf_dock._show_pdf_snapshot_field_picker(
        ["Front", "Back"], MagicMock()
    ) == (-1, False)
    checkbox_type.assert_called_once_with("reader_always_use_snapshot_field")
    checkbox.setAccessibleName.assert_called_once_with(
        "reader_always_use_snapshot_field"
    )


def test_pdf_snapshot_scan_uses_the_original_crop_instead_of_the_small_preview(monkeypatch):
    actions = []
    dialog = MagicMock()
    dialog.exec.return_value = False
    for name in ("QVBoxLayout", "QLabel", "QPushButton", "QCheckBox"):
        monkeypatch.setattr(pdf_dock, name, MagicMock())
    monkeypatch.setattr(pdf_dock, "QDialog", MagicMock(return_value=dialog))
    monkeypatch.setattr(pdf_dock, "add_snapshot_math_action", lambda *args, **kw: actions.append((args, kw)), raising=False)
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    image = MagicMock()
    pdf_dock._show_pdf_snapshot_field_picker(["Front"], image)
    assert len(actions) == 1
    assert actions[0][0][0] is dialog
    assert actions[0][0][2] is image
    assert actions[0][1]["is_current"]()
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 43)
    assert not actions[0][1]["is_current"]()


def test_current_pdf_appearance_re_resolves_after_settings_change(monkeypatch):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        pdf_dock,
        "get_pdf_appearance_mode",
        lambda addon_dir, profile, card_id: "night",
    )

    assert pdf_dock.resolved_current_pdf_appearance(
        {"pdf_default_appearance": "dark", "pdf_force_default_appearance": False}
    ) == "night"
    assert pdf_dock.resolved_current_pdf_appearance(
        {"pdf_default_appearance": "dark", "pdf_force_default_appearance": True}
    ) == "dark"


@pytest.mark.parametrize('payload,expected', [
    ({'cardId': 42, 'enabled': True}, [True]),
    ({'cardId': 42, 'enabled': False}, [False]),
    ({'cardId': 99, 'enabled': True}, []),
    ({'cardId': '42', 'enabled': True}, []),
    ({'cardId': 42, 'enabled': 'false'}, []),
    ({'cardId': 42, 'enabled': 1}, []),
    ({'cardId': 42}, []),
    ([], []),
    (None, []),
])
def test_pdf_focus_toolbar_bridge_only_changes_current_pdf(monkeypatch, payload, expected):
    requested = []
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, '_pdf_dock', types.SimpleNamespace(
        _pdf_focus_mode=types.SimpleNamespace(request_enabled=requested.append)))
    page = types.SimpleNamespace(_bridge_nonce='test-token', _bridge_card_id=42)
    message = 'incremento_pdf_focus:' + json.dumps(payload)
    pdf_dock._dispatch_pdf_bridge_message(page, pdf_dock._PYCMD_BRIDGE + 'wrong:' + message)
    assert requested == [], 'An unauthenticated message must not change layout or preference'
    pdf_dock._dispatch_pdf_bridge_message(page, pdf_dock._PYCMD_BRIDGE + 'test-token:' + message)
    assert requested == expected


def test_pdf_appearance_bridge_saves_only_for_current_card(monkeypatch):
    saved = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        pdf_dock,
        "set_pdf_appearance_mode",
        lambda addon_dir, profile, card_id, mode: saved.append(
            (addon_dir, profile, card_id, mode)
        ),
    )

    pdf_dock._handle_pdf_js_message(
        pdf_dock._MSG_APPEARANCE + json.dumps({"cardId": 99, "mode": "night"})
    )
    pdf_dock._handle_pdf_js_message(
        pdf_dock._MSG_APPEARANCE + json.dumps({"cardId": 42, "mode": "sepia"})
    )
    pdf_dock._handle_pdf_js_message(
        pdf_dock._MSG_APPEARANCE + json.dumps({"cardId": 42, "mode": "dark"})
    )

    assert saved == [(pdf_dock._ADDON_DIR, "TestProfile", 42, "dark")]


def test_pdf_link_preview_zoom_bridge_persists_only_current_profile_and_card(monkeypatch):
    from copy import deepcopy
    config = {"pdf_link_preview_zoom_by_profile": {"Other profile": 1.75}, "future_key": True}
    saved = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "_config", lambda config=None: deepcopy(configured))
    configured = config
    monkeypatch.setattr(pdf_dock, "save_addon_config", lambda manager, package, value: saved.append(deepcopy(value)))
    for payload in [{"cardId": 99, "zoom": 2.5}, {"cardId": 42, "zoom": None},
                    {"cardId": 42, "zoom": True}, {"cardId": 42, "zoom": 99},
                    {"cardId": 42, "zoom": "2.5"}, {"cardId": 42, "zoom": float("nan")},
                    {"cardId": 42, "zoom": 2.5}]:
        pdf_dock._handle_pdf_js_message("incremento_pdf_link_preview_zoom:" + json.dumps(payload))
    assert saved == [{"pdf_link_preview_zoom_by_profile": {"Other profile": 1.75, "TestProfile": 2.5},
                      "future_key": True}]
    assert config == {"pdf_link_preview_zoom_by_profile": {"Other profile": 1.75}, "future_key": True}


def test_pdf_request_boundary_allows_only_viewer_assets_and_active_pdf(tmp_path):
    viewer_root = tmp_path / "web"
    viewer_root.mkdir()
    active_pdf = tmp_path / "profile" / "active.pdf"
    active_pdf.parent.mkdir()
    active_pdf.touch()
    def _url(path):
        return types.SimpleNamespace(scheme=lambda: "file", toLocalFile=lambda: str(path))

    assert pdf_dock._pdf_request_url_is_allowed(
        viewer_root, active_pdf, _url(viewer_root / "pdfjs" / "pdf.min.js")
    )
    assert pdf_dock._pdf_request_url_is_allowed(viewer_root, active_pdf, _url(active_pdf))
    assert not pdf_dock._pdf_request_url_is_allowed(
        viewer_root, active_pdf, _url(tmp_path / "profile" / "other.pdf")
    )
    assert not pdf_dock._pdf_request_url_is_allowed(
        viewer_root,
        active_pdf,
        types.SimpleNamespace(
            scheme=lambda: "https",
            toLocalFile=lambda: "",
        ),
    )


def test_pdf_main_frame_boundary_rejects_data_and_other_documents(tmp_path):
    viewer = tmp_path / "web" / "pdf_dock.html"
    viewer.parent.mkdir()
    viewer.touch()

    def _url(scheme, path=""):
        return types.SimpleNamespace(scheme=lambda: scheme, toLocalFile=lambda: str(path))

    assert pdf_dock._pdf_main_frame_url_is_allowed(
        str(viewer), _url("file", viewer)
    )
    assert pdf_dock._pdf_main_frame_url_is_allowed(str(viewer), _url("about"))
    assert not pdf_dock._pdf_main_frame_url_is_allowed(str(viewer), _url("data"))
    assert not pdf_dock._pdf_main_frame_url_is_allowed(
        str(viewer), _url("file", tmp_path / "other.html")
    )


def test_pdf_viewer_disables_eval_and_declares_csp():
    addon_root = Path(pdf_dock.__file__).resolve().parent.parent
    hook_source = (addon_root / "frontend" / "src" / "usePdfRender.js").read_text(
        encoding="utf-8"
    )
    html = (addon_root / "web" / "pdf_dock.html").read_text(encoding="utf-8")

    assert "isEvalSupported: false" in hook_source
    assert "Content-Security-Policy" in html
    assert "object-src 'none'" in html


def test_main_reader_byte_ranges_are_dispatched_only_after_nonce_and_card_checks(monkeypatch):
    ranges, global_commands = [], []
    page = types.SimpleNamespace(_bridge_nonce='current-nonce', _bridge_card_id=42,
        _range_bridge=types.SimpleNamespace(handle=lambda command: ranges.append(command) or True))
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, '_handle_pdf_js_message', global_commands.append)
    message = 'incremento_pdf_range:{"cardId":42}'
    pdf_dock._dispatch_pdf_bridge_message(page, pdf_dock._PYCMD_BRIDGE + 'stale:' + message)
    assert ranges == []
    pdf_dock._dispatch_pdf_bridge_message(page, pdf_dock._PYCMD_BRIDGE + 'current-nonce:' + message)
    assert ranges == [message] and global_commands == []
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 43)
    pdf_dock._dispatch_pdf_bridge_message(page, pdf_dock._PYCMD_BRIDGE + 'current-nonce:' + message)
    assert ranges == [message]


def test_pdf_viewer_exposes_opt_in_annotation_links():
    addon_root = Path(pdf_dock.__file__).resolve().parent.parent
    hook_source = (addon_root / "frontend" / "src" / "usePdfRender.js").read_text(
        encoding="utf-8"
    )
    viewer_source = (addon_root / "frontend" / "src" / "PdfViewer.jsx").read_text(
        encoding="utf-8"
    )

    assert "getAnnotations({ intent: 'display' })" in hook_source
    assert "resolvePdfAnnotationLink" in hook_source
    assert 'tr("reader_links_enable")' in viewer_source
    assert "incremento_pdf_open_link:" in viewer_source


def test_pdf_link_toggle_has_adjacent_jump_back_control():
    addon_root = Path(pdf_dock.__file__).resolve().parent.parent
    viewer_source = (addon_root / "frontend" / "src" / "PdfViewer.jsx").read_text(
        encoding="utf-8"
    )

    assert viewer_source.count("tr('reader_jump_back')") >= 2
    assert "jumpBackFromPdfLink" in viewer_source
    assert "setLinkBackHistory([])" in viewer_source


def test_pdf_reader_exposes_right_click_anchor_and_native_context_menu():
    addon_root = Path(pdf_dock.__file__).resolve().parent.parent
    viewer_source = (addon_root / "frontend" / "src" / "PdfViewer.jsx").read_text(
        encoding="utf-8"
    )
    dock_source = (addon_root / "frontend" / "pdf_dock.py").read_text(encoding="utf-8")

    assert "incrementoPdfAnchorAtPoint" in viewer_source
    assert "customContextMenuRequested" in dock_source
    assert 't("reader_copy_link_to_place")' in dock_source


def test_pdf_pending_start_keeps_read_anchor_arguments_aligned():
    addon_root = Path(pdf_dock.__file__).resolve().parent.parent
    viewer_source = (addon_root / "frontend" / "src" / "PdfViewer.jsx").read_text(
        encoding="utf-8"
    )

    assert "pending.readPage || 0,\n        pending.readAnchor || null," in viewer_source
    assert "pending.readPage || 0,\n        pending.readPage || 0," not in viewer_source


def test_pdf_external_link_bridge_requires_current_card(monkeypatch):
    opened = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 42)
    monkeypatch.setattr(
        pdf_dock,
        "open_external_reader_link",
        lambda url: opened.append(url) or True,
    )

    for card_id in (99, 42):
        pdf_dock._handle_pdf_js_message(
            pdf_dock._MSG_OPEN_LINK
            + '{"cardId":%d,"url":"https://example.test/docs"}' % card_id
        )

    assert opened == ["https://example.test/docs"]


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


@pytest.mark.parametrize("sort_column,sort_backwards", [
    ("noteFld", False),
    ("noteFld", True),
    ("noteCrt", True),
])
def test_open_all_pdf_cards_in_browser_sorts_by_created_oldest_first(
    monkeypatch, sort_column, sort_backwards
):
    searches, indicators = [], []
    state = types.SimpleNamespace(sort_column=sort_column, sort_backwards=sort_backwards)
    table = types.SimpleNamespace(
        _state=state,
        _set_sort_indicator=lambda: indicators.append((state.sort_column, state.sort_backwards)),
    )
    browser = types.SimpleNamespace(
        table=table,
        search_for=lambda query: searches.append((query, state.sort_column, state.sort_backwards)),
    )
    fake_dialogs = types.SimpleNamespace(open=lambda name, parent: browser)
    monkeypatch.setattr(aqt, "dialogs", fake_dialogs, raising=False)
    monkeypatch.setattr(
        pdf_dock, "_live_pdf_document_source_note_ids", lambda card_id: [30, 10, 20, 10]
    )

    pdf_dock._open_all_pdf_cards_in_browser(42)

    # The Browser applies its own sort: ordering the nid terms alone cannot
    # override an existing alphabetical or newest-first Browser preference.
    assert searches == [("nid:30 OR nid:10 OR nid:20", "noteCrt", False)]
    assert indicators == [("noteCrt", False)]


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


@pytest.mark.parametrize("title, escaped_title", [
    (
        "A Practical Guide to Incremental Reading",
        "A Practical Guide to Incremental Reading",
    ),
    (
        'A webpage title longer than the filename display limit — Čitanje & "Guide" <2026> [2]',
        'A webpage title longer than the filename display limit — Čitanje &amp; &quot;Guide&quot; &lt;2026&gt; [2]',
    ),
], ids=["webpage-title", "full-title-with-special-characters"])
def test_webpage_pdf_extract_and_copied_link_use_full_saved_title(monkeypatch, title, escaped_title):
    from reader_links import reader_anchor_command_from_html

    filename = "incremento-webpage-fdbswq4-0123456789abcdef0123456789abcdef.pdf"
    note = {"Title": title, "PDF_Filename": filename}
    collection = types.SimpleNamespace(
        get_card={55: types.SimpleNamespace(nid=9)}.__getitem__,
        get_note={9: note}.__getitem__,
    )
    copied = []
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=collection))
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", filename)
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", ())
    monkeypatch.setattr(pdf_dock, "_config", lambda config=None: {})
    monkeypatch.setattr(pdf_dock, "set_reader_anchor_clipboard", lambda html, plain: copied.append((html, plain)) or True)
    monkeypatch.setattr(pdf_dock, "tooltip", lambda _text: None)

    citation = pdf_dock.pdf_citation("An extracted paragraph", page=1)
    assert pdf_dock._copy_pdf_context_anchor({"cardId": 55, "page": 1, "scrollRatio": 0.25})

    assert f">Page 1. of {escaped_title}</a>" in citation
    assert f">Page 1. of {escaped_title}</a>" in copied[0][0]
    assert copied[0][1] == f"{title} — page 1"
    command = reader_anchor_command_from_html(citation)
    assert json.loads(command.removeprefix("incremento_open_pdf_ref:")) == {
        "card_id": 55, "filename": filename, "page": 1, "excerpt": "An extracted paragraph",
    }


@pytest.mark.parametrize("note", [{}, {"Title": ""}, {"Title": "  "}, None],
                         ids=["missing-title", "empty-title", "blank-title", "missing-note"])
def test_pdf_citation_uses_readable_filename_when_saved_title_is_unavailable(monkeypatch, note):
    collection = types.SimpleNamespace(
        get_card={55: types.SimpleNamespace(nid=9)}.__getitem__,
        get_note={9: note}.__getitem__,
    )
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=collection))
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "Writer_Guide-0123456789abcdef0123456789abcdef.pdf")
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", ())
    monkeypatch.setattr(pdf_dock, "_config", lambda config=None: {})

    assert ">Page 1. of Writer Guide</a>" in pdf_dock.pdf_citation(page=1)


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


def test_pdf_citation_can_embed_an_exact_scroll_anchor(monkeypatch):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer-guide.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda filename: "Writer Guide")

    html = pdf_dock.pdf_citation(page=42, scroll_ratio=0.625)

    assert "Page 42. of Writer Guide" in html
    assert "scroll_ratio\\&quot;: 0.625" in html


@pytest.mark.parametrize("mode, display_page", [
    ("printed", "v"), ("pdf", "7"), ("both", "v (PDF 7)"),
])
def test_extraction_and_copy_use_configured_numbering_from_current_pdf_metadata(monkeypatch, mode, display_page):
    from reader_links import reader_anchor_command_from_html

    copied = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", (), raising=False)
    monkeypatch.setattr(pdf_dock, "_config", lambda config=None: {"pdf_citation_page_numbering": mode})
    monkeypatch.setattr(pdf_dock, "get_page", lambda *args: 7)
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda *args, **kwargs: "Physics")
    monkeypatch.setattr(pdf_dock, "set_reader_anchor_clipboard", lambda html, plain: copied.append((html, plain)) or True)
    monkeypatch.setattr(pdf_dock, "tooltip", lambda _text: None)
    payload = {"cardId": 55, "filename": "physics.pdf", "labels": ["", "", "i", "ii", "iii", "iv", "v"]}
    bridge = types.SimpleNamespace(_bridge_nonce="private", _bridge_card_id=55)

    pdf_dock._dispatch_pdf_bridge_message(
        bridge, pdf_dock._PYCMD_BRIDGE + "private:incremento_pdf_page_labels:" + json.dumps(payload),
    )
    html = pdf_dock.pdf_citation("An extracted paragraph")
    assert pdf_dock._copy_pdf_context_anchor({"cardId": 55, "page": 7, "scrollRatio": 0.25})

    assert f">Page {display_page}. of Physics</a>" in html
    assert f">Page {display_page}. of Physics</a>" in copied[0][0]
    assert copied[0][1] == f"Physics — page {display_page}"
    command = reader_anchor_command_from_html(html)
    assert json.loads(command.removeprefix("incremento_open_pdf_ref:"))["page"] == 7


def test_bulk_highlight_extraction_uses_each_highlights_printed_page(monkeypatch):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", ("i", "ii", "iii"), raising=False)
    monkeypatch.setattr(pdf_dock, "_config", lambda config=None: {})
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda *args, **kwargs: "Physics")
    monkeypatch.setattr(pdf_dock, "_add_card_dock_module", lambda: types.SimpleNamespace(should_add_extract_source_link=lambda kind: True))
    monkeypatch.setattr(pdf_dock, "pdf_reference_html_for_citation", lambda *args: "")

    html = pdf_dock._pdf_highlight_bulk_generated_text({"text": "Excerpt", "page": 2, "id": "h2"})

    assert ">Page ii. of Physics</a>" in html
    assert "Excerpt<br>" in html


@pytest.mark.parametrize("payload", [
    {"cardId": 99, "filename": "physics.pdf", "labels": ["v"]},
    {"cardId": 55, "filename": "other.pdf", "labels": ["v"]},
    {"cardId": 55, "filename": "physics.pdf", "labels": "v"},
    {"cardId": 55, "filename": "physics.pdf", "labels": [7]},
    {"cardId": 55, "filename": "physics.pdf", "labels": ["v\x00"]},
    {"cardId": 55, "filename": "physics.pdf", "labels": ["x" * 129]},
], ids=["stale-card", "stale-file", "wrong-shape", "not-text", "control", "long-label"])
def test_pdf_page_label_bridge_rejects_stale_or_malformed_metadata(monkeypatch, payload):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", ("i",), raising=False)

    pdf_dock._handle_pdf_js_message("incremento_pdf_page_labels:" + json.dumps(payload))

    assert pdf_dock._current_pdf_page_labels == ("i",)


@pytest.mark.parametrize("labels", [[], [""] * 20_001, ["x" * 128] * 10_000], ids=["empty", "too-many-pages", "message-budget"])
def test_pdf_page_label_bridge_rejects_oversized_or_empty_metadata(monkeypatch, labels):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", ("i",))

    pdf_dock._handle_pdf_js_message("incremento_pdf_page_labels:" + json.dumps({
        "cardId": 55, "filename": "physics.pdf", "labels": labels,
    }))

    assert pdf_dock._current_pdf_page_labels == ("i",)


@pytest.mark.parametrize("mode", ["printed", "pdf", "both"])
def test_pdf_citation_falls_back_to_pdf_page_when_printed_label_is_missing(monkeypatch, mode):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", ("",))
    monkeypatch.setattr(pdf_dock, "_config", lambda config=None: {"pdf_citation_page_numbering": mode})
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda *args, **kwargs: "Physics")

    assert ">Page 1. of Physics</a>" in pdf_dock.pdf_citation(page=1)


def test_clearing_pdf_context_discards_printed_labels(monkeypatch):
    for name in ("_current_pdf_filename", "_current_pdf_search_query", "_current_pdf_search_hits",
                 "_current_pdf_search_hit_index", "_pdf_via_link", "_pdf_preserve_history",
                 "_pdf_showing_missing_screen", "_pdf_annotation_generation"):
        monkeypatch.setattr(pdf_dock, name, getattr(pdf_dock, name))
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_page_labels", ("v",), raising=False)

    pdf_dock._clear_current_pdf_context()

    assert pdf_dock._current_pdf_page_labels == ()


def test_pdf_context_html_for_citation_reads_bounded_page_and_configured_rows(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer-guide.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda filename: "Writer Guide")
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "configured_pdf_context_rows", lambda config=None: 2)
    monkeypatch.setattr(
        pdf_dock,
        "_pdf_page_text",
        lambda addon_dir, profile, card_id, page, max_chars=None: (
            calls.append((addon_dir, profile, card_id, page, max_chars))
            or "\n".join(f"row {number}" for number in range(1, 13))
        ),
    )
    citation = pdf_dock.pdf_citation("row 6", page=3)

    context = pdf_dock.pdf_context_html_for_citation(citation, excerpt_text="row 6")

    assert calls == [("/tmp/addon", "TestProfile", 55, 3, 250_000)]
    assert 'data-incremento-pdf-context="1"' in context
    assert "row 4" in context and "row 8" in context
    assert "row 3" not in context and "row 9" not in context


def test_pdf_reference_html_for_citation_renders_real_page_snapshot_and_uses_highlight_rects(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer-guide.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda filename: "Writer Guide")
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "configured_pdf_context_rows", lambda config=None: 5)
    monkeypatch.setattr(
        pdf_dock,
        "pdf_storage_abspath",
        lambda filename, profile=None: f"/managed/{profile}/{filename}",
    )
    monkeypatch.setattr(
        pdf_dock,
        "load_highlights",
        lambda addon_dir, profile, card_id: [
            {"id": "hl-7", "page": 3, "rects": [{"x": 1, "y": 2, "w": 3, "h": 4}]}
        ],
    )
    monkeypatch.setattr(
        pdf_dock,
        "render_pdf_context_snapshot",
        lambda path, **kwargs: calls.append((path, kwargs)) or b"png",
    )
    monkeypatch.setattr(
        pdf_dock,
        "add_snapshot_to_anki_media",
        lambda collection, image: "incremento-pdf-context-abc.png",
    )
    monkeypatch.setattr(
        pdf_dock,
        "pdf_snapshot_reference_html",
        lambda excerpt, citation, media, preview_label: (
            f"SNAPSHOT:{excerpt}:{citation}:{media}:{preview_label}"
        ),
    )
    citation = pdf_dock.pdf_citation("Exact excerpt", highlight_id="hl-7", page=3)

    rendered = pdf_dock.pdf_reference_html_for_citation("Exact excerpt", citation)

    assert calls == [
        (
            "/managed/TestProfile/writer-guide.pdf",
            {
                "page_number": 3,
                "excerpt": "Exact excerpt",
                "context_rows": 5,
                "highlight_rects": [{"x": 1, "y": 2, "w": 3, "h": 4}],
            },
        )
    ]
    assert rendered.startswith("SNAPSHOT:Exact excerpt:")
    assert ":incremento-pdf-context-abc.png:" in rendered


def test_pdf_reference_html_for_citation_uses_entire_multiline_selection_for_snapshot(monkeypatch):
    selected = " ".join(f"Selected row {number}." for number in range(1, 35))
    calls = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer-guide.pdf")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(
        pdf_dock,
        "pdf_storage_abspath",
        lambda filename, profile=None: f"/managed/{profile}/{filename}",
    )
    monkeypatch.setattr(
        pdf_dock,
        "render_pdf_context_snapshot",
        lambda path, **kwargs: calls.append(kwargs) or b"png",
    )
    monkeypatch.setattr(
        pdf_dock,
        "add_snapshot_to_anki_media",
        lambda collection, image: "incremento-pdf-context-abc.png",
    )
    citation = pdf_dock.pdf_citation(selected, page=3)

    pdf_dock.pdf_reference_html_for_citation(selected, citation)

    assert len(selected) > 320
    assert calls[0]["excerpt"] == selected


@pytest.mark.parametrize("failure", ["render_empty", "render_error", "media_empty", "media_error"])
def test_pdf_extract_keeps_closed_context_control_when_snapshot_fails(monkeypatch, failure):
    """An optional screenshot failure must not hide available source context."""
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer-guide.pdf")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "configured_pdf_context_rows", lambda: 1)
    monkeypatch.setattr(pdf_dock, "pdf_storage_abspath", lambda *args, **kwargs: "/managed/source.pdf")
    page_reads = []
    monkeypatch.setattr(
        pdf_dock,
        "_pdf_page_text",
        lambda addon_dir, profile, card_id, page, max_chars=None: (
            page_reads.append((profile, card_id, page, max_chars))
            or "Outside before\nBefore <script>unsafe()</script>\nExact excerpt\nAfter context\nOutside after"
        ),
    )

    def render(*args, **kwargs):
        if failure == "render_error":
            raise RuntimeError("optional renderer unavailable")
        return b"" if failure == "render_empty" else b"png"

    def store(collection, image):
        if failure == "media_error":
            raise RuntimeError("media unavailable")
        return ""

    monkeypatch.setattr(pdf_dock, "render_pdf_context_snapshot", render)
    monkeypatch.setattr(pdf_dock, "add_snapshot_to_anki_media", store)
    citation = pdf_dock.pdf_citation("Exact excerpt", page=3)

    rendered = pdf_dock.pdf_reference_html_for_citation("<b>Exact</b> excerpt", citation)

    assert rendered.startswith("<b>Exact</b> excerpt<br>" + citation + "<br>")
    assert '<details' in rendered and '<summary' in rendered
    assert '>Source page preview</summary>' in rendered
    assert ' open' not in rendered
    assert 'data-incremento-pdf-context="1"' in rendered
    assert "Before &lt;script&gt;unsafe()&lt;/script&gt;" in rendered
    assert "After context" in rendered
    assert "Outside before" not in rendered and "Outside after" not in rendered
    assert "<script>" not in rendered and "<img" not in rendered
    assert page_reads == [("TestProfile", 55, 3, 250_000)]


@pytest.mark.parametrize("page_text", ["", "Unrelated page text"])
def test_pdf_extract_without_snapshot_or_matching_context_keeps_citation_fallback(monkeypatch, page_text):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer-guide.pdf")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "pdf_storage_abspath", lambda *args, **kwargs: "/managed/source.pdf")
    monkeypatch.setattr(pdf_dock, "render_pdf_context_snapshot", lambda *args, **kwargs: b"")
    monkeypatch.setattr(pdf_dock, "add_snapshot_to_anki_media", lambda *args: "")
    monkeypatch.setattr(pdf_dock, "_pdf_page_text", lambda *args, **kwargs: page_text)
    citation = pdf_dock.pdf_citation("Exact excerpt", page=3, scroll_ratio=0.5)

    assert pdf_dock.pdf_reference_html_for_citation("Exact excerpt", citation) == ""


def test_pdf_highlight_bulk_generated_text_embeds_mobile_snapshot(monkeypatch):
    monkeypatch.setattr(pdf_dock, "pdf_citation", lambda *args, **kwargs: "Citation")
    monkeypatch.setattr(
        pdf_dock,
        "pdf_reference_html_for_citation",
        lambda excerpt, citation: '<span data-incremento-pdf-snapshot="1">Snapshot</span>',
    )
    monkeypatch.setattr(
        pdf_dock,
        "_add_card_dock_module",
        lambda: types.SimpleNamespace(should_add_extract_source_link=lambda kind: True),
    )

    generated = pdf_dock._pdf_highlight_bulk_generated_text(
        {"id": "hl-1", "page": 3, "text": "Excerpt"}
    )

    assert generated == '<span data-incremento-pdf-snapshot="1">Snapshot</span>'


@pytest.mark.parametrize("locale,citation,plain", [
    ("en", "Page 7. of Writer &amp; Guide", "Writer & Guide — page 7"),
    ("hr", "Stranica 7. iz Writer &amp; Guide", "Writer & Guide — stranica 7"),
    ("zh-Hans", "Writer &amp; Guide，第 7 页", "Writer & Guide — 第 7 页"),
])
def test_pdf_copied_citation_translates_generated_labels_and_preserves_title(monkeypatch, locale, citation, plain):
    from backend.i18n import Translator

    copied = []
    monkeypatch.setattr(pdf_dock, "t", Translator(locale).t)
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "writer-guide.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda *args, **kwargs: "Writer & Guide")
    monkeypatch.setattr(pdf_dock, "set_reader_anchor_clipboard", lambda html, label: copied.append((html, label)) or True)
    monkeypatch.setattr(pdf_dock, "tooltip", lambda _text: None)

    assert pdf_dock._copy_pdf_context_anchor({"cardId": 55, "page": 7, "scrollRatio": 0.25})

    assert citation in copied[0][0]
    assert copied[0][1] == plain
    assert "writer-guide.pdf" in copied[0][0]
    assert "scroll_ratio\\&quot;: 0.25" in copied[0][0]


@pytest.mark.parametrize("page_label", ["v", "551", "A-12"])
def test_copy_pdf_place_uses_printed_label_but_opens_physical_page(monkeypatch, page_label):
    from reader_links import reader_anchor_command_from_html

    copied = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda *args, **kwargs: "Physics")
    monkeypatch.setattr(pdf_dock, "set_reader_anchor_clipboard", lambda html, plain: copied.append((html, plain)) or True)
    monkeypatch.setattr(pdf_dock, "tooltip", lambda _text: None)

    assert pdf_dock._copy_pdf_context_anchor({
        "cardId": 55, "page": 7, "pageLabel": page_label, "scrollRatio": 0.25,
    })

    html, plain = copied[0]
    assert f">Page {page_label}. of Physics</a>" in html
    assert plain == f"Physics — page {page_label}"
    command = reader_anchor_command_from_html(html)
    assert command is not None
    assert json.loads(command.removeprefix("incremento_open_pdf_ref:")) == {
        "card_id": 55, "filename": "physics.pdf", "page": 7, "scroll_ratio": 0.25,
    }


@pytest.mark.parametrize("page_label", [None, "", "  ", 7, True, {}, "v" * 129, "v\x00", "v\n", "v\x7f"])
def test_copy_pdf_place_falls_back_to_physical_page_for_invalid_label(monkeypatch, page_label):
    copied = []
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda *args, **kwargs: "Physics")
    monkeypatch.setattr(pdf_dock, "set_reader_anchor_clipboard", lambda html, plain: copied.append((html, plain)) or True)
    monkeypatch.setattr(pdf_dock, "tooltip", lambda _text: None)

    assert pdf_dock._copy_pdf_context_anchor({
        "cardId": 55, "page": 7, "pageLabel": page_label, "scrollRatio": 0.25,
    })

    assert ">Page 7. of Physics</a>" in copied[0][0]
    assert copied[0][1] == "Physics — page 7"


def test_pdf_citation_escapes_printed_label_without_putting_it_in_navigation(monkeypatch):
    from reader_links import reader_anchor_command_from_html

    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "physics.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_display_label_from_filename", lambda *args, **kwargs: "Physics")

    html = pdf_dock.pdf_citation(page=7, page_label='  <img src=x>&"  ')

    assert ">Page &lt;img src=x&gt;&amp;&quot;. of Physics</a>" in html
    assert "<img" not in html
    command = reader_anchor_command_from_html(html)
    assert command is not None
    assert json.loads(command.removeprefix("incremento_open_pdf_ref:")) == {
        "card_id": 55, "filename": "physics.pdf", "page": 7,
    }


def test_pdf_context_anchor_rejects_stale_cards_and_clamps_scroll_ratio(monkeypatch):
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)

    assert pdf_dock._normalize_pdf_context_anchor(
        {"cardId": 55, "page": "42", "scrollRatio": 1.4}
    ) == {"card_id": 55, "page": 42, "scroll_ratio": 1.0}
    assert pdf_dock._normalize_pdf_context_anchor(
        {"cardId": 99, "page": 42, "scrollRatio": 0.5}
    ) is None
    assert pdf_dock._normalize_pdf_context_anchor(
        {"cardId": 55, "page": 0, "scrollRatio": 0.5}
    ) is None


@pytest.mark.parametrize("changed", ["profile", "card", "filename", "load", "closed", "menu"])
def test_embedded_image_menu_uses_captured_profile_path_and_retires_stale_callbacks(monkeypatch, changed):
    requests, paths = [], []
    profile = ["A"]
    page = types.SimpleNamespace(_bridge_nonce="load-one")
    view = types.SimpleNamespace(page=lambda: page)
    dock = types.SimpleNamespace(_view=view, isVisible=lambda: True)
    menu = types.SimpleNamespace(addAction=lambda text: types.SimpleNamespace(triggered=MagicMock()))
    monkeypatch.setattr(pdf_dock, "_pdf_dock", dock)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: profile[0])
    monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 55)
    monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "selected.pdf")
    monkeypatch.setattr(pdf_dock, "pdf_storage_abspath", lambda filename, *, profile: (
        paths.append((filename, profile)) or "/tmp/selected.pdf"))
    monkeypatch.setitem(sys.modules, "pdf_image_copy", types.SimpleNamespace(
        add_pdf_image_copy_action=lambda menu, **kwargs: requests.append(kwargs)))

    def show_menu(current_view, position, **options):
        current_view._incremento_reader_anchor_context_menu = menu
        options["populate_menu"](menu, {
            "cardId": 55, "page": 7, "scrollRatio": .5,
            "imagePoint": {"x": .25, "y": .5, "filename": "/untrusted.pdf", "page": 999},
        })
        return True

    monkeypatch.setattr(pdf_dock, "show_reader_anchor_context_menu", show_menu)
    assert pdf_dock._show_pdf_reader_context_menu(view, types.SimpleNamespace(x=lambda: 10, y=lambda: 20))
    assert paths == [("selected.pdf", "A")]
    assert requests[0]["pdf_path"] == "/tmp/selected.pdf"
    assert requests[0]["point"]["page"] == 7
    assert requests[0]["is_current"]()

    if changed == "profile":
        profile[0] = "B"
    elif changed == "card":
        monkeypatch.setattr(pdf_dock, "_current_pdf_card_id", 99)
    elif changed == "filename":
        monkeypatch.setattr(pdf_dock, "_current_pdf_filename", "other.pdf")
    elif changed == "load":
        page._bridge_nonce = "load-two"
    elif changed == "closed":
        dock.isVisible = lambda: False
    else:
        del view._incremento_reader_anchor_context_menu
    assert not requests[0]["is_current"]()


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


def test_highlight_payload_batches_links_and_live_notes_without_cross_document_cleanup(monkeypatch, tmp_path):
    import sqlite3
    import db

    root, profile = str(tmp_path), "TestProfile"
    conn = db.get_connection(root, profile)
    conn.executemany("INSERT INTO pdf_highlights(id, card_id, page, text) VALUES(?,88,1,'passage')",
                     ((f"h{i}",) for i in range(1203)))
    conn.executemany("INSERT INTO pdf_card_sources(pdf_card_id,page,note_id,highlight_id) VALUES(88,1,?,?)",
                     ((i + 1, f"h{i}") for i in range(1202)))
    conn.execute("INSERT INTO pdf_card_sources(pdf_card_id,page,note_id,highlight_id) VALUES(99,1,1202,'h1201')")
    conn.commit()
    notes = sqlite3.connect(":memory:")
    notes.execute("CREATE TABLE notes(id INTEGER PRIMARY KEY)")
    notes.executemany("INSERT INTO notes VALUES(?)", ((i + 1,) for i in range(1201)))
    note_queries, queries = [], []

    def note_ids(sql, *args):
        note_queries.append(args)
        return [row[0] for row in notes.execute(sql, args)]

    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", root)
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: profile)
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=types.SimpleNamespace(
        db=types.SimpleNamespace(list=note_ids),
        get_note=lambda nid: types.SimpleNamespace(id=nid) if nid <= 1201 else None)))
    conn.set_trace_callback(queries.append)
    try:
        payload = {row["id"]: row for row in pdf_dock._pdf_highlights_payload(88)}
        assert len(payload) == 1203
        assert payload["h1200"]["linked_note_id"] == 1201
        assert payload["h1200"]["linked_highlight_count"] == 1
        assert payload["h1201"]["linked_note_id"] == 0
        assert payload["h1201"]["linked_highlight_count"] == 0
        assert payload["h1202"]["linked_highlight_count"] == 0
        assert conn.execute("SELECT note_id FROM pdf_card_sources WHERE pdf_card_id=99").fetchall() == [(1202,)]
        assert 1 <= len(note_queries) <= 2
        assert all(len(args) <= 900 for args in note_queries)
        assert not any("SELECT COUNT(*) FROM pdf_card_sources" in query for query in queries)
        assert len([query for query in queries if "FROM pdf_highlights WHERE" in query]) == 1
    finally:
        conn.set_trace_callback(None)
        notes.close()


def test_highlight_source_cleanup_preserves_links_when_collection_read_fails(monkeypatch):
    sources = {"h1": {"note_id": 42}, "h2": {"note_id": 43}}
    monkeypatch.setattr(pdf_dock, "get_pdf_card_sources_for_highlights", lambda *args: sources)
    def unavailable(*args):
        raise RuntimeError("collection unavailable")
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(
        col=types.SimpleNamespace(db=types.SimpleNamespace(list=unavailable))))
    monkeypatch.setattr(pdf_dock, "delete_pdf_card_sources_for_note_ids",
                        lambda *args: pytest.fail("unverified links must not be deleted"))
    assert pdf_dock._reconcile_pdf_highlight_sources(
        88, [{"id": "h1"}, {"id": "h2"}], profile="TestProfile",
    ) == sources


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
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(
        col=types.SimpleNamespace(db=types.SimpleNamespace(list=lambda *args: []))))
    monkeypatch.setattr(
        pdf_dock,
        "delete_pdf_card_sources_for_note_ids",
        lambda addon_dir, profile, pdf_card_id, note_ids: deleted.append(sorted(note_ids)),
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


def test_annotation_sync_callback_cannot_update_a_different_card_or_profile(monkeypatch):
    callbacks, scripts = [], []
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: types.SimpleNamespace(runJavaScript=scripts.append)))
    monkeypatch.setattr(pdf_dock, '_pdf_dock', dock)
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, '_current_pdf_filename', 'book.pdf')
    profile = ['Profile A']
    monkeypatch.setattr(pdf_dock, '_active_profile', lambda: profile[0])
    monkeypatch.setattr(pdf_dock, '_annotation_queue', types.SimpleNamespace(request=lambda *args, callback, **kw: callbacks.append(callback)))
    monkeypatch.setattr(pdf_dock, '_pdf_highlights_payload', lambda card: [{'id': 'imported'}])
    pdf_dock._schedule_pdf_annotation_sync()
    profile[0] = 'Profile B'
    callbacks.pop()(dict(reader_path='/tmp/reader.pdf'), None)
    assert scripts == []
    profile[0] = 'Profile A'
    pdf_dock._schedule_pdf_annotation_sync()
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 77)
    callbacks.pop()(dict(reader_path='/tmp/reader.pdf'), None)
    assert scripts == []


def test_replaced_reader_bytes_refresh_the_main_byte_source_after_a_highlight_only_sync(monkeypatch):
    callbacks, reloaded = [], []
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: types.SimpleNamespace(runJavaScript=lambda *_: None)))
    monkeypatch.setattr(pdf_dock, '_pdf_dock', dock)
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, '_current_pdf_filename', 'book.pdf')
    monkeypatch.setattr(pdf_dock, '_active_profile', lambda: 'A')
    monkeypatch.setattr(pdf_dock, '_annotation_queue', types.SimpleNamespace(request=lambda *args, callback, **kw: callbacks.append(callback)))
    monkeypatch.setattr(pdf_dock, '_pdf_highlights_payload', lambda *_: [])
    monkeypatch.setattr(pdf_dock, '_refresh_reference_pdf_state', lambda *_: None)
    monkeypatch.setattr(pdf_dock, '_reload_current_pdf_annotations', reloaded.append)
    pdf_dock._schedule_pdf_annotation_sync()
    result = {'reader_path': '/unused/reader.pdf', 'reader_changed': True, 'appearance_changed': False}
    callbacks.pop()(result, None)
    assert reloaded == [result]


def test_highlight_bridge_saves_only_the_active_card_and_schedules_pdf_sync(monkeypatch):
    saved, synced = [], []
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, 'add_highlight', lambda *args: saved.append(args))
    monkeypatch.setattr(pdf_dock, '_schedule_pdf_annotation_sync', lambda: synced.append(True))
    for card in [77, 42]:
        pdf_dock._handle_pdf_js_message(pdf_dock._MSG_HL_ADD + json.dumps({'cardId': card, 'highlight': {'id': 'h'}}))
    assert len(saved) == 1 and saved[0][2] == 42
    assert synced == [True]


def test_highlight_resize_bridge_updates_only_the_existing_active_highlight(monkeypatch):
    updated, synced = [], []
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(
        pdf_dock,
        'update_highlight',
        lambda *args: updated.append(args) or args[2] == 42,
    )
    monkeypatch.setattr(pdf_dock, '_schedule_pdf_annotation_sync', lambda: synced.append(True))

    for card in [77, 42]:
        pdf_dock._handle_pdf_js_message(
            pdf_dock._MSG_HL_UPDATE
            + json.dumps({'cardId': card, 'highlight': {'id': 'same-highlight'}})
        )

    assert len(updated) == 1
    assert updated[0][2] == 42
    assert updated[0][3]['id'] == 'same-highlight'
    assert synced == [True]


@pytest.mark.parametrize("reader_locale,custom_language", [
    ("zh-Hans", None),
    ("de", {"locale": "de", "messages": {"reader_previous_page": 'Vorherige Seite "<title>"'}}),
])
@pytest.mark.parametrize('page_y_override', [None, .65])
def test_show_pdf_in_dock_reloads_viewer_after_missing_screen(monkeypatch, reader_locale, custom_language, page_y_override):
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
    monkeypatch.setattr(
        pdf_dock,
        "get_pdf_annotation_reader_path",
        lambda *args: types.SimpleNamespace(is_file=lambda: False, is_symlink=lambda: False),
    )
    monkeypatch.setattr(pdf_dock, "get_locale", lambda: reader_locale, raising=False)
    monkeypatch.setattr(pdf_dock, "get_custom_reader_payload", lambda: custom_language, raising=False)
    monkeypatch.setattr(pdf_dock, "_pdf_highlights_payload", lambda card_id: [])
    monkeypatch.setattr(pdf_dock, "_pdf_bookmarks_payload", lambda card_id: [])
    monkeypatch.setattr(pdf_dock, "_current_pdf_limit_status", lambda *args, **kwargs: {"enabled": False})
    monkeypatch.setattr(pdf_dock, "get_read_anchor", lambda *args, **kwargs: None)
    monkeypatch.setattr(pdf_dock, "get_scroll_ratio", lambda *args, **kwargs: 0.42)
    monkeypatch.setattr(pdf_dock, "get_page", lambda *args, **kwargs: 3)
    monkeypatch.setattr(pdf_dock, "get_zoom", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(pdf_dock, "get_pdf_appearance_mode", lambda *args, **kwargs: "night")
    monkeypatch.setattr(pdf_dock, "configured_highlight_when_extracting", lambda *args, **kwargs: False)
    monkeypatch.setattr(pdf_dock, "configured_pdf_show_highlight_delete_buttons", lambda *args, **kwargs: False)
    monkeypatch.setattr(pdf_dock, "configured_pdf_link_preview_zoom", lambda *args, **kwargs: 2.5)
    monkeypatch.setattr(pdf_dock, "configured_pdf_controls_collapsed", lambda *args, **kwargs: False)
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
    monkeypatch.setattr(
        pdf_dock.os.path,
        "exists",
        lambda path: path in {"/tmp/new-file.pdf", "/tmp/cached-reader.pdf"},
    )
    sync_requests = []
    sync_callbacks = []
    cancelled_except = []
    def prepare_annotations(*args, callback, **kwargs):
        sync_requests.append(args)
        sync_callbacks.append(callback)
    monkeypatch.setattr(
        pdf_dock,
        '_annotation_queue',
        types.SimpleNamespace(
            request=prepare_annotations,
            cancel_except=lambda key: cancelled_except.append(key),
        ),
    )

    pdf_dock.show_pdf_in_dock(
        77,
        "old-file.pdf",
        3,
        via_link=True,
        offer_due_review_prompt=False,
        scroll_ratio_override=0.73,
        page_y_override=page_y_override,
    )

    assert pdf_dock._current_pdf_filename == "new-file.pdf"
    assert len(sync_requests) == 1
    assert cancelled_except == [(pdf_dock._ADDON_DIR, "TestProfile", 77, "new-file.pdf")]
    assert pdf_dock._pdf_showing_missing_screen is False
    assert events == []
    assert len(load_calls) == 1
    assert js_calls
    assert '"new-file.pdf"' in js_calls[0]
    assert "scrollRatio: 0.73" in js_calls[0]
    assert "scrollToReadAnchor: false" in js_calls[0]
    assert "scrollToTopOnPageChange: false" in js_calls[0]
    assert "showHighlightDeleteButtons: false" in js_calls[0]
    assert "linkPreviewZoom: 2.5" in js_calls[0]
    assert "controlsCollapsed: false" in js_calls[0]
    assert f'pageY: {json.dumps(page_y_override)}' in js_calls[0]
    assert f'locale: {json.dumps(reader_locale)}' in js_calls[0]
    assert f'customLanguage: {json.dumps(custom_language)}' in js_calls[0]
    assert (
        f', {json.dumps(reader_locale)}, {json.dumps(custom_language)}, "night", false, 2.5, {json.dumps(page_y_override)}, false));'
        in js_calls[0]
    )
    assert 'appearanceMode: "night"' in js_calls[0]
    assert '"old-file.pdf"' not in js_calls[0]

    sync_callbacks.pop()({'reader_path': '/tmp/cached-reader.pdf'}, None)
    assert len(load_calls) == 1
    assert len(js_calls) == 2
    assert '/tmp/cached-reader.pdf' in js_calls[1]
    assert f'pageY: {json.dumps(page_y_override)}' in js_calls[1]
    assert 'scrollRatio: 0.73' in js_calls[1]


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


def test_pdf_find_preserves_trailing_space_while_searching_trimmed_query(monkeypatch):
    import document_query
    from document_query import DocumentQuery
    from types import SimpleNamespace
    timer = SimpleNamespace(start=lambda: None, stop=lambda: None)
    def make_query(parent, **options):
        def dispatch(ticket, success, failure, progress):
            request = ticket.payload
            success(options["read"](request["profile"], request["card_id"], request["query"], ticket.cancel))
        return DocumentQuery(parent, **options, timer=timer, dispatch=dispatch)
    monkeypatch.setattr(document_query, "DocumentQuery", make_query)
    monkeypatch.setattr(pdf_dock, "_pdf_find_jobs", None)
    searched = []
    scripts = []

    class _Page:
        def runJavaScript(self, script):
            scripts.append(script)

    class _View:
        def page(self):
            return _Page()

    fake_dock = types.SimpleNamespace(_view=_View())
    monkeypatch.setattr(pdf_dock, "_pdf_dock", fake_dock)
    monkeypatch.setattr(pdf_dock, "current_pdf_card_id", lambda: 77)
    monkeypatch.setattr(
        pdf_dock,
        "current_card_pdf_search_hits",
        lambda card_id, query, **_kwargs: searched.append((card_id, query)) or [],
    )

    pdf_dock._update_pdf_search("target ")

    assert searched == []
    assert pdf_dock._current_pdf_search_query == "target "
    pdf_dock._pdf_find_jobs.start()
    assert searched == [(77, "target")]
    assert pdf_dock._current_pdf_search_query == "target "
    assert scripts
    payload = json.loads(scripts[-1].split("(", 1)[1].rsplit(");", 1)[0])
    assert payload["query"] == "target "


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
    monkeypatch.setattr(pdf_dock, "_pdf_via_link", False)
    monkeypatch.setattr(
        pdf_dock,
        "set_scroll_ratio",
        lambda addon_dir, profile, card_id, scroll_ratio: calls.append(
            (addon_dir, profile, card_id, scroll_ratio)
        ),
    )

    pdf_dock._handle_pdf_js_message('incremento_pdf_scroll:{"cardId":55,"scrollRatio":0.63}')

    assert calls == [("/tmp/addon", "TestProfile", 55, 0.63)]


def test_pdf_anchor_visit_does_not_replace_saved_reading_scroll(monkeypatch):
    calls = []
    monkeypatch.setattr(pdf_dock, "_pdf_preserve_history", False)
    monkeypatch.setattr(pdf_dock, "_pdf_via_link", True)
    monkeypatch.setattr(
        pdf_dock,
        "set_scroll_ratio",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    pdf_dock._handle_pdf_js_message(
        'incremento_pdf_scroll:{"cardId":55,"scrollRatio":0.63}'
    )

    assert calls == []


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
    anchor = repaired.removeprefix("Before ").removesuffix(" After")
    command = pdf_dock.reader_anchor_command_from_html(anchor)

    assert 'onclick="pycmd(&quot;incremento_open_pdf_ref:' in repaired
    assert "write-a-must-read.pdf" in repaired
    assert command is not None
    assert json.loads(command.split(":", 1)[1])["filename"] == "write-a-must-read.pdf"
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


@pytest.mark.parametrize('transition', ['regular', 'missing-card', 'missing-note', 'review-end'])
def test_leaving_pdf_review_restores_card_pane_and_clears_context(monkeypatch, transition):
    stopped = []
    restored = []

    class _FakeDock:
        def __init__(self):
            self.hidden = False

        def hide(self):
            self.hidden = True

    fake_dock = _FakeDock()
    fake_dock._pdf_focus_mode = types.SimpleNamespace(stop=lambda **kwargs: restored.append(kwargs))
    fake_note = types.SimpleNamespace(mid=1)
    def get_note(note_id):
        if transition == 'missing-note':
            raise KeyError(note_id)
        return fake_note
    fake_col = types.SimpleNamespace(
        get_note=get_note,
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

    if transition == 'review-end':
        pdf_dock.on_pdf_reviewer_will_end()
    else:
        pdf_dock.on_pdf_question_shown(None if transition == 'missing-card' else types.SimpleNamespace(id=88, nid=123))

    assert fake_dock.hidden is True
    assert pdf_dock.current_pdf_card_id() is None
    assert pdf_dock._current_pdf_filename is None
    assert stopped == [55]
    assert restored == [{}]


def test_focused_pdf_keeps_search_and_toolbar_actions_available(monkeypatch):
    scripts = []
    dock = types.SimpleNamespace(
        isVisible=lambda: False,
        _pdf_focus_mode=types.SimpleNamespace(is_visible=lambda: True),
        _view=types.SimpleNamespace(page=lambda: types.SimpleNamespace(runJavaScript=scripts.append)),
    )
    monkeypatch.setattr(pdf_dock, '_pdf_dock', dock)
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 55)
    monkeypatch.setattr(pdf_dock, '_current_pdf_filename', 'source.pdf')
    assert pdf_dock.current_pdf_search_context()['cardId'] == 55
    pdf_dock.trigger_viewer_action('open_find')
    assert pdf_dock.open_current_document_find()
    assert scripts == ["window.incrementoPdfOpenFind && window.incrementoPdfOpenFind();"] * 2


def test_pdf_focus_toggle_saves_through_config_and_survives_reader_restart(monkeypatch):
    stored = {'future_setting': {'keep': True}, 'pdf_focus_mode': False}
    class Manager:
        def getConfig(self, package): return dict(stored)
        def writeConfig(self, package, config): stored.update(config)
    monkeypatch.setattr(pdf_dock, 'mw', types.SimpleNamespace(addonManager=Manager()))
    assert pdf_dock.save_pdf_focus_mode(True)
    assert stored['pdf_focus_mode'] is True
    assert stored['future_setting'] == {'keep': True}
    assert pdf_dock.configured_pdf_focus_mode() is True
    assert pdf_dock.save_pdf_focus_mode(False)
    assert pdf_dock.configured_pdf_focus_mode() is False


def test_controls_bridge_remembers_main_and_side_independently_after_reopening(monkeypatch):
    from copy import deepcopy
    stored = {'future_setting': {'keep': True},
              'pdf_controls_collapsed_by_profile': {'Other': {'main': True}}}
    class Manager:
        def getConfig(self, package): return deepcopy(stored)
        def writeConfig(self, package, config): stored.update(deepcopy(config))
    monkeypatch.setattr(pdf_dock, 'mw', types.SimpleNamespace(addonManager=Manager()))
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, '_active_profile', lambda: 'A')
    for collapsed in (True, False):
        pdf_dock._handle_pdf_js_message('incremento_pdf_controls:' + json.dumps({
            'cardId': 42, 'collapsed': collapsed}))
        assert pdf_dock.configured_pdf_controls_collapsed() is collapsed
    assert pdf_dock.save_pdf_controls_collapsed(True, profile='A', reading_only=True)
    assert pdf_dock.configured_pdf_controls_collapsed() is False
    assert pdf_dock.configured_pdf_controls_collapsed(reading_only=True) is True
    assert stored['pdf_controls_collapsed_by_profile']['Other'] == {'main': True}
    assert stored['future_setting'] == {'keep': True}


@pytest.mark.parametrize('payload', [
    {'cardId': 99, 'collapsed': True}, {'cardId': 42, 'collapsed': 'false'},
    {'cardId': 42, 'collapsed': 0}, {'collapsed': False}, [], None,
])
def test_controls_bridge_rejects_stale_or_malformed_requests(monkeypatch, payload):
    writes = []
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 42)
    monkeypatch.setattr(pdf_dock, 'save_addon_config', lambda *args: writes.append(args))
    pdf_dock._handle_pdf_js_message('incremento_pdf_controls:' + json.dumps(payload))
    assert writes == []


@pytest.mark.parametrize('state,review_id,model_name,eligible', [
    ('review', 55, 'PDF', True), ('review', 56, 'PDF', True),
    ('overview', 55, 'PDF', True), ('review', 55, 'Basic', True),
    ('deckBrowser', None, None, True), ('overview', None, None, True),
])
def test_open_pdf_focus_is_available_on_decks_overview_and_review(monkeypatch, state, review_id, model_name, eligible):
    presentations = []
    preferences = []
    note = type('Note', (dict,), {'mid': 1})(Title='A <title>')
    monkeypatch.setattr(pdf_dock, '_pdf_dock', types.SimpleNamespace(
        _pdf_focus_mode=types.SimpleNamespace(set_enabled=preferences.append,
            present=lambda **kwargs: presentations.append(kwargs))))
    monkeypatch.setattr(pdf_dock, '_config', lambda config=None: {'pdf_focus_mode': True})
    monkeypatch.setattr(pdf_dock, 'mw', types.SimpleNamespace(
        state=state, reviewer=types.SimpleNamespace(card=types.SimpleNamespace(id=review_id)),
        col=types.SimpleNamespace(models=types.SimpleNamespace(
            get=lambda mid: {'name': pdf_dock.PDF_NOTE_TYPE if model_name == 'PDF' else model_name}))))
    pdf_dock._present_pdf_reader(55, note, 'source.pdf')
    assert presentations == [{'eligible': eligible, 'title': 'A <title>'}]
    assert preferences == [True]


@pytest.mark.parametrize('failure', ['load', 'save'])
def test_pdf_focus_save_failure_reports_error_without_claiming_success(monkeypatch, failure):
    writes, messages = [], []
    def load(*args):
        if failure == 'load':
            raise OSError('synthetic read failure')
        return {'future_setting': True}
    def save(*args):
        writes.append(args)
        raise OSError('synthetic write failure')
    monkeypatch.setattr(pdf_dock, 'mw', types.SimpleNamespace(addonManager=object()))
    monkeypatch.setattr(pdf_dock, 'load_addon_config', load)
    monkeypatch.setattr(pdf_dock, 'save_addon_config', save)
    monkeypatch.setattr(pdf_dock, 'tooltip', messages.append)
    assert not pdf_dock.save_pdf_focus_mode(True)
    assert len(messages) == 1
    assert len(writes) == (1 if failure == 'save' else 0)


def test_on_pdf_question_shown_never_opens_automatic_due_prompt(monkeypatch):
    shown = []

    class _FakePdfNote(dict):
        mid = 1

    fake_note = _FakePdfNote(PDF_Filename="source.pdf")
    fake_col = types.SimpleNamespace(
        get_note=lambda _note_id: fake_note,
        models=types.SimpleNamespace(
            get=lambda _mid: {"name": pdf_dock.PDF_NOTE_TYPE}
        ),
    )
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=fake_col))
    monkeypatch.setattr(pdf_dock, "get_page", lambda *_args: 7)
    monkeypatch.setattr(pdf_dock, "get_zoom", lambda *_args: 1.25)
    monkeypatch.setattr(pdf_dock, "get_read_page", lambda *_args: 6)
    monkeypatch.setattr(
        pdf_dock,
        "show_pdf_in_dock",
        lambda *args, **kwargs: shown.append((args, kwargs)),
    )

    pdf_dock.on_pdf_question_shown(types.SimpleNamespace(id=88, nid=123))

    assert shown == [
        (
            (88, "source.pdf", 7, 1.25),
            {"read_page": 6, "offer_due_review_prompt": False},
        )
    ]


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
    monkeypatch.setattr(pdf_dock, '_current_pdf_card_id', 55)
    monkeypatch.setattr(pdf_dock, '_schedule_pdf_annotation_sync', lambda: None)
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


def test_pdf_review_all_bridge_opens_attached_review(monkeypatch):
    calls = []
    monkeypatch.setattr(
        pdf_dock,
        "_start_all_pdf_review",
        lambda card_id, *, current_page: calls.append((card_id, current_page)) or True,
    )

    pdf_dock._handle_pdf_js_message("incremento_pdf_review_all:55:7")

    assert calls == [(55, 7)]


def test_start_all_pdf_review_passes_reader_context_and_restores_reader(monkeypatch):
    starts = []
    selected_decks = []
    restored = []
    fake_note = {"PDF_Filename": "source.pdf"}
    fake_col = types.SimpleNamespace(
        get_card=lambda card_id: types.SimpleNamespace(nid=9),
        get_note=lambda note_id: fake_note,
        decks=types.SimpleNamespace(
            current=lambda: {"id": 44},
            select=lambda deck_id: selected_decks.append(deck_id),
        ),
    )
    fake_launcher = types.SimpleNamespace(
        start_attached_media_review=lambda **kwargs: starts.append(kwargs) or True,
    )
    monkeypatch.setitem(sys.modules, "media_review_dialog", fake_launcher)
    monkeypatch.setattr(pdf_dock, "mw", types.SimpleNamespace(col=fake_col))
    monkeypatch.setattr(pdf_dock, "_ADDON_DIR", "/tmp/addon")
    monkeypatch.setattr(pdf_dock, "_active_profile", lambda: "TestProfile")
    monkeypatch.setattr(pdf_dock, "get_zoom", lambda *_args: 1.25)
    monkeypatch.setattr(pdf_dock, "get_read_page", lambda *_args: 6)
    monkeypatch.setattr(
        pdf_dock,
        "show_pdf_in_dock",
        lambda *args, **kwargs: restored.append((args, kwargs)),
    )
    monkeypatch.setattr(
        pdf_dock,
        "QTimer",
        types.SimpleNamespace(singleShot=lambda _ms, callback: callback()),
    )

    assert pdf_dock._start_all_pdf_review(55, current_page=7) is True
    assert starts[0]["source_card_id"] == 55
    assert starts[0]["media_label"] == "PDF"
    assert starts[0]["media_kind"] == "pdf"
    assert starts[0]["current_position"] == 7
    assert starts[0]["deck_name"] == pdf_dock.INCREMENTO_PDF_REVIEW_DECK

    starts[0]["on_finished"]()
    assert selected_decks == [44]
    assert restored == [
        (
            (55, "source.pdf", 7, 1.25),
            {
                "read_page": 6,
                "preserve_history": False,
                "offer_due_review_prompt": False,
            },
        )
    ]


@pytest.mark.parametrize('switch_context', [False, True], ids=['current-document', 'profile-switched'])
def test_custom_color_result_is_delivered_only_to_its_current_pdf(monkeypatch, switch_context):
    scripts, picks = [], []
    page = types.SimpleNamespace(runJavaScript=scripts.append)
    dock = types.SimpleNamespace(_view=types.SimpleNamespace(page=lambda: page))
    monkeypatch.setattr(pdf_dock, '_pdf_dock', dock)
    monkeypatch.setattr(pdf_dock, '_current_pdf_filename', 'book.pdf')
    monkeypatch.setattr(pdf_dock, '_pdf_annotation_generation', 10)
    monkeypatch.setattr(pdf_dock, 'current_pdf_card_id', lambda: 42)
    monkeypatch.setattr(pdf_dock, '_active_profile', lambda: 'Profile A')
    def choose(parent, current, *, addon_dir, profile):
        picks.append((parent, current, addon_dir, profile))
        if switch_context:
            monkeypatch.setattr(pdf_dock, '_active_profile', lambda: 'Profile B')
        return '#123abc'
    monkeypatch.setitem(sys.modules, 'highlight_color_dialog', types.SimpleNamespace(choose_highlight_color=choose))
    pdf_dock._choose_pdf_highlight_color({'cardId': 999, 'currentColor': 'yellow'})
    assert not picks and not scripts
    pdf_dock._choose_pdf_highlight_color({'cardId': 42, 'currentColor': '#123ABC'})
    assert picks == [(dock, '#123abc', pdf_dock._ADDON_DIR, 'Profile A')]
    if switch_context:
        assert not scripts
    else:
        assert len(scripts) == 1 and 'incrementoPickPdfHighlightColor("#123abc")' in scripts[0]


@pytest.mark.parametrize('action', ['next_page', 'prev_page', 'zoom_in', 'zoom_out', 'mark_read', 'open_find', 'contents'])
def test_reader_shortcuts_target_the_focused_side_pane_without_moving_the_main_pdf(monkeypatch, action):
    primary, beside = [], []
    main_view = types.SimpleNamespace(page=lambda: types.SimpleNamespace(runJavaScript=primary.append))
    side_view = types.SimpleNamespace(page=lambda: types.SimpleNamespace(runJavaScript=beside.append))
    monkeypatch.setattr(pdf_dock, '_pdf_dock', types.SimpleNamespace(_view=main_view))
    monkeypatch.setattr(pdf_dock, '_pdf_reader_is_visible', lambda: True)
    monkeypatch.setattr(pdf_dock, '_focused_pdf_extraction_view', lambda: side_view)
    pdf_dock.trigger_viewer_action(action)
    assert len(beside) == 1
    assert primary == []
