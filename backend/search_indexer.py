"""Background-safe document indexing with persistent retry state."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

try:
    from .db import get_connection, replace_pdf_text_index
    from .pdf_manager import extract_pdf_pages_text
except ImportError:
    from db import get_connection, replace_pdf_text_index  # type: ignore
    from pdf_manager import extract_pdf_pages_text  # type: ignore


_ERROR_RETRY_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class IndexResult:
    total: int
    indexed: int
    skipped: int
    failed: int
    cancelled: bool


def _signature(path: str) -> tuple[int, int]:
    stat = Path(path).stat()
    return int(stat.st_mtime_ns), int(stat.st_size)


def _state_is_current(row, *, mtime_ns: int, size_bytes: int, now: int) -> bool:
    if row is None:
        return False
    status, saved_mtime, saved_size, indexed_at = row
    if int(saved_mtime or 0) != mtime_ns or int(saved_size or 0) != size_bytes:
        return False
    if str(status or "") in {"ready", "empty"}:
        return True
    return (
        str(status or "") == "error"
        and now - int(indexed_at or 0) < _ERROR_RETRY_SECONDS
    )


def index_pdf_documents(
    addon_dir: str,
    profile: str,
    documents: Iterable[tuple[int, str]],
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
    extractor: Callable[..., list[str]] | None = None,
    force: bool = False,
) -> IndexResult:
    """Index PDF documents off the UI thread, checking cancellation per file."""
    work = [(int(card_id), os.fspath(path)) for card_id, path in documents]
    total = len(work)
    indexed = skipped = failed = 0
    is_cancelled = cancelled or (lambda: False)
    extract = extractor or extract_pdf_pages_text
    conn = get_connection(addon_dir, profile)

    for position, (card_id, path) in enumerate(work, start=1):
        if is_cancelled():
            return IndexResult(total, indexed, skipped, failed, True)
        now = int(time.time())
        mtime_ns = 0
        size_bytes = 0
        try:
            mtime_ns, size_bytes = _signature(path)
            row = conn.execute(
                "SELECT status, source_mtime_ns, source_size, indexed_at "
                "FROM document_index_state WHERE kind='pdf' AND card_id=?",
                (card_id,),
            ).fetchone()
            if not force and _state_is_current(
                row,
                mtime_ns=mtime_ns,
                size_bytes=size_bytes,
                now=now,
            ):
                skipped += 1
            else:
                # A legacy text row without a source signature cannot prove
                # that it still describes the current file. Re-extract it once
                # in the background; new imports record state immediately.
                try:
                    pages = extract(path, allow_qt=False)
                except TypeError:
                    pages = extract(path)
                replace_pdf_text_index(addon_dir, profile, card_id, pages)
                status = (
                    "ready"
                    if any(str(page or "").strip() for page in pages)
                    else "empty"
                )
                indexed += 1
                conn.execute(
                    "INSERT INTO document_index_state "
                    "(kind, card_id, source_mtime_ns, source_size, status, indexed_at) "
                    "VALUES ('pdf', ?, ?, ?, ?, ?) "
                    "ON CONFLICT(kind, card_id) DO UPDATE SET "
                    "source_mtime_ns=excluded.source_mtime_ns, "
                    "source_size=excluded.source_size, status=excluded.status, "
                    "indexed_at=excluded.indexed_at",
                    (card_id, mtime_ns, size_bytes, status, now),
                )
                conn.commit()
        except Exception:
            failed += 1
            try:
                conn.execute(
                    "INSERT INTO document_index_state "
                    "(kind, card_id, source_mtime_ns, source_size, status, indexed_at) "
                    "VALUES ('pdf', ?, ?, ?, 'error', ?) "
                    "ON CONFLICT(kind, card_id) DO UPDATE SET "
                    "source_mtime_ns=excluded.source_mtime_ns, "
                    "source_size=excluded.source_size, status='error', "
                    "indexed_at=excluded.indexed_at",
                    (card_id, mtime_ns, size_bytes, now),
                )
                conn.commit()
            except Exception:
                pass
        if progress is not None:
            progress(position, total)

    return IndexResult(total, indexed, skipped, failed, False)
