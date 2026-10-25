"""Shared document edits, independent pane navigation, and stale-reader safety."""
import json
from types import SimpleNamespace

import pytest

from pdf_reader_state import PdfReaderState


@pytest.fixture
def reader(tmp_path, monkeypatch):
    import pdf_shared_reader as module
    from backend import pdf_highlights, reader_bookmarks
    profile = ['A']
    state = PdfReaderState('A', 7, 'book.pdf', page=4, max_page=12)
    scripts, changed = [], []
    service = SimpleNamespace(
        _ADDON_DIR=str(tmp_path), _active_profile=lambda: profile[0],
        load_highlights=pdf_highlights.load_highlights,
        add_highlight=pdf_highlights.add_highlight,
        update_highlight=pdf_highlights.update_highlight,
        remove_highlight=pdf_highlights.remove_highlight,
        list_reader_bookmarks=reader_bookmarks.list_reader_bookmarks,
        add_reader_bookmark=reader_bookmarks.add_reader_bookmark,
        delete_reader_bookmark=reader_bookmarks.delete_reader_bookmark,
        delete_pdf_card_source_for_highlight=lambda *a: None,
    )
    owner = SimpleNamespace(state=state, page=SimpleNamespace(runJavaScript=scripts.append), command=lambda *a: None)
    bridge = module.SharedPdfReader(owner, service=service,
                                  on_change=lambda kind: changed.append(kind))
    return SimpleNamespace(bridge=bridge, state=state, service=service,
                           scripts=scripts, profile=profile, changed=changed)


def send(reader, command, payload):
    return reader.bridge.handle(command + ':' + json.dumps(payload))


def test_side_controls_save_its_own_preference_and_reject_stale_readers(reader):
    saved = []
    reader.service.save_pdf_controls_collapsed = lambda value, **kw: saved.append((value, kw))
    send(reader, 'incremento_pdf_controls', {'cardId': 7, 'collapsed': False})
    assert saved == [(False, {'profile': 'A', 'reading_only': True})]
    for payload in ({'cardId': 8, 'collapsed': True}, {'collapsed': True},
                    {'cardId': 7, 'collapsed': 'false'}):
        send(reader, 'incremento_pdf_controls', payload)
    reader.profile[0] = 'B'
    send(reader, 'incremento_pdf_controls', {'cardId': 7, 'collapsed': True})
    assert len(saved) == 1


@pytest.mark.parametrize('main_open', [False, True])
def test_side_sync_refreshes_replaced_byte_sources_in_the_main_or_all_matching_panes(reader, main_open):
    callbacks, main, panes = [], [], []
    s = reader.service
    s._annotation_queue = SimpleNamespace(request=lambda *args, callback, **kw: callbacks.append(callback))
    s.current_pdf_card_id = lambda: 7 if main_open else None
    s._push_pdf_highlights = lambda *_: None
    s._reload_current_pdf_annotations = main.append
    s._refresh_reference_pdf_state = lambda *args, **kw: panes.append((args, kw))
    reader.bridge.owner._reader_path = '/unused/reader.pdf'
    reader.bridge.owner.reload_reader = lambda *_: pytest.fail('the shared refresh owns all matching panes')
    reader.bridge.sync_annotations(dirty=True)
    result = {'reader_path': '/unused/reader.pdf', 'reader_changed': True, 'appearance_changed': False}
    callbacks.pop()(result, None)
    assert main == ([result] if main_open else [])
    assert panes == ([] if main_open else [((7, 'highlights'), {'annotation_result': result})])


def test_side_highlight_add_edit_delete_uses_the_original_documents_storage(reader):
    highlight = {'id': 'shared', 'page': 4, 'text': 'A passage', 'color': 'yellow',
                 'rects': [{'x': 10, 'y': 20, 'w': 30, 'h': 12}]}
    send(reader, 'incremento_pdf_hl_add', {'cardId': 7, 'highlight': highlight})
    saved = reader.service.load_highlights(reader.service._ADDON_DIR, 'A', 7)
    assert len(saved) == 1 and saved[0]['text'] == 'A passage'
    highlight['color'] = 'green'
    send(reader, 'incremento_pdf_hl_update', {'cardId': 7, 'highlight': highlight})
    assert reader.service.load_highlights(reader.service._ADDON_DIR, 'A', 7)[0]['color'] == 'green'
    send(reader, 'incremento_pdf_hl_del', {'cardId': 7, 'id': 'shared'})
    assert reader.service.load_highlights(reader.service._ADDON_DIR, 'A', 7) == []
    assert reader.changed == ['highlights', 'highlights', 'highlights']


