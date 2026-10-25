"""Workspace content is resolved against the current collection before any pane opens."""
from types import SimpleNamespace
from unittest.mock import Mock
import importlib
import sys

import pytest


@pytest.fixture
def module():
    previous = sys.modules.get('aqt.operations')
    sys.modules['aqt.operations'] = SimpleNamespace(QueryOp=Mock())
    try:
        return importlib.import_module('frontend.workspace_session')
    finally:
        if previous is None:
            sys.modules.pop('aqt.operations', None)
        else:
            sys.modules['aqt.operations'] = previous


def test_workspace_load_skips_deleted_cards_and_discards_stale_success(monkeypatch, module):
    jobs, opened = [], []
    class Query:
        def __init__(self, **kw):
            self.kw = kw
            jobs.append(self)
        def failure(self, callback):
            self.failed = callback
            return self
        def run_in_background(self): pass
    monkeypatch.setattr(module, 'QueryOp', Query)
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_resolve', lambda col, profile, entry:
                        (_ for _ in ()).throw(ValueError('Missing')) if entry['card_id'] == 2 else entry)
    monkeypatch.setattr(session, '_open', lambda entry, result: opened.append(entry['card_id']) or object())
    entries = [{'card_id': 1}, {'card_id': 2}]
    current, finished = [True], []
    session.restore(entries, lambda: current[0], lambda panes, missing: finished.append((panes, missing)))
    result = jobs[0].kw['op'](object())
    assert opened == [], 'A background resolver cannot construct Qt panes'
    current[0] = False
    jobs[0].kw['success'](result)
    assert opened == [] and finished == []
    current[0] = True
    session.restore(entries, lambda: current[0], lambda panes, missing: finished.append((panes, missing)))
    jobs[1].kw['success'](jobs[1].kw['op'](object()))
    assert opened == [1] and len(finished[0][0]) == 1 and finished[0][1] == 1


@pytest.mark.parametrize('kind,model', [('pdf', 'Basic'), ('writing', 'Incremento PDF'), ('epub', 'Basic')])
def test_workspace_rejects_a_saved_card_whose_note_type_changed(kind, model, module):
    class Note(dict):
        def note_type(self): return {'name': model}
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=5), get_note=lambda nid: Note())
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    with pytest.raises(ValueError):
        session._resolve(col, 'A', {'kind': kind, 'card_id': 42})


def test_reopening_the_same_writing_card_preserves_live_unsaved_text(monkeypatch, module):
    dock = SimpleNamespace(setObjectName=Mock())
    reader = SimpleNamespace(show_writing_in_dock=Mock(), _writing_dock=dock,
        _apply_wrap_mode=Mock(), _apply_focus_mode=Mock(), _apply_preview_visibility=Mock(),
        _apply_font_scale=Mock(), set_keep_open=Mock())
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_module', lambda kind: reader)
    entry = {'kind': 'writing', 'card_id': 42, 'name': 'incremento_writing_dock', 'controls': {'preview': False}}
    assert session._open(entry, {'title': 'Writing', 'relpath': 'writing/example.md'}) is dock
    reader.show_writing_in_dock.assert_called_once_with(42, 'Writing', 'writing/example.md', keep_open=True)
    reader._apply_preview_visibility.assert_called_once_with(False)
    assert not hasattr(dock, 'setPlainText'), 'The existing writer owns flushing and restoring its text'


