"""Real Qt preview/printing boundary, with no live profile or desktop windows."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("outcome", ["save", "cancel", "profile-switch"])
def test_offline_cleanup_prints_edited_dom_or_aborts_without_pdf(tmp_path, outcome):
    script = dedent(r'''
        import importlib
        import faulthandler
        faulthandler.enable()
        import sys
        import threading
        from pathlib import Path
        from types import ModuleType
        from aqt.qt import QApplication, QTimer
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEnginePage, QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import QEventLoop
        from PyQt6 import sip
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app = QApplication(['cleanup-fixture'])
        # Anki initializes its main Chromium page before opening import dialogs.
        main_profile = QWebEngineProfile()
        main_page = QWebEnginePage(main_profile)
        main_view = QWebEngineView()
        main_view.setPage(main_page)
        main_view.show()
        ready = QEventLoop()
        main_page.loadFinished.connect(lambda _ok: ready.quit())
        main_page.setHtml('<html><body>Main window fixture</body></html>')
        QTimer.singleShot(5000, ready.quit)
        ready.exec()
        root, destination, outcome = sys.argv[1:]
        package = ModuleType('cleanup_fixture')
        package.__path__ = [root]
        sys.modules[package.__name__] = package
        module = importlib.import_module('cleanup_fixture.frontend.webpage_dialog')
        resources = importlib.import_module('cleanup_fixture.backend.webpage_resources')
        directory = Path(destination)
        source = directory / 'snapshot.html'
        html = '<html><body><nav>REMOVE CLUTTER</nav><main><h1>KEEP ARTICLE</h1><section>KEEP COMMENTS</section></main><script>document.body.textContent="SITE SCRIPT EXECUTED"</script></body></html>'
        source.write_text(resources.build_offline_webpage_html(html, '', timeout_sec=0))
        profile = ['First']
        module._active_profile = lambda: profile[0]
        cancel = threading.Event()
        errors = []
        acted = []
        def interact():
            for dialog in app.topLevelWidgets():
                view = dialog.findChild(QWebEngineView)
                if not dialog.isVisible() or view is None or acted:
                    continue
                acted.append(True)
                # The trusted ApplicationWorld picker must work while original
                # page scripts remain disabled and its strict CSP is retained.
                # Qt's top-level order varies; bind this preview before the
                # asynchronous callback runs and the loop visits another window.
                def removed(result, preview=dialog):
                    if result != 'none':
                        errors.append(AssertionError('Picker failed: ' + str(result)))
                        preview.reject()
                    elif outcome == 'save':
                        preview.save_button.click()
                    elif outcome == 'cancel':
                        cancel.set()
                    else:
                        profile[0] = 'Second'
                view.page().runJavaScript("document.querySelector('nav').dispatchEvent(new MouseEvent('click', {bubbles:true})); getComputedStyle(document.querySelector('nav')).display",
                    QWebEngineScript.ScriptWorldId.ApplicationWorld, removed)
        poll = QTimer()
        poll.timeout.connect(interact)
        poll.start(50)
        def run():
            try:
                module._print_offline_snapshot(str(directory / 'result.pdf'), str(source), wait_ms=0, timeout_ms=10000,
                    screen_media=True, edit_before_save=True, cancel_event=cancel)
                assert outcome == 'save', 'Cancelled preview returned success'
            except RuntimeError as exc:
                expected = 'profile' if outcome == 'profile-switch' else 'cancel'
                if outcome == 'save' or expected not in str(exc).lower():
                    errors.append(exc)
            except BaseException as exc:
                errors.append(exc)
            finally:
                app.quit()
        QTimer.singleShot(0, run)
        app.exec()
        sip.delete(main_view)
        sip.delete(main_page)
        sip.delete(main_profile)
        if errors:
            raise errors[0]
        assert acted, 'Preview never became available'
        assert (directory / 'result.pdf').exists() == (outcome == 'save')
    ''')
    # Keep desktop accessibility services out of the offscreen WebEngine fixture.
    result = subprocess.run([sys.executable, '-c', script, str(Path(__file__).resolve().parents[1]), str(tmp_path), outcome],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_OPENGL='software', QT_QUICK_BACKEND='software',
                 QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --disable-renderer-accessibility'),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    if outcome == 'save':
        inspected = subprocess.run([sys.executable, '-c', dedent('''
            import pymupdf, sys
            with pymupdf.open(sys.argv[1]) as pdf:
                text = ''.join(page.get_text() for page in pdf)
                assert 'KEEP ARTICLE' in text and 'KEEP COMMENTS' in text, text
                assert 'REMOVE CLUTTER' not in text and 'SITE SCRIPT EXECUTED' not in text, text
        '''), str(tmp_path / 'result.pdf')], capture_output=True, text=True, timeout=10)
        assert inspected.returncode == 0, inspected.stdout + inspected.stderr
