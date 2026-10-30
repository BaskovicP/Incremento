"""Footnote preview resizing in the shipped reader, using a synthetic PDF."""

import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


@pytest.mark.parametrize('side_reader', [False, True], ids=['main', 'side'])
@pytest.mark.parametrize('viewport_width', [1280, 350], ids=['wide', 'narrow'])
def test_footnote_preview_resizes_without_navigation_or_zoom_changes(tmp_path, side_reader, viewport_width):
    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    script = dedent(r'''
        import sys
        from pathlib import Path
        from urllib.parse import urlsplit
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        import pymupdf

        root = Path.cwd()
        with pymupdf.open() as pdf:
            pdf.new_page(width=600, height=800).insert_text((40, 100), 'Footnote reference', fontsize=18)
            pdf.new_page(width=600, height=800).insert_text((40, 650), 'The linked footnote', fontsize=18)
            rect = pdf[0].search_for('Footnote reference')[0]
            pdf[0].insert_link({'kind': pymupdf.LINK_GOTO, 'from': rect, 'page': 1,
                'to': pymupdf.Point(40, 630)})
            document = pdf.tobytes()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            viewport_width = int(sys.argv[5])
            page = browser.new_page(viewport={'width': viewport_width, 'height': 900})
            page.set_default_timeout(5000)
            assets = {f'/web/{name}': root/'web'/name for name in (
                'pdf_dock.html', 'dist/pdf_viewer.js', 'pdfjs/pdf.min.js', 'pdfjs/pdf.worker.min.js')}
            def respond(route):
                path = urlsplit(route.request.url).path
                if path == '/fixture.pdf':
                    route.fulfill(body=document, content_type='application/pdf')
                elif path in assets:
                    route.fulfill(body=assets[path].read_bytes(),
                        content_type='text/html' if path.endswith('.html') else 'text/javascript')
                else:
                    route.abort()
            page.route('**/*', respond)
            side = sys.argv[3] == '1'
            page.goto('http://incremento.test/web/pdf_dock.html' + ('?reference=reader' if side else ''))
            page.wait_for_function('typeof window.' + ('incrementoReferenceStart' if side else 'incrementoPdfStart') + ' === "function"')
            start_reader = """({side, size = null}) => {
                window.testCommands = [];
                window.savedPreviewSize = size;
                window.pycmd = command => {
                    window.testCommands.push(command);
                    if (command.startsWith('incremento_pdf_link_preview_size:')) {
                        window.savedPreviewSize = JSON.parse(command.slice(command.indexOf(':') + 1)).size;
                    }
                };
                const worker = 'http://incremento.test/web/pdfjs/pdf.worker.min.js';
                const url = 'http://incremento.test/fixture.pdf';
                if (side) window.incrementoReferenceStart({card_id: 42, filename: 'fixture.pdf', page: 1, url, worker,
                    link_preview_size: window.savedPreviewSize});
                else {
                    window._pdfWorkerSrc = worker;
                    window._pdfFileUrl = url;
                    window.incrementoPdfStart(42, 'fixture.pdf', 1, 1, ...Array(21), window.savedPreviewSize);
                }
            }"""
            page.evaluate(start_reader, {'side': side})
            reference = page.locator('#pdf-text-layer span').filter(has_text='Footnote reference')
            expect(reference).to_be_visible()
            # Link annotations load separately from the visible text layer.
            page.get_by_role('button', name='Links Off', exact=True).click()
            expect(page.locator('[data-pdf-link-index]')).to_be_visible()
            page.get_by_role('button', name='Links On', exact=True).click()
            reference.hover()
            popup = page.get_by_role('dialog', name='Footnote / link preview', exact=True)
            expect(popup.locator('canvas')).to_be_visible()
            page.clock.install()
            before = popup.bounding_box()
            commands = page.evaluate('testCommands.slice()')

            # Exercise the real corner grip; crossing the popup's old edge must
            # not let hover-dismissal close it during the drag.
            def resize(dx, dy):
                box = popup.bounding_box()
                x, y = box['x'] + box['width'] - 3, box['y'] + box['height'] - 3
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x + dx, y + dy, steps=8)
                page.clock.fast_forward(250)
                expect(popup).to_be_visible()
                page.mouse.up()
                return popup.bounding_box()

            larger = resize(140, 100)
            if viewport_width == 1280:
                assert larger['width'] >= before['width'] + 100, (before, larger)
            else:
                assert larger['x'] + larger['width'] <= viewport_width
            assert larger['height'] >= before['height'] + 70, (before, larger)
            smaller = resize(-100, -60)
            assert abs(smaller['width'] - max(280, larger['width'] - 100)) <= 1, (larger, smaller)
            assert smaller['height'] <= larger['height'] - 40, (larger, smaller)
            expect(popup.get_by_role('button', name='Zoom in', exact=True)).to_be_visible()
            expect(popup.locator('output')).to_have_text('150%')
            expect(reference).to_be_visible()
            assert page.evaluate("testCommands.filter(c => !c.startsWith('incremento_pdf_link_preview_size:'))") == commands
            saved_size = page.evaluate('savedPreviewSize')
            assert saved_size == {'width': round(smaller['width']), 'height': round(smaller['height'])}
            page.screenshot(path=str(Path(sys.argv[4])/'resized-footnote.png'))
            page.mouse.move(viewport_width - 8, 8)
            page.clock.fast_forward(250)
            expect(popup).not_to_be_visible()
            reference.hover()
            expect(popup.locator('canvas')).to_be_visible()
            reopened = popup.bounding_box()
            assert [reopened['width'], reopened['height']] == [smaller['width'], smaller['height']]
            # A new reader instance receives the durable profile preference at
            # startup, as it does after reopening Anki. It must not save again.
            page.reload()
            page.wait_for_function('typeof window.' + ('incrementoReferenceStart' if side else 'incrementoPdfStart') + ' === "function"')
            page.evaluate(start_reader, {'side': side, 'size': saved_size})
            expect(reference).to_be_visible()
            page.get_by_role('button', name='Links Off', exact=True).click()
            expect(page.locator('[data-pdf-link-index]')).to_be_visible()
            page.get_by_role('button', name='Links On', exact=True).click()
            reference.hover()
            expect(popup.locator('canvas')).to_be_visible()
            restored = popup.bounding_box()
            assert [restored['width'], restored['height']] == [saved_size['width'], saved_size['height']]
            assert page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_link_preview_size:'))") == []

            # Bounds keep controls on screen, including a small reader window.
            bounded = resize(2000, 2000)
            assert bounded['x'] + bounded['width'] <= viewport_width
            assert bounded['y'] + bounded['height'] <= 900
            minimum = resize(-2000, -2000)
            assert minimum['width'] >= min(280, viewport_width - minimum['x'] - 12)
            assert minimum['height'] >= 160
            for button in popup.get_by_role('button').all():
                box = button.bounding_box()
                assert minimum['x'] <= box['x'] and box['x'] + box['width'] <= minimum['x'] + minimum['width']
                assert minimum['y'] <= box['y'] and box['y'] + box['height'] <= minimum['y'] + minimum['height']
            page.mouse.move(minimum['x'] + 20, minimum['y'] + 20)
            page.keyboard.press('Escape')
            expect(popup).not_to_be_visible()
            page.mouse.move(viewport_width - 10, 10)
            reference.hover()
            expect(popup.locator('canvas')).to_be_visible()
            popup.get_by_role('button', name='Close', exact=True).click()
            expect(popup).not_to_be_visible()
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1],
        '1' if side_reader else '0', str(tmp_path), str(viewport_width)],
        cwd=Path(__file__).resolve().parents[1], env=dict(os.environ), capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