def test_workspace_pdf_uses_current_collection_file_and_reading_limit(tmp_path, monkeypatch, module):
    from backend.pdf_manager import set_page, set_scroll_ratio
    monkeypatch.setattr(module, '_ADDON_DIR', str(tmp_path))
    root = tmp_path / 'user_files' / 'A' / 'pdfs'
    root.mkdir(parents=True)
    (root / 'canonical.pdf').write_bytes(b'%PDF-synthetic')
    set_page(str(tmp_path), 'A', 42, 17)
    set_scroll_ratio(str(tmp_path), 'A', 42, .65)
    class Note(dict):
        def note_type(self): return {'name': 'Incremento PDF'}
    note = Note(PDF_Filename='canonical.pdf', Title='Synthetic document')
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=5), get_note=lambda nid: note)
    monkeypatch.setattr(module, 'get_pdf_daily_limit_status', lambda *args, **kw: {
        'enabled': True, 'enforcement_mode': 'hard_stop', 'allowed_max_page': 3})
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    result = session._resolve(col, 'A', {'kind': 'pdf', 'card_id': 42, 'page': 17,
                                       'path': '/untrusted/other.pdf'})
    assert result['snapshot']['path'] == str(root / 'canonical.pdf')
    assert result['maximum'] == 3
    reader = SimpleNamespace(show_pdf_in_dock=Mock(), _pdf_dock=Mock())
    monkeypatch.setattr(session, '_module', lambda kind: reader)
    monkeypatch.setattr(session, '_restore_pdf_controls', Mock())
    session._open({'kind': 'pdf', 'card_id': 42, 'name': 'incremento_pdf_dock', 'page': 17}, result)
    assert reader.show_pdf_in_dock.call_args.args[:3] == (42, 'canonical.pdf', 3)
    assert reader.show_pdf_in_dock.call_args.kwargs['offer_due_review_prompt'] is False
    assert reader.show_pdf_in_dock.call_args.kwargs['scroll_ratio_override'] == 0


def test_workspace_writing_resolution_rejects_missing_files_without_creating_them(tmp_path, monkeypatch, module):
    monkeypatch.setattr(module, '_ADDON_DIR', str(tmp_path))
    class Note(dict):
        def note_type(self): return {'name': 'Incremento Writing'}
    note = Note(Markdown_File='writing/absent.md', Title='Synthetic writing')
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=5), get_note=lambda nid: note)
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    with pytest.raises(ValueError, match='unavailable'):
        session._resolve(col, 'A', {'kind': 'writing', 'card_id': 42})
    assert not list(tmp_path.rglob('*.md'))


def test_workspace_pdf_capture_fails_if_its_document_changes_before_the_reply(monkeypatch, module):
    timer = Mock()
    monkeypatch.setattr(module, 'QTimer', lambda parent: timer)
    replies, captured = [], []
    dock = SimpleNamespace(_view=SimpleNamespace(page=lambda: SimpleNamespace(
        runJavaScript=lambda js, callback: replies.append(callback))))
    identity = [42]
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_describe', lambda dock: {
        'kind': 'pdf', 'name': 'incremento_pdf_dock', 'card_id': identity[0]})
    session.capture([dock], captured.append)
    assert captured == []
    identity[0] = 43
    replies[0]({'card_id': 42, 'controls': {'collapsed': False}})
    assert captured == [[]], 'The new document cannot be saved with the previous document’s controls'
    timer.stop.assert_called_once()


def test_failed_writing_flush_keeps_the_live_card_instead_of_loading_another(monkeypatch, module):
    reader = SimpleNamespace(_current_writing_card_id=17, _flush_editor_state=Mock(return_value=False),
                             show_writing_in_dock=Mock())
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_module', lambda kind: reader)
    assert session._open({'kind': 'writing', 'card_id': 42, 'name': 'incremento_writing_dock'},
                         {'title': 'Another card', 'relpath': 'writing/another.md'}) is None
    reader.show_writing_in_dock.assert_not_called()


def test_saved_web_pane_reopens_through_its_existing_controller(monkeypatch, module):
    dock = SimpleNamespace(setObjectName=Mock())
    reader = SimpleNamespace(_runtime=SimpleNamespace(dock=dock),
        on_web_question_shown=Mock(), current_web_card_id=lambda: 42)
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_module', lambda kind: reader)
    assert session._open({'kind': 'web', 'card_id': 42, 'name': 'incremento_web_dock'},
                         {'note_id': 5}) is dock
    assert reader.on_web_question_shown.call_args.args[0].id == 42