@pytest.mark.parametrize('invalid', ['other-card', 'locked-page', 'closed', 'profile-switch'])
def test_side_reader_rejects_invalid_edits_without_writing(reader, invalid):
    card_id, page = 7, 4
    if invalid == 'other-card':
        card_id = 8
    if invalid == 'locked-page':
        page = 13
    if invalid == 'closed':
        reader.state.close()
    if invalid == 'profile-switch':
        reader.profile[0] = 'B'
    send(reader, 'incremento_pdf_hl_add', {'cardId': card_id, 'highlight': {
        'id': 'bad', 'page': page, 'text': 'Bad', 'rects': [{'x': 0, 'y': 0, 'w': 1, 'h': 1}]}})
    assert reader.service.load_highlights(reader.service._ADDON_DIR, 'A', 7) == []
    assert reader.changed == []


def test_side_navigation_keeps_independent_position_and_respects_the_limit(reader):
    reader.bridge.handle('incremento_pdf_nav:7:9')
    send(reader, 'incremento_pdf_scroll', {'cardId': 7, 'scrollRatio': .6})
    assert (reader.state.page, reader.state.scroll_ratio) == (9, .6)
    reader.bridge.handle('incremento_pdf_nav:7:13')
    reader.bridge.handle('incremento_pdf_nav:8:2')
    assert (reader.state.page, reader.state.scroll_ratio) == (9, .6)
    assert reader.changed == []


def test_side_bookmarks_are_shared_with_the_main_reader_and_other_profiles_are_untouched(reader):
    send(reader, 'incremento_pdf_bookmark_add', {'cardId': 7, 'page': 4})
    saved = reader.service.list_reader_bookmarks(reader.service._ADDON_DIR, 'A', 7, 'pdf')
    assert len(saved) == 1 and saved[0]['location']['page'] == 4
    assert reader.service.list_reader_bookmarks(reader.service._ADDON_DIR, 'B', 7, 'pdf') == []
    send(reader, 'incremento_pdf_bookmark_delete', {'cardId': 7, 'id': saved[0]['id']})
    assert reader.service.list_reader_bookmarks(reader.service._ADDON_DIR, 'A', 7, 'pdf') == []
    assert reader.changed == ['bookmarks', 'bookmarks']


def test_review_and_unknown_commands_are_not_forwarded_to_the_primary_reader(reader):
    assert reader.bridge.handle('incremento_pdf_finished:7') is False
    assert reader.bridge.handle('incremento_pdf_review_all:7:4') is False
    assert reader.bridge.handle('javascript:alert(1)') is False
    assert reader.changed == []


def test_editing_a_side_highlight_note_updates_the_shared_note(reader):
    highlight = {'id': 'note', 'page': 4, 'text': 'Passage', 'rects': [{'x': 1, 'y': 1, 'w': 5, 'h': 2}]}
    send(reader, 'incremento_pdf_hl_add', {'cardId': 7, 'highlight': highlight})
    from backend.pdf_highlights import update_highlight_note
    reader.service.update_highlight_note = update_highlight_note
    reader.service.t = lambda key: key
    reader.service.HighlightNoteDialog = lambda *a, **kw: SimpleNamespace(exec=lambda: True, note_text=lambda: 'Shared note')
    send(reader, 'incremento_pdf_hl_note', {'id': 'note'})
    assert reader.service.load_highlights(reader.service._ADDON_DIR, 'A', 7)[0]['note'] == 'Shared note'


def test_profile_switch_during_note_dialog_cannot_save_the_old_note(reader):
    highlight = {'id': 'note', 'page': 4, 'text': 'Passage', 'rects': [{'x': 1, 'y': 1, 'w': 5, 'h': 2}]}
    send(reader, 'incremento_pdf_hl_add', {'cardId': 7, 'highlight': highlight})
    reader.service.t = lambda key: key
    def accept():
        reader.profile[0] = 'B'
        return True
    reader.service.HighlightNoteDialog = lambda *a, **kw: SimpleNamespace(exec=accept, note_text=lambda: 'Stale')
    send(reader, 'incremento_pdf_hl_note', {'id': 'note'})
    assert not reader.service.load_highlights(reader.service._ADDON_DIR, 'A', 7)[0].get('note')


