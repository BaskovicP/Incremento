"""PDF search-cache lifecycle. Never deletes files, notes, or reader annotations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
import time

try:
    from .db import get_connection
    from .pdf_manager import pdf_storage_abspath
    from .search_repository import SearchCollection
except ImportError:
    from db import get_connection
    from pdf_manager import pdf_storage_abspath
    from search_repository import SearchCollection


# Only generations, never document text. In-flight extractors must not publish
# an old discovery after a confirmed deletion, including a delete/undo/redo race.
_lock = RLock()
_generation = 0
_versions: dict[tuple[str, str, int], int] = {}


def _key(addon_dir, profile, cid):
    return (str(Path(addon_dir).resolve()), str(profile), int(cid))


@dataclass(frozen=True)
class PdfIndexDocument:
    card_id: int
    path: str
    generation: int


@contextmanager
def publishing_pdf_index(addon_dir, profile, document):
    """Hold the deletion guard through the index/state transaction."""
    with _lock:
        yield (
            not isinstance(document, PdfIndexDocument)
            or _versions.get(_key(addon_dir, profile, document.card_id), 0) == document.generation
        )


def invalidate_pdf_index_jobs(addon_dir, profile):
    """Retire a closing profile's discoveries without touching its stored data."""
    global _generation
    with _lock:
        _generation += 1
        prefix = _key(addon_dir, profile, 0)[:2]
        for key in tuple(_versions):
            if key[:2] == prefix:
                _versions[key] = _generation


def _document(addon_dir, profile, cid, note):
    key = _key(addon_dir, profile, cid)
    with _lock:
        version = _versions.setdefault(key, _generation)
        return PdfIndexDocument(
            int(cid),
            pdf_storage_abspath(
                note.pdf_filename,
                addon_dir=addon_dir,
                profile=profile,
            ),
            version,
        )


def pdf_cards_for_notes(col, note_ids):
    """Capture exact deletion candidates using the hook-provided collection."""
    metadata = SearchCollection(col)
    ids = tuple(dict.fromkeys(int(nid) for nid in note_ids))
    metadata.load_notes(ids)
    pdf_notes = [
        nid for nid in ids if metadata.notes.get(nid) is not None and metadata.notes[nid].pdf_filename is not None
    ]
    cards = set()
    for start in range(0, len(pdf_notes), 900):
        batch = pdf_notes[start : start + 900]
        cards.update(
            int(cid)
            for (cid,) in col.db.all(
                f"SELECT id FROM cards WHERE nid IN ({','.join('?' for _ in batch)})",
                *batch,
            )
        )
    return cards


def prepare_pdf_index_documents(addon_dir, profile, col, card_ids, *, cancel=None):
    metadata = SearchCollection(col, cancel=cancel)
    ids = tuple(dict.fromkeys(int(cid) for cid in card_ids))
    metadata.load_document_titles(ids)
    documents = []
    for cid in ids:
        metadata.check_cancelled()
        if metadata.pdf_card_available(cid, addon_dir, profile):
            documents.append(_document(addon_dir, profile, cid, metadata.notes[metadata.cards[cid]]))
    return documents


def reconcile_pdf_search_indexes(addon_dir, profile, col, *, card_ids=None, cancel=None):
    """Purge confirmed missing Anki owners and return restored PDFs to reindex.

    A missing or moved file alone is never a deletion. A small 'deleted' state
    marker survives pruning so Undo can rebuild text even when other PDFs match.
    Full cache discovery is used only by explicit Search ALL/maintenance, never
    from profile-open hooks. Ordinary deletion/Undo checks use captured IDs.
    """
    global _generation
    metadata = SearchCollection(col, cancel=cancel)
    metadata.check_cancelled()
    conn = get_connection(addon_dir, profile)
    if card_ids is None:
        card_ids = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT card_id FROM pdf_text_index UNION "
                "SELECT card_id FROM document_index_state WHERE kind='pdf'"
            )
        ]
    ids = tuple(dict.fromkeys(int(cid) for cid in card_ids))
    # Read errors propagate: failed reads are never evidence of deletion.
    # Healthy owners need only an ID check, not their note bodies or file stats.
    metadata.load_cards(ids)
    states = {}
    indexed = set()
    for start in range(0, len(ids), 900):
        metadata.check_cancelled()
        batch = ids[start : start + 900]
        placeholders = ",".join("?" for _ in batch)
        states.update(
            conn.execute(
                f"SELECT card_id,status FROM document_index_state WHERE kind='pdf' AND card_id IN ({placeholders})",
                batch,
            )
        )
        indexed.update(
            row[0]
            for row in conn.execute(
                f"SELECT DISTINCT card_id FROM pdf_text_index WHERE card_id IN ({placeholders})",
                batch,
            )
        )
    deleted = [
        cid for cid in ids if metadata.cards.get(cid) is None and (states.get(cid) != "deleted" or cid in indexed)
    ]
    # Commit bounded batches; repeated notifications do not rewrite tombstones.
    for start in range(0, len(deleted), 200):
        metadata.check_cancelled()
        batch = deleted[start : start + 200]
        with _lock:
            for cid in batch:
                _generation += 1
                _versions[_key(addon_dir, profile, cid)] = _generation
            with conn:
                conn.executemany("DELETE FROM pdf_text_index WHERE card_id=?", [(cid,) for cid in batch])
                conn.executemany(
                    "INSERT INTO document_index_state(kind,card_id,status,indexed_at) "
                    "VALUES ('pdf',?,'deleted',?) ON CONFLICT(kind,card_id) DO UPDATE SET "
                    "status='deleted',source_mtime_ns=0,source_size=0,indexed_at=excluded.indexed_at",
                    [(cid, int(time.time())) for cid in batch],
                )
    restored_ids = [cid for cid in ids if metadata.cards.get(cid) is not None and states.get(cid) == "deleted"]
    return prepare_pdf_index_documents(addon_dir, profile, col, restored_ids, cancel=cancel)
