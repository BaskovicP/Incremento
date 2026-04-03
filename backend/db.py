"""
Central SQLite database for all Incremento user data.

One connection is kept open per addon_dir (re-initialised if the path changes).
WAL mode + NORMAL synchronous gives fast writes while staying crash-safe.

Tables
------
pdf_progress    — reading position and zoom per card
pdf_highlights  — highlighted passages per card
epub_progress   — reading section/scroll state per card
epub_highlights — highlighted passages per EPUB section
stats           — daily and lifetime review statistics (JSON blobs per scope)
priorities      — card priority values
pdf_card_sources — notes created while reading a PDF page (for per-page card preview)
epub_card_sources — notes created while reading an EPUB section
web_card_sources — notes created while viewing a web-card URL (for per-URL card preview)
web_progress    — last URL, scroll position, and bookmark state per web card
"""

import atexit
import json
import re
import sqlite3
from pathlib import Path

_connection: sqlite3.Connection | None = None
_initialized_for: str | None = None

DB_NAME = "incremento.db"
_SEARCH_WORD_RE = re.compile(r"\w+", re.UNICODE)


def close_connection() -> None:
    global _connection, _initialized_for
    if _connection is not None:
        try:
            _connection.close()
        except Exception:
            pass
    _connection = None
    _initialized_for = None


# ── Connection ────────────────────────────────────────────────────────────────


def get_connection(addon_dir: str) -> sqlite3.Connection:
    global _connection, _initialized_for
    if _connection is None or _initialized_for != addon_dir:
        close_connection()
        p = Path(addon_dir) / "user_files" / DB_NAME
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _create_tables(conn)
        _connection = conn
        _initialized_for = addon_dir
    return _connection


atexit.register(close_connection)


