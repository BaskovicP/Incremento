import json
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
import pytest


def test_find_updates_external_text_without_observing_its_own_marks():
    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip("Optional webpage browser component has not been explicitly installed")
    root = Path(__file__).resolve().parents[1]
    source = (root / "frontend/src/PdfViewer.jsx").read_text()
    styles = source[source.index("function clearSearchHitStyles(") : source.index("function findExcerptSpanMatch(")]
    observer = (root / "frontend/src/pdfSearchObserver.mjs").read_text().replace("export function", "function")
    script = dedent('''
        import json, sys
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page()
            page.set_content('<div id="layer"><span>alpha beta</span><span>alpha gamma</span></div>')
            page.add_script_tag(content=SOURCE)
            result = page.evaluate("""async () => {
                const layer = document.getElementById('layer');
                const frames = async count => {for(let i=0;i<count;i++) await new Promise(requestAnimationFrame);};
                let renders = 0;
                const stop = observeSearchText(layer, {render() {renders++; applySearchHitStyles(layer, 'alpha');},
                    clear() {clearSearchHitStyles(layer);}});
                layer.firstElementChild.textContent = 'changed alpha';
                await frames(4);
                const text = layer.textContent;
                const settled = renders;
                await frames(5);
                const stable = renders === settled;
                stop();
                return {text, stable, renders, cleared: !layer.querySelector('[data-inc-search-fragment="1"]')};
            }""")
            browser.close()
        print(json.dumps(result))
    ''').replace("SOURCE", repr("function escapeHtml(text) { return String(text); }\n" + styles + "\n" + observer))
    result = subprocess.run(
        [runtime[0], "-I", "-c", script, str(_runtime_dir() / "packages"), runtime[1]],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    state = json.loads(result.stdout.splitlines()[-1])
    assert state["text"] == "changed alphaalpha gamma"
    assert state["stable"] and state["renders"] <= 3
    assert state["cleared"]
