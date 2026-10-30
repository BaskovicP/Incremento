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
            first.insert_text((40, 125), 'Same highlight second line', fontsize=18)
            first.insert_text((40, 160), 'Highlight with a note', fontsize=18)
            highlights = []
            for index, text in enumerate(['Saved highlighted passage', 'Highlight with a note']):
                rect = first.search_for(text)[0]
                highlights.append({'id': f'saved-{index}', 'page': 1, 'color': 'yellow', 'text': text,
                    'note': 'Keep this note' if index else '', 'linked_note_id': 123 + index,
                    'rects': [{'x': rect.x0, 'y': rect.y0, 'w': rect.width, 'h': rect.height}]})
            second_line = first.search_for('Same highlight second line')[0]
            highlights[0]['rects'].append({'x': second_line.x0, 'y': second_line.y0,
                'w': second_line.width, 'h': second_line.height})
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
                        page: 1, url, worker, highlights: fixture.highlights, show_delete: true});
                    else {
                        window._pdfWorkerSrc = worker;
                        window._pdfFileUrl = url;
                        window._incPdfHighlights = fixture.highlights;
                        window.incrementoPdfStart(id, 'fixture.pdf', 1, 1);
                        window.incrementoSetPdfHighlightDeleteButtons(true);
                    }
                };
                window.testStart();
            }""", fixture)
            text = page.locator('#pdf-text-layer span').filter(has_text='Saved highlighted passage')
            expect(text).to_be_visible()
            # Fit Width fills the reading area in both control views, including
            # short panes where the bottom of the page requires scrolling.
            def expect_fitted():
                page.wait_for_function("""() => {
                    const canvas = [...document.querySelectorAll('#pdf-canvas-wrapper canvas')]
                        .find(node => getComputedStyle(node).display !== 'none');
                    const box = canvas?.getBoundingClientRect();
                    const width = document.getElementById('pdf-canvas-wrapper').clientWidth;
                    return box?.height > 0 && box.top >= -.5 && box.left >= -.5
                        && Math.abs(box.width - width) <= .5 && box.right <= innerWidth + .5;
                }""")
            page.get_by_role('button', name='Zoom in', exact=True).click()
            page.get_by_role('button', name='Fit Width', exact=True).click()
            expect_fitted()
            assert page.evaluate("testCommands.at(-1)") == 'incremento_pdf_zoom:42:1'
            page.get_by_role('button', name='Show controls', exact=True).click()
            page.get_by_role('button', name='Fit Width', exact=True).click()
            expect_fitted()
            page.set_viewport_size({'width': 350, 'height': 500})
            expect_fitted()
            page.set_viewport_size({'width': 300, 'height': 500})
            expect_fitted()
            page.set_viewport_size({'width': 350, 'height': 700})
            page.get_by_role('button', name='Minimize controls', exact=True).click()
            expect_fitted()
            def hover_passage(locator):
                # Text may be shorter than 8 px in a narrow reader. Target its
                # center, resolving span geometry atomically across refits.
                box = locator.evaluate('node => {const r = node.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height};}')
                page.mouse.move(box['x'] + min(8, box['width'] / 2), box['y'] + box['height'] / 2)
            def click_passage(locator):
                box = locator.bounding_box()
                locator.click(position={'x': min(8, box['width'] / 2), 'y': box['height'] / 2})
            action = page.locator('.incremento-pdf-color-action').first
            clusters = page.locator('.incremento-pdf-highlight-actions')
            def expect_actions(index, visible):
                buttons = clusters.nth(index).get_by_role('button', include_hidden=True)
                assert buttons.count() == 4
                for button in buttons.all():
                    expect(button).to_have_css('opacity', '1' if visible else '0')
                    expect(button).to_have_css('pointer-events', 'auto' if visible else 'none')
            page.mouse.move(340, 10)
            expect_actions(0, False)
            expect_actions(1, False)
            hover_passage(text)
            expect_actions(0, True)
            expect_actions(1, False)
            hover_passage(page.locator('#pdf-text-layer span').filter(has_text='Same highlight second line'))
            expect_actions(0, True)
            note = page.locator('#pdf-text-layer span').filter(has_text='Highlight with a note')
            hover_passage(note)
            expect_actions(0, False)
            expect_actions(1, True)
            hover_passage(text)
            for button in clusters.first.get_by_role('button').all():
                button.hover()
                expect_actions(0, True)
            page.mouse.move(340, 10)
            expect_actions(0, False)
            # Keyboard focus reveals the whole group, including note, resize,
            # and delete, without revealing another highlight's controls.
            for button in clusters.first.get_by_role('button', include_hidden=True).all():
                button.focus()
                expect_actions(0, True)
                expect_actions(1, False)
            page.evaluate('document.activeElement.blur()')
            expect_actions(0, False)
            # The explicit delete-button preference still removes only X.
            page.evaluate('window.incrementoSetPdfHighlightDeleteButtons(false)')
            expect(clusters.first.get_by_role('button', include_hidden=True)).to_have_count(3)
            # Hovering and dragging on the text must preserve native selection.
            box = text.bounding_box()
            page.mouse.move(box['x'] + 2, box['y'] + box['height'] / 2)
            page.mouse.down()
            page.mouse.move(box['x'] + box['width'] * .6, box['y'] + box['height'] / 2, steps=8)
            page.mouse.up()
            assert page.evaluate('String(window.getSelection()).length') > 0
            page.evaluate('window.getSelection().removeAllRanges()')
            popup = page.get_by_role('dialog', name='Annotation appearance', exact=True)
            # Fitting above the full toolbar can make glyphs shorter than 8px.
            # Keep the click inside the glyphs and left of the hover actions.
            click_passage(text)
            expect(popup).to_be_visible()
            assert popup.get_by_role('button').count() == 15
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
            page.mouse.click(box['x'] + min(8, box['width'] / 2), box['y'] + box['height'] / 2)
            expect(popup).to_be_visible()
            page.keyboard.press('Escape')
            expect(popup).not_to_be_visible()
            for dismissal in ('outside', 'scroll'):
                click_passage(text)
                expect(popup).to_be_visible()
                if dismissal == 'outside': page.mouse.click(340, 10)
                else: page.evaluate('window.scrollBy(0, 80)')
                expect(popup).not_to_be_visible()
            # The circle opens the full picker directly, matching EPUB.
            action = page.locator('.incremento-pdf-color-action').first
            page.mouse.move(340, 10)
            expect(action).to_have_css('opacity', '0')
            expect(action).to_have_css('border-radius', '50%')
            before_picker = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_color:')).length")
            action.focus()
            page.keyboard.press('Shift')
            expect(action).to_have_css('opacity', '1')
            page.keyboard.press('Enter')
            expect(popup).not_to_be_visible()
            requests = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_color:'))")
            assert len(requests) == before_picker + 1
            assert json.loads(requests[-1].split(':', 1)[1]) == {
                'cardId': 42, 'currentColor': 'blue'}
            page.evaluate("window.incrementoPickPdfHighlightColor('#123456')")
            updates = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_update:'))")
            assert json.loads(updates[-1].split(':', 1)[1])['highlight'] == dict(fixture['highlights'][0], color='#123456')
            hover_passage(text)
            action.click()
            expect(popup).not_to_be_visible()
            request = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_color:')).at(-1)")
            assert json.loads(request.split(':', 1)[1]) == {'cardId': 42, 'currentColor': '#123456'}
            page.evaluate('window.incrementoPickPdfHighlightColor(null)')
            assert page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_update:')).length") == len(updates)
            # The explicit default changes future shortcuts, independently of one-off colors.
            page.get_by_role('button', name='Show controls', exact=True).click()
            default_color = page.get_by_role('button', name='Default color', exact=True)
            default_color.click()
            assert json.loads(page.evaluate('testCommands.at(-1)').split(':', 1)[1]) == {
                'cardId': 42, 'currentColor': 'yellow', 'defaultColor': True}
            page.evaluate("window.incrementoPickPdfHighlightColor('#123abc')")
            def select_passage():
                text.evaluate("""element => {
                    const range = document.createRange(); range.selectNodeContents(element);
                    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
                }""")
            select_passage()
            page.get_by_role('button', name='Use blue highlight color', exact=True).click()
            select_passage()
            page.keyboard.press('Control+h')
            default_color.click()
            page.evaluate('window.incrementoPickPdfHighlightColor(null)')
            select_passage()
            page.keyboard.press('Control+h')
            added = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_hl_add:'))")
            assert [json.loads(message.split(':', 1)[1])['highlight']['color'] for message in added] == [
                'blue', '#123abc', '#123abc']
            page.screenshot(path=str(Path(sys.argv[4])/'default-color.png'))
            # Reopening restores saved colors, and switching documents clears the popup.
            page.evaluate("window.incrementoReceivePdfHighlights([JSON.parse(testCommands.filter(c => c.startsWith('incremento_pdf_hl_update:')).at(-1).split(':').slice(1).join(':')).highlight])")
            click_passage(text)
            expect(popup).to_be_visible()
            page.evaluate('window.testStart(99)')
            expect(popup).not_to_be_visible()
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1],
        '1' if side_reader else '0', str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env=dict(os.environ), capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
