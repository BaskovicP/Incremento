"""The dynamic browser must never bypass the guarded public-network client."""

import io
import asyncio
from types import SimpleNamespace

import pytest

import webpage_browser as browser


def test_browser_fetch_preserves_json_and_uses_bounded_guarded_client(monkeypatch):
    calls = []
    def fetch(request, *, timeout):
        calls.append((request.full_url, request.get_header("Cookie"), timeout))
        response = io.BytesIO(b'{"text":"Loaded dynamically"}')
        response.headers = {"Content-Type": "application/json", "Set-Cookie": "private=value"}
        response.geturl = lambda: request.full_url
        return response
    monkeypatch.setattr(browser, "open_public_http", fetch)
    capture = browser.PublicBrowserResources(timeout_sec=10)

    mime, data, final_url = capture.fetch("https://93.184.216.34/api")

    assert mime == "application/json"
    assert data == b'{"text":"Loaded dynamically"}'
    assert final_url == "https://93.184.216.34/api"
    assert calls[0][:2] == ("https://93.184.216.34/api", None)
    assert 0 < calls[0][2] <= 5
    # Rebuilding the clean document must reuse already captured images/assets.
    assert capture.fetch("https://93.184.216.34/api") == (mime, data, final_url)
    assert len(calls) == 1


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "file:///etc/passwd", "https://u:p@example.org/", "http://169.254.169.254/"])
def test_browser_resources_reject_private_credentials_and_local_urls_before_io(monkeypatch, url):
    monkeypatch.setattr(browser, "open_public_http", lambda *_a, **_kw: pytest.fail("Unsafe request escaped"))
    with pytest.raises(ValueError):
        browser.PublicBrowserResources(timeout_sec=10).fetch(url)


def test_browser_routes_abort_posts_subframes_and_downloads_without_fetching():
    calls = []
    capture = browser.PublicBrowserResources(timeout_sec=10)
    capture.fetch = lambda url: pytest.fail("Forbidden request fetched")
    main = object()
    async def abort():
        calls.append("abort")
    async def exercise(route):
        await capture.route(route, main_frame=main, slots=asyncio.Semaphore(1))
    for resource, method, frame in (("document", "GET", object()), ("fetch", "POST", main), ("media", "GET", main)):
        request = SimpleNamespace(resource_type=resource, method=method, frame=frame, url="https://example.org/")
        route = SimpleNamespace(request=request, abort=abort)
        asyncio.run(exercise(route))
    assert calls == ["abort"] * 3


def test_browser_capture_enforces_count_byte_and_time_budgets(monkeypatch):
    capture = browser.PublicBrowserResources(timeout_sec=0)
    monkeypatch.setattr(browser, "open_public_http", lambda *_a, **_kw: pytest.fail("Expired capture fetched"))
    with pytest.raises(TimeoutError):
        capture.fetch("https://93.184.216.34/")
    capture = browser.PublicBrowserResources(timeout_sec=10)
    monkeypatch.setattr(browser, "MAX_REQUESTS", 0)
    with pytest.raises(ValueError, match="limit"):
        capture.fetch("https://93.184.216.34/")


def test_browser_resources_reject_oversized_body_and_private_redirect(monkeypatch):
    def response(_request, **_kwargs):
        value = io.BytesIO(b"12345")
        value.headers = {"Content-Type": "text/plain"}
        value.geturl = lambda: "http://127.0.0.1/secret"
        return value
    monkeypatch.setattr(browser, "open_public_http", response)
    monkeypatch.setattr(browser, "MAX_RESOURCE_BYTES", 4)
    capture = browser.PublicBrowserResources(timeout_sec=10)
    with pytest.raises(ValueError):
        capture.fetch("https://93.184.216.34/")
    assert capture.total == 0
    monkeypatch.setattr(browser, "MAX_RESOURCE_BYTES", 10)
    with pytest.raises(ValueError):
        capture.fetch("https://93.184.216.34/")
    assert capture.total == 0


def test_browser_cancel_kills_owned_process_and_removes_temporary_files(tmp_path, monkeypatch):
    import threading
    event = threading.Event()
    event.set()
    calls = []
    monkeypatch.setattr(browser, "browser_runtime", lambda: ("python", "browser"))
    monkeypatch.setattr(browser.tempfile, "tempdir", str(tmp_path))
    process = SimpleNamespace(pid=12345, wait=lambda **_kw: calls.append("wait"), terminate=lambda: calls.append("terminate"))
    monkeypatch.setattr(browser.subprocess, "Popen", lambda *_args, **_kw: process)
    if browser.os.name != "nt":
        monkeypatch.setattr(browser.os, "killpg", lambda pid, _signal: calls.append(pid))
    else:
        monkeypatch.setattr(browser.subprocess, "run", lambda *_args, **_kw: calls.append(12345))
    with pytest.raises(InterruptedError, match="cancelled"):
        browser.render_browser_pdf("https://93.184.216.34/", "", style="website", include_links=False,
                                   links_heading="Links", timeout_sec=1, cancel_event=event)
    assert calls == (["terminate", "wait", "wait"] if browser.os.name != "nt" else [12345, "wait"])
    assert list(tmp_path.iterdir()) == []


def test_runtime_discovery_rejects_incomplete_or_escaping_installation(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(browser, "_runtime_dir", lambda: tmp_path)
    assert browser.browser_runtime() is None
    (tmp_path / "runtime.json").write_text(json.dumps({"python": "python", "browser": "../../outside"}))
    assert browser.browser_runtime() is None
