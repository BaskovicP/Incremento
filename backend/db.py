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
web_progress    — last URL, scroll position, bookmark state, and media resume state per web card
topic_postpones — timed postpone expiry timestamps per topic card
knowledge_tree_nodes — per-profile hierarchy of linked card ids
knowledge_tree_postpone_presets — saved postpone presets for tree/global/browser scopes
"""

import atexit
import json
import re
import sqlite3
import time
from pathlib import Path

try:
    from .paths import get_db_path
except ImportError:
    from paths import get_db_path  # test environment

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


def get_connection(addon_dir: str, profile: str) -> sqlite3.Connection:
    global _connection, _initialized_for
    cache_key = f"{addon_dir}::{profile}"
    if _connection is None or _initialized_for != cache_key:
        close_connection()
        p = get_db_path(addon_dir, profile)
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        _create_tables(conn)
        _connection = conn
        _initialized_for = cache_key
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
            bookmark_payload TEXT    NOT NULL DEFAULT '',
            media_url        TEXT    NOT NULL DEFAULT '',
            media_title      TEXT    NOT NULL DEFAULT '',
            media_seconds    REAL    NOT NULL DEFAULT 0.0,
            media_updated_at INTEGER NOT NULL DEFAULT 0
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

        CREATE TABLE IF NOT EXISTS topic_postpones (
            card_id  INTEGER PRIMARY KEY,
            until_ts INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_topic_postpones_until
            ON topic_postpones (until_ts);

        CREATE TABLE IF NOT EXISTS knowledge_tree_nodes (
            card_id        INTEGER PRIMARY KEY,
            parent_card_id INTEGER,
            node_kind      TEXT    NOT NULL DEFAULT 'topic',
            sort_order     INTEGER NOT NULL DEFAULT 0,
            created_at     INTEGER NOT NULL DEFAULT 0,
            updated_at     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ktn_parent_order
            ON knowledge_tree_nodes (parent_card_id, sort_order, card_id);

        CREATE TABLE IF NOT EXISTS knowledge_tree_postpone_presets (
            name               TEXT    PRIMARY KEY,
            branch_root_card_id INTEGER,
            config_json        TEXT    NOT NULL DEFAULT '{}',
            is_default         INTEGER NOT NULL DEFAULT 0,
            created_at         INTEGER NOT NULL DEFAULT 0,
            updated_at         INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ktpp_branch
            ON knowledge_tree_postpone_presets (branch_root_card_id, name);
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
        "ALTER TABLE web_progress ADD COLUMN media_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE web_progress ADD COLUMN media_title TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE web_progress ADD COLUMN media_seconds REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE web_progress ADD COLUMN media_updated_at INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            conn.execute(statement)
            conn.commit()
        except Exception:
            pass


# ── Export helpers (called by the export function in __init__.py) ─────────────


def export_priorities_json(addon_dir: str, profile: str) -> str:
    rows = (
        get_connection(addon_dir, profile)
        .execute("SELECT card_id, priority FROM priorities ORDER BY card_id")
        .fetchall()
    )
    return json.dumps({str(r[0]): r[1] for r in rows}, indent=2)


def export_pdf_progress_json(addon_dir: str, profile: str) -> str:
    rows = (
        get_connection(addon_dir, profile)
        .execute("SELECT card_id, page, zoom FROM pdf_progress ORDER BY card_id")
        .fetchall()
    )
    return json.dumps({str(r[0]): {"page": r[1], "zoom": r[2]} for r in rows}, indent=2)


def export_highlights_json(addon_dir: str, profile: str) -> str:
    rows = (
        get_connection(addon_dir, profile)
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
    addon_dir: str, profile: str, pdf_card_id: int, page: int, note_id: int, excerpt: str = ""
) -> None:
    """Record that note_id was created while reading pdf_card_id at page."""
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_card_sources (pdf_card_id, page, note_id, excerpt) VALUES (?, ?, ?, ?)",
        (pdf_card_id, page, note_id, excerpt),
    )
    conn.commit()


def get_pdf_card_sources(addon_dir: str, profile: str, pdf_card_id: int, page: int) -> list:
    """Return list of {note_id, excerpt} for cards created on this PDF page."""
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT note_id, excerpt FROM pdf_card_sources "
            "WHERE pdf_card_id = ? AND page = ? ORDER BY id",
            (pdf_card_id, page),
        )
        .fetchall()
    )
    return [{"note_id": r[0], "excerpt": r[1]} for r in rows]


def get_pdf_page_card_counts(addon_dir: str, profile: str, pdf_card_id: int) -> dict:
    """Return {page: count} for all pages that have at least one card."""
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT page, COUNT(*) FROM pdf_card_sources WHERE pdf_card_id = ? GROUP BY page",
            (pdf_card_id,),
        )
        .fetchall()
    )
    return {r[0]: r[1] for r in rows}


def add_epub_card_source(
    addon_dir: str, profile: str, epub_card_id: int, section_index: int, note_id: int, excerpt: str = ""
) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO epub_card_sources (epub_card_id, section_index, note_id, excerpt) VALUES (?, ?, ?, ?)",
        (epub_card_id, int(section_index), note_id, excerpt),
    )
    conn.commit()


def get_epub_card_sources(addon_dir: str, profile: str, epub_card_id: int, section_index: int) -> list:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT note_id, excerpt FROM epub_card_sources "
            "WHERE epub_card_id = ? AND section_index = ? ORDER BY id",
            (epub_card_id, int(section_index)),
        )
        .fetchall()
    )
    return [{"note_id": r[0], "excerpt": r[1]} for r in rows]


def get_epub_section_card_counts(addon_dir: str, profile: str, epub_card_id: int) -> dict:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT section_index, COUNT(*) FROM epub_card_sources "
            "WHERE epub_card_id = ? GROUP BY section_index",
            (epub_card_id,),
        )
        .fetchall()
    )
    return {int(r[0]): int(r[1]) for r in rows}


def add_web_card_source(
    addon_dir: str, profile: str, web_card_id: int, url: str, note_id: int, excerpt: str = ""
) -> None:
    """Record that note_id was created while viewing web_card_id at url."""
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO web_card_sources (web_card_id, url, note_id, excerpt) VALUES (?, ?, ?, ?)",
        (web_card_id, str(url or "").strip(), note_id, excerpt),
    )
    conn.commit()


def get_web_card_sources(addon_dir: str, profile: str, web_card_id: int, url: str) -> list:
    """Return list of {note_id, excerpt} for cards created at this web-card URL."""
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT note_id, excerpt FROM web_card_sources "
            "WHERE web_card_id = ? AND url = ? ORDER BY id",
            (web_card_id, str(url or "").strip()),
        )
        .fetchall()
    )
    return [{"note_id": r[0], "excerpt": r[1]} for r in rows]


def export_stats_json(addon_dir: str, profile: str) -> str:
    rows = (
        get_connection(addon_dir, profile)
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


def replace_pdf_text_index(addon_dir: str, profile: str, card_id: int, page_texts: list[str]) -> None:
    """Replace stored per-page extracted text for a PDF card."""
    conn = get_connection(addon_dir, profile)
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
    addon_dir: str, profile: str, query: str, limit: int = 120
) -> list[tuple[int, int, str]]:
    """Search indexed per-page PDF text. Returns [(card_id, page, text), ...]."""
    query_terms = split_search_terms(query)
    if not query_terms:
        return []

    conn = get_connection(addon_dir, profile)
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
    addon_dir: str, profile: str, card_id: int, sections: list[tuple[str, str]]
) -> None:
    conn = get_connection(addon_dir, profile)
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
    addon_dir: str, profile: str, query: str, limit: int = 120
) -> list[tuple[int, int, str, str]]:
    query_terms = split_search_terms(query)
    if not query_terms:
        return []

    conn = get_connection(addon_dir, profile)
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


def get_topic_schedule(addon_dir: str, profile: str, card_id: int) -> tuple[float, int]:
    """Return (a_factor, last_interval) for a topic card, or defaults if unseen."""
    row = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT a_factor, interval FROM topic_schedule WHERE card_id = ?",
            (card_id,),
        )
        .fetchone()
    )
    return (row[0], row[1]) if row else (3.5, 1)


def set_topic_schedule(
    addon_dir: str, profile: str, card_id: int, a_factor: float, interval: int
) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO topic_schedule (card_id, a_factor, interval) VALUES (?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "a_factor = excluded.a_factor, interval = excluded.interval",
        (card_id, round(float(a_factor), 3), int(interval)),
    )
    conn.commit()


# ── Knowledge tree ────────────────────────────────────────────────────────────


def get_knowledge_tree_nodes(addon_dir: str, profile: str) -> list[dict]:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT card_id, parent_card_id, node_kind, sort_order, created_at, updated_at "
            "FROM knowledge_tree_nodes "
            "ORDER BY CASE WHEN parent_card_id IS NULL THEN 0 ELSE 1 END, "
            "parent_card_id, sort_order, card_id"
        )
        .fetchall()
    )
    return [
        {
            "card_id": int(card_id),
            "parent_card_id": None if parent_card_id is None else int(parent_card_id),
            "node_kind": str(node_kind or "topic"),
            "sort_order": int(sort_order or 0),
            "created_at": int(created_at or 0),
            "updated_at": int(updated_at or 0),
        }
        for card_id, parent_card_id, node_kind, sort_order, created_at, updated_at in rows
    ]


def get_knowledge_tree_node(addon_dir: str, profile: str, card_id: int) -> dict | None:
    row = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT card_id, parent_card_id, node_kind, sort_order, created_at, updated_at "
            "FROM knowledge_tree_nodes WHERE card_id = ?",
            (int(card_id),),
        )
        .fetchone()
    )
    if not row:
        return None
    return {
        "card_id": int(row[0]),
        "parent_card_id": None if row[1] is None else int(row[1]),
        "node_kind": str(row[2] or "topic"),
        "sort_order": int(row[3] or 0),
        "created_at": int(row[4] or 0),
        "updated_at": int(row[5] or 0),
    }


def set_knowledge_tree_structure(
    addon_dir: str,
    profile: str,
    rows: list[dict],
) -> None:
    conn = get_connection(addon_dir, profile)
    normalized_rows: list[tuple[int, int | None, str, int]] = []
    seen: set[int] = set()

    for index, row in enumerate(rows):
        card_id = int(row["card_id"])
        if card_id in seen:
            raise ValueError(f"Duplicate knowledge-tree card id: {card_id}")
        seen.add(card_id)

        parent_card_id = row.get("parent_card_id")
        if parent_card_id is not None:
            parent_card_id = int(parent_card_id)
        if parent_card_id == card_id:
            raise ValueError("Knowledge-tree node cannot be its own parent.")

        node_kind = str(row.get("node_kind") or "topic").strip().lower()
        if node_kind not in {"topic", "item"}:
            raise ValueError(f"Unsupported knowledge-tree node kind: {node_kind}")

        sort_order = int(row.get("sort_order", index))
        normalized_rows.append((card_id, parent_card_id, node_kind, sort_order))

    valid_ids = {card_id for card_id, _, _, _ in normalized_rows}
    for card_id, parent_card_id, _, _ in normalized_rows:
        if parent_card_id is not None and parent_card_id not in valid_ids:
            raise ValueError(
                f"Knowledge-tree parent {parent_card_id} for card {card_id} is missing."
            )

    parent_map = {card_id: parent_card_id for card_id, parent_card_id, _, _ in normalized_rows}
    for card_id in valid_ids:
        seen_chain: set[int] = set()
        current = card_id
        while current is not None:
            if current in seen_chain:
                raise ValueError("Knowledge-tree structure contains a cycle.")
            seen_chain.add(current)
            current = parent_map.get(current)

    existing = {
        row["card_id"]: row
        for row in get_knowledge_tree_nodes(addon_dir, profile)
    }
    now = int(time.time())

    conn.execute("BEGIN")
    try:
        conn.execute(
            "DELETE FROM knowledge_tree_nodes WHERE card_id NOT IN (%s)" % ",".join("?" for _ in valid_ids),
            tuple(valid_ids),
        ) if valid_ids else conn.execute("DELETE FROM knowledge_tree_nodes")

        grouped: dict[int | None, list[tuple[int, str, int]]] = {}
        for card_id, parent_card_id, node_kind, sort_order in normalized_rows:
            grouped.setdefault(parent_card_id, []).append((card_id, node_kind, sort_order))

        for parent_card_id, items in grouped.items():
            items.sort(key=lambda item: (item[2], item[0]))
            for sort_order, (card_id, node_kind, _raw_sort) in enumerate(items):
                created_at = int(existing.get(card_id, {}).get("created_at") or now)
                conn.execute(
                    "INSERT INTO knowledge_tree_nodes "
                    "(card_id, parent_card_id, node_kind, sort_order, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(card_id) DO UPDATE SET "
                    "parent_card_id = excluded.parent_card_id, "
                    "node_kind = excluded.node_kind, "
                    "sort_order = excluded.sort_order, "
                    "updated_at = excluded.updated_at",
                    (card_id, parent_card_id, node_kind, sort_order, created_at, now),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def get_knowledge_tree_postpone_presets(addon_dir: str, profile: str) -> list[dict]:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT name, branch_root_card_id, config_json, is_default, created_at, updated_at "
            "FROM knowledge_tree_postpone_presets "
            "ORDER BY is_default DESC, lower(name), name"
        )
        .fetchall()
    )
    presets: list[dict] = []
    for name, branch_root_card_id, config_json, is_default, created_at, updated_at in rows:
        try:
            config = json.loads(str(config_json or "{}"))
            if not isinstance(config, dict):
                config = {}
        except Exception:
            config = {}
        presets.append(
            {
                "name": str(name or "").strip(),
                "branch_root_card_id": (
                    None if branch_root_card_id is None else int(branch_root_card_id)
                ),
                "config": config,
                "is_default": bool(is_default),
                "created_at": int(created_at or 0),
                "updated_at": int(updated_at or 0),
            }
        )
    return presets


def get_knowledge_tree_postpone_preset(
    addon_dir: str,
    profile: str,
    name: str,
) -> dict | None:
    target = str(name or "").strip()
    if not target:
        return None
    row = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT name, branch_root_card_id, config_json, is_default, created_at, updated_at "
            "FROM knowledge_tree_postpone_presets WHERE name = ?",
            (target,),
        )
        .fetchone()
    )
    if not row:
        return None
    try:
        config = json.loads(str(row[2] or "{}"))
        if not isinstance(config, dict):
            config = {}
    except Exception:
        config = {}
    return {
        "name": str(row[0] or "").strip(),
        "branch_root_card_id": None if row[1] is None else int(row[1]),
        "config": config,
        "is_default": bool(row[3]),
        "created_at": int(row[4] or 0),
        "updated_at": int(row[5] or 0),
    }


def save_knowledge_tree_postpone_preset(
    addon_dir: str,
    profile: str,
    name: str,
    config: dict,
    *,
    branch_root_card_id: int | None = None,
    is_default: bool = False,
) -> None:
    preset_name = str(name or "").strip()
    if not preset_name:
        raise ValueError("Knowledge-tree postpone preset name cannot be empty.")
    if branch_root_card_id is not None:
        branch_root_card_id = int(branch_root_card_id)
    if not isinstance(config, dict):
        raise ValueError("Knowledge-tree postpone preset config must be a dictionary.")

    conn = get_connection(addon_dir, profile)
    existing = get_knowledge_tree_postpone_preset(addon_dir, profile, preset_name) or {}
    created_at = int(existing.get("created_at") or time.time())
    updated_at = int(time.time())

    conn.execute("BEGIN")
    try:
        if is_default:
            conn.execute("UPDATE knowledge_tree_postpone_presets SET is_default = 0")
        conn.execute(
            "INSERT INTO knowledge_tree_postpone_presets "
            "(name, branch_root_card_id, config_json, is_default, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "branch_root_card_id = excluded.branch_root_card_id, "
            "config_json = excluded.config_json, "
            "is_default = excluded.is_default, "
            "updated_at = excluded.updated_at",
            (
                preset_name,
                branch_root_card_id,
                json.dumps(config, sort_keys=True),
                1 if is_default else 0,
                created_at,
                updated_at,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def delete_knowledge_tree_postpone_preset(
    addon_dir: str,
    profile: str,
    name: str,
) -> bool:
    preset_name = str(name or "").strip()
    if not preset_name:
        return False
    conn = get_connection(addon_dir, profile)
    cursor = conn.execute(
        "DELETE FROM knowledge_tree_postpone_presets WHERE name = ?",
        (preset_name,),
    )
    conn.commit()
    return int(getattr(cursor, "rowcount", 0) or 0) > 0


def set_default_knowledge_tree_postpone_preset(
    addon_dir: str,
    profile: str,
    name: str,
) -> bool:
    preset_name = str(name or "").strip()
    if not preset_name:
        return False
    conn = get_connection(addon_dir, profile)
    row = conn.execute(
        "SELECT 1 FROM knowledge_tree_postpone_presets WHERE name = ?",
        (preset_name,),
    ).fetchone()
    if not row:
        return False

    conn.execute("BEGIN")
    try:
        conn.execute("UPDATE knowledge_tree_postpone_presets SET is_default = 0")
        conn.execute(
            "UPDATE knowledge_tree_postpone_presets SET is_default = 1, updated_at = ? WHERE name = ?",
            (int(time.time()), preset_name),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return True
