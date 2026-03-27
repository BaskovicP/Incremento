"""
Central SQLite database for all Incremento user data.

One connection is kept open per addon_dir (re-initialised if the path changes).
WAL mode + NORMAL synchronous gives fast writes while staying crash-safe.

Tables
------
pdf_progress    — reading position and zoom per card
pdf_highlights  — highlighted passages per card
stats           — daily and lifetime review statistics (JSON blobs per scope)
priorities      — card priority values
pdf_card_sources — notes created while reading a PDF page (for per-page card preview)
"""

import json
import sqlite3
from pathlib import Path

_connection: sqlite3.Connection | None = None
_initialized_for: str | None = None

DB_NAME = "incremento.db"


# ── Connection ────────────────────────────────────────────────────────────────


def get_connection(addon_dir: str) -> sqlite3.Connection:
    global _connection, _initialized_for
    if _connection is None or _initialized_for != addon_dir:
        if _connection is not None:
            try:
                _connection.close()
            except Exception:
                pass
        p = Path(addon_dir) / "user_files" / DB_NAME
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _create_tables(conn)
        _connection = conn
        _initialized_for = addon_dir
    return _connection


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
            card_id INTEGER PRIMARY KEY,
            url     TEXT    NOT NULL DEFAULT ''
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

        CREATE TABLE IF NOT EXISTS pdf_text_index (
            card_id INTEGER NOT NULL,
            page    INTEGER NOT NULL,
            text    TEXT    NOT NULL DEFAULT '',
            PRIMARY KEY (card_id, page)
        );
        CREATE INDEX IF NOT EXISTS idx_pti_card_page
            ON pdf_text_index (card_id, page);

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
    q_norm = " ".join((query or "").casefold().split())
    if len(q_norm) < 2:
        return []
    tokens = [t for t in q_norm.split(" ") if len(t) >= 2]
    if not tokens:
        return []

    conn = get_connection(addon_dir)
    pre = tokens[0]
    rows = conn.execute(
        "SELECT card_id, page, text FROM pdf_text_index "
        "WHERE lower(text) LIKE lower(?) ORDER BY card_id, page LIMIT ?",
        (f"%{pre}%", max(500, limit * 25)),
    ).fetchall()

    def _normalize(s: str) -> str:
        return " ".join((s or "").casefold().split())

    out: list[tuple[int, int, str]] = []
    for cid, page, text in rows:
        norm = _normalize(text or "")
        if not norm:
            continue
        if q_norm in norm:
            out.append((cid, page, text))
        else:
            hits = sum(1 for t in tokens if t in norm)
            if hits >= max(1, int(len(tokens) * 0.7)):
                out.append((cid, page, text))
        if len(out) >= limit:
            break
    return out


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
