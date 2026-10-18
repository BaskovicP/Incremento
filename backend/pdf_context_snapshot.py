"""Render bounded, content-addressed PDF passage previews for Anki cards."""

from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
from hashlib import sha256
import math
from pathlib import Path
import re
import tempfile
import unicodedata


MAX_PDF_BYTES = 512 * 1024 * 1024
MAX_PAGE_NUMBER = 1_000_000
MAX_EXCERPT_CHARS = 12_000
MAX_CONTEXT_ROWS = 20
MAX_WORDS = 100_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_RENDER_PIXELS = 7_000_000


def snapshot_media_filename(image_bytes: bytes) -> str:
    """Return a deterministic Anki media name for one rendered PNG."""
    digest = sha256(bytes(image_bytes or b"")).hexdigest()[:24]
    return f"incremento-pdf-context-{digest}.png"


def add_snapshot_to_anki_media(collection, image_bytes: bytes) -> str:
    """Store one rendered preview through Anki's media manager."""
    image = bytes(image_bytes or b"")
    if not image or len(image) > MAX_IMAGE_BYTES:
        return ""
    filename = snapshot_media_filename(image)
    try:
        with tempfile.TemporaryDirectory(prefix="incremento-pdf-context-") as directory:
            path = Path(directory) / filename
            path.write_bytes(image)
            return str(collection.media.add_file(str(path)) or "").strip()
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return ""


