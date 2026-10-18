"""Optional, disposable Chromium capture; browser requests never go out directly.

Run as a subprocess so the parent can terminate a hung page and its browser.
Playwright and its browser are installed explicitly, outside packaged sources.
"""

from __future__ import annotations

import json
import asyncio
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request
from urllib.error import HTTPError

if __name__ == "__main__":
    sys.path[:0] = [sys.argv[2], str(Path(__file__).resolve().parent)]

try:
    from .network_safety import open_public_http, read_response_limited, validate_public_http_url
    from .webpage_resources import _DeadlineResponse
    from .webpage_export import prepare_export_html, MAX_HTML_BYTES
    from .webpage_handoff import WebpageVerificationRequired, requires_verification
except ImportError:
    from network_safety import open_public_http, read_response_limited, validate_public_http_url
    from webpage_resources import _DeadlineResponse
    from webpage_export import prepare_export_html, MAX_HTML_BYTES
    from webpage_handoff import WebpageVerificationRequired, requires_verification

MAX_REQUESTS = 256
MAX_RESOURCE_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_PDF_BYTES = 48 * 1024 * 1024
_INSTALL_LOCK = threading.Lock()
_REQUIREMENTS = ("playwright>=1.56,<2", "beautifulsoup4>=4.12,<5")


def _runtime_dir() -> Path:
    return Path(__file__).resolve().parent.parent / ".dependencies" / "webpage-browser"


