"""Real Qt/HTTP/PDF evidence for the automatic browser-return transition."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_native_dialog_resumes_after_authenticated_browser_response_without_another_click(tmp_path):
    script = dedent(r'''
        import importlib
        import faulthandler
        faulthandler.enable()
        import json
        import os
        from pathlib import Path
        import sys
        import threading
        from types import ModuleType, SimpleNamespace
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        import aqt
        from aqt.qt import QApplication, QTimer
        from aqt.taskman import TaskManager
        from PyQt6.QtCore import QEventLoop
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        from PyQt6 import sip

        root, output = sys.argv[1:]
        # Match Anki's software-graphics setup before Chromium initializes.
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app = QApplication(['incremento-handoff-test'])
        main_profile = QWebEngineProfile()
        main_page = QWebEnginePage(main_profile)
        # Initialize Chromium without an offscreen QWebEngineView compositor.
        # The real import dialog below still exercises the native Qt event loop.
        ready = QEventLoop()
        loaded = []
        main_page.loadFinished.connect(lambda ok: (loaded.append(ok), ready.quit()))
        main_page.setHtml('<p>Synthetic Anki window</p>')
        QTimer.singleShot(5000, ready.quit)
        ready.exec()
        assert loaded == [True]
        package = ModuleType('handoff_fixture_addon')
        package.__path__ = [root]
        sys.modules[package.__name__] = package
        frontend = importlib.import_module('handoff_fixture_addon.frontend.webpage_dialog')
        resources = importlib.import_module('handoff_fixture_addon.backend.webpage_resources')
        resources.validate_public_http_url = lambda url: url
        bridge = importlib.import_module('handoff_fixture_addon.backend.browser_bridge')
        main = SimpleNamespace(col=None)
        main.weakref = lambda: main
        main.taskman = TaskManager(main)
        aqt.mw = main
        frontend._active_profile = lambda: 'SyntheticProfile'
        frontend.browser_runtime = lambda: None
        frontend.validate_public_http_url = lambda url: url
        frontend._fetch_wikipedia_article_pdf = lambda *_a, **_kw: None
        def blocked(url, **_kwargs):
            raise HTTPError(url, 429, 'Too many requests', {}, None)
        frontend._fetch_webpage_html = blocked
        bridge._bridge_token = 'synthetic-token'
        origin = 'chrome-extension://' + 'a' * 32
        bridge._allowed_extension_origin = origin
        server = bridge._BoundedThreadingHTTPServer(('127.0.0.1', 0), bridge._IncrementoBridgeHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        errors = []
        opened = []
        workers = []
        def open_browser(url):
            opened.append(url)
            ticket = url.split('#', 1)[1]
            def send_browser_result():
                try:
                    endpoint = f'http://127.0.0.1:{server.server_port}/incremento/webpage-pdf-handoff'
                    for body in ({'action':'describe', 'ticket':ticket},
                                 {'action':'submit', 'ticket':ticket, 'url':'https://example.test/article',
                                  'html':'<html><body><article><h1>Verified browser article</h1><p>Returned without another import click.</p></article></body></html>'}):
                        request = Request(endpoint, data=json.dumps(body).encode(), headers={
                            'Origin':origin, 'X-Incremento-Token':'synthetic-token', 'X-Incremento-Protocol':'2',
                            'Content-Type':'application/json'})
                        with urlopen(request, timeout=5) as response:
                            assert json.load(response)['ok']
                except Exception as exc:
                    errors.append(exc)
            worker = threading.Thread(target=send_browser_result)
            workers.append(worker)
            worker.start()
            return True
        frontend.open_companion_url = open_browser
        dialog = frontend.WebpageToPdfDialog()
        dialog._url_edit.setText('https://example.test/article')
        dialog._title_edit.setText('Original title')
        dialog._style_combo.setCurrentIndex(dialog._style_combo.findData('article'))
        QTimer.singleShot(0, dialog._on_import)
        QTimer.singleShot(15000, dialog.reject)
        assert dialog.exec(), errors
        for worker in workers:
            worker.join(5)
        assert not errors, errors
        assert len(opened) == 1
        assert dialog.browser_handoff_completed
        assert dialog.title_text == 'Original title'
        assert dialog.source_url == 'https://example.test/article'
        os.replace(dialog.pdf_path, str(Path(output) / 'handoff.pdf'))
        dialog.deleteLater()
        server.shutdown()
        server.server_close()
        server_thread.join(1)
        main.taskman._no_collection_executor.shutdown()
        main.taskman._collection_executor.shutdown()
        if not sip.isdeleted(main_page):
            sip.delete(main_page)
        sip.delete(main_profile)
        print('Automatic browser return verified')
    ''')
    # Exercise the real dialog without presenting native windows during tests.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu")
    result = subprocess.run([sys.executable, "-c", script, str(Path(__file__).resolve().parents[1]), str(tmp_path)],
                            env=env, capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Automatic browser return verified" in result.stdout
    inspect = subprocess.run([sys.executable, "-c", dedent('''
        import sys, pymupdf
        with pymupdf.open(sys.argv[1]) as doc:
            text = ''.join(page.get_text() for page in doc)
            assert 'Verified browser article' in text, text
            assert 'Returned without another import click.' in text, text
            assert 'Too many requests' not in text
    '''), str(tmp_path / "handoff.pdf")], capture_output=True, text=True, timeout=10)
    assert inspect.returncode == 0, inspect.stdout + inspect.stderr
