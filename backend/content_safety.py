"""Small, dependency-free boundaries for externally supplied content."""

from __future__ import annotations

import re
from html import escape
from urllib.parse import urlsplit, urlunsplit


MAX_EXTERNAL_TEXT_CHARS = 200_000
MAX_EXTERNAL_URL_CHARS = 8_192


def external_plain_text(value: object, *, max_chars: int = MAX_EXTERNAL_TEXT_CHARS) -> str:
    """Normalize bounded text received from documents, webpages, or extensions."""
    raw = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "".join(
        char
        for char in raw
        if char in {"\n", "\t"} or ord(char) >= 0x20
    )
    return cleaned[: max(0, int(max_chars))]


def external_plain_text_to_anki_html(
    value: object,
    *,
    max_chars: int = MAX_EXTERNAL_TEXT_CHARS,
) -> str:
    """Represent external plain text safely inside an Anki HTML field."""
    normalized = external_plain_text(value, max_chars=max_chars)
    return escape(normalized, quote=True).replace("\n", "<br>")


def external_plain_text_to_markdown(
    value: object,
    *,
    max_chars: int = MAX_EXTERNAL_TEXT_CHARS,
) -> str:
    """Render external plain text literally inside a Markdown document."""
    normalized = external_plain_text(value, max_chars=max_chars)
    html_safe = escape(normalized, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+!|>\-])", r"\\\1", html_safe)


def normalize_external_http_url(value: object) -> str:
    """Validate a bounded HTTP(S) URL without credentials or control bytes."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Missing URL.")
    if len(raw) > MAX_EXTERNAL_URL_CHARS:
        raise ValueError("URL is too long.")
    if any(ord(char) < 0x21 or ord(char) == 0x7F for char in raw):
        raise ValueError("URL contains whitespace or control characters.")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL is malformed.") from exc
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must start with http:// or https://")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed.")
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            parsed.path or "",
            parsed.query or "",
            parsed.fragment or "",
        )
    )
