"""Bounded, inert rich text for supplemental PDF/EPUB annotation notes."""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser

try:
    from .content_safety import normalize_external_http_url
except ImportError:
    from content_safety import normalize_external_http_url

MAX_NOTE_CHARS = 65_536
MAX_NOTE_HTML_CHARS = 262_144
_TAGS = frozenset(('p', 'br', 'b', 'i', 'u', 's', 'ul', 'ol', 'li', 'a'))
_ALIASES = {'strong': 'b', 'em': 'i', 'strike': 's', 'div': 'p'}
_DROP = frozenset(('script', 'style', 'head', 'iframe', 'object', 'svg', 'math', 'template'))


class _NoteHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html: list[str] = []
        self.text: list[str] = []
        self.stack: list[tuple[str, str]] = []
        self.dropped = 0

    def handle_starttag(self, tag, attrs):
        if len(self.stack) >= 64:
            raise ValueError('Annotation formatting is too deeply nested.')
        if tag in _DROP or self.dropped:
            self.dropped += 1
            self.stack.append((tag, '!'))
            return
        rendered = _ALIASES.get(tag, tag)
        suffix = ''
        if rendered == 'a':
            try:
                href = normalize_external_http_url(dict(attrs).get('href'))
                suffix = f' href="{escape(href, quote=True)}"'
            except ValueError:
                rendered = ''
        elif rendered not in _TAGS:
            rendered = ''
        if rendered:
            self.html.append(f'<{rendered}{suffix}>')
            if rendered == 'br':
                self.text.append('\n')
                return
        # Void elements never affect the nesting of subsequent text.
        if tag not in ('img', 'hr', 'input', 'meta', 'link', 'br', 'source', 'wbr'):
            self.stack.append((tag, rendered))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None)
        if index is None:
            return
        while len(self.stack) > index:
            _original, rendered = self.stack.pop()
            if rendered == '!':
                self.dropped -= 1
            elif rendered:
                self.html.append(f'</{rendered}>')
                if rendered in ('p', 'li'):
                    self.text.append('\n')

    def handle_data(self, data):
        if not self.dropped:
            self.html.append(escape(data))
            self.text.append(data)

    def finish(self):
        self.close()
        while self.stack:
            self.handle_endtag(self.stack[-1][0])
        return ''.join(self.text).replace('\xa0', ' ').strip(), ''.join(self.html)


def normalize_note(note: object, note_html: object = '') -> tuple[str, str]:
    """Keep plain text canonical; discard stale/mismatched presentation markup."""
    text = str(note or '').replace('\r\n', '\n').replace('\r', '\n').replace('\xa0', ' ').strip()
    markup = str(note_html or '')
    if len(text) > MAX_NOTE_CHARS or len(markup) > MAX_NOTE_HTML_CHARS:
        raise ValueError('Annotation note is too long.')
    if not text or not markup:
        return text, ''
    parser = _NoteHTML()
    parser.feed(markup)
    visible, sanitized = parser.finish()
    return text, sanitized if visible == text else ''


def note_display_html(highlight: dict) -> str:
    text, markup = normalize_note(highlight.get('note'), highlight.get('note_html'))
    return markup or escape(text).replace('\n', '<br>')
