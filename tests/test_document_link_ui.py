"""The link flow previews a destination before persisting its selected spot."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from document_links import list_document_links


@pytest.fixture
def link_ui(monkeypatch, tmp_path):
    pending, displayed, previews = [], [], []
    class Signal:
        def __init__(self): self.callbacks = []
        def connect(self, callback): self.callbacks.append(callback)
        def emit(self):
            for callback in self.callbacks:
                callback()
    class Query:
        def __init__(self, **options): self.options = options
        def failure(self, callback): return self
        def run_in_background(self): pending.append(self)
    class Picker:
        def __init__(self, *args, **options):
            self.selected_card_id, self.accepted = 8, Signal()
            self.finished = Signal()
        def setWindowTitle(self, title): pass
    class Preview:
        def __init__(self, snapshot, **options):
            self.snapshot, self.options = snapshot, options
            self.accepted, self.selected_location, self.finished = Signal(), None, Signal()
            previews.append(self)
    package = ModuleType('_document_link_ui_test_pkg')
    package.__path__ = [str(Path(__file__).resolve().parents[1] / 'frontend')]
    books = SimpleNamespace(_DocumentBookshelfDialog=Picker,
        _load_bookshelf_entries=lambda *a, **kw: [SimpleNamespace(kind='PDF')])
    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, package.__name__, package)
        patch.setitem(sys.modules, package.__name__ + '.pdf_bookshelf', books)
        patch.setitem(sys.modules, package.__name__ + '.pdf_destination_dialog', SimpleNamespace(PdfDestinationDialog=Preview))
        patch.setitem(sys.modules, package.__name__ + '.pdf_page_links', SimpleNamespace(pdf_page_count=lambda path: 10))
        patch.setitem(sys.modules, 'aqt.operations', SimpleNamespace(QueryOp=Query))
        patch.setitem(sys.modules, 'aqt.qt', SimpleNamespace(**{name: object for name in (
            'QDialog', 'QHBoxLayout', 'QInputDialog', 'QLabel', 'QListWidget', 'QPushButton', 'QVBoxLayout', 'Qt')}))
        spec = importlib.util.spec_from_file_location(package.__name__ + '.document_link_ui',
            Path(package.__path__[0]) / 'document_link_ui.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    # Keep only this test's synthetic relative-import boundaries installed.
    for name, value in ((package.__name__, package), (package.__name__ + '.pdf_bookshelf', books),
        (package.__name__ + '.pdf_destination_dialog', SimpleNamespace(PdfDestinationDialog=Preview)),
        (package.__name__ + '.pdf_page_links', SimpleNamespace(pdf_page_count=lambda path: 10))):
        monkeypatch.setitem(sys.modules, name, value)
    monkeypatch.setattr(module, '_ADDON_DIR', str(tmp_path))
    monkeypatch.setattr(module, 'get_active_profile', lambda: 'A')
    monkeypatch.setattr(module, '_keep', displayed.append)
    monkeypatch.setattr(module, '_refresh_page_links', lambda: None)
    monkeypatch.setattr(module, 'get_pdf_daily_limit_status', lambda *a, **kw: {}, raising=False)
    documents = {}
    for cid in (7, 8, 9):
        path = tmp_path / 'user_files' / 'A' / 'pdfs' / f'{cid}.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'%PDF-1.7\n')
        documents[cid] = {'PDF_Filename': f'{cid}.pdf', 'Title': f'Book {cid}'}
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=cid), get_note=lambda nid: documents[nid])
    def finish():
        request = pending.pop(0)
        result = request.options['op'](col)
        request.options['success'](result)
    return SimpleNamespace(module=module, pending=pending, displayed=displayed, previews=previews,
        finish=finish, documents=documents, col=col, root=str(tmp_path))


def test_choosing_a_document_opens_a_live_preview_and_waits_for_explicit_destination_confirmation(link_ui):
    chosen = []
    link_ui.module.choose_pdf(chosen.append)
    link_ui.finish()
    link_ui.displayed[0].accepted.emit()
    link_ui.finish()
    assert len(link_ui.previews) == 1
    preview = link_ui.previews[0]
    assert preview.snapshot['card_id'] == 8
    assert chosen == []
    preview.selected_location = {'card_id': 8, 'page': 4, 'page_y': .65, 'scroll_ratio': .25}
    preview.accepted.emit()
    assert chosen == [preview.selected_location]


def test_confirmed_preview_saves_its_page_and_precise_spot_only_after_validation(link_ui, monkeypatch):
    callbacks = []
    monkeypatch.setattr(link_ui.module, 'choose_pdf', lambda callback, **options: callbacks.append(callback))
    link_ui.module.link_pdf({'card_id': 7, 'kind': 'pdf', 'page': 3}, show_after=False)
    assert list_document_links(link_ui.root, 'A', 7) == []
    target = link_ui.module.resolve_pdf_reference(link_ui.root, 'A', link_ui.col, 8)
    callbacks[0]({**target, 'page': 4, 'page_y': .65, 'scroll_ratio': .25})
    assert list_document_links(link_ui.root, 'A', 7) == []
    link_ui.finish()
    row = list_document_links(link_ui.root, 'A', 7)[0]
    assert (row['target_card_id'], row['target_page'], row['target_y'], row['target_scroll']) == (8, 4, .65, .25)


def test_replaced_target_cannot_be_saved_as_the_document_the_user_previewed(link_ui, monkeypatch):
    callbacks = []
    monkeypatch.setattr(link_ui.module, 'choose_pdf', lambda callback, **options: callbacks.append(callback))
    link_ui.module.link_pdf({'card_id': 7, 'kind': 'pdf', 'page': 3}, show_after=False)
    target = link_ui.module.resolve_pdf_reference(link_ui.root, 'A', link_ui.col, 8)
    callbacks[0]({**target, 'page': 4, 'page_y': .65, 'scroll_ratio': .25})
    link_ui.documents[8]['PDF_Filename'] = '9.pdf'
    with pytest.raises(ValueError, match='changed'):
        link_ui.pending[0].options['op'](link_ui.col)
    assert list_document_links(link_ui.root, 'A', 7) == []
