"""Exercise real workspace callbacks with only Qt and Anki boundaries replaced."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def workspace(monkeypatch):
    class Dock:
        def __init__(self, *args):
            self.floating = True
        def setFloating(self, value):
            self.floating = value
        def isFloating(self):
            return self.floating
        def show(self):
            pass
        def close(self):
            self.closeEvent(None)
        def closeEvent(self, event):
            pass
    class Page:
        def __init__(self, *args):
            pass
    pending = []
    class Query:
        def __init__(self, **kwargs):
            self.options = kwargs
        def failure(self, callback):
            self.failed = callback
            return self
        def run_in_background(self):
            pending.append(self)
    qt = ModuleType("aqt.qt")
    qt.QApplication = SimpleNamespace(focusWidget=lambda: None)
    qt.QDockWidget = Dock
    qt.QSignalBlocker = object
    qt.Qt = SimpleNamespace(Orientation=SimpleNamespace(Horizontal="horizontal"))
    qt.QUrl = object
    mw = SimpleNamespace(splitDockWidget=lambda *args: None)
    aqt = ModuleType("aqt")
    aqt.mw = mw
    core = ModuleType("PyQt6.QtWebEngineCore")
    core.QWebEnginePage = Page
    core.QWebEngineProfile = object
    core.QWebEngineSettings = object
    widget = ModuleType("PyQt6.QtWebEngineWidgets")
    widget.QWebEngineView = object
    profile = ["A"]
    with monkeypatch.context() as patch:
        for key, module in {
            "aqt": aqt, "aqt.qt": qt, "aqt.operations": SimpleNamespace(QueryOp=Query),
            "aqt.utils": SimpleNamespace(tooltip=lambda text: None),
            "PyQt6.QtWebEngineCore": core, "PyQt6.QtWebEngineWidgets": widget,
        }.items():
            patch.setitem(sys.modules, key, module)
        path = Path(__file__).resolve().parents[1] / "frontend/pdf_reference_workspace.py"
        spec = importlib.util.spec_from_file_location("_reference_workspace_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_active_profile", lambda: profile[0])
    return SimpleNamespace(module=module, profile=profile, pending=pending)


def test_nonce_and_profile_bind_the_reference_bridge_and_forbid_stale_close_messages(workspace):
    from pdf_reader_state import PdfReaderState
    module = workspace.module
    state = PdfReaderState("A", 7, "book.pdf", page=2, max_page=10)
    calls = []
    page = module._ReferencePage(None, None, None, state, lambda *args: calls.append(args))
    message = json.dumps({"action": "pin", "page": 3})
    page.javaScriptConsoleMessage(None, "__incremento_reference__:wrong:" + message, 0, "")
    assert not calls
    page.javaScriptConsoleMessage(None, "__incremento_reference__:" + state.nonce + ":" + message, 0, "")
    assert state.page == 3
    assert calls[0][0] == "pin"
    workspace.profile[0] = "B"
    page.javaScriptConsoleMessage(None, "__incremento_reference__:" + state.nonce + ":" + message, 0, "")
    assert len(calls) == 1
    state.close()
    page.javaScriptConsoleMessage(None, "__incremento_reference__:" + state.nonce + ":" + message, 0, "")
    assert len(calls) == 1


def test_pin_keeps_the_same_view_position_and_retires_previous_pinned_reader(workspace):
    from pdf_reader_state import PdfReaderState
    module = workspace.module
    def window(page):
        reader = module.ReferenceWindow.__new__(module.ReferenceWindow)
        reader.state = PdfReaderState("A", 7, "book.pdf", page=page, scroll_ratio=.5)
        reader.owner = None
        reader.view = SimpleNamespace(stop=lambda: None)
        reader.page = SimpleNamespace(deleteLater=lambda: None)
        reader.floating = True
        module._windows.append(reader)
        return reader
    old, new = window(2), window(40)
    old.floating = False
    original_view = new.view
    new.pin()
    assert old.state.closed
    assert not new.isFloating()
    assert new.view is original_view
    assert (new.state.page, new.state.scroll_ratio) == (40, .5)
    module.reset_for_profile_switch()
    assert new.state.closed
    assert module._windows == []


def test_profile_close_retires_pending_reference_load_before_ui_creation(workspace, monkeypatch):
    module = workspace.module
    opened = []
    monkeypatch.setattr(module, "ReferenceWindow", lambda *a, **kw: opened.append(kw))
    module.open_reference(7)
    pending = workspace.pending[0]
    module.reset_for_profile_switch()
    pending.options["success"](({"card_id": 7}, 10))
    assert opened == []


def test_preview_request_does_not_cancel_a_pending_pinned_reader(workspace, monkeypatch):
    module = workspace.module
    opened = []
    class Window:
        def __init__(self, snapshot, **options):
            self.beside = options['beside']
            opened.append(snapshot['card_id'])
        def isFloating(self): return not self.beside
        def show(self): pass
    monkeypatch.setattr(module, 'ReferenceWindow', Window)
    module.open_reference(7, beside=True)
    module.open_reference(8, beside=False)
    for pending, cid in zip(workspace.pending, [7, 8]):
        pending.options['success'](({'card_id': cid}, 10))
    assert opened == [7, 8]


def test_deleted_or_relinked_reference_cannot_copy_a_misleading_citation(workspace, monkeypatch):
    from pdf_reader_state import PdfReaderState
    module, copied = workspace.module, []
    window = module.ReferenceWindow.__new__(module.ReferenceWindow)
    window.state = PdfReaderState('A', 7, 'original.pdf', page=3)
    window.windowTitle = lambda: 'Original'
    monkeypatch.setattr(module, 'set_reader_anchor_clipboard', lambda *args: copied.append(args))
    monkeypatch.setattr(module, 'resolve_pdf_reference', lambda *a: {'filename': 'replacement.pdf'})
    window.command('copy')
    assert copied == []
    with pytest.raises(ValueError):
        workspace.pending[0].options['op'](object())
    assert copied == []


def test_citation_keeps_its_captured_page_during_background_validation(workspace, monkeypatch):
    from pdf_reader_state import PdfReaderState
    from reader_links import reader_anchor_command_from_html
    module, copied = workspace.module, []
    window = module.ReferenceWindow.__new__(module.ReferenceWindow)
    window.state = PdfReaderState('A', 7, 'book.pdf', page=3)
    monkeypatch.setattr(module, 'set_reader_anchor_clipboard', lambda *args: copied.append(args))
    monkeypatch.setattr(module, 'resolve_pdf_reference', lambda *a: {
        'filename': 'book.pdf', 'path': '/unused/book.pdf', 'title': 'Source'})
    monkeypatch.setattr(module, 'get_pdf_daily_limit_status', lambda *a, **kw: {})
    window.command('copy')
    window.state.page = 8
    pending = workspace.pending[0]
    pending.options['success'](pending.options['op'](object()))
    command = reader_anchor_command_from_html(copied[0][0])
    assert json.loads(command.split(':', 1)[1])['page'] == 3


def test_visible_page_link_jump_keeps_the_reference_in_its_own_pane(workspace, monkeypatch):
    from pdf_reader_state import PdfReaderState
    module = workspace.module
    window = module.ReferenceWindow.__new__(module.ReferenceWindow)
    window.state = PdfReaderState('A', 7, 'book.pdf', page=3)
    window.owner, window.floating = object(), False
    window.page = SimpleNamespace(runJavaScript=lambda *args: None)
    created, opened = [], []
    class Bridge:
        def __init__(self, **options):
            self.options = options
            created.append(self)
        def current(self): return True
        def handle(self, payload): self.payload = payload
    monkeypatch.setitem(sys.modules, 'pdf_page_links', SimpleNamespace(PdfPageLinksBridge=Bridge))
    monkeypatch.setattr(module, 'open_reference', lambda *a, **kw: opened.append((a, kw)))
    window.command('page_links', {'operation': 'list', 'page': 3})
    assert created[0].payload['operation'] == 'list'
    created[0].options['open_pdf']({'card_id': 8}, {'target_page': 42, 'target_scroll': 0})
    assert opened[0][0] == (8, 42)
    assert opened[0][1]['beside'] is True
    assert opened[0][1]['owner'] is window.owner
