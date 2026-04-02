import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8766
BRIDGE_PATH = "/incremento/add-content"
_ALLOWED_ORIGIN_PREFIX = "chrome-extension://"
_MAX_HTML_CHARS = 2_000_000

_server: ThreadingHTTPServer | None = None
_server_thread: threading.Thread | None = None
_server_lock = threading.Lock()
_addon_dir: str = ""


def _collapse_ws(value) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_http_url(raw_url) -> str:
    raw = str(raw_url or "").strip()
    if not raw:
        raise ValueError("Missing URL.")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must start with http:// or https://")
    return raw


def build_writing_markdown(title: str, url: str, selected_text: str = "") -> str:
    clean_title = _collapse_ws(title) or "Untitled"
    clean_url = normalize_http_url(url)
    clean_selection = str(selected_text or "").strip()

    lines = [
        f"# {clean_title}",
        "",
        f"Source: {clean_url}",
        "",
    ]
    if clean_selection:
        lines.extend([
            "## Selected text",
            "",
            clean_selection,
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def normalize_add_content_payload(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    raw_kind = _collapse_ws(payload.get("kind", "")).casefold()
    kind_aliases = {
        "pdf": "pdf",
        "video": "video",
        "youtube": "video",
        "web": "webpage",
        "webpage": "webpage",
        "writing": "writing",
    }
    kind = kind_aliases.get(raw_kind)
    if not kind:
        raise ValueError("Kind must be one of: pdf, video, webpage, writing.")

    url = normalize_http_url(payload.get("url", ""))
    title = _collapse_ws(payload.get("title", "")) or url
    deck_name = _collapse_ws(payload.get("deckName", "")) or "Topics"
    selected_text = str(payload.get("selectedText", "") or "").strip()
    html = str(payload.get("html", "") or "")
    if len(html) > _MAX_HTML_CHARS:
        html = ""

    tags = []
    for tag in payload.get("tags") or []:
        clean = _collapse_ws(tag)
        if clean and clean not in tags:
            tags.append(clean)

    return {
        "kind": kind,
        "url": url,
        "title": title,
        "deck_name": deck_name,
        "tags": tags,
        "selected_text": selected_text,
        "html": html,
    }


def _run_on_main_and_wait(fn, timeout_sec: float = 180.0):
    from aqt import mw

    done = threading.Event()
    box: dict[str, object] = {}

    def _wrapped() -> None:
        try:
            box["result"] = fn()
        except Exception as exc:
            box["error"] = exc
        finally:
            done.set()

    mw.taskman.run_on_main(_wrapped)
    if not done.wait(timeout=timeout_sec):
        raise TimeoutError("Incremento browser bridge timed out.")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _add_content_on_main(payload: dict) -> dict:
    from aqt import mw

    from .pdf_manager import add_pdf_card
    from .video_manager import add_video_card, is_supported_video_url, resolve_video_url_for_embed
    from .web_manager import add_web_card
    from .writing_manager import add_writing_card
    from ..frontend.webpage_dialog import render_webpage_to_pdf

    normalized = normalize_add_content_payload(payload)
    kind = normalized["kind"]
    url = normalized["url"]
    title = normalized["title"]
    deck_name = normalized["deck_name"]
    tags = normalized["tags"]
    selected_text = normalized["selected_text"]
    html = normalized["html"]

    if kind == "video":
        video_url = resolve_video_url_for_embed(url)
        if not is_supported_video_url(video_url):
            raise ValueError("Video URL must be a supported YouTube or Vimeo page.")
        card_id = add_video_card(
            mw.col,
            youtube_url=video_url,
            title=title,
            deck_name=deck_name,
            tags=tags,
        )
    elif kind == "webpage":
        card_id = add_web_card(
            mw.col,
            url=url,
            title=title,
            deck_name=deck_name,
            tags=tags,
        )
    elif kind == "writing":
        initial_markdown = build_writing_markdown(title, url, selected_text)
        card_id = add_writing_card(
            _addon_dir,
            mw.col,
            title=title,
            deck_name=deck_name,
            tags=tags,
            initial_markdown=initial_markdown,
        )
    else:
        fd, temp_pdf_path = tempfile.mkstemp(prefix="incremento-webpage-", suffix=".pdf")
        os.close(fd)
        try:
            render_webpage_to_pdf(
                temp_pdf_path,
                url=url,
                html=html,
            )
            card_id = add_pdf_card(
                _addon_dir,
                mw.col,
                temp_pdf_path,
                title,
                deck_name=deck_name,
                tags=tags,
            )
        finally:
            try:
                os.remove(temp_pdf_path)
            except OSError:
                pass

    mw.col.reset()
    return {
        "ok": True,
        "kind": kind,
        "cardId": int(card_id),
        "title": title,
        "deckName": deck_name,
    }


class _IncrementoBridgeHandler(BaseHTTPRequestHandler):
    server_version = "IncrementoBrowserBridge/1.0"

    def log_message(self, format, *args):
        return

    def _request_origin_allowed(self) -> bool:
        origin = str(self.headers.get("Origin") or "")
        return not origin or origin.startswith(_ALLOWED_ORIGIN_PREFIX)

    def _send_cors_headers(self) -> None:
        origin = str(self.headers.get("Origin") or "")
        if origin.startswith(_ALLOWED_ORIGIN_PREFIX):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        if self.path != BRIDGE_PATH:
            self.send_error(404)
            return
        if not self._request_origin_allowed():
            self.send_error(403)
            return
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != BRIDGE_PATH:
            self._send_json(404, {"ok": False, "error": "Unknown path."})
            return
        if not self._request_origin_allowed():
            self._send_json(403, {"ok": False, "error": "Origin not allowed."})
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(max(0, length))

        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send_json(400, {"ok": False, "error": "Invalid JSON."})
            return

        try:
            result = _run_on_main_and_wait(lambda: _add_content_on_main(payload))
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
            return

        self._send_json(200, result)


def start_browser_bridge(addon_dir: str) -> None:
    global _server, _server_thread, _addon_dir

    with _server_lock:
        _addon_dir = addon_dir
        if _server is not None and _server_thread is not None and _server_thread.is_alive():
            return
        try:
            server = ThreadingHTTPServer((BRIDGE_HOST, BRIDGE_PORT), _IncrementoBridgeHandler)
        except OSError as exc:
            print(f"[Incremento] Browser bridge failed to start on {BRIDGE_HOST}:{BRIDGE_PORT}: {exc}")
            return
        server.daemon_threads = True
        _server = server
        _server_thread = threading.Thread(
            target=server.serve_forever,
            name="IncrementoBrowserBridge",
            daemon=True,
        )
        _server_thread.start()


def stop_browser_bridge(*_args, **_kwargs) -> None:
    global _server, _server_thread

    with _server_lock:
        server = _server
        thread = _server_thread
        _server = None
        _server_thread = None

    if server is not None:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=1.0)
