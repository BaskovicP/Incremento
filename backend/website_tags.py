"""Validation for opt-in website tag preferences; never stores visited URLs."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

try:
    from .content_safety import normalize_external_http_url
except ImportError:
    from content_safety import normalize_external_http_url


def website_key(url: object) -> str:
    """Match exact hostnames across schemes/paths, keeping subdomains separate."""
    if not isinstance(url, str):
        raise ValueError("Website URL must be text.")
    host = (urlsplit(normalize_external_http_url(url)).hostname or "").rstrip(".")
    try:
        return ipaddress.ip_address(host).compressed
    except ValueError:
        pass
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("Invalid website hostname.") from exc
    if (not host or len(host) > 253
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                   for label in host.split("."))):
        raise ValueError("Invalid website hostname.")
    return host


def normalize_website_tags(tags: object) -> list[str]:
    if not isinstance(tags, list) or len(tags) > 100:
        raise ValueError("Website tags must be a list of at most 100 tags.")
    result = []
    seen = set()
    for tag in tags:
        if (not isinstance(tag, str) or not tag or len(tag) > 200
                or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in tag)):
            raise ValueError("Each website tag must be 1–200 characters without whitespace.")
        if tag.casefold() not in seen:
            seen.add(tag.casefold())
            result.append(tag)
    return result
