"""A browser verification belongs to one short-lived, profile-bound import."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from webpage_handoff import BrowserPdfHandoffs, WebpageVerificationRequired, requires_verification


def test_verified_snapshot_returns_once_to_the_original_profile():
    jobs = BrowserPdfHandoffs()
    ticket = jobs.create("https://example.org/article", "First")
    assert jobs.describe(ticket)["url"] == "https://example.org/article"
    assert jobs.take(ticket, "First") is None
    jobs.submit(ticket, "https://example.org/article", "<article>Verified article</article>")
    # A repeated delivery never creates a second import.
    jobs.submit(ticket, "https://example.org/article", "<article>Duplicate</article>")
    assert jobs.take(ticket, "First") == "<article>Verified article</article>"
    assert jobs.take(ticket, "First") is None
    jobs.cancel(ticket)
    with pytest.raises(ValueError):
        jobs.describe(ticket)


@pytest.mark.parametrize("failure", ["expired", "cancelled", "profile-switch"])
def test_stale_browser_result_cannot_be_imported(failure):
    now = [100.0]
    jobs = BrowserPdfHandoffs(clock=lambda: now[0])
    ticket = jobs.create("https://example.org/article", "First")
    if failure == "expired":
        now[0] += 601
    elif failure == "cancelled":
        jobs.cancel(ticket)
    else:
        with pytest.raises(ValueError):
            jobs.take(ticket, "Second")
    if failure != "profile-switch":
        with pytest.raises(ValueError):
            jobs.submit(ticket, "https://example.org/article", "<p>Article</p>")
    else:
        assert jobs.take(ticket, "First") is None


@pytest.mark.parametrize("url,html", [
    ("https://other.example/article", "<p>Article</p>"),
    ("https://example.org/another-article", "<p>Article</p>"),
    ("file:///etc/passwd", "<p>Article</p>"),
    ("https://u:p@example.org/article", "<p>Article</p>"),
    ("https://example.org/article", ""),
    ("https://example.org/article", "x" * 2_000_001),
    ("https://example.org/article", "<title>Just a moment...</title><form id='challenge-form'>Verify you are human</form>"),
])
def test_handoff_rejects_wrong_page_invalid_snapshot_and_unfinished_challenge(url, html):
    jobs = BrowserPdfHandoffs()
    ticket = jobs.create("https://example.org/article", "First")
    with pytest.raises(ValueError):
        jobs.submit(ticket, url, html)
    assert jobs.take(ticket, "First") is None


def test_archive_alias_redirect_can_return_to_the_same_import():
    jobs = BrowserPdfHandoffs()
    ticket = jobs.create("https://archive.is/abc", "First")
    jobs.submit(ticket, "https://archive.ph/abc", "<article>Verified article</article>")
    assert jobs.take(ticket, "First") == "<article>Verified article</article>"


def test_concurrent_deliveries_still_produce_one_result_and_capacity_is_bounded():
    jobs = BrowserPdfHandoffs()
    ticket = jobs.create("https://example.org/article", "First")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: jobs.submit(ticket, "https://example.org/article", "<p>Article</p>"), range(4)))
    assert jobs.take(ticket, "First") == "<p>Article</p>"
    for _ in range(3):
        jobs.create("https://example.org/article", "First")
    with pytest.raises(ValueError, match="pending"):
        jobs.create("https://example.org/article", "First")


@pytest.mark.parametrize("html,blocked", [
    ("<title>Just a moment...</title><p>Checking your browser</p>", True),
    ("<title>Security check</title><form id='captcha-form'>Please complete the CAPTCHA</form>", True),
    ("<title>Article</title><article>How CAPTCHA works and why people use it.</article>", False),
    ("<article>Normal article</article><footer><div class='g-recaptcha'></div></footer>", False),
])
def test_challenge_detection_does_not_confuse_articles_about_captcha(html, blocked):
    assert requires_verification(html) is blocked
    assert isinstance(WebpageVerificationRequired(), RuntimeError)


def test_handoff_rpc_keeps_the_existing_extension_authentication_boundary(monkeypatch):
    import io
    import json
    import browser_bridge
    from webpage_handoff import browser_pdf_handoffs, HANDOFF_RPC_PATH
    ticket = browser_pdf_handoffs.create("https://example.org/article", "Test")
    try:
        monkeypatch.setattr(browser_bridge, "_bridge_token", "secret")
        origin = "chrome-extension://" + "a" * 32
        monkeypatch.setattr(browser_bridge, "_allowed_extension_origin", origin)
        results = []
        for authenticated in (False, True):
            handler = object.__new__(browser_bridge._IncrementoBridgeHandler)
            body = json.dumps({"action": "describe", "ticket": ticket}).encode()
            handler.path = HANDOFF_RPC_PATH
            handler.headers = {"Origin": origin, "Content-Length": str(len(body))}
            if authenticated:
                handler.headers.update({"X-Incremento-Token": "secret", "X-Incremento-Protocol": "2"})
            handler.rfile = io.BytesIO(body)
            handler._send_json = lambda status, value: results.append((status, value))
            handler._do_POST()
        assert results[0][0] == 401
        assert results[1][0] == 200 and results[1][1]["url"] == "https://example.org/article"
    finally:
        browser_pdf_handoffs.cancel(ticket)


def test_handoff_landing_page_contains_no_request_data_or_authentication_token(monkeypatch):
    import io
    import browser_bridge
    from webpage_handoff import HANDOFF_PATH
    handler = object.__new__(browser_bridge._IncrementoBridgeHandler)
    handler.path = HANDOFF_PATH
    handler.headers = {"Host": "127.0.0.1:8766"}
    handler.wfile = io.BytesIO()
    headers = []
    handler.send_response = lambda code: headers.append(("status", code))
    handler.send_header = lambda key, value: headers.append((key, value))
    handler.end_headers = lambda: None
    monkeypatch.setattr(browser_bridge, "_bridge_token", "private-auth-token")
    handler._do_GET()
    assert ("status", 200) in headers
    assert ("Cache-Control", "no-store") in headers
    assert "private-auth-token" not in handler.wfile.getvalue().decode()


def test_browser_primary_http_block_is_preserved_for_automatic_handoff():
    import asyncio
    from types import SimpleNamespace
    from urllib.error import HTTPError
    import webpage_browser
    capture = webpage_browser.PublicBrowserResources(timeout_sec=10)
    def blocked(_url):
        raise HTTPError("https://example.org/article", 429, "Too many requests", {}, None)
    capture.fetch = blocked
    main = object()
    async def abort():
        pass
    request = SimpleNamespace(resource_type="document", method="GET", frame=main, url="https://example.org/article")
    asyncio.run(capture.route(SimpleNamespace(request=request, abort=abort), main_frame=main, slots=asyncio.Semaphore(1)))
    assert capture.verification_required is True


def test_dynamic_worker_verification_signal_reaches_the_waiting_dialog_and_cleans_temp_files(tmp_path, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    import webpage_browser
    monkeypatch.setattr(webpage_browser, "browser_runtime", lambda: ("python", "browser"))
    monkeypatch.setattr(webpage_browser.tempfile, "tempdir", str(tmp_path))
    def process(command, **_kwargs):
        Path(command[-1]).with_name("verification-required").touch()
        return SimpleNamespace(returncode=0, communicate=lambda *_a, **_kw: None)
    monkeypatch.setattr(webpage_browser.subprocess, "Popen", process)
    with pytest.raises(WebpageVerificationRequired):
        webpage_browser.render_browser_pdf("https://example.org/article", "", style="article", include_links=False,
                                            links_heading="Links", timeout_sec=10)
    assert list(tmp_path.iterdir()) == []


def test_http_200_challenge_is_handed_off_before_any_pdf_is_printed():
    import ast
    import time
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "frontend/webpage_dialog.py"
    function = next(node for node in ast.parse(path.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_prepare_webpage")
    namespace = {"time": time, "_t": lambda key: key, "validate_public_http_url": lambda url: url,
                 "requires_verification": requires_verification, "WebpageVerificationRequired": WebpageVerificationRequired,
                 "_fetch_webpage_html": lambda *_a, **_kw: ("https://example.org/article", "<title>Just a moment...</title><p>Verify you are human</p>"),
                 "prepare_export_html": lambda *_a, **_kw: pytest.fail("A challenge must never become a study PDF")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    with pytest.raises(WebpageVerificationRequired):
        namespace["_prepare_webpage"]("https://example.org/article", "", 10, "article")
