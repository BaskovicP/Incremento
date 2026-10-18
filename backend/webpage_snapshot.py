"""Guarded webpage acquisition for the offline PDF snapshot renderer."""

import os
import stat
import tempfile
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit
from urllib.request import Request

try:
    from .network_safety import (
        open_public_http,
        read_response_limited,
        validate_public_http_url,
    )
except ImportError:
    from network_safety import (  # type: ignore
        open_public_http,
        read_response_limited,
        validate_public_http_url,
    )


MAX_WEBPAGE_HTML_BYTES = 16 * 1024 * 1024
MAX_WEBPAGE_PDF_BYTES = 48 * 1024 * 1024


def copy_browser_saved_pdf(source_path: str, *, cancel_event=None) -> str:
    """Stage a bounded, user-selected PDF; the caller owns only the returned copy."""
    def check_cancelled():
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Browser PDF import cancelled.")

    check_cancelled()
    # Nonblocking prevents special files from hanging before fstat can reject
    # them. No-follow also rejects a replaced/symlinked picker result on POSIX.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    if os.path.islink(source_path):
        raise ValueError("Choose a regular PDF file.")
    output_path = ""
    try:
        with os.fdopen(os.open(source_path, flags), "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_WEBPAGE_PDF_BYTES:
                raise ValueError("Choose a regular PDF within the size limit.")
            prefix = source.read(5)
            if prefix != b"%PDF-":
                raise ValueError("The selected file is not a PDF.")
            with tempfile.NamedTemporaryFile(prefix="incremento-webpage-", suffix=".pdf", delete=False) as output:
                output_path = output.name
                output.write(prefix)
                total = len(prefix)
                while True:
                    check_cancelled()
                    chunk = source.read(min(65536, MAX_WEBPAGE_PDF_BYTES - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_WEBPAGE_PDF_BYTES:
                        raise ValueError("The selected PDF exceeds the size limit.")
                    output.write(chunk)
        check_cancelled()
        return output_path
    except BaseException:
        if output_path:
            try:
                os.remove(output_path)
            except OSError:
                pass
        raise


def offline_snapshot_resource_allowed(candidate_url: str, *, document_url: str = "") -> bool:
    """Allow only self-contained resources once guarded HTML is captured."""
    try:
        scheme = str(urlsplit(str(candidate_url or "")).scheme or "").casefold()
    except (TypeError, ValueError):
        return False
    return scheme in {"about", "data"} or (
        scheme == "file" and bool(document_url) and candidate_url == document_url
    )


def wikipedia_article_pdf_url(url: str) -> str | None:
    """Return Wikipedia's official PDF endpoint for a public article URL."""
    clean_url = validate_public_http_url(url)
    parts = urlsplit(clean_url)
    hostname = str(parts.hostname or "").rstrip(".").casefold()
    if hostname != "wikipedia.org" and not hostname.endswith(".wikipedia.org"):
        return None

    title = ""
    if parts.path.startswith("/wiki/"):
        title = unquote(parts.path.removeprefix("/wiki/"))
    elif parts.path == "/w/index.php":
        title = unquote(parse_qs(parts.query).get("title", [""])[0])
    title = title.strip()
    if not title:
        return None

    endpoint_path = "/api/rest_v1/page/pdf/" + quote(title, safe="")
    return urlunsplit((parts.scheme, parts.netloc, endpoint_path, "", ""))


def fetch_wikipedia_article_pdf(
    url: str,
    *,
    timeout_sec: float = 45.0,
) -> bytes | None:
    """Fetch Wikipedia's print-quality PDF, or return ``None`` for other sites."""
    endpoint = wikipedia_article_pdf_url(url)
    if endpoint is None:
        return None
    request = Request(
        endpoint,
        headers={
            "User-Agent": "Incremento/1.0",
            "Accept": "application/pdf",
        },
    )
    with open_public_http(request, timeout=max(1.0, float(timeout_sec))) as response:
        content_type = str(response.headers.get("Content-Type") or "").casefold()
        mime_type = content_type.split(";", 1)[0].strip()
        raw = read_response_limited(response, max_bytes=MAX_WEBPAGE_PDF_BYTES)
        validate_public_http_url(
            str(getattr(response, "geturl", lambda: endpoint)() or endpoint)
        )
    if mime_type != "application/pdf" or not raw.startswith(b"%PDF-"):
        raise ValueError("Wikipedia did not return a valid PDF document.")
    return raw


def fetch_webpage_html(
    url: str,
    *,
    timeout_sec: float = 30.0,
) -> tuple[str, str]:
    """Fetch a bounded public HTML document without ambient proxy routing."""
    clean_url = validate_public_http_url(url)
    request = Request(
        clean_url,
        headers={
            "User-Agent": "Incremento/1.0",
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5",
        },
    )
    with open_public_http(request, timeout=max(1.0, float(timeout_sec))) as response:
        content_type = str(response.headers.get("Content-Type") or "").casefold()
        mime_type = content_type.split(";", 1)[0].strip()
        if mime_type and mime_type not in {
            "application/xhtml+xml",
            "text/html",
            "text/plain",
        }:
            raise ValueError("URL did not return an HTML document.")
        raw = read_response_limited(response, max_bytes=MAX_WEBPAGE_HTML_BYTES)
        final_url = validate_public_http_url(
            str(getattr(response, "geturl", lambda: clean_url)() or clean_url)
        )
    charset = ""
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    try:
        html = raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")
    if not html.strip():
        raise ValueError("URL returned an empty document.")
    return final_url, html
