"""Bounded, inert rich text for supplemental PDF/EPUB annotation notes."""
from __future__ import annotations

import base64
import binascii
from html import escape
from html.parser import HTMLParser
import re
import struct

try:
    from .content_safety import normalize_external_http_url
except ImportError:
    from content_safety import normalize_external_http_url

MAX_NOTE_CHARS = 65_536
MAX_NOTE_HTML_CHARS = 262_144
MAX_IMAGE_BYTES = 80 * 1024
MAX_IMAGE_EDGE = 960
_TAGS = frozenset(('p', 'br', 'b', 'i', 'u', 's', 'ul', 'ol', 'li', 'a'))
_ALIASES = {'strong': 'b', 'em': 'i', 'strike': 's', 'div': 'p'}
_DROP = frozenset(('script', 'style', 'head', 'iframe', 'object', 'svg', 'math', 'template'))


def image_info(source: str) -> tuple[bytes, int, int]:
    """Only bounded embedded PNG/JPEG bitmaps; never resolve a URL or file."""
    match = re.fullmatch(r'data:image/(png|jpeg);base64,([A-Za-z0-9+/]+={0,2})', source)
    if not match or len(match[2]) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        raise ValueError('Invalid annotation image.')
    try:
        data = base64.b64decode(match[2], validate=True)
    except binascii.Error as exc:
        raise ValueError('Invalid annotation image.') from exc
    width = height = 0
    if match[1] == 'png' and data.startswith(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR') and len(data) >= 45:
        width, height = struct.unpack('>II', data[16:24])
        if not data.endswith(b'\x00\x00\x00\x00IEND\xaeB`\x82'):
            raise ValueError('Invalid annotation image.')
    elif match[1] == 'jpeg' and data.startswith(b'\xff\xd8') and data.endswith(b'\xff\xd9'):
        offset = 2
        while offset + 4 <= len(data):
            if data[offset] != 255:
                break
            marker = data[offset + 1]
            size = int.from_bytes(data[offset + 2:offset + 4], 'big')
            if size < 2 or offset + 2 + size > len(data):
                break
            if marker in (0xc0, 0xc2) and size >= 8:
                height, width = struct.unpack('>HH', data[offset + 5:offset + 9])
                break
            offset += size + 2
    if len(data) > MAX_IMAGE_BYTES or not 1 <= min(width, height) <= max(width, height) <= MAX_IMAGE_EDGE:
        raise ValueError('Invalid annotation image.')
    return data, width, height


def image_html(source: str, width: object = 320, height: object = None, float_side: str = '') -> str:
    _data, natural_width, natural_height = image_info(source)
    try:
        display_width = max(1, min(int(width), 640))
    except (ValueError, TypeError, OverflowError):
        display_width = min(320, natural_width)
    proportional_height = max(1, int(display_width * natural_height / natural_width + 0.5))
    try:
        display_height = max(1, min(int(height), MAX_IMAGE_EDGE))
    except (ValueError, TypeError, OverflowError):
        if proportional_height > MAX_IMAGE_EDGE:
            display_width = max(1, round(display_width * MAX_IMAGE_EDGE / proportional_height))
        display_height = min(proportional_height, MAX_IMAGE_EDGE)
    placement = f' style="float:{float_side}"' if float_side in ('left', 'right') else ''
    return f'<img src="{source}" width="{display_width}" height="{display_height}" alt=""{placement}>'


class _NoteHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.html: list[str] = []
        self.text: list[str] = []
        self.stack: list[tuple[str, str]] = []
        self.dropped = 0
        self.images = 0

    def handle_starttag(self, tag, attrs):
        if len(self.stack) >= 64:
            raise ValueError('Annotation formatting is too deeply nested.')
        if tag in _DROP or self.dropped:
            self.dropped += 1
            self.stack.append((tag, '!'))
            return
        if tag == 'img':
            try:
                values = dict(attrs)
                floating = re.fullmatch(r'float:\s*(left|right);?', str(values.get('style') or '').strip())
                rendered_image = image_html(values.get('src') or '', values.get('width', 320), values.get('height'),
                                            floating[1] if floating else '')
            except ValueError:
                return
            self.images += 1
            if self.images > 4:
                raise ValueError('Too many annotation images.')
            self.html.append(rendered_image)
            return
        rendered = _ALIASES.get(tag, tag)
        suffix = ''
        if rendered == 'p' and dict(attrs).get('align') in ('left', 'center', 'right'):
            suffix = f' align="{dict(attrs)["align"]}"'
        elif rendered == 'a':
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
    if not markup:
        return text, ''
    visible, sanitized = sanitize_note_html(markup)
    return text, sanitized if visible == text else ''


def sanitize_note_html(markup: str) -> tuple[str, str]:
    """Bound clipboard markup and detect empty/blocked resource-only pastes."""
    if len(markup) > MAX_NOTE_HTML_CHARS:
        raise ValueError('Annotation note is too long.')
    parser = _NoteHTML()
    parser.feed(markup)
    visible, sanitized = parser.finish()
    return visible, sanitized if visible or parser.images else ''


def note_display_html(highlight: dict) -> str:
    text, markup = normalize_note(highlight.get('note'), highlight.get('note_html'))
    if ' style="float:' in markup:
        # A Qt-supported containing frame keeps the next note outside the float.
        return '<table width="100%" cellspacing="0" cellpadding="0"><tr><td>' + markup + '</td></tr></table>'
    return markup or escape(text).replace('\n', '<br>')
