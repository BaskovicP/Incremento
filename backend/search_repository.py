"""Bounded read model for the Search ALL frontend."""

from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import dataclass
import os

try:
    from .db import get_connection, search_text_match_score, split_search_terms
except ImportError:
    from db import get_connection, search_text_match_score, split_search_terms  # type: ignore


_SEARCH_SPECS = {
    "pdf_annotations": ("pdf_highlights", ("card_id", "page", "note"), "note"),
    "epub_annotations": ("epub_highlights", ("card_id", "section_index", "note"), "note"),
    "pdf_highlights": ("pdf_highlights", ("card_id", "page", "text"), "text"),
    "pdf_sources": (
        "pdf_card_sources",
        ("pdf_card_id", "page", "excerpt", "note_id"),
        "excerpt",
    ),
    "epub_highlights": (
        "epub_highlights",
        ("card_id", "section_index", "text"),
        "text",
    ),
    "epub_sources": (
        "epub_card_sources",
        ("epub_card_id", "section_index", "excerpt", "note_id"),
        "excerpt",
    ),
}


@dataclass(frozen=True)
class SearchNote:
    fields: tuple[str, ...]
    model_name: str
    pdf_filename: str | None = None


class SearchCollection:
    """Bounded metadata batches belonging to one search and operation collection."""

    def __init__(self, col, *, cancel=None):
        self.col = col
        self.cancel = cancel
        self.cards: dict[int, int | None] = {}
        self.notes: dict[int, SearchNote | None] = {}
        self._model_names: dict[int, str] = {}
        self._pdf_fields: dict[int, int | None] = {}
        self._pdf_files: dict[tuple[str, str, str], bool] = {}

    def check_cancelled(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise CancelledError()

    def _batches(self, ids, cache):
        missing = list(dict.fromkeys(int(value) for value in ids if int(value) not in cache))
        for start in range(0, len(missing), 900):
            self.check_cancelled()
            yield missing[start:start + 900]
        self.check_cancelled()

    def load_cards(self, ids) -> None:
        for batch in self._batches(ids, self.cards):
            self.cards.update((cid, None) for cid in batch)
            placeholders = ",".join("?" for _ in batch)
            self.cards.update(
                (int(cid), int(nid)) for cid, nid in self.col.db.all(
                    f"SELECT id, nid FROM cards WHERE id IN ({placeholders})", *batch,
                )
            )

    def load_notes(self, ids) -> None:
        for batch in self._batches(ids, self.notes):
            self.notes.update((nid, None) for nid in batch)
            placeholders = ",".join("?" for _ in batch)
            for nid, mid, fields in self.col.db.all(
                f"SELECT id, mid, flds FROM notes WHERE id IN ({placeholders})", *batch,
            ):
                self.check_cancelled()
                if mid not in self._model_names:
                    model = self.col.models.get(mid) or {}
                    self._model_names[mid] = str(model.get("name") or "")
                    self._pdf_fields[mid] = next(
                        (int(field.get("ord", i)) for i, field in enumerate(model.get("flds", ()))
                         if field.get("name") == "PDF_Filename"), None,
                    )
                values = tuple(str(fields or "").split("\x1f"))
                ordinal = self._pdf_fields[mid]
                filename = (values[ordinal].strip()
                            if ordinal is not None and 0 <= ordinal < len(values) else "")
                if not filename and self._model_names[mid] != "Incremento PDF":
                    filename = None
                self.notes[int(nid)] = SearchNote(
                    values, self._model_names[mid], filename,
                )

    def pdf_available(self, note, addon_dir: str, profile: str) -> bool:
        if note is None or note.pdf_filename is None:
            return False
        key = (addon_dir, profile, note.pdf_filename)
        if key not in self._pdf_files:
            try:
                from .pdf_manager import pdf_storage_abspath
            except ImportError:
                from pdf_manager import pdf_storage_abspath
            try:
                path = pdf_storage_abspath(note.pdf_filename, profile=profile, addon_dir=addon_dir)
                self._pdf_files[key] = bool(path and os.path.isfile(path))
            except (OSError, ValueError, RuntimeError):
                self._pdf_files[key] = False
        return self._pdf_files[key]

    def pdf_card_available(self, cid: int, addon_dir: str, profile: str) -> bool:
        return self.pdf_available(self.notes.get(self.cards.get(cid)), addon_dir, profile)

    def load_document_titles(self, ids) -> None:
        ids = tuple(ids)
        self.load_cards(ids)
        self.load_notes(self.cards[cid] for cid in ids if self.cards.get(cid) is not None)

    def document_title(self, cid: int) -> str | None:
        note = self.notes.get(self.cards.get(cid))
        return note.fields[0] if note is not None and note.fields else None


def search_excerpt_rows(
    addon_dir: str,
    profile: str,
    kind: str,
    query: str,
    *,
    limit: int = 120,
) -> list[tuple]:
    """Return a ranked, bounded set of highlight/source rows."""
    spec = _SEARCH_SPECS.get(str(kind or ""))
    terms = split_search_terms(query)
    if spec is None or not terms:
        return []
    table, columns, text_column = spec
    candidate_limit = max(500, max(1, int(limit)) * 25)
    conn = get_connection(addon_dir, profile)
    rows = conn.execute(
        f"SELECT {', '.join(columns)} FROM {table} "
        f"WHERE lower({text_column}) LIKE lower(?) "
        f"ORDER BY {columns[0]}, {columns[1]} LIMIT ?",
        (f"%{terms[0]}%", candidate_limit),
    ).fetchall()
    ranked = []
    for row in rows:
        normalized = tuple(row)
        score = search_text_match_score(str(normalized[2] or ""), query)
        if score is not None:
            ranked.append((score, normalized))
    ranked.sort(key=lambda item: (item[0], item[1][0], item[1][1]))
    return [row for _, row in ranked[: max(1, int(limit))]]


def pdf_candidate_card_ids(addon_dir: str, profile: str) -> set[int]:
    conn = get_connection(addon_dir, profile)
    card_ids: set[int] = set()
    for table in ("pdf_highlights", "pdf_progress", "pdf_text_index"):
        rows = conn.execute(f"SELECT DISTINCT card_id FROM {table}").fetchall()
        card_ids.update(int(row[0]) for row in rows)
    return card_ids


def pdf_page_text(
    addon_dir: str,
    profile: str,
    card_id: int,
    page: int,
    *,
    max_chars: int | None = None,
) -> str:
    conn = get_connection(addon_dir, profile)
    if max_chars is None:
        row = conn.execute(
            "SELECT text FROM pdf_text_index WHERE card_id=? AND page=?",
            (int(card_id), int(page)),
        ).fetchone()
    else:
        bounded_chars = max(1, min(int(max_chars), 1_000_000))
        row = conn.execute(
            "SELECT substr(text, 1, ?) FROM pdf_text_index WHERE card_id=? AND page=?",
            (bounded_chars, int(card_id), int(page)),
        ).fetchone()
    return str((row[0] or "") if row else "")


def epub_section_text(
    addon_dir: str,
    profile: str,
    card_id: int,
    section_index: int,
) -> tuple[str, str]:
    row = get_connection(addon_dir, profile).execute(
        "SELECT title, text FROM epub_text_index "
        "WHERE card_id=? AND section_index=?",
        (int(card_id), int(section_index)),
    ).fetchone()
    if not row:
        return "", ""
    return str(row[0] or ""), str(row[1] or "")