@pytest.mark.parametrize('kind', ['pdf', 'pdf_reference'])
def test_reopened_workspace_pdf_uses_latest_profile_progress_instead_of_its_saved_page(
    tmp_path, monkeypatch, module, kind,
):
    from backend.pdf_manager import set_page, set_scroll_ratio
    monkeypatch.setattr(module, '_ADDON_DIR', str(tmp_path))
    root = tmp_path / 'user_files' / 'A' / 'pdfs'
    root.mkdir(parents=True)
    (root / 'book.pdf').write_bytes(b'%PDF-synthetic')
    class Note(dict):
        def note_type(self): return {'name': 'Incremento PDF'}
    note = Note(PDF_Filename='book.pdf', Title='Synthetic document')
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=5), get_note=lambda nid: note)
    set_page(str(tmp_path), 'A', 42, 31)
    set_scroll_ratio(str(tmp_path), 'A', 42, .65)
    set_page(str(tmp_path), 'B', 42, 99)
    monkeypatch.setattr(module, 'get_pdf_daily_limit_status', lambda *args, **kw: {'enabled': False})
    entry = {'kind': kind, 'card_id': 42, 'name': 'incremento_pdf_dock' if kind == 'pdf'
             else 'incremento_pdf_reference_saved_0', 'page': 17, 'scroll': .2, 'zoom': 1.5}
    dock = SimpleNamespace(setObjectName=Mock())
    main_reader = SimpleNamespace(show_pdf_in_dock=Mock(), _pdf_dock=dock,
                                   _live_pdf_location=lambda cid: None)
    windows = []
    reference_reader = SimpleNamespace(_windows=[], _pending_windows=set(), _MAX_WINDOWS=8,
        ReferenceWindow=lambda snapshot, **kw: windows.append(kw) or dock)
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_module', lambda kind: main_reader if kind == 'pdf' else reference_reader)
    monkeypatch.setattr(session, '_restore_pdf_controls', Mock())
    result = session._resolve(col, 'A', entry)
    session._open(entry, result)
    if kind == 'pdf':
        assert main_reader.show_pdf_in_dock.call_args.args[2:] == (31, 1.5)
        assert main_reader.show_pdf_in_dock.call_args.kwargs['scroll_ratio_override'] == .65
    else:
        assert (windows[0]['page'], windows[0]['scroll_ratio'], windows[0]['zoom']) == (31, .65, 1.5)


def test_workspace_load_keeps_a_live_pdf_position_that_advanced_after_background_resolution(monkeypatch, module):
    dock = SimpleNamespace(setObjectName=Mock())
    reader = SimpleNamespace(show_pdf_in_dock=Mock(), _pdf_dock=dock,
        _live_pdf_location=lambda cid: {'profile': 'A', 'card_id': 42, 'filename': 'book.pdf',
                                      'page': 44, 'scroll_ratio': .8})
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_module', lambda kind: reader)
    monkeypatch.setattr(session, '_restore_pdf_controls', Mock())
    session._open({'kind': 'pdf', 'card_id': 42, 'name': 'incremento_pdf_dock', 'page': 17},
                  {'snapshot': {'filename': 'book.pdf'}, 'maximum': 100,
                   'position': {'page': 31, 'scroll': .65}})
    assert reader.show_pdf_in_dock.call_args.args[2] == 44
    assert reader.show_pdf_in_dock.call_args.kwargs['scroll_ratio_override'] == .8


