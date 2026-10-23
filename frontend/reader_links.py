"""Security boundary for links opened from untrusted reader documents."""

from __future__ import annotations

import json
import math
import re
import textwrap
import unicodedata
from difflib import SequenceMatcher
from pathlib import PurePath
from html import escape as _escape_html
from html.parser import HTMLParser
from urllib.parse import urlsplit


_MAX_EXTERNAL_READER_URL_CHARS = 4096
_ALLOWED_EXTERNAL_READER_SCHEMES = {"http", "https"}
READER_ANCHOR_MIME_TYPE = "application/x-incremento-reader-anchor+json"
_READER_ANCHOR_MIME_VERSION = 1
_MAX_READER_ANCHOR_HTML_CHARS = 32_768
_MAX_READER_ANCHOR_TEXT_CHARS = 2_048
_MAX_READER_ANCHOR_MIME_BYTES = 40_000
_READER_ANCHOR_STYLE = "cursor:pointer; color:#4a90d9; text-decoration:none;"
_READER_ANCHOR_ONCLICK_RE = re.compile(
    r'^pycmd\(("(?:\\.|[^"\\])*")\); return false;$'
)
_PDF_REFERENCE_LINK_RE = re.compile(
    r"<a\b(?=[^>]*incremento_open_pdf_ref:)[^>]*>.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
_LEGACY_PDF_REF_ANCHOR_RE = re.compile(
    r"(?P<open><a\b[^>]*incremento_open_pdf_ref:[^>]*>)"
    r"(?P<label>.*?)(?P<close></a>)",
    re.IGNORECASE | re.DOTALL,
)
_PDF_CARD_CONTEXT_AFTER_LINK_RE = re.compile(
    r"^\s*(?:<br\s*/?>\s*)?<div\b[^>]*"
    r"\bdata-incremento-pdf-context=(?:\"1\"|'1')[^>]*>.*?</div>",
    re.IGNORECASE | re.DOTALL,
)
_PDF_CARD_SNAPSHOT_AFTER_LINK_RE = re.compile(
    r"^\s*(?:<br\s*/?>\s*)?<(?:span|div)\b[^>]*"
    r"\bdata-incremento-pdf-snapshot=(?:\"1\"|'1')[^>]*>.*?"
    r"<!--incremento-pdf-snapshot-end-->",
    re.IGNORECASE | re.DOTALL,
)
_PDF_CARD_TEXT_PREVIEW_AFTER_LINK_RE = re.compile(
    r"^\s*(?:<br\s*/?>\s*)?<div\b[^>]*"
    r"\bdata-incremento-pdf-text-preview=(?:\"1\"|'1')[^>]*>.*?"
    r"<!--incremento-pdf-text-preview-end-->",
    re.IGNORECASE | re.DOTALL,
)
_PDF_SNAPSHOT_SOURCE_OPEN_RE = re.compile(
    r"<span\b(?=[^>]*\bdata-incremento-pdf-source-text=(?:\"1\"|'1'))[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
_PDF_SNAPSHOT_BLOCK_RE = re.compile(
    r"<div\b(?=[^>]*\bdata-incremento-pdf-snapshot=(?:\"1\"|'1'))[^>]*>"
    r".*?<!--incremento-pdf-snapshot-end-->",
    re.IGNORECASE | re.DOTALL,
)
_PDF_HOVER_CONTEXT_ROWS = 5
_MAX_PDF_HOVER_LINKS = 12
_MAX_PDF_CONTEXT_LINKS_PER_FIELD = 100
_MAX_PDF_CONTEXT_FIELD_HTML_CHARS = 2_000_000
_MAX_PDF_HOVER_PAGE_TEXT_CHARS = 250_000
_MAX_PDF_HOVER_PREVIEW_CHARS = 12_000
_MAX_CARD_HOVER_SOURCE_HTML_CHARS = 32_768
_MAX_CARD_HOVER_EXCERPT_CHARS = 2_000
_PDF_HOVER_STYLE = """
<style id="incremento-pdf-hover-preview-style">
.incremento-pdf-hover-link {
  display: inline;
  position: relative;
}
.incremento-pdf-hover-preview {
  display: none;
  position: absolute;
  z-index: 2147483646;
  left: 50%;
  bottom: calc(100% + 0.55em);
  width: max-content;
  min-width: min(28rem, 84vw);
  max-width: min(46rem, 90vw);
  max-height: min(28rem, 60vh);
  overflow: auto;
  box-sizing: border-box;
  padding: 0.75rem 0.9rem;
  border: 1px solid rgba(148, 163, 184, 0.48);
  border-radius: 0.55rem;
  background: rgba(23, 29, 40, 0.98);
  color: #f4f7fb;
  box-shadow: 0 0.9rem 2.2rem rgba(0, 0, 0, 0.38);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 0.88rem;
  font-weight: 400;
  line-height: 1.45;
  text-align: left;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  transform: translateX(-50%);
  cursor: text;
  user-select: text;
  -webkit-user-select: text;
}
.incremento-pdf-hover-link:hover > .incremento-pdf-hover-preview,
.incremento-pdf-hover-link:focus-within > .incremento-pdf-hover-preview {
  display: block;
}
.incremento-pdf-hover-excerpt {
  color: #60a5fa;
  font-weight: 700;
}
</style>
""".strip()
_PDF_HOVER_CENTER_HANDLER = (
    "var preview=this.querySelector('.incremento-pdf-hover-preview'),"
    "excerpt=preview&&preview.querySelector('.incremento-pdf-hover-excerpt');"
    "if(preview&&excerpt){preview.scrollTop=Math.max(0,excerpt.offsetTop-"
    "(preview.clientHeight-excerpt.offsetHeight)/2);}"
)


class _ReaderAnchorHtmlParser(HTMLParser):
    """Parse the one narrow anchor shape Incremento puts on the clipboard."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.onclick = ""
        self.text_parts: list[str] = []
        self.started = False
        self.ended = False
        self.invalid = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.started or self.ended or tag.casefold() != "a":
            self.invalid = True
            return
        normalized: dict[str, str] = {}
        for key, value in attrs:
            normalized_key = str(key or "").casefold()
            if not normalized_key or value is None or normalized_key in normalized:
                self.invalid = True
                return
            normalized[normalized_key] = str(value)
        if set(normalized) != {"onclick", "style"}:
            self.invalid = True
            return
        if normalized["style"] != _READER_ANCHOR_STYLE:
            self.invalid = True
            return
        self.onclick = normalized["onclick"]
        self.started = True

    def handle_endtag(self, tag: str) -> None:
        if not self.started or self.ended or tag.casefold() != "a":
            self.invalid = True
            return
        self.ended = True

    def handle_data(self, data: str) -> None:
        if not self.started or self.ended:
            if data.strip():
                self.invalid = True
            return
        self.text_parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.invalid = True

    def handle_comment(self, data: str) -> None:
        self.invalid = True

    def handle_decl(self, decl: str) -> None:
        self.invalid = True

    def handle_pi(self, data: str) -> None:
        self.invalid = True


class _VisibleCardTextParser(HTMLParser):
    """Collect bounded visible card text without interpreting card markup."""

    _BREAK_TAGS = {
        "br",
        "div",
        "p",
        "li",
        "tr",
        "td",
        "th",
        "blockquote",
        "section",
        "article",
        "header",
        "footer",
        "hr",
    }
    _HIDDEN_TAGS = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if normalized in self._HIDDEN_TAGS:
            self._hidden_depth += 1
            return
        if self._hidden_depth == 0 and normalized in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._hidden_depth == 0 and tag.casefold() in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in self._HIDDEN_TAGS:
            if self._hidden_depth > 0:
                self._hidden_depth -= 1
            return
        if self._hidden_depth == 0 and normalized in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            self.parts.append(data)


def _valid_reader_anchor_command(command: object) -> bool:
    if not isinstance(command, str) or not command or len(command) > 24_000:
        return False

    pdf_prefix = "incremento_open_pdf_ref:"
    if command.startswith(pdf_prefix):
        try:
            payload = json.loads(command[len(pdf_prefix) :])
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(payload, dict):
            return False
        allowed_keys = {
            "card_id",
            "filename",
            "page",
            "excerpt",
            "highlight_id",
            "scroll_ratio",
        }
        if not {"card_id", "filename", "page"}.issubset(payload) or not set(payload).issubset(
            allowed_keys
        ):
            return False
        card_id = payload.get("card_id")
        page = payload.get("page")
        filename = payload.get("filename")
        if (
            isinstance(card_id, bool)
            or not isinstance(card_id, int)
            or card_id <= 0
            or isinstance(page, bool)
            or not isinstance(page, int)
            or page <= 0
            or page > 1_000_000
            or not isinstance(filename, str)
            or not filename.strip()
            or len(filename) > 4_096
            or "\x00" in filename
        ):
            return False
        for key, limit in (("excerpt", 12_000), ("highlight_id", 1_024)):
            value = payload.get(key)
            if value is not None and (
                not isinstance(value, str) or len(value) > limit or "\x00" in value
            ):
                return False
        if "scroll_ratio" in payload:
            value = payload.get("scroll_ratio")
            if isinstance(value, bool):
                return False
            try:
                ratio = float(value)
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
                return False
        return True

    epub_prefix = "incremento_open_epub:"
    if command.startswith(epub_prefix):
        parts = command.split(":")
        if len(parts) not in {4, 5}:
            return False
        try:
            card_id = int(parts[1])
            section_index = int(parts[2])
            focus_offset = int(parts[3])
        except (TypeError, ValueError, OverflowError):
            return False
        if (
            card_id <= 0
            or section_index < 0
            or section_index > 1_000_000
            or focus_offset < -1
            or focus_offset > 50_000_000
        ):
            return False
        if len(parts) == 5:
            try:
                ratio = float(parts[4])
            except (TypeError, ValueError, OverflowError):
                return False
            if not math.isfinite(ratio) or not 0.0 <= ratio <= 1.0:
                return False
        return True

    return False


def _canonical_reader_anchor_html(raw_html: object) -> str | None:
    candidate = str(raw_html or "").strip()
    if (
        not candidate
        or len(candidate) > _MAX_READER_ANCHOR_HTML_CHARS
        or "\x00" in candidate
    ):
        return None
    parser = _ReaderAnchorHtmlParser()
    try:
        parser.feed(candidate)
        parser.close()
    except Exception:
        return None
    label = "".join(parser.text_parts).strip()
    if (
        parser.invalid
        or not parser.started
        or not parser.ended
        or not label
        or len(label) > _MAX_READER_ANCHOR_TEXT_CHARS
        or "\x00" in label
    ):
        return None
    match = _READER_ANCHOR_ONCLICK_RE.fullmatch(parser.onclick)
    if match is None:
        return None
    try:
        command = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not _valid_reader_anchor_command(command):
        return None
    onclick = _escape_html(
        f"pycmd({json.dumps(command)}); return false;",
        quote=True,
    )
    return (
        f'<a onclick="{onclick}" style="{_READER_ANCHOR_STYLE}">'
        f"{_escape_html(label)}</a>"
    )


def make_reader_anchor_html(command: str, label: str) -> str:
    """Build the same narrowly trusted shape for every independent reader."""
    if not _valid_reader_anchor_command(command) or not isinstance(label, str) or not label.strip():
        return ""
    onclick = _escape_html(f"pycmd({json.dumps(command)}); return false;", quote=True)
    html = f'<a onclick="{onclick}" style="{_READER_ANCHOR_STYLE}">{_escape_html(label)}</a>'
    return _canonical_reader_anchor_html(html) or ""


def reader_anchor_command_from_html(raw_html: object) -> str | None:
    """Return the validated pycmd command from one Incremento reader anchor."""
    canonical = _canonical_reader_anchor_html(raw_html)
    if canonical is None:
        return None
    parser = _ReaderAnchorHtmlParser()
    try:
        parser.feed(canonical)
        parser.close()
    except Exception:
        return None
    match = _READER_ANCHOR_ONCLICK_RE.fullmatch(parser.onclick)
    if match is None:
        return None
    try:
        command = json.loads(match.group(1))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return command if _valid_reader_anchor_command(command) else None


def repair_legacy_pdf_reference_links_html(html: object) -> str:
    """Repair the malformed citation attributes produced by older releases."""
    rendered = str(html or "")
    if (
        not rendered
        or "incremento_open_pdf_ref:" not in rendered
        or 'onclick="pycmd("' not in rendered
    ):
        return rendered

    def _replace(match: re.Match[str]) -> str:
        open_tag = match.group("open")
        label = match.group("label")
        card_id_match = re.search(
            r'card_id\\?":(?:\s*=""\s*)?(?P<card_id>\d+)', open_tag
        )
        filename_match = re.search(
            r'filename\\?":(?:\s*=""\s*)?\\?"(?P<filename>[^"\\]+)\\?"',
            open_tag,
        )
        page_match = re.search(
            r'page\\?":(?:\s*=""\s*)?(?P<page>\d+)', open_tag
        )
        if not (card_id_match and filename_match and page_match):
            return match.group(0)
        command = "incremento_open_pdf_ref:" + json.dumps(
            {
                "card_id": int(card_id_match.group("card_id")),
                "filename": str(filename_match.group("filename")).strip(),
                "page": int(page_match.group("page")),
            },
            ensure_ascii=False,
        )
        onclick = _escape_html(
            f"pycmd({json.dumps(command)}); return false;",
            quote=True,
        )
        return (
            f'<a onclick="{onclick}" '
            f'style="{_READER_ANCHOR_STYLE}">{label}</a>'
        )

    return _LEGACY_PDF_REF_ANCHOR_RE.sub(_replace, rendered)


def _pdf_hover_rows(page_text: object) -> list[str]:
    rows: list[str] = []
    text = str(page_text or "")[:_MAX_PDF_HOVER_PAGE_TEXT_CHARS]
    for physical_line in text.splitlines():
        line = " ".join(physical_line.split()).strip()
        if not line:
            continue
        # Some PDF extractors return a whole page as one line. Treat a
        # readable soft-wrapped line as a row so the five-row contract remains
        # useful for those documents too.
        rows.extend(
            textwrap.wrap(
                line,
                width=120,
                break_long_words=False,
                break_on_hyphens=False,
            )
            or [line]
        )
    return rows


def _pdf_hover_excerpt_span(rows: list[str], excerpt: object) -> tuple[int, int] | None:
    needle = " ".join(str(excerpt or "").split()).strip()
    if not needle:
        return None
    # A citation excerpt may cross several PDF text rows. Searching a bounded
    # run of adjacent rows locates both single-line and multi-line selections.
    bounded_needle = needle[:2_000].casefold()
    for index, row in enumerate(rows):
        if bounded_needle in row.casefold():
            return index, index
    for start in range(len(rows)):
        combined = ""
        for end in range(start, min(len(rows), start + 24)):
            combined = (combined + " " + rows[end]).strip()
            folded = combined.casefold()
            if end > start and bounded_needle in folded:
                return start, end
            if len(folded) > len(bounded_needle) + 240:
                break
    joined = "\n".join(rows)
    fuzzy_span = _source_excerpt_match_span(joined, excerpt)
    if fuzzy_span is None:
        return None
    start, end = fuzzy_span
    return (
        joined.count("\n", 0, start),
        joined.count("\n", 0, max(start, end - 1)),
    )


def pdf_hover_context_text(
    page_text: object,
    *,
    excerpt: object = "",
    scroll_ratio: object = None,
    context_rows: int = _PDF_HOVER_CONTEXT_ROWS,
) -> str:
    """Build a bounded PDF text preview around a citation's exact location."""
    preview, _highlight_start, _highlight_end = _pdf_hover_context_parts(
        page_text,
        excerpt=excerpt,
        scroll_ratio=scroll_ratio,
        context_rows=context_rows,
    )
    return preview


def _collapsed_text_offsets(text: str) -> tuple[str, list[int], list[int]]:
    collapsed: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            start = index
            while index < len(text) and text[index].isspace():
                index += 1
            collapsed.append(" ")
            starts.append(start)
            ends.append(index)
            continue
        collapsed.append(text[index])
        starts.append(index)
        index += 1
        ends.append(index)
    return "".join(collapsed).strip(), starts, ends


def _normalized_match_span(text: str, needle: object) -> tuple[int, int] | None:
    normalized_needle = " ".join(str(needle or "").split()).strip()
    if not normalized_needle:
        return None
    normalized_text, starts, ends = _collapsed_text_offsets(text)
    try:
        match = re.search(re.escape(normalized_needle), normalized_text, re.IGNORECASE)
    except re.error:
        return None
    if match is None or match.end() <= match.start():
        return _source_excerpt_match_span(text, needle)
    return starts[match.start()], ends[match.end() - 1]


def _match_token(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _word_tokens_with_spans(text: object) -> list[tuple[str, int, int]]:
    source = str(text or "")
    tokens: list[tuple[str, int, int]] = []
    for match in re.finditer(r"\w+", source, re.UNICODE):
        token = _match_token(match.group(0))
        if token:
            tokens.append((token, match.start(), match.end()))
    return tokens


def _source_excerpt_match_span(text: object, excerpt: object) -> tuple[int, int] | None:
    """Locate an excerpt despite PDF punctuation, ligature, or OCR differences."""
    source_tokens = _word_tokens_with_spans(text)
    excerpt_tokens = [
        token
        for token, _start, _end in _word_tokens_with_spans(excerpt)
    ]
    if not source_tokens or not excerpt_tokens:
        return None
    source_words = [token for token, _start, _end in source_tokens]

    # First prefer an exact word sequence. This ignores typographic quotes,
    # line wrapping, hyphenation punctuation, and compatibility ligatures.
    first_word = excerpt_tokens[0]
    excerpt_count = len(excerpt_tokens)
    for index, word in enumerate(source_words):
        if word != first_word:
            continue
        if source_words[index : index + excerpt_count] == excerpt_tokens:
            end_index = index + excerpt_count - 1
            return source_tokens[index][1], source_tokens[end_index][2]

    # Longer excerpts can tolerate a small number of OCR or contraction
    # differences. Anchor the comparison on its longest contiguous match, then
    # score only nearby, similarly sized windows so unrelated page prose cannot
    # win merely by sharing common words.
    if excerpt_count < 6:
        return None
    matcher = SequenceMatcher(None, excerpt_tokens, source_words, autojunk=False)
    anchor = matcher.find_longest_match(
        0,
        excerpt_count,
        0,
        len(source_words),
    )
    required_anchor = max(4, min(12, math.ceil(excerpt_count * 0.25)))
    if anchor.size < required_anchor:
        return None

    estimated_start = anchor.b - anchor.a
    radius = min(20, max(4, excerpt_count // 5))
    length_slack = min(12, max(3, excerpt_count // 8))
    best: tuple[float, int, int] | None = None
    for start in range(
        max(0, estimated_start - radius),
        min(len(source_words), estimated_start + radius + 1),
    ):
        for length in range(
            max(1, excerpt_count - length_slack),
            excerpt_count + length_slack + 1,
        ):
            end = min(len(source_words), start + length)
            if end <= start:
                continue
            score = SequenceMatcher(
                None,
                excerpt_tokens,
                source_words[start:end],
                autojunk=False,
            ).ratio()
            candidate = (score, start, end)
            if best is None or candidate > best:
                best = candidate
    if best is None or best[0] < 0.72:
        return None
    _score, start, end = best
    return source_tokens[start][1], source_tokens[end - 1][2]


def _pdf_hover_context_parts(
    page_text: object,
    *,
    excerpt: object = "",
    scroll_ratio: object = None,
    context_rows: int = _PDF_HOVER_CONTEXT_ROWS,
) -> tuple[str, int, int]:
    rows = _pdf_hover_rows(page_text)
    if not rows:
        return "", 0, 0
    span = _pdf_hover_excerpt_span(rows, excerpt)
    if span is None:
        ratio = normalize_reader_anchor_scroll_ratio(scroll_ratio)
        if ratio is None:
            return "", 0, 0
        center = (
            int(round(ratio * (len(rows) - 1)))
            if ratio is not None
            else len(rows) // 2
        )
        span = (center, center)
    before_after = max(0, min(int(context_rows), 20))
    start = max(0, span[0] - before_after)
    end = min(len(rows), span[1] + before_after + 1)
    visible = list(rows[start:end])
    body = "\n".join(visible)
    prefix = "…\n" if start > 0 else ""
    suffix = "\n…" if end < len(rows) else ""
    preview = prefix + body + suffix

    highlight = _normalized_match_span(body, excerpt)
    if highlight is None:
        relative_start = max(0, min(span[0] - start, len(visible) - 1))
        relative_end = max(relative_start, min(span[1] - start, len(visible) - 1))
        row_start = sum(len(row) + 1 for row in visible[:relative_start])
        row_end = sum(len(row) + 1 for row in visible[:relative_end]) + len(
            visible[relative_end]
        )
        highlight = (row_start, row_end)
    highlight_start = len(prefix) + highlight[0]
    highlight_end = len(prefix) + highlight[1]
    bounded_preview = preview[:_MAX_PDF_HOVER_PREVIEW_CHARS].rstrip()
    if highlight_start >= len(bounded_preview):
        return bounded_preview, 0, 0
    return (
        bounded_preview,
        highlight_start,
        min(highlight_end, len(bounded_preview)),
    )


def pdf_hover_context_html(
    page_text: object,
    *,
    excerpt: object = "",
    scroll_ratio: object = None,
    context_rows: int = _PDF_HOVER_CONTEXT_ROWS,
) -> str:
    """Return escaped hover context with the cited excerpt visually marked."""
    preview, highlight_start, highlight_end = _pdf_hover_context_parts(
        page_text,
        excerpt=excerpt,
        scroll_ratio=scroll_ratio,
        context_rows=context_rows,
    )
    if not preview:
        return ""
    if highlight_end <= highlight_start:
        return _escape_html(preview)
    displayed_excerpt = " ".join(str(excerpt or "").split()).strip()
    if not displayed_excerpt:
        displayed_excerpt = preview[highlight_start:highlight_end]
    return (
        _escape_html(preview[:highlight_start])
        + '<span class="incremento-pdf-hover-excerpt">'
        + _escape_html(displayed_excerpt[:_MAX_PDF_HOVER_PREVIEW_CHARS])
        + "</span>"
        + _escape_html(preview[highlight_end:])
    )


def pdf_context_card_html(
    page_text: object,
    *,
    excerpt: object = "",
    scroll_ratio: object = None,
    context_rows: int = _PDF_HOVER_CONTEXT_ROWS,
) -> str:
    """Return self-contained PDF context stored in an Anki field for mobile."""
    preview, highlight_start, highlight_end = _pdf_hover_context_parts(
        page_text,
        excerpt=excerpt,
        scroll_ratio=scroll_ratio,
        context_rows=context_rows,
    )
    if not preview:
        return ""
    if highlight_end <= highlight_start:
        marked = _escape_html(preview)
    else:
        displayed_excerpt = " ".join(str(excerpt or "").split()).strip()
        if not displayed_excerpt:
            displayed_excerpt = preview[highlight_start:highlight_end]
        marked = (
            _escape_html(preview[:highlight_start])
            + '<span class="incremento-pdf-context-excerpt" '
            + 'style="color:#60a5fa;font-weight:700;">'
            + _escape_html(displayed_excerpt[:_MAX_PDF_HOVER_PREVIEW_CHARS])
            + "</span>"
            + _escape_html(preview[highlight_end:])
        )
    return (
        '<div data-incremento-pdf-context="1" role="note" '
        'style="box-sizing:border-box;margin:.65em 0;padding:.7em .85em;'
        'border-left:3px solid #60a5fa;border-radius:.35em;'
        'background:rgba(96,165,250,.10);color:inherit;'
        'font:inherit;line-height:1.45;white-space:pre-wrap;'
        'overflow-wrap:anywhere;text-align:left;">'
        f"{marked}</div>"
    )


def _safe_snapshot_media_filename(value: object) -> str:
    filename = str(value or "").strip()
    if (
        not filename
        or len(filename) > 255
        or "\x00" in filename
        or "/" in filename
        or "\\" in filename
        or PurePath(filename).name != filename
        or not filename.casefold().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ):
        return ""
    return filename


def _normalize_pdf_snapshot_source_style(html: object) -> str:
    """Remove old hover attributes and inherited color overrides from saved text."""
    return _PDF_SNAPSHOT_SOURCE_OPEN_RE.sub(
        '<span data-incremento-pdf-source-text="1">', str(html or "")
    )


def pdf_snapshot_source_html(extracted_html: object) -> str:
    """Keep exact extracted text visible with the card template's typography."""
    source = str(extracted_html or "")
    if 'data-incremento-pdf-source-text="1"' in source:
        return _normalize_pdf_snapshot_source_style(source)
    return source


def prepare_pdf_previews_for_editor(editor) -> None:
    """Protect saved preview controls and leave a caret target outside them."""
    fields = getattr(getattr(editor, "note", None), "fields", ())
    if not any(
        "incremento-pdf-snapshot-details" in str(field)
        or "incremento-pdf-context-details" in str(field)
        for field in fields
    ):
        return
    web = getattr(editor, "web", None)
    if web is None:
        return
    web.eval(r"""
        (() => {
            function prepare(root) {
                const previews = root.querySelectorAll(
                    'details.incremento-pdf-snapshot-details, details.incremento-pdf-context-details'
                );
                for (const preview of previews) {
                    if (!preview.closest('[contenteditable="true"]')) continue;
                    preview.contentEditable = 'false';
                    let tail = preview.closest(
                        '[data-incremento-pdf-snapshot="1"], [data-incremento-pdf-text-preview="1"]'
                    ) || preview;
                    let next = tail.nextSibling;
                    while (next && (next.nodeType === 8 ||
                            (next.nodeType === 3 && !next.textContent.trim()))) {
                        tail = next;
                        next = next.nextSibling;
                    }
                    if (!next) {
                        const line = document.createElement('div');
                        line.appendChild(document.createElement('br'));
                        tail.after(line);
                    }
                }
                for (const element of root.querySelectorAll('*')) {
                    if (element.shadowRoot) prepare(element.shadowRoot);
                }
            }
            prepare(document);
        })();
    """)


def _pdf_preview_details_html(content: str, preview_label: object, class_name: str) -> str:
    label = " ".join(str(preview_label or "").split()).strip()[:200]
    if not content or not label:
        return ""
    # Enter inside an editable summary clones the button instead of making a
    # normal paragraph. The reference helpers provide a separate typing line.
    return (
        f'<details class="{class_name}" contenteditable="false">'
        '<summary style="display:inline-block;cursor:pointer;padding:.35em .65em;'
        'border:1px solid #64748b;border-radius:.4em;color:inherit;'
        'background:rgba(100,116,139,.12);">'
        f"{_escape_html(label)}</summary>"
        f'<div style="margin-top:.5em;">{content}</div>'
        '</details>'
    )


def pdf_text_context_reference_html(
    extracted_html: object,
    citation_html: object,
    page_text: object,
    *,
    excerpt: object,
    context_rows: int,
    preview_label: object,
) -> str:
    """Keep matched, escaped source context available when a screenshot fails."""
    citation = str(citation_html or "")
    command = reader_anchor_command_from_html(citation)
    if command is None or not command.startswith("incremento_open_pdf_ref:"):
        return ""
    # Require a passage match; a scroll estimate alone can show unrelated text.
    context = pdf_context_card_html(page_text, excerpt=excerpt, context_rows=context_rows)
    preview = _pdf_preview_details_html(context, preview_label, "incremento-pdf-context-details")
    source = pdf_snapshot_source_html(extracted_html)
    if not source or not preview:
        return ""
    return (
        source + "<br>" + citation + "<br>"
        '<div data-incremento-pdf-text-preview="1" '
        'style="display:block;margin:.55em 0;text-align:left;">'
        + preview + '</div><!--incremento-pdf-text-preview-end--><div><br></div>'
    )


def pdf_snapshot_card_html(
    media_filename: object,
    *,
    preview_label: object,
) -> str:
    """Return a syncable screenshot revealed by a visible control."""
    filename = _safe_snapshot_media_filename(media_filename)
    label = " ".join(str(preview_label or "").split()).strip()[:200]
    if not filename or not label:
        return ""
    escaped_filename = _escape_html(filename, quote=True)
    image = (
        f'<img src="{escaped_filename}" alt="{_escape_html(label, quote=True)}" '
        'style="display:block;max-width:100%;height:auto;margin:0 auto;">'
    )
    preview = _pdf_preview_details_html(image, label, "incremento-pdf-snapshot-details")
    return (
        '<div data-incremento-pdf-snapshot="1" '
        'style="display:block;margin:.55em 0;text-align:left;">'
        f'{preview}</div><!--incremento-pdf-snapshot-end-->'
    )


class _SnapshotImageParser(HTMLParser):
    """Read the saved media reference from an older snapshot preview block."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.filename = ""
        self.label = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img" or self.filename:
            return
        attributes = dict(attrs)
        filename = _safe_snapshot_media_filename(attributes.get("src"))
        if filename:
            self.filename = filename
            self.label = str(attributes.get("alt") or "").strip()


def collapsible_pdf_snapshot_previews(html: object) -> str:
    """Give saved hover or inline snapshots a reveal control without editing notes."""
    rendered = str(html or "")
    if (
        "incremento-pdf-snapshot-popover" not in rendered
        and "incremento-pdf-snapshot-inline" not in rendered
    ) or len(rendered) > _MAX_PDF_CONTEXT_FIELD_HTML_CHARS:
        return rendered
    converted = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal converted
        if 'class="incremento-pdf-snapshot-details"' in match.group(0):
            return match.group(0)
        parser = _SnapshotImageParser()
        try:
            parser.feed(match.group(0))
            parser.close()
        except Exception:
            return match.group(0)
        replacement = pdf_snapshot_card_html(
            parser.filename, preview_label=parser.label
        )
        if not replacement:
            return match.group(0)
        converted += 1
        return replacement

    displayed = _PDF_SNAPSHOT_BLOCK_RE.sub(_replace, rendered)
    return _normalize_pdf_snapshot_source_style(displayed) if converted else rendered


def pdf_snapshot_reference_html(
    extracted_html: object,
    citation_html: object,
    media_filename: object,
    *,
    preview_label: object,
) -> str:
    """Combine exact extracted text, its citation, and a screenshot preview."""
    citation = str(citation_html or "")
    if reader_anchor_command_from_html(citation) is None:
        return ""
    context = pdf_snapshot_card_html(media_filename, preview_label=preview_label)
    source = pdf_snapshot_source_html(extracted_html)
    if not source or not context:
        return ""
    # Keep user additions outside the block replaced by the preview rebuild tool.
    return source + "<br>" + citation + "<br>" + context + '<div><br></div>'


def rebuild_pdf_reference_card_snapshots(
    html: object,
    snapshot_loader,
    *,
    preview_label: object,
) -> tuple[str, int, int]:
    """Insert or replace syncable PDF screenshots for citations in one field."""
    rendered = repair_legacy_pdf_reference_links_html(html)
    if (
        "incremento_open_pdf_ref:" not in rendered
        or len(rendered) > _MAX_PDF_CONTEXT_FIELD_HTML_CHARS
        or not callable(snapshot_loader)
    ):
        return rendered, 0, 0

    pieces: list[str] = []
    cursor = 0
    updated = 0
    skipped = 0
    matches = list(_PDF_REFERENCE_LINK_RE.finditer(rendered))
    for match in matches[:_MAX_PDF_CONTEXT_LINKS_PER_FIELD]:
        if match.start() < cursor:
            continue
        segment = rendered[cursor : match.start()]
        original = match.group(0)
        command = reader_anchor_command_from_html(original)
        prefix = "incremento_open_pdf_ref:"
        if command is None or not command.startswith(prefix):
            pieces.extend((segment, original))
            cursor = match.end()
            skipped += 1
            continue
        try:
            payload = json.loads(command[len(prefix) :])
        except (TypeError, ValueError, json.JSONDecodeError):
            pieces.extend((segment, original))
            cursor = match.end()
            skipped += 1
            continue

        stored_excerpt = str(payload.get("excerpt") or "").strip()
        nearby_candidates = _card_hover_excerpt_candidates(
            segment, max_chars=_MAX_PDF_HOVER_PREVIEW_CHARS
        )
        excerpt_candidates = []
        if stored_excerpt:
            for candidate in nearby_candidates:
                excerpt_match = _normalized_match_span(candidate, stored_excerpt)
                if excerpt_match is not None:
                    complete_selection = candidate[excerpt_match[0] :]
                    if len(complete_selection) > len(stored_excerpt):
                        excerpt_candidates.append(complete_selection)
            excerpt_candidates.append(stored_excerpt)
        else:
            excerpt_candidates = nearby_candidates
        media_filename = ""
        for excerpt in excerpt_candidates:
            try:
                media_filename = _safe_snapshot_media_filename(snapshot_loader(payload, excerpt))
            except Exception:
                media_filename = ""
            if media_filename:
                break
        context_html = pdf_snapshot_card_html(
            media_filename,
            preview_label=preview_label,
        )
        if not context_html:
            pieces.extend((segment, original))
            cursor = match.end()
            skipped += 1
            continue

        normalized_segment = _normalize_pdf_snapshot_source_style(segment)
        after_link = rendered[match.end() :]
        old_context = _PDF_CARD_SNAPSHOT_AFTER_LINK_RE.match(after_link)
        if old_context is None:
            old_context = _PDF_CARD_TEXT_PREVIEW_AFTER_LINK_RE.match(after_link)
        if old_context is None:
            old_context = _PDF_CARD_CONTEXT_AFTER_LINK_RE.match(after_link)
        old_end = match.end() + (old_context.end() if old_context else 0)
        replacement = original + "<br>" + context_html
        if normalized_segment != segment or replacement != rendered[match.start() : old_end]:
            updated += 1
        pieces.extend((normalized_segment, replacement))
        cursor = old_end

    pieces.append(rendered[cursor:])
    skipped += max(0, len(matches) - _MAX_PDF_CONTEXT_LINKS_PER_FIELD)
    return "".join(pieces), updated, skipped


def _card_hover_excerpt_candidates(
    html_before_link: object,
    *,
    max_chars: int = _MAX_CARD_HOVER_EXCERPT_CHARS,
) -> list[str]:
    """Return bounded visible card text near a PDF citation."""
    bounded = str(html_before_link or "")[-_MAX_CARD_HOVER_SOURCE_HTML_CHARS:]
    parser = _VisibleCardTextParser()
    try:
        parser.feed(bounded)
        parser.close()
    except Exception:
        return []
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return []

    candidates: list[str] = []

    def _append(value: str) -> None:
        candidate = value[-max_chars:].strip()
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    # Prefer all nearby text first so a normal one-field extraction highlights
    # the complete selection. Then progressively narrow to the final rendered
    # lines; this handles templates and cards containing several citations.
    _append(" ".join(lines))
    for line_count in range(min(6, len(lines)), 0, -1):
        _append(" ".join(lines[-line_count:]))
    return candidates


def rebuild_pdf_reference_card_contexts(
    html: object,
    page_text_loader,
    *,
    context_rows: int = _PDF_HOVER_CONTEXT_ROWS,
) -> tuple[str, int, int]:
    """Insert or replace syncable context blocks for PDF citations in one field."""
    rendered = str(html or "")
    if (
        "incremento_open_pdf_ref:" not in rendered
        or len(rendered) > _MAX_PDF_CONTEXT_FIELD_HTML_CHARS
        or not callable(page_text_loader)
    ):
        return rendered, 0, 0

    cache: dict[tuple[int, int], str] = {}
    pieces: list[str] = []
    cursor = 0
    updated = 0
    skipped = 0
    matches = list(_PDF_REFERENCE_LINK_RE.finditer(rendered))
    for match in matches[:_MAX_PDF_CONTEXT_LINKS_PER_FIELD]:
        if match.start() < cursor:
            continue
        pieces.append(rendered[cursor : match.start()])
        original = match.group(0)
        command = reader_anchor_command_from_html(original)
        prefix = "incremento_open_pdf_ref:"
        if command is None or not command.startswith(prefix):
            pieces.append(original)
            cursor = match.end()
            skipped += 1
            continue
        try:
            payload = json.loads(command[len(prefix) :])
            card_id = int(payload["card_id"])
            page = int(payload["page"])
        except (KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
            pieces.append(original)
            cursor = match.end()
            skipped += 1
            continue

        key = (card_id, page)
        if key not in cache:
            try:
                cache[key] = str(page_text_loader(card_id, page) or "")
            except Exception:
                cache[key] = ""
        page_text = cache[key]
        excerpt_candidates = [str(payload.get("excerpt") or "").strip()]
        if not excerpt_candidates[0]:
            excerpt_candidates = _card_hover_excerpt_candidates(rendered[: match.start()])
        context_html = ""
        for excerpt in excerpt_candidates:
            context_html = pdf_context_card_html(
                page_text,
                excerpt=excerpt,
                scroll_ratio=payload.get("scroll_ratio"),
                context_rows=context_rows,
            )
            if context_html:
                break
        if not context_html:
            pieces.append(original)
            cursor = match.end()
            skipped += 1
            continue

        after_link = rendered[match.end() :]
        old_context = _PDF_CARD_TEXT_PREVIEW_AFTER_LINK_RE.match(after_link)
        if old_context is None:
            old_context = _PDF_CARD_CONTEXT_AFTER_LINK_RE.match(after_link)
        old_end = match.end() + (old_context.end() if old_context else 0)
        replacement = original + "<br>" + context_html
        if replacement != rendered[match.start() : old_end]:
            updated += 1
        cursor = old_end
        pieces.append(replacement)

    pieces.append(rendered[cursor:])
    skipped += max(0, len(matches) - _MAX_PDF_CONTEXT_LINKS_PER_FIELD)
    return "".join(pieces), updated, skipped


def decorate_pdf_reference_link_previews(
    html: object,
    page_text_loader,
    *,
    context_rows: int = _PDF_HOVER_CONTEXT_ROWS,
) -> str:
    """Add reviewer-only hover previews to valid indexed PDF citations."""
    rendered = str(html or "")
    if (
        "incremento_open_pdf_ref:" not in rendered
        or 'data-incremento-pdf-snapshot="1"' in rendered
        or "incremento-pdf-hover-preview-style" in rendered
        or not callable(page_text_loader)
    ):
        return rendered

    cache: dict[tuple[int, int], str] = {}
    decorated_count = 0

    def _decorate(match: re.Match[str]) -> str:
        nonlocal decorated_count
        original = match.group(0)
        if decorated_count >= _MAX_PDF_HOVER_LINKS:
            return original
        command = reader_anchor_command_from_html(original)
        prefix = "incremento_open_pdf_ref:"
        if command is None or not command.startswith(prefix):
            return original
        try:
            payload = json.loads(command[len(prefix) :])
            card_id = int(payload["card_id"])
            page = int(payload["page"])
        except (KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
            return original
        key = (card_id, page)
        if key not in cache:
            try:
                cache[key] = str(page_text_loader(card_id, page) or "")
            except Exception:
                cache[key] = ""
        page_text = cache[key]
        preview = pdf_hover_context_html(
            page_text,
            excerpt=payload.get("excerpt", ""),
            scroll_ratio=payload.get("scroll_ratio"),
            context_rows=context_rows,
        )
        if not preview:
            for candidate in _card_hover_excerpt_candidates(rendered[: match.start()]):
                preview = pdf_hover_context_html(
                    page_text,
                    excerpt=candidate,
                    context_rows=context_rows,
                )
                if preview:
                    break
        if not preview:
            return original
        decorated_count += 1
        return (
            '<span class="incremento-pdf-hover-link" '
            f'onmouseenter="{_PDF_HOVER_CENTER_HANDLER}" '
            f'onfocusin="{_PDF_HOVER_CENTER_HANDLER}">'
            f"{original}"
            '<span class="incremento-pdf-hover-preview" role="tooltip">'
            f"{preview}"
            "</span></span>"
        )

    decorated = _PDF_REFERENCE_LINK_RE.sub(_decorate, rendered)
    if decorated_count <= 0:
        return rendered
    return decorated + _PDF_HOVER_STYLE


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
    try:
        from .file_shell import open_companion_url
    except ImportError:
        from file_shell import open_companion_url
    return open_companion_url(url)


def open_external_reader_link(raw_url: object) -> bool:
    """Open an explicit HTTP(S) reader link in the selected Companion browser."""
    normalized = normalize_external_reader_url(raw_url)
    if normalized is None:
        return False
    try:
        return _open_normalized_external_url(normalized)
    except Exception:
        return False


def normalize_reader_anchor_scroll_ratio(raw_ratio: object) -> float | None:
    """Return a finite reader position bounded to the persisted 0..1 range."""
    if raw_ratio is None or isinstance(raw_ratio, bool):
        return None
    try:
        ratio = float(raw_ratio)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(ratio):
        return None
    return max(0.0, min(ratio, 1.0))


def set_reader_anchor_clipboard(
    html: object,
    plain_text: object,
    *,
    clipboard=None,
    mime_data_factory=None,
) -> bool:
    """Write a card-ready rich anchor plus a readable plain-text fallback."""
    rich_link = _canonical_reader_anchor_html(html)
    fallback = str(plain_text or "").strip()
    if (
        not rich_link
        or not fallback
        or len(fallback) > _MAX_READER_ANCHOR_TEXT_CHARS
        or "\x00" in rich_link
        or "\x00" in fallback
    ):
        return False
    try:
        if clipboard is None:
            from aqt.qt import QApplication

            app = QApplication.instance()
            if app is None:
                return False
            clipboard = app.clipboard()
        if mime_data_factory is None:
            from PyQt6.QtCore import QMimeData

            mime_data_factory = QMimeData
        mime_data = mime_data_factory()
        mime_data.setHtml(rich_link)
        mime_data.setText(fallback)
        marker = json.dumps(
            {"version": _READER_ANCHOR_MIME_VERSION, "html": rich_link},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        mime_data.setData(READER_ANCHOR_MIME_TYPE, marker)
        clipboard.setMimeData(mime_data)
        return True
    except Exception:
        return False


def reader_anchor_html_from_mime(mime_data) -> str | None:
    """Return a validated Incremento anchor from its private clipboard marker."""
    try:
        if not mime_data.hasFormat(READER_ANCHOR_MIME_TYPE):
            return None
        raw = bytes(mime_data.data(READER_ANCHOR_MIME_TYPE))
        if not raw or len(raw) > _MAX_READER_ANCHOR_MIME_BYTES:
            return None
        payload = json.loads(raw.decode("utf-8"))
    except (AttributeError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or set(payload) != {"version", "html"}
        or payload.get("version") != _READER_ANCHOR_MIME_VERSION
        or not isinstance(payload.get("html"), str)
    ):
        return None
    return _canonical_reader_anchor_html(payload["html"])


def _new_mime_data():
    from PyQt6.QtCore import QMimeData

    return QMimeData()


def _schedule_reader_anchor_paste(callback) -> None:
    from aqt.qt import QTimer

    QTimer.singleShot(0, callback)


def force_reader_anchor_rich_paste(
    mime_data,
    editor_web_view,
    internal: bool,
    extended: bool,
    drop_event: bool,
):
    """Keep Incremento reader anchors clickable under Anki's plain-paste mode."""
    if internal or drop_event:
        return mime_data
    rich_link = reader_anchor_html_from_mime(mime_data)
    if rich_link is None:
        return mime_data
    try:
        editor = editor_web_view.editor
        replacement = _new_mime_data()

        def _paste() -> None:
            try:
                # Anki's external HTML sanitizer preserves only ``href`` on an
                # anchor and would remove Incremento's validated ``onclick``.
                # Treat this narrow, fully rebuilt private-MIME payload like an
                # internal field paste so the command remains clickable.
                editor.doPaste(rich_link, True, True)
            except Exception:
                return

        _schedule_reader_anchor_paste(_paste)
        return replacement
    except Exception:
        return mime_data


def show_reader_anchor_context_menu(
    view,
    position,
    *,
    resolver_script: str,
    on_copy,
    run_javascript=None,
    action_label: str = "Copy Link to This Place",
    populate_menu=None,
) -> bool:
    """Append an anchor-copy action to WebEngine's standard context menu."""
    try:
        menu = view.createStandardContextMenu()
        global_position = view.mapToGlobal(position)
    except Exception:
        return False

    try:
        from .selection_search import add_selection_search_action
    except ImportError:
        from frontend.selection_search import add_selection_search_action
    add_selection_search_action(view, menu)

    try:
        view._incremento_reader_anchor_context_menu = menu
    except Exception:
        pass

    finished = False

    def _show_menu(payload=None) -> None:
        nonlocal finished
        if finished:
            return
        finished = True
        if isinstance(payload, dict):
            try:
                if menu.actions():
                    menu.addSeparator()
                action = menu.addAction(str(action_label))
                captured_payload = dict(payload)

                def _copy(_checked=False) -> None:
                    try:
                        on_copy(captured_payload)
                    except Exception:
                        return

                action.triggered.connect(_copy)
            except Exception:
                pass
        if populate_menu is not None:
            try:
                populate_menu(menu, payload)
            except Exception:
                pass
        try:
            menu.exec(global_position)
        finally:
            try:
                if view._incremento_reader_anchor_context_menu is menu:
                    del view._incremento_reader_anchor_context_menu
            except Exception:
                pass

    try:
        runner = run_javascript or view.page().runJavaScript
        runner(str(resolver_script), _show_menu)
        return True
    except Exception:
        _show_menu(None)
        return True