# ── Schema ────────────────────────────────────────────────────────────────────


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pdf_progress (
            card_id   INTEGER PRIMARY KEY,
            page      INTEGER NOT NULL DEFAULT 1,
            zoom      REAL    NOT NULL DEFAULT 1.0,
            read_page INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pdf_highlights (
            id      TEXT    NOT NULL,
            card_id INTEGER NOT NULL,
            page    INTEGER NOT NULL DEFAULT 1,
            color   TEXT    NOT NULL DEFAULT 'yellow',
            text    TEXT    NOT NULL DEFAULT '',
            rects   TEXT    NOT NULL DEFAULT '[]',
            PRIMARY KEY (id, card_id)
        );

        CREATE TABLE IF NOT EXISTS epub_progress (
            card_id       INTEGER PRIMARY KEY,
            section_index INTEGER NOT NULL DEFAULT 0,
            scroll_ratio  REAL    NOT NULL DEFAULT 0.0,
            is_finished   INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS epub_highlights (
            id            TEXT    NOT NULL,
            card_id       INTEGER NOT NULL,
            section_index INTEGER NOT NULL DEFAULT 0,
            color         TEXT    NOT NULL DEFAULT 'yellow',
            text          TEXT    NOT NULL DEFAULT '',
            start_offset  INTEGER NOT NULL DEFAULT 0,
            end_offset    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (id, card_id)
        );

        CREATE TABLE IF NOT EXISTS stats (
            scope TEXT PRIMARY KEY,
            date  TEXT,
            data  TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS priorities (
            card_id  INTEGER PRIMARY KEY,
            priority REAL    NOT NULL DEFAULT 50.0
        );

        CREATE TABLE IF NOT EXISTS video_progress (
            card_id  INTEGER PRIMARY KEY,
            position REAL    NOT NULL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS web_progress (
            card_id          INTEGER PRIMARY KEY,
            url              TEXT    NOT NULL DEFAULT '',
            scroll_ratio     REAL    NOT NULL DEFAULT 0.0,
            bookmark_url     TEXT    NOT NULL DEFAULT '',
            bookmark_payload TEXT    NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS pdf_card_sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_card_id INTEGER NOT NULL,
            page        INTEGER NOT NULL,
            note_id     INTEGER NOT NULL,
            excerpt     TEXT    NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_pcs_card_page
            ON pdf_card_sources (pdf_card_id, page);

        CREATE TABLE IF NOT EXISTS epub_card_sources (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            epub_card_id  INTEGER NOT NULL,
            section_index INTEGER NOT NULL,
            note_id       INTEGER NOT NULL,
            excerpt       TEXT    NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_ecs_card_section
            ON epub_card_sources (epub_card_id, section_index);

        CREATE TABLE IF NOT EXISTS web_card_sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            web_card_id INTEGER NOT NULL,
            url         TEXT    NOT NULL DEFAULT '',
            note_id     INTEGER NOT NULL,
            excerpt     TEXT    NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_wcs_card_url
            ON web_card_sources (web_card_id, url);

        CREATE TABLE IF NOT EXISTS pdf_text_index (
            card_id INTEGER NOT NULL,
            page    INTEGER NOT NULL,
            text    TEXT    NOT NULL DEFAULT '',
            PRIMARY KEY (card_id, page)
        );
        CREATE INDEX IF NOT EXISTS idx_pti_card_page
            ON pdf_text_index (card_id, page);

        CREATE TABLE IF NOT EXISTS epub_text_index (
            card_id       INTEGER NOT NULL,
            section_index INTEGER NOT NULL,
            title         TEXT    NOT NULL DEFAULT '',
            text          TEXT    NOT NULL DEFAULT '',
            PRIMARY KEY (card_id, section_index)
        );
        CREATE INDEX IF NOT EXISTS idx_eti_card_section
            ON epub_text_index (card_id, section_index);

        CREATE TABLE IF NOT EXISTS topic_schedule (
            card_id  INTEGER PRIMARY KEY,
            a_factor REAL    NOT NULL DEFAULT 3.5,
            interval INTEGER NOT NULL DEFAULT 1
        );
    """)
    # Add read_page to existing pdf_progress tables that predate this column
    try:
        conn.execute(
            "ALTER TABLE pdf_progress ADD COLUMN read_page INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    except Exception:
        pass  # column already exists
    for statement in (
        "ALTER TABLE web_progress ADD COLUMN scroll_ratio REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE web_progress ADD COLUMN bookmark_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE web_progress ADD COLUMN bookmark_payload TEXT NOT NULL DEFAULT ''",
    ):
        try:
            conn.execute(statement)
            conn.commit()
        except Exception:
            pass


# ── Export helpers (called by the export function in __init__.py) ─────────────


def export_priorities_json(addon_dir: str) -> str:
    rows = (
        get_connection(addon_dir)
        .execute("SELECT card_id, priority FROM priorities ORDER BY card_id")
        .fetchall()
    )
    return json.dumps({str(r[0]): r[1] for r in rows}, indent=2)


def export_pdf_progress_json(addon_dir: str) -> str:
    rows = (
        get_connection(addon_dir)
        .execute("SELECT card_id, page, zoom FROM pdf_progress ORDER BY card_id")
        .fetchall()
    )
    return json.dumps({str(r[0]): {"page": r[1], "zoom": r[2]} for r in rows}, indent=2)


def export_highlights_json(addon_dir: str) -> str:
    rows = (
        get_connection(addon_dir)
        .execute(
            "SELECT card_id, id, page, color, text, rects FROM pdf_highlights ORDER BY card_id"
        )
        .fetchall()
    )
    result: dict = {}
    for cid, hl_id, page, color, text, rects in rows:
        key = str(cid)
        result.setdefault(key, []).append(
            {
                "id": hl_id,
                "page": page,
                "color": color,
                "text": text,
                "rects": json.loads(rects),
            }
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


def add_pdf_card_source(
    addon_dir: str, pdf_card_id: int, page: int, note_id: int, excerpt: str = ""
) -> None:
    """Record that note_id was created while reading pdf_card_id at page."""
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO pdf_card_sources (pdf_card_id, page, note_id, excerpt) VALUES (?, ?, ?, ?)",
        (pdf_card_id, page, note_id, excerpt),
    )
    conn.commit()


def get_pdf_card_sources(addon_dir: str, pdf_card_id: int, page: int) -> list:
    """Return list of {note_id, excerpt} for cards created on this PDF page."""
    rows = (
        get_connection(addon_dir)
        .execute(
            "SELECT note_id, excerpt FROM pdf_card_sources "
            "WHERE pdf_card_id = ? AND page = ? ORDER BY id",
            (pdf_card_id, page),
        )
        .fetchall()
    )
    return [{"note_id": r[0], "excerpt": r[1]} for r in rows]


def get_pdf_page_card_counts(addon_dir: str, pdf_card_id: int) -> dict:
    """Return {page: count} for all pages that have at least one card."""
    rows = (
        get_connection(addon_dir)
        .execute(
            "SELECT page, COUNT(*) FROM pdf_card_sources WHERE pdf_card_id = ? GROUP BY page",
            (pdf_card_id,),
        )
        .fetchall()
    )
    return {r[0]: r[1] for r in rows}


def add_epub_card_source(
    addon_dir: str, epub_card_id: int, section_index: int, note_id: int, excerpt: str = ""
) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO epub_card_sources (epub_card_id, section_index, note_id, excerpt) VALUES (?, ?, ?, ?)",
        (epub_card_id, int(section_index), note_id, excerpt),
    )
    conn.commit()


def get_epub_card_sources(addon_dir: str, epub_card_id: int, section_index: int) -> list:
    rows = (
        get_connection(addon_dir)
        .execute(
            "SELECT note_id, excerpt FROM epub_card_sources "
            "WHERE epub_card_id = ? AND section_index = ? ORDER BY id",
            (epub_card_id, int(section_index)),
        )
        .fetchall()
    )
    return [{"note_id": r[0], "excerpt": r[1]} for r in rows]


def get_epub_section_card_counts(addon_dir: str, epub_card_id: int) -> dict:
    rows = (
        get_connection(addon_dir)
        .execute(
            "SELECT section_index, COUNT(*) FROM epub_card_sources "
            "WHERE epub_card_id = ? GROUP BY section_index",
            (epub_card_id,),
        )
        .fetchall()
    )
    return {int(r[0]): int(r[1]) for r in rows}


def add_web_card_source(
    addon_dir: str, web_card_id: int, url: str, note_id: int, excerpt: str = ""
) -> None:
    """Record that note_id was created while viewing web_card_id at url."""
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO web_card_sources (web_card_id, url, note_id, excerpt) VALUES (?, ?, ?, ?)",
        (web_card_id, str(url or "").strip(), note_id, excerpt),
    )
    conn.commit()


def get_web_card_sources(addon_dir: str, web_card_id: int, url: str) -> list:
    """Return list of {note_id, excerpt} for cards created at this web-card URL."""
    rows = (
        get_connection(addon_dir)
        .execute(
            "SELECT note_id, excerpt FROM web_card_sources "
            "WHERE web_card_id = ? AND url = ? ORDER BY id",
            (web_card_id, str(url or "").strip()),
        )
        .fetchall()
    )
    return [{"note_id": r[0], "excerpt": r[1]} for r in rows]


def export_stats_json(addon_dir: str) -> str:
    rows = (
        get_connection(addon_dir)
        .execute("SELECT scope, date, data FROM stats")
        .fetchall()
    )
    result: dict = {}
    for scope, date, data in rows:
        if scope == "daily":
            result["daily"] = {"date": date, "counts": json.loads(data)}
        else:
            result[scope] = json.loads(data)
    return json.dumps(result, indent=2, ensure_ascii=False)


def normalize_search_text(text: str) -> str:
    return " ".join((text or "").casefold().split())


def split_search_terms(text: str, *, min_len: int = 2) -> list[str]:
    return [
        tok
        for tok in _SEARCH_WORD_RE.findall(normalize_search_text(text))
        if len(tok) >= min_len
    ]


def _find_consecutive_prefix_match(
    query_terms: list[str], text_terms: list[str]
) -> tuple[int, int] | None:
    if not query_terms or len(query_terms) > len(text_terms):
        return None
    window = len(query_terms)
    for start in range(len(text_terms) - window + 1):
        if all(text_terms[start + idx].startswith(tok) for idx, tok in enumerate(query_terms)):
            return (start, start + window - 1)
    return None


def _find_ordered_prefix_match(
    query_terms: list[str], text_terms: list[str]
) -> list[int] | None:
    positions: list[int] = []
    start = 0
    for tok in query_terms:
        for idx in range(start, len(text_terms)):
            if text_terms[idx].startswith(tok):
                positions.append(idx)
                start = idx + 1
                break
        else:
            return None
    return positions


def _find_unordered_prefix_match(
    query_terms: list[str], text_terms: list[str]
) -> list[int] | None:
    positions: list[int] = []
    used: set[int] = set()
    for tok in query_terms:
        for idx, term in enumerate(text_terms):
            if idx in used:
                continue
            if term.startswith(tok):
                used.add(idx)
                positions.append(idx)
                break
        else:
            return None
    return sorted(positions)


def search_text_match_score(
    text: str, query: str
) -> tuple[int, int, int, int] | None:
    query_terms = split_search_terms(query)
    if not query_terms:
        return None
    text_terms = split_search_terms(text, min_len=1)
    if not text_terms:
        return None

    consecutive = _find_consecutive_prefix_match(query_terms, text_terms)
    if consecutive is not None:
        start, end = consecutive
        return (0, end - start, start, len(text_terms))

    ordered = _find_ordered_prefix_match(query_terms, text_terms)
    if ordered is not None:
        return (1, ordered[-1] - ordered[0], ordered[0], len(text_terms))

    unordered = _find_unordered_prefix_match(query_terms, text_terms)
    if unordered is not None:
        return (2, unordered[-1] - unordered[0], unordered[0], len(text_terms))

    return None


def replace_pdf_text_index(addon_dir: str, card_id: int, page_texts: list[str]) -> None:
    """Replace stored per-page extracted text for a PDF card."""
    conn = get_connection(addon_dir)
    conn.execute("DELETE FROM pdf_text_index WHERE card_id = ?", (card_id,))
    rows = [
        (card_id, i + 1, (txt or "").strip())
        for i, txt in enumerate(page_texts)
        if (txt or "").strip()
    ]
    if rows:
        conn.executemany(
            "INSERT INTO pdf_text_index (card_id, page, text) VALUES (?, ?, ?)",
            rows,
        )
    conn.commit()


def search_pdf_text_index(
    addon_dir: str, query: str, limit: int = 120
) -> list[tuple[int, int, str]]:
    """Search indexed per-page PDF text. Returns [(card_id, page, text), ...]."""
    query_terms = split_search_terms(query)
    if not query_terms:
        return []

    conn = get_connection(addon_dir)
    pre = query_terms[0]
    rows = conn.execute(
        "SELECT card_id, page, text FROM pdf_text_index "
        "WHERE lower(text) LIKE lower(?) ORDER BY card_id, page LIMIT ?",
        (f"%{pre}%", max(500, limit * 25)),
    ).fetchall()

    ranked: list[tuple[tuple[int, int, int, int], int, int, str]] = []
    for cid, page, text in rows:
        score = search_text_match_score(text or "", query)
        if score is None:
            continue
        ranked.append((score, int(cid), int(page), text))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(cid, page, text) for _, cid, page, text in ranked[:limit]]


def replace_epub_text_index(
    addon_dir: str, card_id: int, sections: list[tuple[str, str]]
) -> None:
    conn = get_connection(addon_dir)
    conn.execute("DELETE FROM epub_text_index WHERE card_id = ?", (card_id,))
    rows = [
        (card_id, idx, str(title or "").strip(), (text or "").strip())
        for idx, (title, text) in enumerate(sections)
        if (title or "").strip() or (text or "").strip()
    ]
    if rows:
        conn.executemany(
            "INSERT INTO epub_text_index (card_id, section_index, title, text) VALUES (?, ?, ?, ?)",
            rows,
        )
    conn.commit()


def search_epub_text_index(
    addon_dir: str, query: str, limit: int = 120
) -> list[tuple[int, int, str, str]]:
    query_terms = split_search_terms(query)
    if not query_terms:
        return []

    conn = get_connection(addon_dir)
    pre = query_terms[0]
    rows = conn.execute(
        "SELECT card_id, section_index, title, text FROM epub_text_index "
        "WHERE lower(title || ' ' || text) LIKE lower(?) "
        "ORDER BY card_id, section_index LIMIT ?",
        (f"%{pre}%", max(500, limit * 25)),
    ).fetchall()

    ranked: list[tuple[tuple[int, int, int, int], int, int, str, str]] = []
    for cid, section_index, title, text in rows:
        combined = " ".join(part for part in (title or "", text or "") if part)
        score = search_text_match_score(combined, query)
        if score is None:
            continue
        ranked.append((score, int(cid), int(section_index), str(title or ""), str(text or "")))

    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(cid, section_index, title, text) for _, cid, section_index, title, text in ranked[:limit]]


# ── Topic A-factor schedule ───────────────────────────────────────────────────


def get_topic_schedule(addon_dir: str, card_id: int) -> tuple[float, int]:
    """Return (a_factor, last_interval) for a topic card, or defaults if unseen."""
    row = (
        get_connection(addon_dir)
        .execute(
            "SELECT a_factor, interval FROM topic_schedule WHERE card_id = ?",
            (card_id,),
        )
        .fetchone()
    )
    return (row[0], row[1]) if row else (3.5, 1)


def set_topic_schedule(
    addon_dir: str, card_id: int, a_factor: float, interval: int
) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO topic_schedule (card_id, a_factor, interval) VALUES (?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "a_factor = excluded.a_factor, interval = excluded.interval",
        (card_id, round(float(a_factor), 3), int(interval)),
    )
    conn.commit()