@pytest.mark.parametrize('just_saved', [False, True])
def test_loading_a_workspace_keeps_an_open_additional_pdf_on_its_current_page(monkeypatch, module, just_saved):
    from backend.pdf_reader_state import PdfReaderState
    name = 'incremento_pdf_reference_saved_0'
    dock = SimpleNamespace(objectName=lambda: 'incremento_pdf_reference_nonce' if just_saved else name,
        _workspace_saved_name=name, setObjectName=Mock(),
        state=PdfReaderState('A', 42, 'book.pdf', page=44, scroll_ratio=.8),
        reload_reader=Mock(), reader=SimpleNamespace(service=SimpleNamespace(
            _initial_pdf_annotation_result=lambda *args: {})))
    reader = SimpleNamespace(_windows=[dock])
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_module', lambda kind: reader)
    monkeypatch.setattr(session, '_restore_pdf_controls', Mock())
    session._open({'kind': 'pdf_reference', 'card_id': 42, 'name': name, 'page': 17, 'scroll': .2},
                  {'snapshot': {'filename': 'book.pdf', 'path': 'synthetic.pdf'}, 'maximum': 100,
                   'position': {'page': 31, 'scroll': .65}})
    assert (dock.state.page, dock.state.scroll_ratio) == (44, .8)
    dock.reload_reader.assert_called_once()


@pytest.mark.parametrize('kind', ['epub', 'epub_reference'])
def test_workspace_epub_resumes_latest_section_instead_of_the_old_workspace_location(
    tmp_path, monkeypatch, module, kind,
):
    from backend.epub_manager import set_epub_progress
    monkeypatch.setattr(module, '_ADDON_DIR', str(tmp_path))
    set_epub_progress(str(tmp_path), 'A', 42, section_index=8, scroll_ratio=.7)
    set_epub_progress(str(tmp_path), 'B', 42, section_index=12, scroll_ratio=.2)
    class Note(dict):
        def note_type(self): return {'name': 'Incremento EPUB'}
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=5), get_note=lambda nid: Note())
    snapshot = {'card_id': 42, 'filename': 'book.epub', 'sections': [{}] * 20}
    monkeypatch.setattr(module, 'resolve_epub_reference', lambda *args: snapshot)
    monkeypatch.setattr(module, 'get_epub_daily_limit_status', lambda *args, **kw: {'enabled': False})
    main_reader = SimpleNamespace(show_epub_in_dock=Mock(), _epub_dock=SimpleNamespace(setObjectName=Mock()),
                                   current_epub_card_id=lambda: None)
    locations = []
    reference_reader = SimpleNamespace(_windows=[], _load=lambda *args: (),
        EpubReferenceWindow=lambda result, location, **kw:
            locations.append(location) or SimpleNamespace(setObjectName=Mock()))
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_module', lambda kind: main_reader if kind == 'epub' else reference_reader)
    entry = {'kind': kind, 'card_id': 42, 'name': 'incremento_epub_dock' if kind == 'epub'
             else 'incremento_epub_reference_saved_0', 'section': 3, 'offset': 100, 'scroll': .1}
    result = session._resolve(col, 'A', entry)
    session._open(entry, result)
    if kind == 'epub':
        assert main_reader.show_epub_in_dock.call_args.kwargs['section_index'] == 8
        assert main_reader.show_epub_in_dock.call_args.kwargs['scroll_ratio'] == .7
        assert main_reader.show_epub_in_dock.call_args.kwargs['focus_offset'] == -1
    else:
        assert locations == [{'card_id': 42, 'section': 8, 'offset': -1, 'scroll': .7}]


def test_new_workspace_captures_reader_layout_without_freezing_the_page(monkeypatch, module):
    monkeypatch.setattr(module, 'QTimer', lambda parent: Mock())
    replies, captured = [], []
    dock = SimpleNamespace(_view=SimpleNamespace(page=lambda: SimpleNamespace(
        runJavaScript=lambda js, callback: replies.append(callback))))
    session = module.WorkspaceSession(SimpleNamespace(), lambda: 'A')
    monkeypatch.setattr(session, '_describe', lambda dock: {
        'kind': 'pdf', 'name': 'incremento_pdf_dock', 'card_id': 42})
    session.capture([dock], captured.append)
    replies[0]({'card_id': 42, 'page': 31, 'scroll': .65, 'zoom': 1.5, 'controls': {'collapsed': False}})
    assert captured == [[{'kind': 'pdf', 'name': 'incremento_pdf_dock', 'card_id': 42,
                         'zoom': 1.5, 'controls': {'collapsed': False}}]]
