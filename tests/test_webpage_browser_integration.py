"""Optional real Chromium check with deterministic, brokered network responses."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest

from webpage_browser import browser_runtime, _runtime_dir, render_browser_pdf


def test_disposable_worker_timeout_removes_its_temporary_output(tmp_path, monkeypatch):
    if browser_runtime() is None:
        pytest.skip("Optional webpage browser component has not been explicitly installed")
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))

    with pytest.raises(TimeoutError, match="timed out"):
        render_browser_pdf("https://93.184.216.34/article", "<script>while(true){}</script>",
                           style="website", include_links=False, links_heading="Links", timeout_sec=1)

    assert list(tmp_path.iterdir()) == []


def test_browser_pdf_includes_javascript_content_links_and_screen_or_article_layout(tmp_path):
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip("Optional webpage browser component has not been explicitly installed")
    script = dedent('''
        import io, json, sys
        from pathlib import Path
        sys.path[:0] = [sys.argv[1], sys.argv[2]]
        import webpage_browser as module
        calls = []
        def fetch(request, *, timeout):
            calls.append(request.full_url)
            body = {
                'https://93.184.216.34/dynamic.js': ('text/javascript', b'setTimeout(()=>fetch("/api").then(r=>r.json()).then(data=>{const p=document.createElement("p");p.textContent=data.text;document.querySelector("article").append(p)}),200)'),
                'https://93.184.216.34/api': ('application/json', b'{"text":"Loaded by JavaScript"}'),
            }
            mime, data = body[request.full_url]
            response = io.BytesIO(data)
            response.headers = {'Content-Type': mime}
            response.geturl = lambda: request.full_url
            return response
        module.open_public_http = fetch
        html = '<html><head><title>Article fixture</title><style>h1{color:#123456}@media print{.screen-only{display:none}}</style></head><body><nav>WEBSITE MENU</nav><article><h1>Article fixture</h1><p class="screen-only">Screen appearance text</p><a href="/reference">A reference</a><details><summary>More</summary><p>Expanded detail text</p></details></article><script src="/dynamic.js"></script></body></html>'
        for style in ('website', 'article'):
            request = dict(url='https://93.184.216.34/article', html=html, style=style,
                           include_links=True, links_heading='Links', timeout_sec=15)
            pdf = module._capture(request, sys.argv[3])
            Path(sys.argv[4], style + '.pdf').write_bytes(pdf)
        assert calls.count('https://93.184.216.34/dynamic.js') == 2, calls
        assert calls.count('https://93.184.216.34/api') == 2, calls
        print('Dynamic capture verified')
    ''')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([runtime[0], "-I", "-c", script, str(_runtime_dir() / "packages"),
                             str(root / "backend"), runtime[1], str(tmp_path)],
                            capture_output=True, text=True, timeout=45, env=dict(os.environ))
    assert result.returncode == 0, result.stdout + result.stderr
    inspect = dedent('''
        import sys, pymupdf
        from pathlib import Path
        for style in ('website', 'article'):
            with pymupdf.open(Path(sys.argv[1]) / (style + '.pdf')) as doc:
                text = ''.join(page.get_text() for page in doc)
                assert 'Loaded by JavaScript' in text, text
                assert 'Expanded detail text' in text, text
                assert 'Screen appearance text' in text, text
                assert ('WEBSITE MENU' in text) == (style == 'website'), text
                links = [link.get('uri') for page in doc for link in page.get_links()]
                assert 'https://93.184.216.34/reference' in links, links
                assert 'https://93.184.216.34/reference' in text, text
                doc[0].get_pixmap().save(Path(sys.argv[1]) / (style + '.png'))
    ''')
    result = subprocess.run([sys.executable, "-c", inspect, str(tmp_path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
