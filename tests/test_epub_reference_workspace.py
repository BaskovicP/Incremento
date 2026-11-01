"""Reference panes never route messages through the singleton main reader."""
import json
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def workspace(monkeypatch):
    # Restore the exact global Anki stand-ins immediately after loading.
    with monkeypatch.context() as patch:
        patch.setattr(sys.modules['aqt.qt'], 'QDockWidget', type('Dock', (), {}))
        patch.setitem(sys.modules, 'aqt.operations', SimpleNamespace(QueryOp=MagicMock()))
        patch.setitem(sys.modules, 'session', MagicMock())
        path = Path(__file__).resolve().parents[1] / 'frontend/epub_reference_workspace.py'
        spec = importlib.util.spec_from_file_location('_epub_workspace_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def test_reference_progress_is_transient_and_rejects_another_card(monkeypatch, workspace):
    window = SimpleNamespace(location=dict(card_id=7, section=0, offset=42, scroll=0),
        current=lambda: True, limit={}, snapshot={'sections': [{}]}, _last_allowed_scroll=0,
        js=MagicMock(), profile='A', loaded=True)
    payload = {'cardId': 7, 'sectionIndex': 0, 'scrollRatio': .75, 'pageIndex': 0}
    workspace.EpubReferenceWindow.command(window, 'incremento_epub_progress:' + json.dumps(payload))
    assert window.location['scroll'] == .75
    assert window.location['offset'] == -1  # Return to the new scroll position, not the original link.
    payload.update(cardId=8, scrollRatio=.1)
    workspace.EpubReferenceWindow.command(window, 'incremento_epub_progress:' + json.dumps(payload))
    assert window.location['scroll'] == .75


def test_closed_or_switched_reference_cannot_write_highlights(monkeypatch, workspace):
    write = MagicMock()
    monkeypatch.setattr(workspace, 'add_highlight', write)
    window = SimpleNamespace(current=lambda: False)
    workspace.EpubReferenceWindow.command(window, 'incremento_epub_hl_add:' + json.dumps({'cardId': 7}))
    write.assert_not_called()


def test_style_edit_refreshes_other_panes_without_dismissing_its_own_palette(monkeypatch, workspace):
    rows = [dict(id='mark', sectionIndex=0, style='dashed')]
    source = SimpleNamespace(current=lambda: True, location=dict(card_id=7, section=0), js=MagicMock())
    other = SimpleNamespace(current=lambda: True, location=dict(card_id=7, section=0), js=MagicMock())
    monkeypatch.setattr(workspace, '_windows', [source, other])
    monkeypatch.setattr(workspace, 'get_active_profile', lambda: 'Synthetic')
    monkeypatch.setattr(workspace, 'load_highlights', lambda *args: rows)
    workspace.refresh_readers('Synthetic', 7, include_main=False, exclude=source)
    assert source.highlights == rows
    source.js.assert_not_called()
    other.js.assert_called_once()
    assert '"style": "dashed"' in other.js.call_args.args[0]


@pytest.mark.parametrize('message', ['{', '[]', '{"cardId":true}', '{"cardId":7,"scrollRatio":NaN}'])
def test_reference_malformed_progress_does_not_change_position(message, workspace):
    window = SimpleNamespace(location=dict(card_id=7, section=0, offset=0, scroll=.4), current=lambda: True,
                             loaded=True, limit={}, snapshot={'sections': [{}]})
    workspace.EpubReferenceWindow.command(window, 'incremento_epub_progress:' + message)
    assert window.location['scroll'] == .4


def test_superseded_or_profile_switched_reference_result_cannot_open_a_window(monkeypatch, workspace):
    pending, opened, profile = [], [], ['A']
    class Query:
        def __init__(self, **kw): self.kw = kw
        def failure(self, fn): return self
        def run_in_background(self): pending.append(self.kw)
    monkeypatch.setattr(workspace, 'QueryOp', Query)
    monkeypatch.setattr(workspace, 'get_active_profile', lambda: profile[0])
    monkeypatch.setattr(workspace, 'EpubReferenceWindow', lambda *a, **k: opened.append(a))
    location = dict(card_id=7, section=0, offset=4, scroll=.2)
    workspace.open_reference(location)
    workspace.open_reference(location | {'section': 1})
    pending[0]['success'](None)
    assert not opened
    profile[0] = 'B'
    pending[1]['success'](None)
    assert not opened


def test_reference_reading_lock_rejects_forward_position_without_changing_location(workspace):
    calls = []
    window = SimpleNamespace(location=dict(card_id=7, section=0, offset=-1, scroll=.2), current=lambda: True,
        loaded=True, limit=dict(enabled=True, enforcement_mode='hard_stop', allowed_max_page=1),
        _last_allowed_scroll=.2, js=calls.append)
    workspace.EpubReferenceWindow.command(window, 'incremento_epub_progress:' + json.dumps(
        dict(cardId=7, sectionIndex=0, scrollRatio=.9, pageIndex=8)))
    assert window.location['scroll'] == .2
    assert len(calls) == 1 and 'window.scrollTo' in calls[0]


def test_initial_reference_position_cannot_bypass_reflowed_reading_limit(workspace):
    window = SimpleNamespace(location=dict(card_id=7, section=0, offset=900, scroll=.9), current=lambda: True,
        loaded=True, limit=dict(enabled=True, enforcement_mode='hard_stop', allowed_max_page=1),
        _last_allowed_scroll=None, js=MagicMock(), close=MagicMock())
    workspace.EpubReferenceWindow.command(window, 'incremento_epub_progress:' + json.dumps(
        dict(cardId=7, sectionIndex=0, scrollRatio=.9, pageIndex=8)))
    window.close.assert_called_once()
    window.js.assert_not_called()


def test_reference_extract_uses_its_captured_book_and_section(monkeypatch, workspace):
    filled = []
    window = SimpleNamespace(current=lambda: True, loaded=True,
        location=dict(card_id=7, section=3, offset=0, scroll=.4), snapshot={'title': 'Reference'})
    monkeypatch.setattr(workspace.reader, '_cb_open_add_card_dock', lambda: None)
    monkeypatch.setattr(workspace.reader, '_cb_fill_dock_field', lambda *a, **kw: filled.append((a,kw)))
    workspace.EpubReferenceWindow.command(window, 'incremento_epub_fill_field:' + json.dumps(
        dict(cardId=7, idx=1, text='A <passage>', startOffset=42, endOffset=53)))
    assert filled[0][0] == (1, 'A &lt;passage&gt;')
    assert filled[0][1]['source_card_id'] == 7
    assert filled[0][1]['source_position'] == 3
    assert 'incremento_open_epub:7:3:42:0.4' in filled[0][1]['citation_html']


def test_read_markers_sync_between_panes_without_navigating(monkeypatch, workspace):
    anchor = {'sectionIndex': 2, 'startOffset': 50, 'endOffset': 60}
    window = SimpleNamespace(current=lambda: True, location=dict(card_id=7, section=2), js=MagicMock())
    other = SimpleNamespace(current=lambda: True, location=dict(card_id=8, section=2), js=MagicMock())
    monkeypatch.setattr(workspace, '_windows', [window, other])
    monkeypatch.setattr(workspace, 'get_active_profile', lambda: 'A')
    monkeypatch.setattr(workspace, 'get_read_anchor', lambda *a: anchor)
    monkeypatch.setattr(workspace, 'get_read_section_index', lambda *a: 2, raising=False)
    monkeypatch.setattr(workspace.reader, '_current_epub_card_id', 7)
    monkeypatch.setattr(workspace.reader, '_current_epub_section_index', 4)
    monkeypatch.setattr(workspace.reader, '_current_epub_read_anchor', None)
    monkeypatch.setattr(workspace.reader, '_current_epub_read_section_index', 0)
    monkeypatch.setattr(workspace.reader, '_epub_dock', object())
    monkeypatch.setattr(workspace.reader, '_push_epub_read_anchor', MagicMock())
    monkeypatch.setattr(workspace.reader, '_update_title_and_buttons', MagicMock())
    workspace.refresh_read_progress('A', 7)
    assert window.anchor == anchor
    assert 'incrementoSetEpubReadAnchor' in window.js.call_args.args[0]
    assert workspace.reader._current_epub_read_anchor == anchor
    assert workspace.reader._current_epub_read_section_index == 2
    assert workspace.reader._current_epub_section_index == 4
    other.js.assert_not_called()


def test_failed_jump_back_keeps_return_position(monkeypatch, workspace):
    pending = []
    class Query:
        def __init__(self, **kw): self.kw = kw
        def failure(self, fn):
            self.kw['failure'] = fn
            return self
        def run_in_background(self): pending.append(self.kw)
    monkeypatch.setattr(workspace, 'QueryOp', Query)
    window = SimpleNamespace(current=lambda: True, history=[dict(card_id=7,section=0,offset=-1,scroll=.7)],
        location=dict(card_id=7,section=1,offset=-1,scroll=.2), profile='A',
        snapshot={'sections': [{}, {}]}, request=0, back_button=MagicMock(), load=MagicMock())
    window.navigate = lambda *a, **kw: workspace.EpubReferenceWindow.navigate(window, *a, **kw)
    workspace.EpubReferenceWindow.back(window)
    assert len(window.history) == 1
    pending[0]['success']((window.snapshot, {}, [], 1.0, None))
    assert window.history == []
    assert window.location['scroll'] == .7


def test_replacing_a_pinned_reference_splits_against_the_main_dock(monkeypatch, workspace):
    pending, created = [], []
    class Query:
        def __init__(self, **kw): self.kw = kw
        def failure(self, fn): return self
        def run_in_background(self): pending.append(self.kw)
    main_dock = object()
    old = SimpleNamespace(owner=main_dock, isFloating=lambda: False, close=MagicMock())
    monkeypatch.setattr(workspace, 'QueryOp', Query)
    monkeypatch.setattr(workspace, '_windows', [old])
    monkeypatch.setattr(workspace, 'get_active_profile', lambda: 'A')
    def construct(*args, **kwargs):
        created.append(kwargs)
        return SimpleNamespace(show=lambda: None)
    monkeypatch.setattr(workspace, 'EpubReferenceWindow', construct)
    workspace.open_reference(dict(card_id=7,section=0,offset=-1,scroll=0), owner=old, beside=True)
    pending[0]['success'](None)
    assert created[0]['owner'] is main_dock
    old.close.assert_called_once()


def test_reference_annotation_editor_is_deferred_and_preserves_rich_notes_after_section_navigation(monkeypatch, workspace):
    pending, writes, refreshed = [], [], []
    monkeypatch.setitem(sys.modules, 'highlight_note_dialog', SimpleNamespace(HighlightNoteDialog=SimpleNamespace(
        show_for_annotation=lambda *args, **kwargs: pending.append(kwargs))))
    monkeypatch.setattr(workspace, 'load_highlights', lambda *args: [
        dict(id='h', sectionIndex=0, text='source', note='Original', note_html='<b>Original</b>')])
    monkeypatch.setattr(workspace, 'update_highlight_note', lambda *args, **kwargs:
        writes.append((args, kwargs)) or dict(id='h', note='Edited', note_html='<i>Edited</i>'))
    monkeypatch.setattr(workspace, 'refresh_readers', lambda *args: refreshed.append(args))
    window = SimpleNamespace(current=lambda: True, profile='One', location=dict(card_id=7, section=0),
                             snapshot=dict(filename='book.epub'))
    workspace.EpubReferenceWindow.edit_highlight(window, 'h')
    assert writes == []
    assert pending[0]['current_note_html'] == '<b>Original</b>'
    window.location['section'] = 1
    assert pending[0]['is_current']()
    pending[0]['save'](SimpleNamespace(note_text=lambda: 'Edited', note_html=lambda: '<i>Edited</i>'))
    assert writes[0][0][1:4] == ('One', 7, 'h')
    assert writes[0][1] == dict(note_html='<i>Edited</i>', expected_note=('Original', '<b>Original</b>'))
    assert refreshed == [('One', 7)]
