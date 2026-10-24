"""Open two isolated, real EPUB WebEngine panes using only synthetic chapters."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_reference_navigation_highlights_and_close_preserve_main_reader(tmp_path):
    script = dedent('''
        import json, sys, types
        from pathlib import Path
        root = Path.cwd()
        sys.path[:0] = [str(root/'frontend'), str(root/'backend')]
        sys.modules['session'] = types.SimpleNamespace(INCREMENTO_EPUB_REVIEW_DECK='Test',
                                                       start_explicit_review=lambda *a, **k: None)
        from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel
        from PyQt6.QtCore import QEventLoop, QTimer
        import epub_reference_workspace as workspace
        import epub_dock as reader
        from backend.db import get_connection
        from backend.epub_manager import _EPUB_SANITIZER_VERSION
        app = QApplication(['epub-reference-test'])
        app.setQuitOnLastWindowClosed(False)
        main = QMainWindow()
        main.setCentralWidget(QWidget())
        layout = QVBoxLayout(main.centralWidget())
        main.web, main.bottomWeb = QLabel('Main position'), QLabel('Answer controls')
        layout.addWidget(main.web)
        layout.addWidget(main.bottomWeb)
        main.addonManager = types.SimpleNamespace(getConfig=lambda _: {})
        workspace.mw = reader.mw = main
        workspace._ADDON_DIR = reader._ADDON_DIR = sys.argv[1]
        workspace.get_active_profile = lambda: 'A'
        reader._active_profile = lambda: 'A'
        reader._current_epub_card_id = 99
        reader._current_epub_section_index = 8
        reader._current_epub_scroll_ratio = .65
        directory = Path(sys.argv[1])/'user_files'/'A'
        (directory/'epubs').mkdir(parents=True)
        (directory/'epubs'/'test.epub').write_bytes(b'fixture')
        chapters = directory/'epub_extracted'/'test.epub'
        chapters.mkdir(parents=True)
        sections = []
        for index in range(2):
            href = f'chapter{index}.xhtml'
            text = ' '.join(['Some synthetic text for selection.'] * 500)
            (chapters/href).write_text('<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Test</title>'
                '</head><body><p>'+text+'</p><a href="#top">Jump</a></body></html>')
            sections.append(dict(href=href, title='Chapter', text=text))
        (chapters/'metadata.json').write_text(json.dumps(dict(sanitizer_version=_EPUB_SANITIZER_VERSION,
                                                            sections=sections)))
        col = types.SimpleNamespace(get_card=lambda cid: types.SimpleNamespace(nid=cid),
            get_note=lambda nid: {'EPUB_Filename': 'test.epub', 'Title': 'Synthetic book'})
        class Query:
            def __init__(self, **kw): self.kw = kw
            def failure(self, fn): self.fail = fn; return self
            def run_in_background(self): self.kw['success'](self.kw['op'](col))
        workspace.QueryOp = Query
        def wait_for(predicate):
            loop = QEventLoop()
            timer = QTimer()
            timer.timeout.connect(lambda: loop.quit() if predicate() else None)
            timer.start(10)
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            timeout.start(5000)
            if not predicate(): loop.exec()
            assert predicate(), 'Timed out waiting for reference state'
        def evaluate(window, script):
            values = []
            window.js(script, values.append)
            wait_for(lambda: bool(values))
            return values[0]
        place = dict(card_id=7, section=0, offset=-1, scroll=0)
        saved = get_connection(sys.argv[1], 'A')
        saved.execute('INSERT INTO epub_progress(card_id,section_index,scroll_ratio) VALUES(7,1,.65)')
        saved.commit()
        result = workspace._load(col, 'A', place)
        window = workspace.EpubReferenceWindow(result, place, profile='A', owner=None, beside=True)
        workspace._windows.append(window)
        main.resize(1200, 800)
        main.show()
        window.show()
        wait_for(lambda: window.loaded)
        assert evaluate(window, 'typeof window.incrementoEpubCurrentLocation') == 'function'
        second = workspace.EpubReferenceWindow(workspace._load(col, 'A', place), place,
                                               profile='A', beside=False)
        workspace._windows.append(second)
        second.show()
        wait_for(lambda: second.loaded)
        window.set_appearance('night')
        assert evaluate(window, "!!document.getElementById('incremento-epub-appearance')")
        assert evaluate(second, "!!document.getElementById('incremento-epub-appearance')")
        assert second.appearance.currentData() == 'night'
        assert evaluate(second, "getComputedStyle(document.querySelector('a')).color") == 'rgb(138, 180, 248)'
        second.set_appearance('original')
        assert not evaluate(window, "!!document.getElementById('incremento-epub-appearance')")
        second.close()
        window.zoom(.1)
        assert evaluate(window, 'window._incrementoEpubTextScale') == 1.1
        window.toggle_links(True)
        assert evaluate(window, "document.documentElement.classList.contains('incremento-epub-links-enabled')")
        assert evaluate(window, """(() => {
            const r=document.createRange(), n=document.querySelector('p').firstChild;
            r.setStart(n,0);r.setEnd(n,14);getSelection().removeAllRanges();getSelection().addRange(r);
            return window.incrementoAddEpubHighlight();
        })()""")
        wait_for(lambda: len(workspace.load_highlights(sys.argv[1], 'A', 7)) == 1)
        window.navigate(1, remember=True)
        wait_for(lambda: window.loaded and window.location['section'] == 1)
        assert evaluate(window, 'window.incrementoEpubCurrentLocation().sectionIndex') == 1
        assert evaluate(window, 'window._incrementoEpubTextScale') == 1.1
        window.back()
        wait_for(lambda: window.loaded and window.location['section'] == 0)
        assert evaluate(window, "document.querySelectorAll('.incremento-epub-highlight').length") > 0
        window.bookmark()
        window.close()
        assert window.closed and not workspace._windows
        assert (reader._current_epub_card_id, reader._current_epub_section_index,
                reader._current_epub_scroll_ratio) == (99, 8, .65)
        assert saved.execute('SELECT section_index,scroll_ratio FROM epub_progress WHERE card_id=7').fetchone() == (1,.65)
        main.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30,
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QTWEBENGINE_DISABLE_SANDBOX': '1',
             'QTWEBENGINE_CHROMIUM_FLAGS': '--disable-gpu'})
    assert result.returncode == 0, result.stdout + result.stderr
