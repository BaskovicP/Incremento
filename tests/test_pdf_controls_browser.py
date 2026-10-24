"""Exercise shipped reader controls in an isolated browser with synthetic data."""
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


@pytest.mark.parametrize('scale', [1, 1.5])
def test_pdf_essential_controls_and_drawers_fit_narrow_and_wide_readers(tmp_path, scale):
    from webpage_browser import browser_runtime, _runtime_dir
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    script = dedent(r'''
        import json, sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright
        root = Path.cwd()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width':900, 'height':700}, device_scale_factor=float(sys.argv[3]))
            page.goto((root/'web/pdf_dock.html').as_uri())
            page.wait_for_function('typeof window.incrementoPdfStart === "function"')
            # PDF rendering is tested separately. Give the real toolbar a card;
            # no user document, profile or network resource is opened.
            page.evaluate("""() => {
                window.testCommands=[];window.pycmd=c=>window.testCommands.push(c);
                window.pdfjsLib.getDocument=()=>({destroy:()=>Promise.resolve(),promise:Promise.reject(new Error('Synthetic layout-only document'))});
                window.incrementoPdfStart(42,'synthetic.pdf',1,1,0,1);
            }""")
            controls = page.locator('#pdf-controls')
            for width in (900,350):
                page.set_viewport_size({'width':width, 'height':700})
                for label in ('Read to here','Extract','Review All'):
                    assert controls.get_by_role('button', name=label, exact=True).is_visible(), label
                assert controls.bounding_box()['height'] <= 350
                controls.get_by_role('button', name='Annotate', exact=True).click()
                controls.locator('[title="Show highlights list"]').wait_for()
                assert controls.locator('button[aria-label^="Use "]').count() == 8
                assert controls.locator('button, input, select').evaluate_all("""nodes=>nodes.filter(el=>el.getClientRects().length).every(el=>{
                    const r=el.getBoundingClientRect();return r.left>=-1 && r.right<=innerWidth+1;
                })"""), 'Toolbar controls must fit the current pane width'
                controls.get_by_role('button', name='Annotate', exact=True).click()
                controls.get_by_role('button', name='Search', exact=True).click()
                controls.get_by_placeholder('Search this PDF').wait_for()
                assert page.evaluate("testCommands.filter(c=>c.startsWith('incremento_pdf_controls:')).length") == 0
                controls.get_by_role('button', name='Close', exact=True).click()
                controls.get_by_role('button', name='More', exact=True).click()
                assert controls.get_by_role('combobox', name='PDF appearance', exact=True).is_visible()
                controls.get_by_role('button', name='More', exact=True).click()
            controls.get_by_role('button', name='Show controls', exact=True).click()
            assert controls.get_by_role('button', name='Minimize controls', exact=True).is_visible()
            assert page.evaluate("testCommands.filter(c=>c.startsWith('incremento_pdf_controls:'))") == ['incremento_pdf_controls:{"cardId":42,"collapsed":false}']
            assert controls.bounding_box()['height'] <= 350
            # A control below the fold must remain reachable through toolbar scrolling.
            controls.get_by_role('button', name='Finished reading', exact=False).scroll_into_view_if_needed()
            assert controls.get_by_role('button', name='Finished reading', exact=False).is_visible()
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1], str(scale)],
        cwd=Path(__file__).resolve().parents[1], env=dict(os.environ), capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
