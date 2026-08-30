"""Guarded webpage acquisition for the offline PDF snapshot renderer."""

from urllib.parse import urlsplit
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


def offline_snapshot_resource_allowed(candidate_url: str) -> bool:
    """Allow only self-contained resources once guarded HTML is captured."""
    try:
        scheme = str(urlsplit(str(candidate_url or "")).scheme or "").casefold()
    except (TypeError, ValueError):
        return False
    return scheme in {"about", "data"}


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
