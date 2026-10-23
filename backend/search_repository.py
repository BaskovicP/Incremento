"""Bounded read model for the Search ALL frontend."""

from __future__ import annotations

try:
    from .db import get_connection, search_text_match_score, split_search_terms
except ImportError:
    from db import get_connection, search_text_match_score, split_search_terms  # type: ignore


_SEARCH_SPECS = {
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
    if kind in ("pdf_highlights", "epub_highlights"):
        # Use the same text for candidate selection, ranking, snippets and hover
        # previews so a match found only in a personal note remains visible.
        text_column = (
            "coalesce(text, '') || CASE WHEN coalesce(note, '') != '' "
            "THEN char(10) || char(10) || note ELSE '' END"
        )
        columns = (*columns[:2], text_column)
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
