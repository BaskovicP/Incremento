"""PDF preview controls must leave the rest of an Anki field editable."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


_BROWSER_SETUP = dedent('''
        import json
        from html import escape
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from aqt.qt import QApplication, QCoreApplication, QEvent, QEventLoop, QImage, QTimer, QUrl
        from PyQt6.QtQuick import QQuickWindow, QSGRendererInterface
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from frontend import reader_links

        # Match Anki's software graphics setup before offscreen WebEngine starts.
        QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.Software)
        app = QApplication(['pdf-preview-editor-test'])
        # Resolve the screenshot against real temporary media, as Anki does.
        # A missing image under about:blank can crash this offscreen Qt build.
        media = TemporaryDirectory(prefix='incremento-editor-media-')
        image = QImage(16, 16, QImage.Format.Format_RGB32)
        image.fill(0xffffffff)
        assert image.save(str(Path(media.name) / 'synthetic-preview.png'))
        # Keep a real editor view alive across page loads. These DOM editing
        # checks need a viewport, not an unsupported macOS offscreen surface.
        view = QWebEngineView()
        view.resize(800, 600)
        page = view.page()

        def wait_for(start):
            loop = QEventLoop()
            results = []
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            def done(value):
                results.append(value)
                loop.quit()
            timer.start(5000)
            start(done)
            if not results:
                loop.exec()
            timer.stop()
            assert results, 'WebEngine operation timed out'
            return results[0]

        def load(html):
            def start(done):
                def loaded(ok):
                    page.loadFinished.disconnect(loaded)
                    done(ok)
                page.loadFinished.connect(loaded)
                page.setHtml('<div id="field" contenteditable="true">' + html + '</div>',
                             QUrl.fromLocalFile(str(Path(media.name) / 'editor.html')))
            assert wait_for(start)

        def js(source):
            return wait_for(lambda done: page.runJavaScript(source, done))

''')


def _run_editor_browser_script(script):
    script = _BROWSER_SETUP + dedent(script) + dedent('''
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        media.cleanup()
    ''')
    result = subprocess.run(
        [sys.executable, '-X', 'faulthandler', '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        # Offscreen macOS has no native compositor surface, even with GPU
        # rendering disabled. Keep real WebEngine editing on the software path.
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QTWEBENGINE_DISABLE_SANDBOX': '1',
             'QTWEBENGINE_CHROMIUM_FLAGS': '--disable-gpu --disable-gpu-compositing'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["snapshot", "context"])
@pytest.mark.parametrize("mode", ["new", "saved-review", "saved-editor"])
def test_source_preview_toggles_inside_card_without_activating_enclosing_pdf_link(kind, mode):
    _run_editor_browser_script(f'kind = {kind!r}\nmode = {mode!r}\n' + dedent('''
        from types import SimpleNamespace

        command = 'incremento_open_pdf_ref:{"card_id":7,"filename":"synthetic.pdf","page":3}'
        citation = reader_links.make_reader_anchor_html(command, 'Page 3')
        if mode == 'new':
            if kind == 'snapshot':
                preview = reader_links.pdf_snapshot_card_html(
                    'synthetic-preview.png', preview_label='Source page preview')
            else:
                preview = reader_links.pdf_text_context_reference_html(
                    'Exact excerpt', citation, 'Before\\nExact excerpt\\nAfter', excerpt='Exact excerpt',
                    context_rows=1, preview_label='Source page preview')
                preview = preview[preview.index('<div data-incremento-pdf-text-preview'):]
        else:
            content = '<img src="synthetic-preview.png">' if kind == 'snapshot' else 'Saved context'
            preview = ('<details class="incremento-pdf-' + kind + '-details" contenteditable="false">'
                       '<summary>Source page preview</summary><div>' + content + '</div></details>')
            if mode == 'saved-review':
                preview = reader_links.collapsible_pdf_snapshot_previews(preview)
        # An edited citation can accidentally enclose the preview. Its click
        # opens the reference reader and cancels the summary's native toggle.
        enclosing_link = citation.replace('</a>', '<br>' + preview + '</a>')
        # Match Anki replacing card HTML in an already loaded reviewer page.
        load('')
        js('document.getElementById("field").innerHTML = ' + json.dumps(enclosing_link))
        if mode == 'saved-editor':
            reader_links.prepare_pdf_previews_for_editor(SimpleNamespace(
                note=SimpleNamespace(fields=[enclosing_link]), web=SimpleNamespace(eval=js)))
        js("document.getElementById('field').contentEditable = 'false';"
           "window.commands = []; window.pycmd = command => window.commands.push(command);")
        assert js("document.querySelector('summary').closest('a') === document.querySelector('a')")
        assert js("""(() => {
            const preview = document.querySelector('details');
            preview.querySelector('summary').click();
            return {open: preview.open, commands: window.commands};
        })()""") == {'open': True, 'commands': []}, \
            'Source page preview must expand inline without opening the PDF reader'
        assert js("""(() => {
            const preview = document.querySelector('details');
            const content = preview.querySelector('div');
            content.click();
            return preview.open && window.commands.length === 0;
        })()""") is True, 'Preview content must not activate its enclosing citation'
        assert js("""(() => {
            const preview = document.querySelector('details');
            preview.querySelector('summary').click();
            return {open: preview.open, commands: window.commands};
        })()""") == {'open': False, 'commands': []}
        js("document.querySelector('a').click()")
        assert js('window.commands') == [command], 'The citation must still open the PDF reader'
    '''))


def test_pdf_extract_preview_allows_typing_below_it_without_creating_more_buttons():
    _run_editor_browser_script('''
        command = 'incremento_open_pdf_ref:{"card_id":7,"filename":"synthetic.pdf","page":3}'
        citation = '<a onclick="' + escape('pycmd(' + json.dumps(command) + '); return false;', quote=True) + '" '
        citation += 'style="cursor:pointer; color:#4a90d9; text-decoration:none;">Page 3</a>'
        previews = [
            reader_links.pdf_snapshot_reference_html(
                'Exact excerpt', citation, 'synthetic-preview.png', preview_label='Source page preview'),
            reader_links.pdf_text_context_reference_html(
                'Exact excerpt', citation, 'Before\\nExact excerpt\\nAfter', excerpt='Exact excerpt',
                context_rows=1, preview_label='Source page preview'),
        ]
        for html in previews:
            load(html)
            assert js("document.querySelector('summary').isContentEditable") is False, \
                'The preview button must not become an editable paragraph'
            assert js("""(() => {
                const field = document.getElementById('field');
                const summary = field.querySelector('summary');
                summary.click();
                if (!summary.parentElement.open) return false;
                summary.click();
                if (summary.parentElement.open) return false;
                const range = document.createRange();
                range.selectNodeContents(field);
                range.collapse(false);
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                field.focus();
                document.execCommand('insertText', false, 'First added line');
                document.execCommand('insertParagraph');
                document.execCommand('insertText', false, 'Second added line');
                return field.querySelectorAll('summary').length === 1
                    && summary.textContent === 'Source page preview'
                    && field.innerText.includes('First added line')
                    && field.innerText.includes('Second added line')
                    && !summary.parentElement.textContent.includes('added line');
            })()""") is True, js("document.getElementById('field').innerHTML")
            edited = js("document.getElementById('field').innerHTML")
            rebuilt, _, _ = reader_links.rebuild_pdf_reference_card_snapshots(
                edited, lambda *_args: 'rebuilt-preview.png', preview_label='Source page preview')
            assert 'First added line' in rebuilt and 'Second added line' in rebuilt, \
                'Rebuilding a preview must preserve text added below it'
    ''')


def test_opening_older_previews_preserves_content_and_adds_one_typing_line_including_shadow_fields():
    _run_editor_browser_script('''
        from types import SimpleNamespace

        for kind in ('snapshot', 'context'):
            old_html = (
                'Keep <b>my excerpt</b><br><a href="#synthetic">Page 3</a><br>'
                '<div data-incremento-pdf-' + ('snapshot' if kind == 'snapshot' else 'text-preview') + '="1">'
                '<details class="incremento-pdf-' + kind + '-details">'
                '<summary>Source page preview</summary><div>Saved context</div></details></div>'
            )
            for shadow in (False, True):
                load(old_html)
                if shadow:
                    js("""(() => {
                        const host = document.createElement('anki-editable');
                        document.body.appendChild(host);
                        host.attachShadow({mode:'open'}).appendChild(document.getElementById('field'));
                    })()""")
                field_js = ("document.querySelector('anki-editable').shadowRoot.getElementById('field')"
                            if shadow else "document.getElementById('field')")
                editor = SimpleNamespace(note=SimpleNamespace(fields=[old_html]),
                                         web=SimpleNamespace(eval=js))
                reader_links.prepare_pdf_previews_for_editor(editor)
                assert editor.note.fields == [old_html], 'Opening an editor must not write to its note'
                protected = js(field_js + '.innerHTML')
                reader_links.prepare_pdf_previews_for_editor(editor)
                assert js(field_js + '.innerHTML') == protected, 'Reload must not add extra blank lines'
                assert js(field_js + ".querySelector('summary').isContentEditable") is False
                assert js("""((field) => {
                    const details = field.querySelector('details');
                    details.querySelector('summary').click();
                    if (!details.open) return false;
                    details.querySelector('summary').click();
                    const line = field.lastElementChild;
                    if (!line || !line.isContentEditable) return false;
                    if (line.closest('[data-incremento-pdf-snapshot], [data-incremento-pdf-text-preview]')) return false;
                    const range = document.createRange();
                    range.selectNodeContents(line);
                    range.collapse(false);
                    const selection = field.getRootNode().getSelection
                        ? field.getRootNode().getSelection() : window.getSelection();
                    selection.removeAllRanges();
                    selection.addRange(range);
                    field.focus();
                    document.execCommand('insertText', false, 'My added text');
                    return line.textContent === 'My added text'
                        && details.textContent === 'Source page previewSaved context'
                        && field.querySelector('b').outerHTML === '<b>my excerpt</b>'
                        && field.querySelector('a').getAttribute('href') === '#synthetic';
                })(""" + field_js + ')') is True, js(field_js + '.innerHTML')

        load('<details><summary>My own control</summary><div>My own text</div></details>')
        original = js("document.getElementById('field').innerHTML")
        editor = SimpleNamespace(note=SimpleNamespace(fields=[original]), web=SimpleNamespace(eval=js))
        reader_links.prepare_pdf_previews_for_editor(editor)
        assert js("document.getElementById('field').innerHTML") == original
    ''')
