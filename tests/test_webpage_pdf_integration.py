"""Real Qt printing checks, isolated from the suite's mocked Anki modules."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
import pytest


@pytest.mark.parametrize("style", ["print", "website"])
@pytest.mark.parametrize("opened_page", [False, True])
def test_real_renderer_keeps_styles_images_and_large_html_without_browser_network(tmp_path, style, opened_page):
    script = dedent(r'''
        import importlib
        import faulthandler
        faulthandler.enable()
        import io
        import os
        from pathlib import Path
        import random
        import struct
        from types import ModuleType, SimpleNamespace
        import sys
        import threading
        import zlib

        import aqt
        from aqt.qt import QApplication, QCoreApplication, QEvent, QTimer
        from aqt.taskman import TaskManager
        from PyQt6.QtCore import QEventLoop
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        from PyQt6 import sip

        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app = QApplication.instance() or QApplication(['incremento-snapshot-test'])
        # Anki's main webview initializes Chromium before add-on workers start.
        main_profile = QWebEngineProfile()
        main_page = QWebEnginePage(main_profile)
        ready = QEventLoop()
        ready_result = []
        main_page.loadFinished.connect(lambda ok: (ready_result.append(ok), ready.quit()))
        main_page.setHtml('<html><body>Main window fixture</body></html>')
        QTimer.singleShot(5000, ready.quit)
        ready.exec()
        assert ready_result == [True], 'The main browser did not initialize.'
        root, output_dir, style, opened_page_arg = sys.argv[1:]
        opened_page = opened_page_arg == '1'
        package = ModuleType('snapshot_fixture_addon')
        package.__path__ = [root]
        sys.modules[package.__name__] = package
        frontend = importlib.import_module('snapshot_fixture_addon.frontend.webpage_dialog')
        resources = importlib.import_module('snapshot_fixture_addon.backend.webpage_resources')
        main = SimpleNamespace()
        main.weakref = lambda: main
        main.taskman = TaskManager(main)
        aqt.mw = main
        def validate_source(url):
            if opened_page:
                from snapshot_fixture_addon.backend.network_safety import UnsafeNetworkTargetError
                raise UnsafeNetworkTargetError('The remote host resolves to a private or special address.')
            return url
        frontend.validate_public_http_url = validate_source
        official_calls = []
        def official_pdf(*_args, **_kwargs):
            official_calls.append(_args)
            return None
        frontend._fetch_wikipedia_article_pdf = official_pdf
        resources.validate_public_http_url = lambda url: url
        def png_chunk(kind, value):
            return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value))
        # A real photo-sized image makes the captured HTML exceed Qt's 2 MiB
        # setHtml limit, while keeping the regression focused on visible content.
        pixels = random.Random(0).randbytes(900 * 900 * 3)
        rows = b''.join(b'\0' + pixels[index:index+2700] for index in range(0, len(pixels), 2700))
        png = (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 900, 900, 8, 2, 0, 0, 0))
               + png_chunk(b'IDAT', zlib.compress(rows)) + png_chunk(b'IEND', b''))
        assert len(png) > 2 * 1024 * 1024
        calls = []
        def fetch(request, *, timeout):
            assert threading.current_thread() is not threading.main_thread()
            calls.append(request.full_url)
            mime, data = {
                'https://example.test/site.css': ('text/css', b'h1 {color: #123456} .hidden {display: none} img {width: 120px; height: 80px} @media print { .screen-only {display: none} }'),
                'https://example.test/photo.png': ('image/png', png),
            }[request.full_url]
            response = io.BytesIO(data)
            response.headers = {'Content-Type': mime}
            response.geturl = lambda: request.full_url
            return response
        resources.open_public_http = fetch
        output = str(Path(output_dir) / 'webpage.pdf')
        temporary_documents = []
        original_tempfile = frontend.tempfile.NamedTemporaryFile
        def temporary(*args, **kwargs):
            result = original_tempfile(*args, **kwargs)
            temporary_documents.append(result.name)
            return result
        frontend.tempfile.NamedTemporaryFile = temporary
        html = ('<html><head><link rel="stylesheet" href="/site.css"></head><body>'
                '<h1>Styled article heading</h1><p>Preserved article text</p>'
                '<p class="screen-only">SCREEN MEDIA TEXT</p>'
                '<p class="hidden">HIDDEN NAVIGATION</p><img src="/photo.png">'
                '<script>document.body.textContent="SCRIPT EXECUTED"</script></body></html>')
        errors = []
        def render():
            try:
                frontend.render_webpage_to_pdf(output, url='https://example.test/article', html=html, wait_ms=0, timeout_ms=15000,
                                              style=style, dynamic=opened_page, prefer_snapshot=opened_page)
            except Exception as exc:
                errors.append(exc)
            finally:
                app.quit()
        # Anki invokes this dialog from its running QApplication event loop.
        QTimer.singleShot(0, render)
        app.exec()
        if errors:
            raise errors[0]
        assert not opened_page or not official_calls, 'Opened-page capture requested a replacement PDF.'
        assert len(temporary_documents) == 1
        assert all(not os.path.exists(path) for path in temporary_documents)
        assert sorted(calls) == ['https://example.test/photo.png', 'https://example.test/site.css']
        # The page may load only its own generated document as a main frame.
        from PyQt6.QtCore import QUrl
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        profile = QWebEngineProfile()
        page = frontend._SnapshotPage(profile, None, 'file:///tmp/owned.html')
        assert page.acceptNavigationRequest(QUrl('file:///tmp/owned.html'), None, True)
        assert not page.acceptNavigationRequest(QUrl('file:///tmp/owned.html'), None, False)
        assert not page.acceptNavigationRequest(QUrl('https://example.test/'), None, True)
        assert not page.acceptNavigationRequest(QUrl('file:///etc/passwd'), None, True)
        page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        sip.delete(profile)
        main.taskman._no_collection_executor.shutdown()
        main.taskman._collection_executor.shutdown()
        sip.delete(main_page)
        sip.delete(main_profile)
        print('Styled PDF, image, large HTML, off-main fetch, and cleanup verified.')
    ''')
    # Keep real rendering checks offscreen so they cannot take desktop focus.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu")
    result = subprocess.run(
        [sys.executable, "-c", script, str(Path(__file__).resolve().parents[1]), str(tmp_path), style, "1" if opened_page else "0"],
        env=env, capture_output=True, text=True, timeout=45,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "cleanup verified" in result.stdout

    # Isolate native PDF libraries and the suite's module/path stand-ins from Qt.
    inspect_script = dedent('''
        from pathlib import Path
        import sys
        import pymupdf
        output = Path(sys.argv[1])
        with pymupdf.open(output / "webpage.pdf") as doc:
            text = "".join(page.get_text() for page in doc)
            assert "Styled article heading" in text
            assert "Preserved article text" in text
            assert "HIDDEN NAVIGATION" not in text
            assert "SCRIPT EXECUTED" not in text
            assert ("SCREEN MEDIA TEXT" in text) == (sys.argv[2] == "website"), text
            spans = [span for block in doc[0].get_text("dict")["blocks"] if "lines" in block
                     for line in block["lines"] for span in line["spans"]]
            assert any(span["color"] == 0x123456 for span in spans), spans
            assert doc[0].get_images()
            doc[0].get_pixmap().save(output / "webpage.png")
    ''')
    inspected = subprocess.run(
        [sys.executable, "-c", inspect_script, str(tmp_path), style],
        capture_output=True, text=True, timeout=15,
    )
    assert inspected.returncode == 0, inspected.stdout + inspected.stderr
