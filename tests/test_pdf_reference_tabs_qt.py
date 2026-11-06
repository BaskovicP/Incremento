"""PDF link navigation from real Qt tab groups, without a browser or user data."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize('placed', [False, True], ids=['grouped-preview', 'independent-reader'])
def test_open_beside_from_second_pdf_tab_keeps_source_and_opens_another_tab(placed):
    script = dedent('''
        import sys, types
        from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
        app = QtWidgets.QApplication([])
        main = QtWidgets.QMainWindow()
        main.resize(1200, 800)
        main.setCentralWidget(QtWidgets.QLabel('Synthetic reviewer'))
        main.col = object()
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtGui, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        aqt = types.ModuleType('aqt')
        aqt.mw = main
        pending, errors = [], []
        class Query:
            def __init__(self, **options): self.options = options
            def failure(self, callback): self.failed = callback; return self
            def run_in_background(self): pending.append(self)
        def drain():
            while pending:
                query = pending.pop(0)
                query.options['success'](query.options['op'](main.col))
            app.processEvents()
        def wait_until(predicate):
            deadline = QtCore.QDeadlineTimer(1500)
            while not predicate() and not deadline.hasExpired():
                app.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 20)
            return predicate()
        # Replace document/annotation storage and rendering at their boundaries.
        class Reader:
            def __init__(self, owner):
                self.service = types.SimpleNamespace(_ADDON_DIR='/unused',
                    _initial_pdf_annotation_result=lambda *args: {},
                    _annotation_queue=types.SimpleNamespace(retain=lambda *a: None, release=lambda *a: None))
            def current(self): return True
        class View(QtWidgets.QLabel):
            loadFinished = QtCore.pyqtSignal(bool)
            def stop(self): pass
        class Page(QtCore.QObject):
            def runJavaScript(self, script): pass
        for name, module in {
            'aqt': aqt, 'aqt.qt': qt,
            'aqt.operations': types.SimpleNamespace(QueryOp=Query),
            'aqt.utils': types.SimpleNamespace(tooltip=errors.append),
            'PyQt6.QtWebEngineCore': types.SimpleNamespace(QWebEnginePage=QtCore.QObject,
                QWebEngineProfile=object, QWebEngineSettings=object),
            'PyQt6.QtWebEngineWidgets': types.SimpleNamespace(QWebEngineView=QtWidgets.QWidget),
            'frontend.pdf_shared_reader': types.SimpleNamespace(SharedPdfReader=Reader),
        }.items(): sys.modules[name] = module
        from frontend import pdf_reference_workspace as references, pdf_page_links as links
        from frontend.workspace import WorkspaceLayouts
        references.get_active_profile = links.get_active_profile = lambda: 'Synthetic'
        def snapshot(addon, profile, col, cid):
            return dict(card_id=cid, filename=str(cid)+'.pdf', path='/unused/'+str(cid)+'.pdf', title='PDF '+str(cid))
        references.resolve_pdf_reference = links.resolve_pdf_reference = snapshot
        references.get_pdf_daily_limit_status = links.get_pdf_daily_limit_status = lambda *a, **kw: {}
        links.pdf_page_count = lambda path: 20
        links.writing_links = lambda *a, **kw: []
        references.ReferenceWindow.reader_config = lambda self, result: dict(path=self._source_path)
        def create_view(parent, config, state, handler, **kwargs):
            return View('Live PDF '+str(state.card_id), parent), Page(parent), object(), object()
        references.create_reference_view = create_view
        primary = QtWidgets.QDockWidget('PDF 1', main)
        primary.setObjectName('incremento_pdf_dock')
        primary.setWidget(QtWidgets.QLabel('Live PDF 1'))
        main.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, primary)
        main.show(); app.processEvents()
        references.open_reference(2, beside=True, owner=primary)
        drain()
        source = references._windows[0]
        source_view = source.view
    ''') + f'placed = {placed!r}\n' + dedent('''
        if placed: source.keep_window()
        manager = WorkspaceLayouts(main)
        assert manager.arrange('tabs')
        source.raise_(); app.processEvents()
        assert not source.visibleRegion().isEmpty()
        # A link from the main reader must not evict another grouped PDF tab.
        references.open_reference(5, beside=True, owner=primary)
        drain()
        assert not source.state.closed, 'Grouped PDF tabs must survive later preview requests'
        source.raise_(); app.processEvents()
        def open_link(window, target):
            links.list_pdf_page_links = lambda *a, **kw: [dict(id=1, direction='outgoing',
                target_card_id=target, target_page=3, target_scroll=.4, target_y=.5)]
            request = dict(cardId=window.state.card_id, page=window.state.page, request=1, generation=1)
            window.command('page_links', dict(request, operation='list'))
            drain()
            window.command('page_links', dict(request, operation='jump', id=1, direction='outgoing', mode='beside'))
            drain()
            return next(w for w in references._windows if w.state.card_id == target)
        destination = open_link(source, 3)
        assert not source.state.closed, 'Opening beside a grouped source must keep that source open'
        assert source.view is source_view and source_view.text() == 'Live PDF 2'
        # Group as tabs now remains active for later Open beside reading actions.
        expected = {primary, source, destination, next(w for w in references._windows if w.state.card_id == 5)}
        assert set(main.tabifiedDockWidgets(source)) == expected - {source}
        assert not destination.visibleRegion().isEmpty(), 'The new destination becomes the active tab'
        bars = [bar for bar in main.findChildren(QtWidgets.QTabBar)
                if {bar.tabText(i) for i in range(bar.count())} == {'PDF 1', 'PDF 2', 'PDF 3', 'PDF 5'}]
        assert len(bars) == 1 and wait_until(bars[0].isVisible), 'The source tabs must remain reachable'
        for title, pane in (('PDF 1', primary), ('PDF 2', source)):
            index = next(i for i in range(bars[0].count()) if bars[0].tabText(i) == title)
            QtTest.QTest.mouseClick(bars[0], QtCore.Qt.MouseButton.LeftButton,
                QtCore.Qt.KeyboardModifier.NoModifier, bars[0].tabRect(index).center())
            assert wait_until(lambda: not pane.visibleRegion().isEmpty()), 'Each tab must still select its reader'
        assert not source.visibleRegion().isEmpty(), 'The initiating tab must remain visible'
        assert (destination.state.page, destination.state.scroll_ratio) == (3, .4)
        # Following another link from the fresh beside reader must not close it.
        destination.raise_(); app.processEvents()
        third = open_link(destination, 4)
        assert not destination.state.closed and not third.visibleRegion().isEmpty()
        assert set(main.tabifiedDockWidgets(third)) == expected
        assert not errors, errors
        references.reset_for_profile_switch()
        assert not references._windows and primary.isVisible()
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
