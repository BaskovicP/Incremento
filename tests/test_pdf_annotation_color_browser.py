"""Click-to-recolor behavior in the shipped reader, using only synthetic PDFs."""
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


@pytest.mark.parametrize('side_reader', [False, True], ids=['main', 'side'])
def test_pdf_annotation_palette_recolors_and_dismisses_without_losing_metadata(tmp_path, side_reader):
    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    script = dedent(r'''
        import base64, json, sys
        from pathlib import Path
        from urllib.parse import urlsplit
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        import pymupdf
        root = Path.cwd()
        # Build the PDF in this clean interpreter: the pytest harness installs
        # backend stand-ins and a statistics module that shadows the stdlib.
        with pymupdf.open() as pdf:
            first = pdf.new_page(width=600, height=1000)
            first.insert_text((40, 100), 'Saved highlighted passage', fontsize=18)
            first.insert_text((40, 160), 'Highlight with a note', fontsize=18)
            highlights = []
            for index, text in enumerate(['Saved highlighted passage', 'Highlight with a note']):
                rect = first.search_for(text)[0]
                highlights.append({'id': f'saved-{index}', 'page': 1, 'color': 'yellow', 'text': text,
                    'note': 'Keep this note' if index else '', 'linked_note_id': 123 + index,
                    'rects': [{'x': rect.x0, 'y': rect.y0, 'w': rect.width, 'h': rect.height}]})
            pdf.new_page(width=600, height=1000).insert_text((40, 100), 'Second page')
            fixture = {'pdf': base64.b64encode(pdf.tobytes()).decode(), 'highlights': highlights,
                'side': sys.argv[3] == '1'}
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width': 350, 'height': 700})
            page.set_default_timeout(5000)
            assets = {f'/web/{name}': root/'web'/name for name in (
                'pdf_dock.html', 'dist/pdf_viewer.js', 'pdfjs/pdf.min.js', 'pdfjs/pdf.worker.min.js')}
            def respond(route):
                path = urlsplit(route.request.url).path
                if path == '/fixture.pdf':
                    route.fulfill(body=base64.b64decode(fixture['pdf']), content_type='application/pdf')
                elif path in assets:
                    route.fulfill(body=assets[path].read_bytes(), content_type='text/html' if path.endswith('.html') else 'text/javascript')
                else:
                    route.abort()
            page.route('**/*', respond)
            page.goto('http://incremento.test/web/pdf_dock.html' + ('?reference=reader' if fixture['side'] else ''))
            page.wait_for_function('typeof window.' + ('incrementoReferenceStart' if fixture['side'] else 'incrementoPdfStart') + ' === "function"')
            page.evaluate("""fixture => {
                window.testCommands = [];
                window.pycmd = c => window.testCommands.push(c);
                window.testStart = (id = 42) => {
                    const worker = 'http://incremento.test/web/pdfjs/pdf.worker.min.js';
                    const url = 'http://incremento.test/fixture.pdf';
                    if (fixture.side) window.incrementoReferenceStart({card_id: id, filename: 'fixture.pdf',
                        page: 1, url, worker, highlights: fixture.highlights, show_delete: false});
                    else {
                        window._pdfWorkerSrc = worker;
                        window._pdfFileUrl = url;
                        window._incPdfHighlights = fixture.highlights;
                        window.incrementoPdfStart(id, 'fixture.pdf', 1, 1);
                        window.incrementoSetPdfHighlightDeleteButtons(false);
                    }
                };
                window.testStart();
            }""", fixture)
            text = page.locator('#pdf-text-layer span').filter(has_text='Saved highlighted passage')
            expect(text).to_be_visible()
            popup = page.get_by_role('dialog', name='Choose annotation color', exact=True)
            # A real text-layer click must work without needing the Highlights list.
            text.click(position={'x': 8, 'y': 8})
            expect(popup).to_be_visible()
            assert popup.get_by_role('button').count() == 9
            box = popup.bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= 350
            assert box['y'] >= 0 and box['y'] + box['height'] <= 700
            page.screenshot(path=str(Path(sys.argv[4])/'palette.png'))
            popup.get_by_role('button', name='Highlight blue', exact=True).click()
            expect(popup).not_to_be_visible()
            updates = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_update:'))")
            assert len(updates) == 1
            assert json.loads(updates[0].split(':', 1)[1]) == {
                'cardId': 42, 'highlight': dict(fixture['highlights'][0], color='blue')}
            # Clicking the note's hover overlay must reach the same palette.
            note_text = page.locator('#pdf-text-layer span').filter(has_text='Highlight with a note')
            box = note_text.bounding_box()
            page.mouse.click(box['x'] + 8, box['y'] + 8)
            expect(popup).to_be_visible()
            page.keyboard.press('Escape')
            expect(popup).not_to_be_visible()
            for dismissal in ('outside', 'scroll'):
                text.click(position={'x': 8, 'y': 8})
                expect(popup).to_be_visible()
                if dismissal == 'outside': page.mouse.click(340, 10)
                else: page.evaluate('window.scrollBy(0, 80)')
                expect(popup).not_to_be_visible()
            # Keyboard users can use the color dot and continue into the popup.
            action = page.locator('.incremento-pdf-color-action').first
            action.focus()
            page.keyboard.press('Enter')
            expect(popup).to_be_visible()
            assert popup.locator(':focus').count() == 1
            popup.get_by_role('button', name='More colors…', exact=True).click()
            expect(popup).not_to_be_visible()
            page.evaluate("window.incrementoPickPdfHighlightColor('#123456')")
            updates = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_update:'))")
            assert json.loads(updates[-1].split(':', 1)[1])['highlight'] == dict(fixture['highlights'][0], color='#123456')
            # Reopening restores saved colors, and switching documents clears the popup.
            page.evaluate("window.incrementoReceivePdfHighlights([JSON.parse(testCommands.filter(c => c.startsWith('incremento_pdf_hl_update:')).at(-1).split(':').slice(1).join(':')).highlight])")
            action.focus()
            page.keyboard.press('Enter')
            expect(popup).to_be_visible()
            page.evaluate('window.testStart(99)')
            expect(popup).not_to_be_visible()
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1],
        '1' if side_reader else '0', str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env=dict(os.environ), capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
