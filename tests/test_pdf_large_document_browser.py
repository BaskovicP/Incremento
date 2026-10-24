"""Large-document resource lifecycle in the shipped viewer, with synthetic PDFs."""
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


@pytest.mark.parametrize('side_reader', [False, True], ids=['main', 'side'])
def test_large_pdf_keeps_rendering_bounded_and_snapshot_crops_correct(tmp_path, side_reader):
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
        target = Path(sys.argv[4]) / 'textbook.pdf'
        with pymupdf.open() as pdf:
            for number in range(1, 1748):
                sheet = pdf.new_page(width=600, height=800)
                sheet.insert_text((40, 40), f'Synthetic page {number}', fontsize=18)
                if number <= 12:
                    image = pymupdf.Pixmap(pymupdf.csRGB, 128, 128,
                        bytes((pixel * 37 + number) % 256 for pixel in range(128 * 128 * 3)), False)
                    sheet.insert_image(pymupdf.Rect(40, 180, 560, 760), pixmap=image)
                sheet.draw_rect(pymupdf.Rect(270, 80, 330, 130), color=(1, 0, 0), fill=(1, 0, 0))
            pdf.save(target)

        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width': 1400, 'height': 1000}, device_scale_factor=2)
            page.set_default_timeout(10000)
            assets = {f'/web/{name}': root/'web'/name for name in (
                'pdf_dock.html', 'dist/pdf_viewer.js', 'pdfjs/pdf.min.js', 'pdfjs/pdf.worker.min.js')}
            def respond(route):
                path = urlsplit(route.request.url).path
                if path == '/textbook.pdf':
                    route.fulfill(path=str(target), content_type='application/pdf')
                elif path in assets:
                    route.fulfill(path=str(assets[path]),
                        content_type='text/html' if path.endswith('.html') else 'text/javascript')
                else:
                    route.abort()
            page.route('**/*', respond)
            side = sys.argv[3] == '1'
            page.goto('http://incremento.test/web/pdf_dock.html' + ('?reference=reader' if side else ''))
            page.wait_for_function('() => typeof window.' + ('incrementoReferenceStart' if side else 'incrementoPdfStart') + ' === "function"')
            page.evaluate("""side => {
                window.testCommands = []; window.pycmd = c => window.testCommands.push(c);
                window.testPages = new Map();
                const original = window.pdfjsLib.getDocument;
                window.pdfjsLib.getDocument = options => {
                    const task = original(options);
                    task.promise.then(doc => {
                        const getPage = doc.getPage.bind(doc);
                        doc.getPage = number => getPage(number).then(sheet => {
                            window.testPages.set(number, sheet); return sheet;
                        });
                    });
                    return task;
                };
                const worker = 'http://incremento.test/web/pdfjs/pdf.worker.min.js';
                const url = 'http://incremento.test/textbook.pdf';
                if (side) window.incrementoReferenceStart({card_id: 42, filename: 'textbook.pdf',
                    page: 1, zoom: 4, url, worker, highlights: []});
                else {
                    window._pdfWorkerSrc = worker; window._pdfFileUrl = url;
                    window.incrementoPdfStart(42, 'textbook.pdf', 1, 4);
                }
            }""", side)

            def ready(number):
                page.wait_for_function("""number => {
                    const canvas = [...document.querySelectorAll('#pdf-canvas-wrapper > canvas')]
                        .find(c => c.style.display === 'block' && +c.dataset.pdfPage === number);
                    return canvas && document.querySelector('#pdf-text-layer')?.textContent.includes(`Synthetic page ${number}`);
                }""", arg=number)

            ready(1)
            canvas = page.locator('#pdf-canvas-wrapper > canvas:visible')
            geometry = canvas.evaluate('c => ({width: c.width, height: c.height, css: c.getBoundingClientRect().toJSON()})')
            assert geometry['width'] * geometry['height'] <= 8_000_000, geometry
            assert geometry['css']['width'] == 2640, 'High zoom preserves the displayed page geometry'
            page.get_by_role('button', name='Annotate', exact=True).click()
            page.locator('button').filter(has_text='Snapshot').first.click()
            page.locator('[data-pdf-snapshot-overlay]').wait_for()
            box = canvas.bounding_box()
            x1, y1 = box['x'] + box['width'] * .48, box['y'] + box['height'] * .115
            x2, y2 = box['x'] + box['width'] * .52, box['y'] + box['height'] * .135
            page.mouse.move(x1, y1); page.mouse.down()
            page.mouse.move(x2, y2, steps=2); page.mouse.up()
            page.wait_for_function("() => testCommands.some(c => c.startsWith('incremento_pdf_snapshot:'))")
            capture = page.evaluate("""async () => {
                const command = testCommands.find(c => c.startsWith('incremento_pdf_snapshot:'));
                const {image} = JSON.parse(command.slice('incremento_pdf_snapshot:'.length));
                const bitmap = new Image(); bitmap.src = image; await bitmap.decode();
                const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height;
                const ctx = canvas.getContext('2d'); ctx.drawImage(bitmap, 0, 0);
                return {width: bitmap.width, height: bitmap.height,
                    pixel: [...ctx.getImageData(bitmap.width >> 1, bitmap.height >> 1, 1, 1).data]};
            }""")
            assert capture['width'] < x2 - x1, 'Capture must use the bounded backing resolution'
            assert capture['pixel'] == [255, 0, 0, 255], capture

            for number in [*range(2, 13), 1747, 1]:
                current = int(canvas.get_attribute('data-pdf-page'))
                page.evaluate('delta => window.incrementoPdfNav(delta)', number - current)
                ready(number)
                surfaces = page.locator('#pdf-canvas-wrapper > canvas').evaluate_all('nodes => nodes.map(c => c.width * c.height)')
                assert sum(surfaces) <= 8_000_000, surfaces
                # Inspect actual PDF.js resources; the library's cleanup must
                # clear operator lists rather than only evict our own handles.
                retained = page.evaluate('[...testPages.values()].filter(p => p._intentStates.size > 0).length')
                assert retained <= 3, retained
            expect(page.locator('#pdf-text-layer')).to_contain_text('Synthetic page 1')
            browser.close()
    ''')
    result = subprocess.run(
        [runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1],
         '1' if side_reader else '0', str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env=dict(os.environ),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
