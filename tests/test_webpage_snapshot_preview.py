"""Styled snapshot preview uses a disposable, script-disabled offline page."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_snapshot_preview_shows_captured_html_and_blocks_scripts_navigation_and_resources(tmp_path):
    script = dedent(r'''
        import faulthandler
        faulthandler.enable()
        import sys
        from pathlib import Path
        from aqt.qt import QApplication, QEventLoop, QTimer, QUrl, QWebEngineSettings, QWebEngineScript
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        from PyQt6.QtTest import QTest
        from backend.i18n import initialize_language
        from frontend.webpage_snapshot_preview import SnapshotPreview
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app = QApplication(['snapshot-preview-test'])
        initialize_language('en')
        path = Path(sys.argv[1]) / 'preview.html'
        path.write_text('<html><head><style>.card {background:rgb(12, 34, 56); width:240px; height:120px}</style></head><body><div class="card">Saved layout</div><script>document.body.textContent="Executed"</script></body></html>')
        view = SnapshotPreview()
        view.resize(800,600)
        settings = view.page().settings()
        assert not settings.testAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled)
        assert not settings.testAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls)
        assert not settings.testAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls)
        loop = QEventLoop(); loaded = []
        view.loadFinished.connect(lambda ok: (loaded.append(ok), loop.quit()))
        view.load_snapshot(str(path)); view.show(); QTimer.singleShot(8000, loop.quit); loop.exec()
        assert loaded == [True]
        page = view.page()
        assert page.acceptNavigationRequest(QUrl.fromLocalFile(str(path)), 0, True)
        for url in ('https://example.com', 'file:///etc/passwd', 'data:text/html,changed'):
            assert not page.acceptNavigationRequest(QUrl(url), 0, True)
        blocked = []
        class Request:
            def __init__(self, url): self.url = url
            def requestUrl(self): return QUrl(self.url)
            def block(self, value): blocked.append(value)
        for url in ('https://example.com/image.png', 'file:///etc/passwd'):
            view._requests.interceptRequest(Request(url))
        assert blocked == [True, True]
        html = []
        page.toHtml(lambda value: (html.append(value), loop.quit()))
        QTimer.singleShot(8000, loop.quit); loop.exec()
        assert 'Saved layout' in html[0] and 'rgb(12, 34, 56)' in html[0]
        assert '<div class="card">Saved layout</div>' in html[0]
        styles = []
        page.runJavaScript('JSON.stringify({width:getComputedStyle(document.querySelector(".card")).width,background:getComputedStyle(document.querySelector(".card")).backgroundColor})',
            int(QWebEngineScript.ScriptWorldId.ApplicationWorld.value), lambda value: (styles.append(value), loop.quit()))
        QTimer.singleShot(8000, loop.quit); loop.exec()
        import json
        assert json.loads(styles[0]) == {'width': '240px', 'background': 'rgb(12, 34, 56)'}
        view.clear()
        view.close()
        from PyQt6 import sip
        sip.delete(view)
        print('HTML snapshot preview: ok')
    ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_OPENGL": "software",
                                 "QT_QUICK_BACKEND": "software",
                                 "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu --disable-gpu-compositing"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HTML snapshot preview: ok" in result.stdout


def test_snapshot_zap_controls_remove_undo_and_serialize_without_enabling_site_scripts(tmp_path):
    script = dedent(r'''
        import faulthandler
        faulthandler.enable()
        import sys
        from pathlib import Path
        from aqt.qt import QApplication, QEventLoop, QTimer, QWebEngineScript, QWebEngineSettings
        from PyQt6.QtQuick import QQuickWindow,QSGRendererInterface
        from PyQt6.QtCore import QEvent,QPointF,QPoint,Qt
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtTest import QTest
        from backend.i18n import initialize_language
        from frontend.webpage_snapshot_preview import SnapshotPreview
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app=QApplication(['snapshot-zap-test']);initialize_language('en')
        def wait(start):
            loop=QEventLoop(); values=[]; timer=QTimer();timer.setSingleShot(True)
            timer.timeout.connect(loop.quit);timer.start(8000)
            def done(value):values.append(value);loop.quit()
            start(done)
            if not values:loop.exec()
            timer.stop();assert values,'Preview timed out'
            return values[0]
        view=SnapshotPreview();view.resize(800,600)
        assert not view.zap_button.isChecked() and not view.undo_button.isEnabled()
        path=Path(sys.argv[1])/'preview.html'
        path.write_text('<html><head><style>aside{width:240px;height:100px}</style></head><body><aside><span>Unwanted sidebar</span></aside><main><h1>Keep article</h1></main><script>document.body.textContent="Executed"</script></body></html>')
        def load(done):
            view.loadFinished.connect(done);view.load_snapshot(str(path));view.show()
        assert wait(load) and view.is_ready
        assert QTest.qWaitForWindowExposed(view,8000)
        world=int(QWebEngineScript.ScriptWorldId.ApplicationWorld.value)
        def js(code):return wait(lambda done:view.page().runJavaScript(code,world,done))
        assert not view.page().settings().testAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled)
        assert js('document.querySelector("h1").textContent')=='Keep article'
        view.zap_button.setChecked(True)
        assert js('incrementoCleanup.state().enabled') is True
        canvas=view._view.focusProxy() or view._view
        point=QPoint(20,20)
        # Real Qt input must work with JavascriptEnabled=False; programmatic
        # dispatch inside runJavaScript alone cannot prove this boundary.
        QApplication.sendEvent(canvas,QMouseEvent(QEvent.Type.MouseMove,QPointF(point),
            QPointF(canvas.mapToGlobal(point)),Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier))
        assert js('getComputedStyle(document.querySelector("[data-incremento-zap-overlay]")).display')=='block'
        QApplication.sendEvent(canvas,QEvent(QEvent.Type.Leave))
        assert js('getComputedStyle(document.querySelector("[data-incremento-zap-overlay]")).display')=='none'
        QApplication.sendEvent(canvas,QMouseEvent(QEvent.Type.MouseMove,QPointF(point),
            QPointF(canvas.mapToGlobal(point)),Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier))
        QTest.keyPress(canvas,Qt.Key.Key_Shift)
        assert js('document.querySelector("[data-incremento-zap-overlay]").getBoundingClientRect().width')==240
        QTest.mouseClick(canvas,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=point)
        QTest.keyRelease(canvas,Qt.Key.Key_Shift)
        js('true')
        assert view.removal_count==1 and view.undo_button.isEnabled() and view.reset_button.isEnabled()
        assert js('document.querySelector("aside")===null')
        edited=wait(view.snapshot_html)
        assert 'Unwanted sidebar' not in edited and 'Keep article' in edited
        assert 'incremento-zap' not in edited
        view.undo_button.click()
        assert js('document.querySelector("aside").textContent')=='Unwanted sidebar'
        assert view.removal_count==0 and not view.undo_button.isEnabled()
        QTest.keyClick(canvas,Qt.Key.Key_Down)
        QTest.keyClick(canvas,Qt.Key.Key_Delete)
        assert js('document.querySelector("aside")===null')
        QTest.keyClick(canvas,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        assert js('document.querySelector("aside")!==null')
        QTest.keyClick(canvas,Qt.Key.Key_Escape)
        assert js('incrementoCleanup.state().enabled') is False
        assert not view.zap_button.isChecked()
        view.zap_button.setChecked(True)
        QTest.keyClick(canvas,Qt.Key.Key_Down)
        QTest.keyClick(canvas,Qt.Key.Key_Delete)
        assert js('document.querySelector("aside")===null')
        view.set_editable(False)
        QTest.keyClick(canvas,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        assert js('document.querySelector("aside")===null')
        view.clear()
        assert not view.is_ready and not view.zap_button.isEnabled()
        assert wait(view.snapshot_html) is None
        from PyQt6 import sip
        sip.delete(view)
        print('snapshot zap: ok')
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_OPENGL':'software','QT_QUICK_BACKEND':'software',
             'QTWEBENGINE_CHROMIUM_FLAGS':'--disable-gpu --disable-gpu-compositing'},
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'snapshot zap: ok' in result.stdout