def browser_runtime() -> tuple[str, str] | None:
    """Read only the verified explicit installation's interpreter/browser pair."""
    root = _runtime_dir()
    try:
        metadata = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
        python = Path(metadata["python"])
        executable = root / metadata["browser"]
        executable.resolve().relative_to(root.resolve())
        if python.is_file() and executable.is_file() and (root / "packages/playwright/__init__.py").is_file():
            return str(python), str(executable)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def install_browser_runtime() -> bool:
    """Explicit setup action only; ordinary imports never install dependencies."""
    try:
        from .deps import _installer_python, _subprocess_env
    except ImportError:
        from deps import _installer_python, _subprocess_env
    if not _INSTALL_LOCK.acquire(blocking=False):
        return False
    try:
        if browser_runtime():
            return True
        python = _installer_python()
        if not python:
            return False
        root = _runtime_dir()
        root.mkdir(parents=True, exist_ok=True)
        env = _subprocess_env()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(root / "browsers")
        installed = subprocess.run([python, "-I", "-m", "pip", "install", "--disable-pip-version-check",
                                    "--target", str(root / "packages"), *_REQUIREMENTS],
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        if installed.returncode:
            return False
        script = "import sys; sys.path.insert(0,sys.argv[1]); from playwright.__main__ import main; sys.argv=['playwright','install','chromium','--only-shell']; main()"
        installed = subprocess.run([python, "-I", "-c", script, str(root / "packages")],
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
        if installed.returncode:
            return False
        names = {"chrome-headless-shell", "chrome-headless-shell.exe"}
        executables = sorted(path for path in (root / "browsers").rglob("chrome-headless-shell*")
                             if path.name in names and path.is_file())
        if not executables:
            return False
        # Commit readiness only after both components exist; interrupted setup
        # stays unavailable and can be retried through the same explicit button.
        metadata = {"python": python, "browser": str(executables[-1].relative_to(root))}
        staging = root / "runtime.json.tmp"
        staging.write_text(json.dumps(metadata), encoding="utf-8")
        staging.replace(root / "runtime.json")
        return browser_runtime() is not None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    finally:
        _INSTALL_LOCK.release()


class PublicBrowserResources:
    """Public GET-only network broker with one shared count/byte/deadline budget."""

    def __init__(self, *, timeout_sec: float):
        self.deadline = time.monotonic() + max(0, timeout_sec)
        self.count = 0
        self.total = 0
        self.headers = {}
        self.cache = {}
        self.lock = threading.Lock()
        self.verification_required = False

    def fetch(self, url: str) -> tuple[str, bytes, str]:
        url = validate_public_http_url(url)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Webpage browser capture timed out.")
        with self.lock:
            if url in self.cache:
                return self.cache[url]
            if self.count >= MAX_REQUESTS or self.total >= MAX_TOTAL_BYTES:
                raise ValueError("Webpage browser resource limit exceeded.")
            self.count += 1
            limit = min(MAX_RESOURCE_BYTES, MAX_TOTAL_BYTES - self.total)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 Incremento/1.0", "Accept": "*/*", "Accept-Encoding": "identity"})
        with open_public_http(request, timeout=min(5.0, remaining)) as response:
            raw = read_response_limited(_DeadlineResponse(response, self.deadline),
                                        max_bytes=limit, chunk_bytes=65536)
            final_url = validate_public_http_url(response.geturl() or url)
            content_type = str(response.headers.get("Content-Type") or "application/octet-stream")
            # Forward only representation/CORS headers; never cookies, redirects,
            # credentials, or browser control headers from the original response.
            self.headers[url] = {name: str(response.headers[name]) for name in
                                 ("Access-Control-Allow-Origin", "Access-Control-Allow-Headers") if response.headers.get(name)}
        with self.lock:
            if self.total + len(raw) > MAX_TOTAL_BYTES:
                raise ValueError("Webpage browser resource limit exceeded.")
            self.total += len(raw)
            result = content_type, raw, final_url
            self.cache[url] = result
        return result

    async def route(self, route, *, main_frame, slots) -> None:
        request = route.request
        try:
            if request.method != "GET" or request.resource_type in {"media", "websocket", "eventsource", "manifest"} or request.frame != main_frame:
                await route.abort()
                return
            async with slots:
                mime, raw, final_url = await asyncio.to_thread(self.fetch, request.url)
            headers = {"content-type": mime, **self.headers.get(request.url, {})}
            if final_url != request.url:
                # Preserve the final origin/base for relative URLs and scripts.
                await route.fulfill(status=302, headers={"location": final_url})
            else:
                await route.fulfill(status=200, headers=headers, body=raw)
        except Exception as exc:
            if (isinstance(exc, HTTPError) and exc.code in {403, 429}
                    and request.resource_type == "document" and request.frame == main_frame):
                self.verification_required = True
            try:
                await route.abort()
            except Exception:
                pass  # The bounded worker may already be shutting down.


_PREPARE_PAGE = """async () => {
  document.querySelectorAll('details').forEach(el => el.open = true);
  document.querySelectorAll('img').forEach(img => {
    img.loading = 'eager';
    const lazy = img.dataset.src || img.dataset.lazySrc;
    if (lazy) img.src = lazy;
  });
  const start = performance.now();
  for (let step = 0; step < 60 && performance.now() - start < 6000; step++) {
    window.scrollTo(0, step * Math.max(innerHeight, 600));
    await new Promise(resolve => setTimeout(resolve, 80));
    if (scrollY + innerHeight >= document.documentElement.scrollHeight) break;
  }
  window.scrollTo(0, 0);
  await Promise.race([Promise.all([document.fonts.ready,
    ...Array.from(document.images, img => img.decode().catch(() => {}))]),
    new Promise(resolve => setTimeout(resolve, 2500))]);
}"""


def _capture(request: dict, executable: str) -> bytes:
    return asyncio.run(_capture_async(request, executable))


async def _capture_async(request: dict, executable: str) -> bytes:
    from playwright.async_api import async_playwright

    if os.name != "nt" and threading.current_thread() is threading.main_thread():
        # Let cancellation unwind Playwright and close its separately grouped
        # browser processes before the parent uses a hard timeout fallback.
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, asyncio.current_task().cancel)
    source = validate_public_http_url(request["url"]) if request["url"] else "https://snapshot.invalid/"
    supplied_html = request["html"]
    if len(supplied_html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("Webpage HTML exceeds the size limit.")
    resources = PublicBrowserResources(timeout_sec=request["timeout_sec"])
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=executable, headless=True, chromium_sandbox=True,
            proxy={"server": "http://127.0.0.1:9", "bypass": ""},
            args=["--proxy-bypass-list=<-loopback>", "--disable-background-networking", "--disable-quic",
                  "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"])
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block",
                                          accept_downloads=False, permissions=[])
            async def close_socket(socket):
                await socket.close()
            await context.route_web_socket("**/*", close_socket)
            page = await context.new_page()
            page.set_default_timeout(8000)
            page.on("dialog", lambda dialog: dialog.dismiss())
            await context.add_init_script("window.RTCPeerConnection = undefined; window.webkitRTCPeerConnection = undefined;")
            slots = asyncio.Semaphore(8)
            async def route_request(route):
                nonlocal supplied_html
                if supplied_html and route.request.url == source and route.request.resource_type == "document":
                    raw, supplied_html = supplied_html, ""
                    await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=raw)
                else:
                    await resources.route(route, main_frame=page.main_frame, slots=slots)
            await context.route("**/*", route_request)
            try:
                await page.goto(source, wait_until="domcontentloaded", timeout=max(1000, request["timeout_sec"] * 1000))
            except Exception:
                if resources.verification_required:
                    raise WebpageVerificationRequired() from None
                raise
            # SPAs often fetch their article after DOMContentLoaded. This wait is
            # bounded so perpetual analytics traffic cannot prevent an export.
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            await page.evaluate(_PREPARE_PAGE)
            if resources.verification_required or requires_verification(await page.content()):
                raise WebpageVerificationRequired()
            if request["style"] == "article" or request["include_links"]:
                captured = await page.evaluate("""() => {
                    document.querySelectorAll('img').forEach(img => { if (img.currentSrc) { img.src = img.currentSrc; img.removeAttribute('srcset'); } });
                    return document.documentElement.outerHTML;
                }""")
                # Reconstructing the article also removes site scripts and CSS.
                captured = prepare_export_html(captured, page.url, style=request["style"],
                    include_links=request["include_links"], links_heading=request["links_heading"])
                if request["style"] == "article":
                    await page.set_content(captured, wait_until="domcontentloaded")
                    await page.evaluate(_PREPARE_PAGE)
                else:
                    from bs4 import BeautifulSoup
                    appendix = BeautifulSoup(captured, "html.parser").find(id="incremento-link-list")
                    if appendix:
                        await page.evaluate("html => document.body.insertAdjacentHTML('beforeend', html)", str(appendix))
            await page.emulate_media(media="screen" if request["style"] == "website" else "print")
            await page.add_style_tag(content="html { -webkit-print-color-adjust: exact; print-color-adjust: exact; } * { animation: none !important; transition: none !important; }")
            result = await page.pdf(format="A4", print_background=True, margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"},
                              prefer_css_page_size=request["style"] == "article", tagged=True, outline=True)
            if len(result) > MAX_PDF_BYTES or not result.startswith(b"%PDF-"):
                raise ValueError("Webpage PDF exceeds the size limit or is invalid.")
            return result
        finally:
            await browser.close()


def render_browser_pdf(url: str, html: str, *, style: str, include_links: bool,
                       links_heading: str, timeout_sec: float, cancel_event=None) -> bytes:
    runtime = browser_runtime()
    if runtime is None:
        raise RuntimeError("Webpage browser component is unavailable.")
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("Webpage HTML exceeds the size limit.")
    if style not in {"print", "website", "article"}:
        raise ValueError("Unknown webpage PDF style.")
    python, executable = runtime
    request = dict(url=url, html=html, style=style, include_links=include_links,
                   links_heading=links_heading, timeout_sec=max(1, timeout_sec - 2))
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="incremento-browser-") as directory:
        output = Path(directory) / "capture.pdf"
        command = [python, "-I", str(Path(__file__).resolve()), "--worker", str(_runtime_dir() / "packages"), executable, str(output)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   env=env, start_new_session=os.name != "nt")
        deadline = time.monotonic() + max(1, timeout_sec)
        pending_input = json.dumps(request).encode("utf-8")
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("Webpage browser capture cancelled.")
                if time.monotonic() >= deadline:
                    raise TimeoutError("Webpage browser capture timed out.")
                try:
                    process.communicate(pending_input, timeout=min(.25, max(.01, deadline - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    pending_input = None
        except (TimeoutError, InterruptedError):
            if os.name != "nt":
                try:
                    process.terminate()
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                try:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    process.kill()
            process.wait()
            raise
        if (Path(directory) / "verification-required").is_file():
            raise WebpageVerificationRequired()
        if process.returncode or not output.is_file():
            raise RuntimeError("The browser could not capture this webpage.")
        if output.stat().st_size > MAX_PDF_BYTES:
            raise ValueError("Webpage PDF exceeds the size limit.")
        result = output.read_bytes()
        if not result.startswith(b"%PDF-"):
            raise ValueError("The browser returned an invalid PDF.")
        return result


if __name__ == "__main__":
    # -I ignores ambient Python paths; only our installed package folder and
    # trusted sibling source directory are added for this disposable worker.
    request = json.loads(sys.stdin.buffer.read(MAX_HTML_BYTES * 6 + 4096))
    try:
        Path(sys.argv[4]).write_bytes(_capture(request, sys.argv[3]))
    except WebpageVerificationRequired:
        Path(sys.argv[4]).with_name("verification-required").touch()
