"""Security boundary for links opened from untrusted reader documents."""

from __future__ import annotations

from urllib.parse import urlsplit


_MAX_EXTERNAL_READER_URL_CHARS = 4096
_ALLOWED_EXTERNAL_READER_SCHEMES = {"http", "https"}


def normalize_external_reader_url(raw_url: object) -> str | None:
    """Return a safe browser URL, or ``None`` for unsupported input."""
    candidate = str(raw_url or "").strip()
    if not candidate or len(candidate) > _MAX_EXTERNAL_READER_URL_CHARS:
        return None
    if "\\" in candidate or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in candidate):
        return None
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() not in _ALLOWED_EXTERNAL_READER_SCHEMES:
            return None
        if not parsed.netloc or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        # Accessing ``port`` validates malformed or out-of-range port text.
        parsed.port
    except (TypeError, ValueError):
        return None
    return candidate


def _open_normalized_external_url(url: str) -> bool:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    target = QUrl(url)
    if not target.isValid():
        return False
    return bool(QDesktopServices.openUrl(target))


def open_external_reader_link(raw_url: object) -> bool:
    """Open an explicit HTTP(S) reader link in the system browser."""
    normalized = normalize_external_reader_url(raw_url)
    if normalized is None:
        return False
    try:
        return _open_normalized_external_url(normalized)
    except Exception:
        return False