def test_explicit_read_marker_is_shared_without_moving_the_pane(reader):
    from backend.pdf_manager import set_read_page, get_read_page
    reader.service.set_read_page = set_read_page
    send(reader, 'incremento_pdf_mark_read', {'cardId': 7, 'readPage': 6, 'anchor': None})
    assert get_read_page(reader.service._ADDON_DIR, 'A', 7) == 6
    assert reader.state.page == 4
    assert reader.changed == ['reading']


def test_manual_navigation_retires_a_pending_side_search(reader, monkeypatch):
    import sys
    pending = []
    class Query:
        def __init__(self, **kwargs): self.options = kwargs
        def failure(self, callback): return self
        def run_in_background(self): pending.append(self)
    monkeypatch.setitem(sys.modules, 'aqt.operations', SimpleNamespace(QueryOp=Query))
    send(reader, 'incremento_pdf_find', {'query': 'passage'})
    reader.bridge.handle('incremento_pdf_nav:7:9')
    pending[0].options['success']([{'page': 2, 'snippet': 'passage'}])
    assert reader.scripts == []
    assert reader.state.page == 9


def test_full_side_search_keeps_all_results_when_a_hit_is_chosen(reader, monkeypatch):
    import sys
    dialogs = []
    class Dialog:
        def __init__(self, owner, **options):
            self.options = options
            self._search_all_btn = SimpleNamespace(hide=lambda: None)
            dialogs.append(self)
        def show(self): pass
    monkeypatch.setitem(sys.modules, 'current_document_search_dialog', SimpleNamespace(_CurrentDocumentSearchDialog=Dialog))
    reader.bridge.owner.windowTitle = lambda: 'Side book'
    reader.service.search_pdf_text_index_for_card = lambda *a, **kw: [(2, 'first'), (5, 'second'), (20, 'locked')]
    reader.service._pdf_search_snippet = lambda text, query, **kw: text
    retired = []
    reader.bridge.owner._search_dialog = SimpleNamespace(
        close=lambda: retired.append('close'), deleteLater=lambda: retired.append('delete'))
    previous_generation = reader.bridge.search_generation
    reader.bridge.search_dialog()
    assert retired == ['close', 'delete']
    assert reader.bridge.search_generation > previous_generation
    options = dialogs[0].options
    hits = options['search_hits_fn']('word')
    options['open_hit_fn'](hits[1], 1, 'word')
    assert reader.bridge.search['hits'] == hits
    assert reader.bridge.search['activeIndex'] == 1
    send(reader, 'incremento_pdf_find_nav', {'direction': -1})
    assert reader.bridge.search['activeIndex'] == 0
    assert 'incrementoPdfNav?.(-2)' in reader.scripts[-2]


def test_side_reader_retains_its_own_printed_labels_for_citations(reader):
    reader.service.configured_pdf_citation_page_numbering = lambda: 'both'
    reader.service.t = lambda key, **kw: f"{kw['label']} (PDF {kw['page']})"
    assert send(reader, 'incremento_pdf_page_labels', {'cardId': 7, 'filename': 'book.pdf', 'labels': ['iv', 'v']})
    assert reader.bridge.citation_page(2) == 'v (PDF 2)'
    assert reader.bridge.citation_page(3) == '3'
    send(reader, 'incremento_pdf_page_labels', {'cardId': 7, 'filename': 'other.pdf', 'labels': ['wrong']})
    assert reader.bridge.citation_page(1) == 'iv (PDF 1)'
    send(reader, 'incremento_pdf_page_labels', {'cardId': 7, 'filename': 'book.pdf', 'labels': None})
    assert reader.bridge.citation_page(1) == '1'


@pytest.mark.parametrize('command,payload,expected', [
    ('incremento_pdf_zoom', '7:2.5', 2.5), ('incremento_pdf_zoom', '8:2.5', 1),
    ('incremento_pdf_zoom', '7:9', 1), ('incremento_pdf_zoom', '7:nan', 1),
])
def test_side_zoom_is_local_and_rejects_invalid_or_other_document_commands(reader, command, payload, expected):
    reader.bridge.handle(command + ':' + payload)
    assert reader.state.zoom == expected
    assert reader.changed == []


