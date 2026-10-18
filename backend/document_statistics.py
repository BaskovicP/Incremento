"""Read-only, profile-scoped document completion for the statistics library.

Daily page observations measure activity, not completion. PDFs use the reader's
read marker; EPUBs use stable reference pages derived from cached section text.
No extraction, indexing, note changes or new progress ledger happens here.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from bs4 import BeautifulSoup

try:
    from .db import get_connection
    from . import paths
except ImportError:
    from db import get_connection
    import paths


MAX_METADATA_BYTES = 32 * 1024 * 1024
EPUB_CHARS_PER_PAGE = 1500


def _integer(value, default=0):
    try:
        return max(0, int(value))
    except (ValueError, TypeError, OverflowError):
        return default


def _completion(total, read, unit):
    total = _integer(total) or None
    read = _integer(read)
    if total is not None:
        read = min(read, total)
    return {"read": read, "left": total - read if total else None, "total": total,
            "percent": 100 * read / total if total else None, "unit": unit}


def pdf_completion(total_pages, progress):
    return _completion(total_pages, (progress or {}).get("read_page"), "pages")


def _epub_lengths(metadata):
    sections = (metadata or {}).get("sections")
    if not isinstance(sections, list) or not sections or len(sections) > 5000:
        return ()
    if any(not isinstance(section, dict) or not isinstance(section.get("text"), str) for section in sections):
        return ()
    return tuple(len(section["text"]) for section in sections)


def epub_completion(metadata, progress):
    """Reference pages stay stable across font/window changes (1,500 chars/page).

    The legacy section marker is inclusive. Zero without an anchor is ambiguous
    with a freshly opened book, so it must not claim the whole first section read.
    An exact text anchor counts only reference pages before that saved location.
    """
    lengths = metadata if isinstance(metadata, tuple) else _epub_lengths(metadata)
    if not lengths:
        return _completion(None, 0, "estimated_pages")
    pages = [max(1, math.ceil(length / EPUB_CHARS_PER_PAGE)) for length in lengths]
    total = sum(pages)
    read = 0
    progress = progress or {}
    index = min(_integer(progress.get("read_section_index")), len(pages) - 1)
    if index > 0:
        read = sum(pages[:index + 1])
    try:
        anchor = json.loads(str(progress.get("read_anchor_json") or "{}"))
        if isinstance(anchor, dict) and "sectionIndex" in anchor and "offset" in anchor:
            index = min(_integer(anchor["sectionIndex"]), len(pages) - 1)
            offset = min(_integer(anchor["offset"]), lengths[index])
            read = sum(pages[:index]) + min(pages[index], offset // EPUB_CHARS_PER_PAGE)
    except (ValueError, TypeError):
        pass
    if _integer(progress.get("is_finished")) == 1:
        read = total
    return _completion(total, read, "estimated_pages")


def _contained_file(root, filename):
    """Resolve legacy managed names without allowing traversal or symlink escape."""
    raw = str(filename or "").strip().replace("\\", "/")
    if not raw or ".." in raw.split("/"):
        return None
    if raw.startswith("user_files/") and f"/{root.name}/" in raw:
        raw = raw.split(f"/{root.name}/", 1)[1]
    elif raw.startswith(root.name + "/"):
        raw = raw[len(root.name) + 1:]
    try:
        root = root.resolve()
        path = (root / raw).resolve()
        path.relative_to(root)
        return path if path.is_file() else None
    except (OSError, ValueError, RuntimeError):
        return None


def _epub_metadata(addon_dir, profile, filename):
    raw = str(filename or "").replace("\\", "/")
    if not raw or ".." in raw.split("/"):
        return None
    root = paths.get_epub_extract_root(addon_dir, profile)
    path = _contained_file(root, Path(raw).name + "/metadata.json")
    if path is None:
        return None
    try:
        if path.stat().st_size > MAX_METADATA_BYTES:
            return None
        with path.open("rb") as stream:
            data = stream.read(MAX_METADATA_BYTES + 1)
        if len(data) > MAX_METADATA_BYTES:
            return None
        metadata = json.loads(data)
        return metadata if isinstance(metadata, dict) else None
    except (OSError, ValueError):
        return None


def _pdf_page_count(path):
    # Metadata only: no rendering or full text extraction. Optional dependency.
    try:
        import pymupdf
        with pymupdf.open(str(path)) as document:
            return document.page_count if not document.needs_pass else None
    except Exception:
        return None


def _progress_rows(connection, table, ids):
    cursor = connection.execute(
        f"SELECT * FROM {table} WHERE card_id IN ({','.join('?' for _ in ids)})", ids,
    )
    columns = [column[0] for column in cursor.description]
    return {int(row[0]): dict(zip(columns, row)) for row in cursor.fetchall()}


def document_progress_from_collection(collection, addon_dir, profile, *, should_cancel=None, pdf_page_counter=None):
    """Load the whole library in bounded batches off the UI thread; None=unknown."""
    if collection is None:
        return None
    cancelled = should_cancel or (lambda: False)
    count_pdf_pages = pdf_page_counter or _pdf_page_count
    try:
        models = {}
        for kind in ("pdf", "epub"):
            model = collection.models.by_name(f"Incremento {kind.upper()}")
            if model:
                fields = {field["name"]: index for index, field in enumerate(model["flds"])}
                if f"{kind.upper()}_Filename" in fields:
                    models[int(model["id"])] = (kind, fields)
        if not models:
            return []
        if cancelled():
            return None
        connection = get_connection(addon_dir, profile)
        last_id = 0
        result = []
        totals = {}
        while not cancelled():
            rows = collection.db.all(
                "SELECT c.id, n.mid, n.flds FROM cards c JOIN notes n ON n.id=c.nid "
                f"WHERE n.mid IN ({','.join('?' for _ in models)}) AND c.id > ? "
                "ORDER BY c.id LIMIT 200", *models, last_id,
            )
            if not rows:
                return result
            ids = [int(row[0]) for row in rows]
            progress = {kind: _progress_rows(connection, kind + "_progress", ids) for kind in ("pdf", "epub")}
            for cid, mid, raw_fields in rows:
                if cancelled():
                    return None
                kind, fields = models[int(mid)]
                values = str(raw_fields).split("\x1f")
                filename_index = fields[f"{kind.upper()}_Filename"]
                filename = values[filename_index] if filename_index < len(values) else ""
                title_index = fields.get("Title", len(values))
                title = values[title_index] if title_index < len(values) else ""
                title = BeautifulSoup(title[:8192], "html.parser").get_text(" ", strip=True)
                title = title or Path(filename).stem[:256]
                saved = progress[kind].get(int(cid))
                key = (kind, filename)
                if key not in totals:
                    if kind == "pdf":
                        path = _contained_file(paths.get_pdf_dir(addon_dir, profile), filename)
                        totals[key] = count_pdf_pages(path) if path else None
                    else:
                        # Keep only lengths in this request's cache, never a whole
                        # library's extracted text in memory at once.
                        totals[key] = _epub_lengths(_epub_metadata(addon_dir, profile, filename))
                completion = pdf_completion(totals[key], saved) if kind == "pdf" else epub_completion(totals[key], saved)
                result.append({"card_id": int(cid), "title": title, "kind": kind, **completion})
            last_id = ids[-1]
        return None
    except Exception:
        return None