def _token(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _excerpt_tokens(value: object) -> list[str]:
    return [
        token
        for raw in re.findall(r"\w+", str(value or "")[:MAX_EXCERPT_CHARS], re.UNICODE)
        if (token := _token(raw))
    ]


def _word_token_entries(words: list[tuple]) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    for word_index, word in enumerate(words):
        if len(word) < 5:
            continue
        for raw in re.findall(r"\w+", str(word[4] or ""), re.UNICODE):
            token = _token(raw)
            if token:
                entries.append((token, word_index))
    return entries


def _matched_word_indexes(words: list[tuple], excerpt: object) -> list[int]:
    target = _excerpt_tokens(excerpt)
    entries = _word_token_entries(words)
    if not target or not entries:
        return []
    source = [token for token, _word_index in entries]
    count = len(target)
    for start in range(max(0, len(source) - count + 1)):
        if source[start : start + count] == target:
            return list(dict.fromkeys(index for _token_value, index in entries[start : start + count]))

    if count < 6:
        return []
    matcher = SequenceMatcher(None, target, source, autojunk=False)
    anchor = matcher.find_longest_match(0, count, 0, len(source))
    if anchor.size < max(4, min(12, math.ceil(count * 0.25))):
        return []
    estimated_start = anchor.b - anchor.a
    radius = min(20, max(4, count // 5))
    length_slack = min(12, max(3, count // 8))
    best: tuple[float, int, int] | None = None
    for start in range(max(0, estimated_start - radius), min(len(source), estimated_start + radius + 1)):
        for length in range(max(1, count - length_slack), count + length_slack + 1):
            end = min(len(source), start + length)
            if end <= start:
                continue
            score = SequenceMatcher(None, target, source[start:end], autojunk=False).ratio()
            candidate = (score, start, end)
            if best is None or candidate > best:
                best = candidate
    if best is None or best[0] < 0.72:
        return []
    return list(dict.fromkeys(index for _token_value, index in entries[best[1] : best[2]]))


def _safe_rect(fitz, value: object, page_rect):
    try:
        if isinstance(value, dict):
            x = float(value["x"])
            y = float(value["y"])
            width = float(value["w"])
            height = float(value["h"])
            raw = fitz.Rect(x, y, x + width, y + height)
        else:
            raw = fitz.Rect(value)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    coordinates = (raw.x0, raw.y0, raw.x1, raw.y1)
    if not all(math.isfinite(number) for number in coordinates):
        return None
    clipped = raw & page_rect
    return clipped if clipped.width > 0 and clipped.height > 0 else None


def _union_rect(fitz, rects: list):
    result = fitz.Rect(rects[0])
    for rect in rects[1:]:
        result |= rect
    return result


def render_pdf_context_snapshot(
    pdf_path: str | Path,
    *,
    page_number: int,
    excerpt: object,
    context_rows: int = 5,
    highlight_rects: object = None,
) -> bytes:
    """Render the cited passage plus surrounding PDF lines as a highlighted PNG.

    The page is one-based, matching the citation payload. Missing or unmatched
    passages fail closed and return empty bytes.
    """
    path = Path(pdf_path)
    try:
        page_value = int(page_number)
        row_count = max(0, min(int(context_rows), MAX_CONTEXT_ROWS))
    except (TypeError, ValueError, OverflowError):
        return b""
    if (
        page_value <= 0
        or page_value > MAX_PAGE_NUMBER
        or path.is_symlink()
        or not path.is_file()
        or path.suffix.casefold() != ".pdf"
    ):
        return b""
    try:
        if path.stat().st_size > MAX_PDF_BYTES:
            return b""
        with path.open("rb") as stream:
            if not stream.read(1024).lstrip().startswith(b"%PDF-"):
                return b""
    except OSError:
        return b""

    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # type: ignore[no-redef]
        except ImportError:
            return b""

    try:
        document = fitz.open(str(path))
    except Exception:
        return b""
    try:
        if page_value > document.page_count:
            return b""
        page = document.load_page(page_value - 1)
        raw_words = list(page.get_text("words", sort=True) or [])[:MAX_WORDS]
        words = [word for word in raw_words if len(word) >= 8 and str(word[4] or "").strip()]
        if not words:
            return b""

        page_rect = fitz.Rect(page.rect)
        saved_rects = [
            rect
            for value in (highlight_rects if isinstance(highlight_rects, list) else [])
            if (rect := _safe_rect(fitz, value, page_rect)) is not None
        ]
        matched_indexes = _matched_word_indexes(words, excerpt)
        matched_rects = [fitz.Rect(words[index][:4]) for index in matched_indexes]
        if not saved_rects and not matched_rects:
            return b""

        lines: OrderedDict[tuple[int, int], list] = OrderedDict()
        for word in words:
            key = (int(word[5]), int(word[6]))
            lines.setdefault(key, []).append(fitz.Rect(word[:4]))
        line_rects = [_union_rect(fitz, rects) for rects in lines.values()]
        def _target_lines(rects: list) -> list[int]:
            return [
                index
                for index, line_rect in enumerate(line_rects)
                if any((line_rect & target).get_area() > 0 for target in rects)
            ]

        saved_line_indexes = _target_lines(saved_rects)
        matched_line_indexes = _target_lines(matched_rects)
        if not matched_line_indexes and matched_indexes:
            matched_keys = {(int(words[index][5]), int(words[index][6])) for index in matched_indexes}
            ordered_keys = list(lines)
            matched_line_indexes = [index for index, key in enumerate(ordered_keys) if key in matched_keys]
        saved_span = max(saved_line_indexes) - min(saved_line_indexes) if saved_line_indexes else -1
        matched_span = max(matched_line_indexes) - min(matched_line_indexes) if matched_line_indexes else -1
        if matched_span > saved_span:
            target_rects = matched_rects
            target_line_indexes = matched_line_indexes
        else:
            target_rects = saved_rects
            target_line_indexes = saved_line_indexes
        if not target_line_indexes:
            return b""

        first_line = max(0, min(target_line_indexes) - row_count)
        last_line = min(len(line_rects) - 1, max(target_line_indexes) + row_count)
        visible_rects = line_rects[first_line : last_line + 1]
        clip = _union_rect(fitz, visible_rects)
        clip = fitz.Rect(
            max(page_rect.x0, clip.x0 - 18),
            max(page_rect.y0, clip.y0 - 12),
            min(page_rect.x1, clip.x1 + 18),
            min(page_rect.y1, clip.y1 + 12),
        )
        if clip.width <= 0 or clip.height <= 0:
            return b""

        for rect in target_rects:
            annotation = page.add_highlight_annot(rect)
            annotation.set_colors(stroke=(1.0, 0.78, 0.0))
            annotation.set_opacity(0.45)
            annotation.update()

        scale = min(2.0, 1400.0 / max(1.0, clip.width))
        scale = max(1.0, scale)
        if clip.width * clip.height * scale * scale > MAX_RENDER_PIXELS:
            scale = math.sqrt(MAX_RENDER_PIXELS / (clip.width * clip.height))
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(scale, scale),
            clip=clip,
            alpha=False,
            annots=True,
        )
        image = bytes(pixmap.tobytes("png") or b"")
        return image if 0 < len(image) <= MAX_IMAGE_BYTES else b""
    except Exception:
        return b""
    finally:
        document.close()
