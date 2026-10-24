"""Render synthetic EPUB highlights in Anki's engine and isolated JS world."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("suffix", [".html", ".xhtml"])
def test_cross_paragraph_highlight_paints_without_reflow_in_qt_application_world(tmp_path, suffix):
    chapter = tmp_path / ("chapter" + suffix)
    chapter.write_text(
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Highlight fixture</title>'
        '<style>p, em { background: white; }</style></head><body>'
        '<p id="first">First paragraph with <em>styled text</em> and an ending.</p>'
        '<p id="second">Second paragraph with another ending.</p>'
        '<p>Third paragraph provides another text row.</p></body></html>',
        encoding="utf-8",
    )
    script = dedent('''
        import ast, json, sys
        from pathlib import Path
        from PyQt6.QtCore import QEventLoop, QTimer, QUrl
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        # Exercise the real script builder without importing Anki or storage.
        source = Path('frontend/epub_dock.py')
        tree = ast.parse(source.read_text())
        constants = {'_PYCMD_BRIDGE', '_EPUB_HIGHLIGHT_COLORS', '_MAX_EPUB_SELECTION_CHARS'}
        namespace = {node.targets[0].id: ast.literal_eval(node.value)
                     for node in tree.body if isinstance(node, ast.Assign)
                     and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants}
        namespace.update(json=json, _current_sections=lambda: [{'text': 'Synthetic chapter'}],
                         normalize_highlight_color=lambda color: color,
                         configured_highlight_when_extracting=lambda: False,
                         get_locale=lambda: 'en', t=lambda key, **kwargs: key)
        builder = next(node for node in tree.body
                       if isinstance(node, ast.FunctionDef) and node.name == '_build_page_script')
        exec(compile(ast.Module(body=[builder], type_ignores=[]), str(source), 'exec'), namespace)
        page_script = namespace['_build_page_script'](
            card_id=7, section_index=0, scroll_ratio=0, text_scale=1.3, read_anchor=None,
            focus_offset=-1, search_query='', highlights=[], bridge_nonce='test-nonce')

        app = QApplication(['epub-highlight-test'])
        app.setQuitOnLastWindowClosed(False)
        view = QWebEngineView()
        profile = QWebEngineProfile(view)  # Anonymous, with no persisted browser state.
        page = QWebEnginePage(profile, view)
        view.setPage(page)
        view.resize(900, 600)
        view.show()
        world = QWebEngineScript.ScriptWorldId.ApplicationWorld.value
        errors = []

        def evaluate(code, script_world=world):
            loop = QEventLoop()
            values = []
            def done(value):
                values.append(value)
                loop.quit()
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(5000)
            page.runJavaScript(code, script_world, done)
            loop.exec()
            assert values, 'Timed out waiting for the isolated reader script'
            return values[0]

        def exercise():
            try:
                loop = QEventLoop()
                loaded = []
                def on_load(ok):
                    loaded.append(ok)
                    loop.quit()
                page.loadFinished.connect(on_load)
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(loop.quit)
                timer.start(10000)
                view.load(QUrl.fromLocalFile(sys.argv[1]))
                loop.exec()
                page.loadFinished.disconnect(on_load)
                assert loaded == [True]
                evaluate(page_script)
                rectangles = """JSON.stringify(Array.from(document.querySelectorAll('p')).map(p => {
                    const r = p.getBoundingClientRect(); return [r.x, r.y, r.width, r.height];
                }))"""
                before = evaluate(rectangles)
                # The user's native selection is shared with ApplicationWorld.
                evaluate("""(() => {
                    const range = document.createRange();
                    range.setStart(document.getElementById('first').firstChild, 6);
                    range.setEnd(document.getElementById('second').firstChild, 16);
                    window.getSelection().removeAllRanges();
                    window.getSelection().addRange(range);
                })()""", QWebEngineScript.ScriptWorldId.MainWorld.value)
                assert evaluate('window.incrementoAddEpubHighlight()') is True
                assert evaluate(rectangles) == before, 'Highlighting changed paragraph layout'
                assert evaluate("""(() => {
                    const nodes = Array.from(document.querySelectorAll('.incremento-epub-highlight'));
                    return nodes.length > 1 && nodes.every(node => !node.querySelector('p, em')
                        && getComputedStyle(node).backgroundColor === 'rgba(255, 220, 0, 0.45)');
                })()"""), 'Every selected text run must paint above chapter backgrounds'
                assert evaluate("""(() => {
                    const first = document.querySelector('.incremento-epub-highlight');
                    const id = first.dataset.id;
                    window.incrementoUpdateEpubHighlightNote(id, 'keep this note');
                    window.incrementoUpdateEpubHighlightColor(id, '#12ab34');
                    return Array.from(document.querySelectorAll('.incremento-epub-highlight')).every(node =>
                        node.dataset.id === id && node.dataset.note === 'keep this note'
                        && node.dataset.color === '#12ab34'
                        && getComputedStyle(node).backgroundColor === 'rgba(18, 171, 52, 0.42)');
                })()"""), 'Recoloring must retain every run, identity and note'
                assert evaluate(rectangles) == before
                assert evaluate('typeof window.incrementoAddEpubHighlight',
                                QWebEngineScript.ScriptWorldId.MainWorld.value) == 'undefined'
                # Exercise pointer coordinates with Qt's real DOM/caret geometry.
                # OS pointer capture is the only stub in this offscreen frame.
                point = json.loads(evaluate("""JSON.stringify((() => {
                    const target = document.querySelector('.incremento-epub-highlight');
                    window._incrementoEpubClickListener({
                        isTrusted: true, target, preventDefault(){}, stopPropagation(){}
                    });
                    document.getElementById('incremento-epub-highlight-resize-btn').click();
                    const handle = document.querySelector(
                        '.incremento-epub-resize-handle[data-endpoint="end"]');
                    const r = handle.getBoundingClientRect();
                    handle.setPointerCapture = () => {};
                    window._pinTestTarget = handle;
                    return {x: r.left + 14, y: r.top + 21};
                })())"""))
                original = evaluate('JSON.stringify(window._incrementoEpubHighlightResize.highlight)')
                def pointer_event(kind):
                    evaluate('window._pinTestTarget.dispatchEvent(new PointerEvent('
                             + json.dumps(kind) + ', ' + json.dumps({
                                 'clientX': point['x'], 'clientY': point['y'],
                                 'pointerId': 1, 'button': 0, 'bubbles': True,
                             }) + '));')
                pointer_event('pointerdown')
                assert evaluate('window._incrementoEpubHighlightResize.dragging') is True
                pointer_event('pointermove')
                pointer_event('pointerup')
                assert evaluate('window._incrementoEpubHighlightResize.dragging') is False
                assert evaluate('JSON.stringify(window._incrementoEpubHighlightResize.highlight)') == original
            except BaseException as error:
                errors.append(error)
            finally:
                view.close()
                app.quit()
        QTimer.singleShot(0, exercise)
        app.exec()
        if errors:
            raise errors[0]
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(chapter)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QTWEBENGINE_DISABLE_SANDBOX": "1",
             "QTWEBENGINE_CHROMIUM_FLAGS": "--disable-gpu"},
        capture_output=True, text=True, timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
