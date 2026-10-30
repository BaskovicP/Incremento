"""Rich notes render in the shipped PDF reader without navigating its web view."""
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


def test_saved_rich_note_renders_updates_and_opens_links_through_the_reader_bridge():
    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    script = dedent(r'''
        import json, re, sys
        from pathlib import Path
        from urllib.parse import urlsplit
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        import pymupdf
        root = Path.cwd()
        with pymupdf.open() as pdf:
            document_page = pdf.new_page(width=600, height=900)
            document_page.insert_text((40, 100), 'Source passage', fontsize=18)
            rect = document_page.search_for('Source passage')[0]
            data = pdf.tobytes()
            highlight = {'id': 'rich', 'page': 1, 'color': 'yellow', 'text': 'Source passage',
                'note': 'Formatted link', 'note_html': '<p><b>Formatted</b> <a href="https://example.com/note">link</a></p>',
                'rects': [{'x': rect.x0, 'y': rect.y0, 'w': rect.width, 'h': rect.height}]}
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width': 900, 'height': 800})
            page.set_default_timeout(5000)
            assets = {f'/web/{name}': root/'web'/name for name in (
                'pdf_dock.html', 'dist/pdf_viewer.js', 'pdfjs/pdf.min.js', 'pdfjs/pdf.worker.min.js')}
            def respond(route):
                path = urlsplit(route.request.url).path
                if path == '/fixture.pdf':
                    route.fulfill(body=data, content_type='application/pdf')
                elif path in assets:
                    route.fulfill(body=assets[path].read_bytes(), content_type='text/html' if path.endswith('.html') else 'text/javascript')
                else:
                    route.abort()
            page.route('**/*', respond)
            page.goto('http://incremento.test/web/pdf_dock.html')
            page.wait_for_function('typeof window.incrementoPdfStart === "function"')
            page.evaluate("""highlight => {
                window.testCommands = [];
                window.pycmd = command => window.testCommands.push(command);
                window._pdfWorkerSrc = 'http://incremento.test/web/pdfjs/pdf.worker.min.js';
                window._pdfFileUrl = 'http://incremento.test/fixture.pdf';
                window._incPdfHighlights = [highlight];
                window.incrementoPdfStart(42, 'fixture.pdf', 1, 1);
            }""", highlight)
            source = page.locator('#pdf-text-layer span').filter(has_text='Source passage')
            expect(source).to_be_visible()
            box = source.evaluate('node => {const r = node.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height};}')
            page.mouse.move(box['x'] + min(8, box['width'] / 2), box['y'] + box['height'] / 2)
            expect(page.get_by_role('tooltip').locator('b')).to_have_text('Formatted')
            page.get_by_role('button', name='Show controls', exact=True).click()
            panel_button = page.get_by_role('button', name=re.compile(r'Highlights \('))
            panel_button.click()
            link = page.locator('a[href="https://example.com/note"]')
            expect(link).to_be_visible()
            link.click()
            opened = page.evaluate("testCommands.filter(c => c.startsWith('incremento_pdf_open_link:'))")
            assert json.loads(opened[-1].split(':', 1)[1]) == {'cardId': 42, 'url': 'https://example.com/note'}
            assert page.url == 'http://incremento.test/web/pdf_dock.html'
            page.evaluate("window.incrementoUpdatePdfHighlightNote('rich','Changed note','<p><u>Changed</u> note</p>')")
            expect(page.locator('u').filter(has_text='Changed')).to_be_visible()
            expect(link).to_have_count(0)
            page.evaluate("window.incrementoUpdatePdfHighlightNote('rich','Literal text','<img src=https://example.com/unwanted onerror=bad()>')")
            expect(page.get_by_text('Literal text', exact=True)).to_be_visible()
            assert page.locator('img').count() == 0
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1]],
        cwd=Path(__file__).resolve().parents[1], env=dict(os.environ), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
