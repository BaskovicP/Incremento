"""Visible page buttons resolve saved connections, never browser-provided targets."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from document_links import add_document_link, replace_document_target


@pytest.fixture
def bridge(monkeypatch, tmp_path):
    pending, replies, opened, alive = [], [], [], [True]
    class Query:
        def __init__(self, **kwargs): self.options = kwargs
        def failure(self, callback):
            self.failed = callback
            return self
        def run_in_background(self): pending.append(self)
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, 'aqt.operations', SimpleNamespace(QueryOp=Query))
        path = Path(__file__).resolve().parents[1] / 'frontend/pdf_page_links.py'
        spec = importlib.util.spec_from_file_location('_pdf_page_links_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_ADDON_DIR', str(tmp_path))
    monkeypatch.setattr(module, 'get_active_profile', lambda: 'A')
    monkeypatch.setattr(module, 'get_pdf_daily_limit_status', lambda *a, **kw: {})
    monkeypatch.setattr(module, 'pdf_page_count', lambda path: 100, raising=False)
    documents = {}
    for cid in (7, 8, 9):
        path = tmp_path / 'user_files' / 'A' / 'pdfs' / f'{cid}.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'%PDF-1.7\n')
        documents[cid] = {'PDF_Filename': f'{cid}.pdf', 'Title': f'Book {cid}'}
    collection = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=cid),
                                 get_note=lambda nid: documents[nid])
    controller = module.PdfPageLinksBridge(profile='A', card_id=7, filename='7.pdf',
        is_current=lambda: alive[0], reply=replies.append,
        open_pdf=lambda snapshot, link: opened.append((snapshot, link)), owner=None)
    def finish():
        operation = pending.pop(0)
        result = operation.options['op'](collection)
        operation.options['success'](result)
    request = dict(cardId=7, page=3, generation=1, request=1, operation='list')
    return SimpleNamespace(module=module, controller=controller, pending=pending, replies=replies,
                           opened=opened, alive=alive, documents=documents, collection=collection,
                           root=str(tmp_path), finish=finish, request=request)


def test_visible_button_jumps_to_fresh_saved_destination_and_reverse_button_returns(bridge):
    link = add_document_link(bridge.root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42)
    assert bridge.controller.handle(bridge.request)
    bridge.finish()
    row = bridge.replies[-1]['links'][0]
    assert (row['title'], row['target_page'], row['available']) == ('Book 8', 42, True)
    # Replacing a saved destination while its button is visible must use the new target.
    replace_document_target(bridge.root, 'A', link, source_card_id=7, target_card_id=9, target_page=5)
    bridge.controller.handle({**bridge.request, 'operation': 'jump', 'id': link,
                              'direction': 'outgoing', 'mode': 'jump', 'target_card_id': 999})
    bridge.finish()
    assert bridge.opened[0][0]['card_id'] == 9
    assert bridge.opened[0][1]['target_page'] == 5
    reverse = bridge.module.PdfPageLinksBridge(profile='A', card_id=9, filename='9.pdf',
        is_current=lambda: True, reply=bridge.replies.append,
        open_pdf=lambda snapshot, row: bridge.opened.append((snapshot, row)), owner=None)
    request = {**bridge.request, 'cardId': 9, 'page': 5}
    reverse.handle(request)
    bridge.finish()
    assert bridge.replies[-1]['links'][0]['direction'] == 'incoming'
    reverse.handle({**request, 'operation': 'jump', 'id': link, 'direction': 'incoming', 'mode': 'jump'})
    bridge.finish()
    assert (bridge.opened[-1][0]['card_id'], bridge.opened[-1][1]['target_page']) == (7, 3)


@pytest.mark.parametrize('operation', ['recordings', 'link_recording'])
def test_recording_actions_use_only_the_current_page_and_drop_stale_callbacks(bridge, monkeypatch, operation):
    opened = []
    monkeypatch.setattr(bridge.module, 'open_recording_action', lambda *args, **kw: opened.append(args), raising=False)
    bridge.controller.handle(bridge.request)
    bridge.finish()
    assert bridge.controller.handle({**bridge.request, 'operation': operation, 'target_card_id': 999})
    bridge.finish()
    assert opened[0][0] == operation
    assert opened[0][1]['card_id'] == 7 and opened[0][1]['page'] == 3
    bridge.controller.handle({**bridge.request, 'operation': operation})
    bridge.alive[0] = False
    bridge.finish()
    assert len(opened) == 1


@pytest.mark.parametrize('change', [dict(cardId=8), dict(page=4), dict(request=0),
                                  dict(generation=2), dict(id=True), dict(direction='other')])
def test_forged_or_stale_button_cannot_open_another_pdf(bridge, change):
    link = add_document_link(bridge.root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42)
    bridge.controller.handle(bridge.request)
    bridge.finish()
    bridge.controller.handle({**bridge.request, 'operation': 'jump', 'id': link,
                              'direction': 'outgoing', 'mode': 'jump', **change})
    assert bridge.pending == []
    assert bridge.opened == []


@pytest.mark.parametrize('retire', ['close', 'new-page', 'new-document'])
def test_late_page_links_reply_is_dropped_after_reader_changes(bridge, retire):
    bridge.controller.handle(bridge.request)
    operation = bridge.pending.pop()
    result = operation.options['op'](bridge.collection)
    if retire == 'close':
        bridge.controller.close()
    elif retire == 'new-page':
        bridge.controller.handle({**bridge.request, 'page': 4, 'request': 2})
    else:
        bridge.alive[0] = False
    operation.options['success'](result)
    assert bridge.replies == []


def test_locked_destination_page_cannot_be_opened_from_a_visible_button(bridge, monkeypatch):
    link = add_document_link(bridge.root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42)
    bridge.controller.handle(bridge.request)
    bridge.finish()
    monkeypatch.setattr(bridge.module, 'get_pdf_daily_limit_status', lambda *a, **kw: {
        'enabled': True, 'enforcement_mode': 'hard_stop', 'allowed_max_page': 10})
    bridge.controller.handle({**bridge.request, 'operation': 'jump', 'id': link,
                              'direction': 'outgoing', 'mode': 'jump'})
    with pytest.raises(ValueError, match='locked'):
        bridge.pending.pop().options['op'](bridge.collection)
    assert bridge.opened == []


def test_a_page_removed_from_the_target_pdf_cannot_silently_jump_to_its_last_page(bridge, monkeypatch):
    link = add_document_link(bridge.root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42)
    bridge.controller.handle(bridge.request)
    bridge.finish()
    monkeypatch.setattr(bridge.module, 'pdf_page_count', lambda path: 5)
    bridge.controller.handle({**bridge.request, 'operation': 'jump', 'id': link,
                              'direction': 'outgoing', 'mode': 'jump'})
    with pytest.raises(ValueError, match='page unavailable'):
        bridge.pending.pop().options['op'](bridge.collection)
    assert bridge.opened == []


def test_relinked_source_cannot_create_buttons_for_the_previous_document(bridge):
    bridge.controller.handle(bridge.request)
    bridge.documents[7]['PDF_Filename'] = '9.pdf'
    with pytest.raises(ValueError, match='changed'):
        bridge.finish()
    assert bridge.replies == []


def test_link_picker_stays_usable_after_refresh_but_retires_when_the_source_page_changes(bridge, monkeypatch):
    pickers = []
    monkeypatch.setitem(sys.modules, 'document_link_ui', SimpleNamespace(
        link_pdf=lambda *args, **options: pickers.append(options)))
    bridge.controller.handle(bridge.request)
    bridge.finish()
    bridge.controller.handle({**bridge.request, 'operation': 'create'})
    bridge.finish()
    current = pickers[0]['is_current']
    assert pickers[0]['show_after'] is False
    bridge.controller.handle({**bridge.request, 'request': 2})
    assert current()
    bridge.controller.handle({**bridge.request, 'request': 3, 'page': 4})
    assert not current()


@pytest.mark.parametrize('reverse', [False, True])
def test_remove_visible_connection_from_either_endpoint_refreshes_both_readers(bridge, reverse):
    from document_links import list_pdf_page_links
    link = add_document_link(bridge.root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42)
    if reverse:
        bridge.controller.card_id, bridge.controller.filename = 8, '8.pdf'
        bridge.request.update(cardId=8, page=42)
    refreshed = []
    bridge.controller.refresh = lambda: refreshed.append(True)
    bridge.controller.handle(bridge.request)
    bridge.finish()
    assert bridge.controller.handle({**bridge.request, 'operation': 'remove', 'id': link,
                                     'direction': 'incoming' if reverse else 'outgoing'})
    bridge.finish()
    assert list_pdf_page_links(bridge.root, 'A', 7, 3) == []
    assert list_pdf_page_links(bridge.root, 'A', 8, 42) == []
    assert refreshed == [True]


def test_remove_rejects_a_connection_that_does_not_belong_to_the_current_page(bridge):
    from document_links import list_pdf_page_links
    link = add_document_link(bridge.root, 'A', source_card_id=7, source_kind='pdf', source_page=4,
                             target_card_id=8, target_page=42)
    bridge.controller.handle(bridge.request)
    bridge.finish()
    bridge.controller.handle({**bridge.request, 'operation': 'remove', 'id': link,
                              'direction': 'outgoing'})
    with pytest.raises(ValueError, match='unavailable'):
        bridge.finish()
    assert len(list_pdf_page_links(bridge.root, 'A', 7, 4)) == 1
