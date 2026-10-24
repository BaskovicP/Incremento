"""Exercise sanitized EPUB chapters with an actual, disposable browser parser."""

import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest

import epub_manager
from webpage_browser import browser_runtime, _runtime_dir


@pytest.mark.parametrize("payload", [
    '<x:script xmlns:x="http://www.w3.org/1999/xhtml">window.__epubProbe=1</x:script>',
    '<s:svg xmlns:s="http://www.w3.org/2000/svg"><s:script>window.__epubProbe=1</s:script></s:svg>',
])
def test_xhtml_namespaces_cannot_bypass_epub_script_policy(tmp_path, payload):
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip("Optional webpage browser component has not been explicitly installed")
    chapter = tmp_path / "chapter.xhtml"
    chapter.write_text(
        '<html xmlns="http://www.w3.org/1999/xhtml"><head xmlns="">'
        '<title>Namespace fixture</title></head><body>' + payload +
        '<p>Readable chapter text</p></body></html>', encoding="utf-8",
    )
    epub_manager._clean_html_file(str(chapter))
    script = dedent('''
        import sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True,
                                        chromium_sandbox=True)
            page = browser.new_page()
            page.goto(Path(sys.argv[3]).as_uri())
            assert page.evaluate('document.contentType') == 'application/xhtml+xml'
            assert not page.locator('parsererror').count(), page.content()
            assert 'Readable chapter text' in page.locator('body').inner_text()
            assert page.evaluate('window.__epubProbe || 0') == 0, 'EPUB script executed'
            browser.close()
    ''')
    result = subprocess.run(
        [runtime[0], "-I", "-c", script, str(_runtime_dir() / "packages"), runtime[1], str(chapter)],
        capture_output=True, text=True, timeout=30, env=dict(os.environ),
    )
    assert result.returncode == 0, result.stdout + result.stderr
