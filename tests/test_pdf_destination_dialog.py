"""Destination selection is read-only until an explicit, validated confirmation."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from pdf_reader_state import PdfReaderState


@pytest.fixture
def destination(monkeypatch, tmp_path):
    pending, accepted, scripts = [], [], []
    class Query:
        def __init__(self, **options): self.options = options
        def failure(self, callback):
            self.failed = callback
            return self
        def run_in_background(self): pending.append(self)
    class Dialog:
        pass
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, 'aqt.operations', SimpleNamespace(QueryOp=Query))
        patch.setitem(sys.modules, 'aqt.qt', SimpleNamespace(QDialog=Dialog, QVBoxLayout=object, Qt=object))
        path = Path(__file__).resolve().parents[1] / 'frontend/pdf_destination_dialog.py'
        spec = importlib.util.spec_from_file_location('_destination_dialog_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    profile, source_current = ['A'], [True]
    monkeypatch.setattr(module, 'get_active_profile', lambda: profile[0])
    monkeypatch.setattr(module, '_ADDON_DIR', str(tmp_path))
    monkeypatch.setattr(module, 'pdf_page_count', lambda path: 100)
    monkeypatch.setattr(module, 'get_pdf_daily_limit_status', lambda *a, **kw: {})
    path = tmp_path / 'user_files' / 'A' / 'pdfs' / 'target.pdf'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'%PDF-1.7\n')
    snapshot = {'card_id': 8, 'filename': 'target.pdf', 'path': str(path), 'title': 'Target'}
    documents = {8: {'PDF_Filename': 'target.pdf', 'Title': 'Target'}}
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=cid), get_note=lambda nid: documents[nid])
    dialog = module.PdfDestinationDialog.__new__(module.PdfDestinationDialog)
    dialog.state = PdfReaderState('A', 8, 'target.pdf', page=3, scroll_ratio=.4)
    dialog._snapshot, dialog._nonce = snapshot, dialog.state.nonce
    dialog._source_current = lambda: source_current[0]
    dialog._closed, dialog._saving, dialog.selected_location = False, False, None
    dialog.view = SimpleNamespace(stop=lambda: None)
    dialog.page = SimpleNamespace(runJavaScript=scripts.append, deleteLater=lambda: None)
    dialog.accept = lambda: accepted.append(dialog.selected_location)
    dialog.reject = dialog._dispose
    return SimpleNamespace(module=module, dialog=dialog, pending=pending, accepted=accepted, scripts=scripts,
        profile=profile, source_current=source_current, col=col, documents=documents, root=tmp_path)


def test_confirming_a_preview_captures_its_exact_page_and_spot_without_writing_a_link(destination):
    d = destination
    d.dialog.command('pick', {'page': 3, 'page_y': .75})
    assert d.accepted == []
    assert len(d.pending) == 1
    request = d.pending[0]
    result = request.options['op'](d.col)
    request.options['success'](result)
    assert len(d.accepted) == 1
    assert {key: d.accepted[0][key] for key in ('card_id', 'page', 'page_y', 'scroll_ratio')} == {
        'card_id': 8, 'page': 3, 'page_y': .75, 'scroll_ratio': .4}
    assert not (d.root / 'user_files' / 'A' / 'incremento.db').exists()


@pytest.mark.parametrize('point', [None, True, -1, 2, float('nan'), float('inf'), '.5'])
def test_invalid_preview_spots_cannot_confirm_or_write(destination, point):
    destination.dialog.command('pick', {'page': 3, 'page_y': point})
    assert destination.pending == []
    assert destination.accepted == []


@pytest.mark.parametrize('retire', ['cancel', 'profile', 'source'])
def test_late_destination_validation_is_dropped_after_cancel_or_source_change(destination, retire):
    d = destination
    d.dialog.command('pick', {'page': 3, 'page_y': .5})
    request = d.pending[0]
    result = request.options['op'](d.col)
    if retire == 'cancel':
        d.dialog.reject()
    elif retire == 'profile':
        d.profile[0] = 'B'
    else:
        d.source_current[0] = False
    request.options['success'](result)
    assert d.accepted == []
    assert d.dialog.selected_location is None


def test_a_changed_target_cannot_be_confirmed_under_the_previous_preview(destination):
    d = destination
    d.dialog.command('pick', {'page': 3, 'page_y': .5})
    d.documents[8]['PDF_Filename'] = 'other.pdf'
    with pytest.raises(ValueError):
        d.pending[0].options['op'](d.col)
    assert d.accepted == []


def test_preview_confirmation_rechecks_daily_locks_and_prevents_duplicate_requests(destination, monkeypatch):
    d = destination
    d.dialog.command('pick', {'page': 3, 'page_y': .5})
    d.dialog.command('pick', {'page': 3, 'page_y': .7})
    assert len(d.pending) == 1
    monkeypatch.setattr(d.module, 'get_pdf_daily_limit_status', lambda *a, **kw: {
        'enabled': True, 'enforcement_mode': 'hard_stop', 'allowed_max_page': 2})
    with pytest.raises(ValueError, match='locked'):
        d.pending[0].options['op'](d.col)
    assert d.accepted == []


@pytest.mark.parametrize('action', ['pin', 'open', 'copy', 'extract', 'page_links'])
def test_destination_preview_cannot_trigger_reader_or_extraction_actions(destination, action):
    destination.dialog.command(action, {'page': 3, 'page_y': .5})
    assert destination.pending == []
    assert destination.accepted == []
