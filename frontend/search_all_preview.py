"""Bounded, escaped annotation-source markup for Search ALL previews."""

from html import escape
from html.parser import HTMLParser
import unicodedata

try:
    from ..backend.highlight_colors import highlight_appearance
    from ..backend.annotation_notes import note_display_html
except ImportError:
    from backend.highlight_colors import highlight_appearance
    from backend.annotation_notes import note_display_html


PREVIEW_CONTEXT_CHARS = 250_000
_MAX_SOURCE_CHARS = 12_000
_IGNORED = frozenset("-\u00ad\u2010\u2011\u2012\u2013\u2014")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def annotation_note_html(note: str, markup: str, highlight_text) -> str:
    """Preserve safe formatting and term marks; preview links stay inert."""
    class Preview(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_starttag(self, tag, attrs):
            self.parts.append('<u>' if tag == 'a' else f'<{tag}>')

        def handle_endtag(self, tag):
            self.parts.append('</u>' if tag == 'a' else f'</{tag}>')

        def handle_data(self, data):
            self.parts.append(highlight_text(data))

    parser = Preview()
    parser.feed(note_display_html({'note': note, 'note_html': markup}))
    parser.close()
    return ''.join(parser.parts)


def _match_text(text: str) -> tuple[str, list[int]]:
    """Retain original character positions across wrapping and ligatures."""
    characters, offsets = [], []
    for index, raw in enumerate(text):
        for char in unicodedata.normalize("NFKC", raw).casefold().translate(_QUOTES):
            if not char.isspace() and char not in _IGNORED:
                characters.append(char)
                offsets.append(index)
    return "".join(characters), offsets


def annotation_source_html(page_text: str, source_text: str, color: str) -> str:
    """Mark the saved source in its surrounding page, or show the saved source.

    Matching never substitutes the annotation's search query for its origin.
    Unmatched/absent indexes fall back to the source instead of coloring an
    unrelated page. Only the display copy is bounded; saved text is unchanged.
    """
    source = str(source_text or "")[:_MAX_SOURCE_CHARS]
    if not source.strip():
        return ""
    page = str(page_text or "")[:PREVIEW_CONTEXT_CHARS]
    start = page.find(source)
    end = start + len(source)
    if start < 0:
        needle, _ = _match_text(source)
        haystack, offsets = _match_text(page)
        position = haystack.find(needle) if needle else -1
        if position >= 0:
            start, end = offsets[position], offsets[position + len(needle) - 1] + 1
    if start < 0:
        page, start, end = source, 0, len(source)

    try:
        rgb, opacity = highlight_appearance(color)
    except ValueError:
        rgb, opacity = highlight_appearance("yellow")
    red, green, blue = (round(channel * 255) for channel in rgb)
    return (
        escape(page[:start])
        + '<mark id="incremento-search-source" '
        + f'style="background:rgba({red},{green},{blue},{opacity});color:#111">'
        + escape(page[start:end])
        + "</mark>"
        + escape(page[end:])
    )
