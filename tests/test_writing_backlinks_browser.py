"""Shipped PDF backlinks use a real margin and retain the exact source identity."""
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


@pytest.mark.parametrize('side', [False, True], ids=['main', 'side'])
def test_pdf_writing_margin_never_covers_text_and_opens_only_its_saved_excerpt(tmp_path, side):
    from webpage_browser import browser_runtime, _runtime_dir
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    script = dedent(r'''
        import sys, json
        from pathlib import Path
        from urllib.parse import urlsplit
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        import pymupdf
        root = Path.cwd()
        with pymupdf.open() as pdf:
            pdf.new_page(width=600, height=900).insert_text((40, 100), 'Before. Original source passage. After.', fontsize=18)
            pdf.new_page(width=600, height=900).insert_text((40, 100), 'Another page', fontsize=18)
            data = pdf.tobytes()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width': 900, 'height': 800})
            page.set_default_timeout(5000)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            assets = {f'/web/{name}': root/'web'/name for name in (
                'pdf_dock.html', 'dist/pdf_viewer.js', 'pdfjs/pdf.min.js', 'pdfjs/pdf.worker.min.js')}
            def respond(route):
                path = urlsplit(route.request.url).path
                if path == '/fixture.pdf':
                    route.fulfill(body=data, content_type='application/pdf')
                elif path in assets:
                    route.fulfill(body=assets[path].read_bytes(),
                        content_type='text/html' if path.endswith('.html') else 'text/javascript')
                else:
                    route.abort()
            page.route('**/*', respond)
            side = sys.argv[3] == '1'
            page.goto('http://incremento.test/web/pdf_dock.html' + ('?reference=reader' if side else ''))
            page.wait_for_function('typeof window.' + ('incrementoReferenceStart' if side else 'incrementoPdfStart') + ' === "function"')
            page.evaluate("""side => {
                window.commands = [];
                window.pycmd = command => {
                    commands.push(command);
                    if (!command.startsWith('incremento_pdf_page_links:')) return;
                    const request = JSON.parse(command.slice(command.indexOf(':') + 1));
                    if (request.operation === 'list') {
                        setTimeout(() => window.incrementoReceivePdfPageLinks({...request, links: [],
                            writing: request.page === 1 ? [{anchor: 'a'.repeat(32),
                                title: '<Draft><img src="https://example.invalid/tracker">',
                                quote: 'Original source passage.'}] : []}), 0);
                    }
                };
                const worker = 'http://incremento.test/web/pdfjs/pdf.worker.min.js';
                const url = 'http://incremento.test/fixture.pdf';
                if (side) window.incrementoReferenceStart({card_id: 42, filename: 'fixture.pdf',
                    page: 1, url, worker, highlights: []});
                else {
                    window._pdfWorkerSrc = worker; window._pdfFileUrl = url;
                    window.incrementoPdfStart(42, 'fixture.pdf', 1, 1);
                }
            }""", side)
            margin = page.get_by_role('complementary', name='Writing excerpts', exact=True)
            expect(margin).to_be_visible()
            page.wait_for_function('() => !!document.querySelector("#pdf-text-layer span")')
            assert margin.bounding_box()['width'] <= 36, 'Backlinks must use a narrow arrow gutter'
            arrow = margin.get_by_role('button').first
            expect(arrow).to_have_text('↗')
            assert 'Original source passage.' in arrow.get_attribute('title')
            assert 'Original source passage.' not in margin.inner_text()
            page.wait_for_function("""() => {
                const arrow = document.querySelector('#pdf-writing-margin button');
                const text = document.querySelector('#pdf-text-layer span');
                return Math.abs(arrow.getBoundingClientRect().top - text.getBoundingClientRect().top) < 15;
            }""")
            reveal = {'cardId': 42, 'page': 1, 'excerpt': 'Original source passage.'}
            assert page.evaluate('v => window.incrementoRevealPdfExcerpt(v)', reveal)
            pulse = page.locator('[data-inc-excerpt-reveal]')
            expect(pulse).to_have_count(1)
            # The gutter-width repaint can replace the cue between browser calls.
            # Measure the visible cue and its source together after that repaint.
            page.wait_for_function("""() => {
                const cue = document.querySelector('[data-inc-excerpt-reveal]')?.getBoundingClientRect();
                const text = document.querySelector('#pdf-text-layer span')?.getBoundingClientRect();
                return cue?.width > 0 && cue.height > 0 && text?.width > 0 && cue.width < text.width * .8;
            }""")
            page.screenshot(path=str(Path(sys.argv[4])/'source-reveal.png'))
            page.clock.install()
            page.clock.fast_forward(4100)
            expect(pulse).to_have_count(0)
            page.evaluate('v => window.incrementoRevealPdfExcerpt(v)', reveal)
            expect(pulse).to_have_count(1)
            page.locator('#pdf-canvas-wrapper').click(position={'x': 10, 'y': 10})
            expect(pulse).to_have_count(0)
            assert not page.evaluate("commands.some(c => c.startsWith('incremento_pdf_highlight_add:'))")
            assert not page.evaluate('v => window.incrementoRevealPdfExcerpt({...v, cardId: 99})', reveal)
            page.evaluate('window.incrementoRevealPdfExcerpt({cardId: 42, page: 2, excerpt: "Another page"})')
            expect(pulse).to_have_count(1)
            expect(page.locator('#pdf-text-layer')).to_contain_text('Another page')
            page.evaluate('v => window.incrementoRevealPdfExcerpt(v)', reveal)
            expect(page.locator('#pdf-text-layer')).to_contain_text('Original source passage')
            expect(pulse).to_have_count(1)
            page.clock.fast_forward(2000)
            previous_reveal = pulse.element_handle()
            page.evaluate('v => window.incrementoRevealPdfExcerpt(v)', reveal)
            page.wait_for_function('element => !element.isConnected', arg=previous_reveal)
            expect(pulse).to_have_count(1)
            page.clock.fast_forward(2100)
            expect(pulse).to_have_count(1)
            page.clock.fast_forward(2000)
            expect(pulse).to_have_count(0)
            assert margin.locator('img').count() == 0
            page.get_by_role('button', name='Fit Width', exact=True).click()
            page.wait_for_function("""() => {
                const canvas = [...document.querySelectorAll('#pdf-canvas-wrapper > canvas')]
                    .find(node => getComputedStyle(node).display !== 'none');
                const box = canvas?.getBoundingClientRect();
                const margin = document.getElementById('pdf-writing-margin').getBoundingClientRect();
                return box && Math.abs(box.right - margin.left) < 1 && margin.right <= innerWidth + 1;
            }""")
            margin.get_by_role('button').click()
            opened = page.evaluate("JSON.parse(commands.at(-1).split('incremento_pdf_page_links:')[1])")
            assert opened['operation'] == 'writing' and opened['anchor'] == 'a' * 32
            assert opened['cardId'] == 42 and opened['page'] == 1
            page.screenshot(path=str(Path(sys.argv[4])/'writing-margin.png'))
            page.evaluate('window.incrementoPdfNav(1)')
            expect(margin).to_have_count(0)
            assert not errors, errors
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'),
        runtime[1], '1' if side else '0', str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