def test_side_appearance_and_exact_read_anchor_are_saved_for_its_document(reader):
    from backend.pdf_manager import set_pdf_appearance_mode, get_pdf_appearance_mode, set_read_page, get_read_anchor
    reader.service.set_pdf_appearance_mode = set_pdf_appearance_mode
    reader.service.set_read_page = set_read_page
    assert send(reader, 'incremento_pdf_appearance', {'cardId': 7, 'mode': 'night'})
    assert get_pdf_appearance_mode(reader.service._ADDON_DIR, 'A', 7) == 'night'
    assert get_pdf_appearance_mode(reader.service._ADDON_DIR, 'A', 8) is None
    anchor = {'page': 4, 'x': 20, 'y': 30, 'w': 40, 'h': 10, 'text': 'exact row'}
    assert send(reader, 'incremento_pdf_mark_read', {'cardId': 7, 'readPage': 4, 'anchor': anchor})
    assert get_read_anchor(reader.service._ADDON_DIR, 'A', 7) == anchor
    assert reader.state.page == 4


def test_side_custom_color_reply_is_scoped_to_the_live_reader(reader, monkeypatch):
    import sys
    def choose(*args, **kwargs):
        assert kwargs['profile'] == 'A'
        return '#123456'
    monkeypatch.setitem(sys.modules, 'highlight_color_dialog', SimpleNamespace(choose_highlight_color=choose))
    send(reader, 'incremento_pdf_hl_color', {'cardId': 7, 'currentColor': 'yellow'})
    assert reader.scripts == ['window.incrementoPickPdfHighlightColor?.("#123456");']
    def stale(*args, **kwargs):
        reader.profile[0] = 'B'
        return '#abcdef'
    monkeypatch.setitem(sys.modules, 'highlight_color_dialog', SimpleNamespace(choose_highlight_color=stale))
    send(reader, 'incremento_pdf_hl_color', {'cardId': 7, 'currentColor': 'yellow'})
    assert len(reader.scripts) == 1


def test_side_contents_can_jump_and_save_an_exact_place_but_rejects_stale_callbacks(reader, monkeypatch):
    import sys
    popups = []
    class Popup:
        def __init__(self, owner, **options):
            self.options = options
            popups.append(self)
        def show_at(self, view): pass
    monkeypatch.setitem(sys.modules, 'reader_contents_popup', SimpleNamespace(ReaderContentsPopup=Popup))
    reader.bridge.owner.view = object()
    send(reader, 'incremento_pdf_contents', {'cardId': 7, 'token': 3, 'totalPages': 20,
        'location': {'page': 4, 'scrollRatio': .6},
        'entries': [{'id': 0, 'title': 'Chapter', 'depth': 0, 'page': 2},
                    {'id': 1, 'title': 'Locked', 'depth': 0, 'page': 18}]})
    options = popups[0].options
    assert [row['page'] for row in options['entries']] == [2]
    options['save_place']('Named spot')
    saved = reader.service.list_reader_bookmarks(reader.service._ADDON_DIR, 'A', 7, 'pdf')
    assert saved[0]['label'] == 'Named spot' and saved[0]['location']['scroll_ratio'] == .6
    options['open_entry'](options['entries'][0])
    assert 'incrementoPdfContentsJump?.(' in reader.scripts[-1]
    reader.state.close()
    options['save_place']('Stale')
    options['open_entry'](options['entries'][0])
    assert len(reader.scripts) == 1
    assert reader.service.list_reader_bookmarks(reader.service._ADDON_DIR, 'A', 7, 'pdf')[0]['label'] == 'Named spot'


@pytest.mark.parametrize('retire', ['close', 'profile'])
def test_late_inline_search_does_not_touch_a_retired_reader(reader, monkeypatch, retire):
    import sys
    pending = []
    class Query:
        def __init__(self, **kwargs): self.options = kwargs
        def failure(self, callback): return self
        def run_in_background(self): pending.append(self)
    monkeypatch.setitem(sys.modules, 'aqt.operations', SimpleNamespace(QueryOp=Query))
    reader.bridge.find('word')
    if retire == 'close':
        reader.state.close()
    else:
        reader.profile[0] = 'B'
    pending[0].options['success']([{'page': 2, 'snippet': 'word'}])
    assert reader.scripts == []
