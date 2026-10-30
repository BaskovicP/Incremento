"""Real Qt docking geometry, with the PDF engine replaced at its boundary."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("floating_primary", [False, True])
def test_native_pdf_panes_are_visible_and_horizontal_after_pin(floating_primary):
    script = dedent('''
        import importlib.util, sys, types
        from pathlib import Path
        from PyQt6.QtCore import QObject, QSignalBlocker, Qt, QUrl
        from PyQt6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QWidget
        app = QApplication(['incremento-reference-layout-test'])
        main = QMainWindow()
        main.resize(1400, 800)
        main.setCentralWidget(QLabel('Synthetic study area'))
        qt = types.ModuleType('aqt.qt')
        qt.QApplication, qt.QDockWidget, qt.Qt, qt.QUrl = QApplication, QDockWidget, Qt, QUrl
        qt.QSignalBlocker = QSignalBlocker
        aqt = types.ModuleType('aqt')
        aqt.mw = main
        for name, module in {
            'aqt': aqt, 'aqt.qt': qt,
            'aqt.operations': types.SimpleNamespace(QueryOp=object),
            'aqt.utils': types.SimpleNamespace(tooltip=lambda text: None),
            'PyQt6.QtWebEngineCore': types.SimpleNamespace(QWebEnginePage=QObject,
                QWebEngineProfile=object, QWebEngineSettings=object),
            'PyQt6.QtWebEngineWidgets': types.SimpleNamespace(QWebEngineView=QWidget),
            'backend.pdf_manager': types.SimpleNamespace(get_pdf_daily_limit_status=lambda *a, **kw: {}),
        }.items():
            sys.modules[name] = module
        spec = importlib.util.spec_from_file_location('_reference_layout', 'frontend/pdf_reference_workspace.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        primary = QDockWidget('Primary PDF', main)
        primary.setObjectName('incremento_pdf_dock')
        primary.setWidget(QLabel('PDF A'))
        primary.setMinimumWidth(400)
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, primary)
        reference = module.ReferenceWindow.__new__(module.ReferenceWindow)
        QDockWidget.__init__(reference, 'Reference PDF', main)
        reference.state = module.PdfReaderState('Test', 8, 'synthetic.pdf', page=3)
        reference.owner = primary
        reference.view = QLabel('PDF B')
        reference.view.stop = lambda: None
        reference.page = QObject(reference)
        reference.setWidget(reference.view)
        reference.setMinimumWidth(280)
        main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, reference)
        reference.setFloating(True)
        module._windows.append(reference)
        main.show()
        primary.show()
        reference.show()
        app.processEvents()
    ''') + f'primary.setFloating({floating_primary!r})\n' + dedent('''
        app.processEvents()
        visibility = []
        primary.visibilityChanged.connect(visibility.append)
        reference.pin()
        app.processEvents()
        main.layout().activate()
        left, right = primary.geometry(), reference.geometry()
        assert primary.isVisible() and reference.isVisible()
        assert not primary.isFloating() and not reference.isFloating()
        assert right.x() >= left.x() + left.width(), (left.getRect(), right.getRect())
        assert abs(right.y() - left.y()) <= 2, (left.getRect(), right.getRect())
        assert False not in visibility, 'Layout changes must not stop primary reading-time tracking'
        module.reset_for_profile_switch()
        main.close()
        app.processEvents()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('confirm', [True, False], ids=['confirm', 'cancel'])
def test_destination_actions_and_pdf_bytes_cross_the_injected_javascript_bridge(tmp_path, confirm):
    script = dedent(r'''
        import base64, json, sys, types
        from concurrent.futures import Future
        from pathlib import Path
        import pymupdf
        from PyQt6 import QtCore, QtWidgets
        from PyQt6.QtCore import QObject
        from PyQt6.QtQml import QJSEngine
        from PyQt6.QtWidgets import QApplication, QWidget

        app = QApplication(['incremento-destination-bridge-test'])
        engine = QJSEngine()
        engine.evaluate('var window = {}; var messages = [];'
            'var console = {info: message => messages.push(message)};'
            'window.incrementoReferenceStart = config => {window.config = config;};'
            'window.incrementoReceivePdfRange = reply => {window.rangeReply = reply;};')
        root, addon = Path.cwd(), Path(sys.argv[1])
        sys.path.extend([str(root / 'backend'), str(root / 'frontend')])
        profile = 'Synthetic'
        pdf = addon / 'user_files' / profile / 'pdfs' / 'target.pdf'
        pdf.parent.mkdir(parents=True)
        with pymupdf.open() as document:
            document.new_page()
            document.new_page()
            document.save(pdf)
        col = types.SimpleNamespace(get_card=lambda cid: types.SimpleNamespace(nid=cid),
            get_note=lambda nid: {'PDF_Filename': pdf.name, 'Title': 'Synthetic PDF'})
        validation = []
        class Query:
            def __init__(self, **options): self.options = options
            def failure(self, callback): return self
            def run_in_background(self): validation.append(self)
        def submit(work, done):
            future = Future()
            future.set_result(work())
            done(future)
        qt = types.ModuleType('aqt.qt')
        for module in (QtCore, QtWidgets):
            for name in dir(module): setattr(qt, name, getattr(module, name))
        # Replace the native rendering surface with a JS engine. The injected
        # bridge, nonce/profile validation, byte transport, and dialog are real.
        class Page(QObject):
            def __init__(self, profile, parent): super().__init__(parent)
            def settings(self): return types.SimpleNamespace(setAttribute=lambda *a: None)
            def runJavaScript(self, script):
                value = engine.evaluate(script)
                assert not value.isError(), value.toString()
                for message in engine.evaluate('messages.splice(0)').toVariant():
                    self.javaScriptConsoleMessage(None, message, 0, '')
        class View(QWidget):
            loadFinished = QtCore.pyqtSignal(bool)
            def setPage(self, page): self.page = page
            def load(self, url): self.loadFinished.emit(True)
            def stop(self): pass
        class Interceptor:
            def __init__(self, *a): pass
            def set_pdf_path(self, path): pass
        for name, module in {
            'aqt': types.SimpleNamespace(mw=None), 'aqt.qt': qt,
            'aqt.operations': types.SimpleNamespace(QueryOp=Query),
            'aqt.utils': types.SimpleNamespace(tooltip=lambda text: None),
            'PyQt6.QtWebEngineCore': types.SimpleNamespace(QWebEnginePage=Page,
                QWebEngineProfile=lambda parent: types.SimpleNamespace(setUrlRequestInterceptor=lambda value: None),
                QWebEngineSettings=types.SimpleNamespace(WebAttribute=types.SimpleNamespace(LocalContentCanAccessFileUrls=1))),
            'PyQt6.QtWebEngineWidgets': types.SimpleNamespace(QWebEngineView=View),
            'backend.pdf_manager': types.SimpleNamespace(get_pdf_daily_limit_status=lambda *a, **kw: {}),
            'frontend.pdf_dock': types.SimpleNamespace(_PdfRequestInterceptor=Interceptor,
                _WORKER_URL='file:///synthetic-worker.js', _DOCK_HTML='file:///synthetic-reader.html'),
        }.items(): sys.modules[name] = module
        from frontend import pdf_destination_dialog as destination, pdf_reference_workspace as workspace
        workspace.mw = types.SimpleNamespace(taskman=types.SimpleNamespace(run_in_background=submit))
        destination._ADDON_DIR = workspace._ADDON_DIR = str(addon)
        destination.get_active_profile = workspace.get_active_profile = lambda: profile
        snapshot = destination.resolve_pdf_reference(str(addon), profile, col, 8)
        dialog = destination.PdfDestinationDialog(snapshot, profile=profile, max_page=2, is_current=lambda: True)
        accepted = []
        dialog.accepted.connect(lambda: accepted.append(dialog.selected_location))
        descriptor = dialog.page._range_bridge.source.descriptor
        request = {**descriptor, 'requestId': 1, 'begin': 0, 'end': pdf.stat().st_size}
        dialog.page.runJavaScript("window.pycmd('incremento_pdf_range:' + " + json.dumps(json.dumps(request)) + ');')
        reply = engine.evaluate('window.rangeReply').toVariant()
        assert base64.b64decode(reply['data']) == pdf.read_bytes()
        assert validation == [], 'PDF loading must not confirm a destination'

        def send(payload):
            dialog.page.runJavaScript('window.pycmd(' + json.dumps(json.dumps(payload)) + ');')
        send({'action': 'position', 'page': 2, 'scroll_ratio': .3, 'zoom': 1.25})
        assert (dialog.state.page, dialog.state.scroll_ratio, dialog.state.zoom) == (2, .3, 1.25)
        send({'action': 'pick' if sys.argv[2] == '1' else 'close',
            'page': 2, 'scroll_ratio': .4, 'zoom': 1.25, 'page_y': .65})
        if sys.argv[2] == '1':
            assert len(validation) == 1, 'Link to this spot must request validation'
            assert accepted == [], 'No destination is accepted before validation'
            request = validation[0]
            request.options['success'](request.options['op'](col))
            assert len(accepted) == 1
            assert {key: accepted[0][key] for key in ('card_id', 'page', 'page_y', 'scroll_ratio')} == {
                'card_id': 8, 'page': 2, 'page_y': .65, 'scroll_ratio': .4}
        else:
            assert dialog._closed and validation == [] and accepted == []
        assert not (addon / 'user_files' / profile / 'incremento.db').exists()
        app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), '1' if confirm else '0'],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_link_target_page_bounds_use_real_pdf_metadata_in_a_worker():
    script = dedent('''
        import importlib.util, sys, tempfile, types
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        import pymupdf
        from PyQt6.QtWidgets import QApplication
        app = QApplication(['incremento-page-count-test'])
        for name, module in {
            'aqt': types.SimpleNamespace(mw=None),
            'aqt.operations': types.SimpleNamespace(QueryOp=object),
            'aqt.utils': types.SimpleNamespace(tooltip=lambda text: None),
            'backend.pdf_manager': types.SimpleNamespace(get_pdf_daily_limit_status=lambda *a, **kw: {}),
        }.items():
            sys.modules[name] = module
        spec = importlib.util.spec_from_file_location('_page_count', 'frontend/pdf_page_links.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder, ThreadPoolExecutor(max_workers=1) as worker:
            path = Path(folder) / 'synthetic.pdf'
            document = pymupdf.open()
            for _ in range(3):
                document.new_page()
            document.save(path)
            document.close()
            assert worker.submit(module.pdf_page_count, str(path)).result(timeout=5) == 3
            broken = Path(folder) / 'broken.pdf'
            broken.write_bytes(b'not a PDF')
            try:
                worker.submit(module.pdf_page_count, str(broken)).result(timeout=5)
            except ValueError:
                pass
            else:
                raise AssertionError('An unreadable PDF must not offer invented target pages')
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
