"""Inert browser excerpts and bounded links back to their original passages."""

from __future__ import annotations

import hashlib
import re
from html import escape
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit, urlunsplit

try:
    from .content_safety import external_plain_text, external_plain_text_to_anki_html, normalize_external_http_url
    from .note_metadata import is_incremento_hidden_field
except ImportError:
    from content_safety import external_plain_text, external_plain_text_to_anki_html, normalize_external_http_url
    from note_metadata import is_incremento_hidden_field


MAX_SELECTION_CHARS = 200_000
_ALLOWED = frozenset("p div br strong b em i u s ul ol li blockquote pre code h1 h2 h3 h4 h5 h6 sub sup".split())
_DISCARD = frozenset("script style template noscript iframe object embed svg math nav header footer aside form button select textarea input".split())
_VOID = frozenset("br img input hr meta link embed source wbr".split())
_BLOCK = frozenset("p div br ul ol li blockquote pre h1 h2 h3 h4 h5 h6".split())


def _comparison_text(value: str) -> str:
    return " ".join(value.split())


def clean_selection_text(value: str) -> str:
    if len(value) > MAX_SELECTION_CHARS:
        raise ValueError("Selected text is too large.")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in external_plain_text(value).split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class _SelectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.text: list[str] = []
        self.stack: list[str] = []
        self.discard: list[str] = []

    def handle_starttag(self, tag, attrs):
        if len(self.stack) + len(self.discard) >= 64:
            raise ValueError("Selected HTML is too deeply nested.")
        if self.discard or tag in _DISCARD:
            if tag not in _VOID:
                self.discard.append(tag)
            return
        if tag not in _ALLOWED:
            return
        self.output.append(f"<{tag}>")
        if tag in _BLOCK:
            self.text.append(" ")
        if tag != "br":
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.discard:
            if tag in self.discard:
                del self.discard[len(self.discard) - 1 - self.discard[::-1].index(tag):]
            return
        if tag not in self.stack:
            return
        while self.stack:
            current = self.stack.pop()
            self.output.append(f"</{current}>")
            if current in _BLOCK:
                self.text.append(" ")
            if current == tag:
                break

    def handle_data(self, data):
        if self.discard:
            return
        self.text.append(data)
        safe = external_plain_text(data)
        if "pre" not in self.stack:
            safe = re.sub(r"\s+", " ", safe)
        self.output.append(escape(safe, quote=True))


def selection_html(text: str, markup: str = "") -> str:
    """Use only matching semantic markup; edited/plain excerpts remain literal."""
    cleaned = clean_selection_text(text)
    if len(markup) > MAX_SELECTION_CHARS:
        raise ValueError("Selected HTML is too large.")
    if markup:
        parser = _SelectionParser()
        parser.feed(markup)
        parser.close()
        if _comparison_text("".join(parser.text)) == _comparison_text(cleaned):
            while parser.stack:
                parser.output.append(f"</{parser.stack.pop()}>")
            return "".join(parser.output).strip()
    return external_plain_text_to_anki_html(cleaned)


def capture_source_url(url: str, source_text: str = "") -> str:
    validated = normalize_external_http_url(url)
    if not source_text.strip():
        return validated
    clean_selection_text(source_text)  # enforce the same capture budget
    parts = urlsplit(validated)
    blocks = [line.strip() for line in source_text.splitlines() if line.strip()]
    # Keep each term inside a block, use whole words, and bound URL growth.
    start = _comparison_text(blocks[0])
    end = _comparison_text(blocks[-1])
    use_range = len(blocks) > 1 or (len(start) > 160 and " " in start)
    if use_range:
        if len(start) > 64:
            start = start[:64].rsplit(" ", 1)[0] if " " in start[:64] else start.split()[0]
        if len(end) > 64:
            end = end[-64:].split(" ", 1)[-1] if " " in end[-64:] else end.split()[-1]
    def encode(value):
        return quote(value, safe="").replace("-", "%2D")
    directive = encode(start)
    if use_range:
        directive += "," + encode(end)
    fragment = parts.fragment.split(":~:", 1)[0] + ":~:text=" + directive
    linked = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, fragment))
    return linked if len(linked) <= 8192 else validated


def capture_source_html(url: str, title: str) -> str:
    safe_url = escape(normalize_external_http_url(url), quote=True)
    return f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{escape(title or url)}</a>'


def capture_fingerprint(url: str, text: str) -> str:
    if not text.strip():
        return ""
    parts = urlsplit(normalize_external_http_url(url))
    base = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment.split(":~:", 1)[0]))
    return hashlib.sha256((base + "\0" + _comparison_text(text)).encode("utf-8")).hexdigest()


def legacy_capture_matches(note, url: str, text: str) -> bool:
    """Match exact legacy excerpts, including old merged title/URL mappings."""
    try:
        if note["Incremento_Source_Type"] != "Browser Capture":
            return False
        source_link = str(note["Incremento_Source_Link"])
        if capture_fingerprint(source_link, text) != capture_fingerprint(url, text):
            return False
        title = _comparison_text(str(note["Incremento_Source_Title"]))
        values = [value for name, value in note.items() if not is_incremento_hidden_field(name)]
    except (KeyError, ValueError, TypeError, AttributeError):
        return False
    target = _comparison_text(text)
    candidates = {target, title + " " + target}
    candidates |= {value + " " + link for value in list(candidates) for link in (source_link, url)}
    for raw in values:
        if len(str(raw)) > MAX_SELECTION_CHARS + 12_000:
            continue
        parser = _SelectionParser()
        try:
            parser.feed(str(raw))
            parser.close()
        except ValueError:
            continue
        value = _comparison_text("".join(parser.text))
        value = re.sub(r" \[snapshot \d{8}-\d{6}-[a-f0-9]{8}\]", "", value, count=1)
        if value in candidates:
            return True
    return False
