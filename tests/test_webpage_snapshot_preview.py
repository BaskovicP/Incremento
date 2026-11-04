"""Styled snapshot preview uses a disposable, script-disabled offline page."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_snapshot_preview_shows_captured_html_and_blocks_scripts_navigation_and_resources(tmp_path):
    script = dedent(r'''
        import sys
        from pathlib import Path
        from aqt.qt import QApplication, QEventLoop, QTimer, QUrl, QWebEngineSettings, QWebEngineScript
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        from frontend.webpage_snapshot_preview import SnapshotPreview
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app = QApplication(['snapshot-preview-test'])
        path = Path(sys.argv[1]) / 'preview.html'
        path.write_text('<html><head><style>.card {background:rgb(12, 34, 56); width:240px; height:120px}</style></head><body><div class="card">Saved layout</div><script>document.body.textContent="Executed"</script></body></html>')
        view = SnapshotPreview()
        settings = view.page().settings()
        assert not settings.testAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled)
        assert not settings.testAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls)
        assert not settings.testAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls)
        loop = QEventLoop(); loaded = []
        view.loadFinished.connect(lambda ok: (loaded.append(ok), loop.quit()))
        view.load_snapshot(str(path)); QTimer.singleShot(8000, loop.quit); loop.exec()
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
