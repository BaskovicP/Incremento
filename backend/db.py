"""
Central SQLite database for all Incremento user data.

One connection is kept open per addon_dir (re-initialised if the path changes).
WAL mode + NORMAL synchronous gives fast writes while staying crash-safe.

Tables
------
pdf_progress    — reading position and zoom per card
pdf_daily_limits — per-card daily reading limit config for PDFs
pdf_due_review_prompts — per-card on-open due-review prompt config for PDFs
pdf_daily_limit_usage — per-card per-day PDF reading usage and overrides
pdf_highlights  — highlighted passages per card
epub_progress   — reading section/scroll state per card
epub_daily_limits — per-card daily reading limit config for EPUBs
epub_due_review_prompts — per-card on-open due-review prompt config for EPUBs
epub_daily_limit_usage — per-card per-day EPUB reading usage and overrides
epub_highlights — highlighted passages per EPUB section
writing_progress — per-card editor state for markdown writing notes
writing_word_stats — per-card writing word-count baselines and totals
stats           — daily and lifetime review statistics (JSON blobs per scope)
priorities      — card priority values
pdf_card_sources — notes created while reading a PDF page (for per-page card preview)
epub_card_sources — notes created while reading an EPUB section
web_card_sources — notes created while viewing a web-card URL (for per-URL card preview)
note_ocr_index  — searchable OCR text extracted from image-based non-document notes
web_progress    — last URL, scroll position, bookmark state, and media resume state per web card
reader_bookmarks — permanent interesting-place bookmarks per reader card
browser_media_refs — latest manually saved browser media reference per card
reviewer_recent_tags — latest reviewer-added tags for quick reuse
topic_postpones — timed postpone expiry timestamps per topic card
item_postpones  — timed skip expiry timestamps per non-topic card
custom_schedule_rules — per-card recurring custom scheduling rules
knowledge_tree_nodes — per-profile hierarchy of linked card ids
knowledge_tree_postpone_presets — saved postpone presets for tree/global/browser scopes
"""

import atexit
import json
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    from .paths import get_db_checkpoint_dir, get_db_path, get_stats_path
except ImportError:
    from paths import get_db_checkpoint_dir, get_db_path, get_stats_path  # test environment

_connection: sqlite3.Connection | None = None
_initialized_for: str | None = None

DB_NAME = "incremento.db"
_SEARCH_WORD_RE = re.compile(r"\w+", re.UNICODE)
_TOPIC_A_FACTOR_MIN = 1.1
_TOPIC_A_FACTOR_MAX = 100.0
_DEFAULT_TOPIC_A_FACTOR = 3.5


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


def open_database_editor_connection(
    addon_dir: str,
    profile: str,
    *,
    read_only: bool = True,
) -> sqlite3.Connection:
    db_path = get_db_path(addon_dir, profile)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        conn = get_connection(addon_dir, profile)
        conn.commit()
    if read_only:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
        )
    else:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def create_database_checkpoint(
    addon_dir: str,
    profile: str,
    *,
    label: str = "sqlite_editor",
) -> dict[str, object]:
    conn = get_connection(addon_dir, profile)
    conn.commit()
    checkpoints_dir = get_db_checkpoint_dir(addon_dir, profile)
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    created_at = int(time.time())
    safe_label = re.sub(r"[^a-z0-9_-]+", "_", str(label or "checkpoint").strip().lower()).strip("_")
    if not safe_label:
        safe_label = "checkpoint"
    checkpoint_name = f"{created_at}_{safe_label}.sqlite3"
    checkpoint_path = checkpoints_dir / checkpoint_name
    snapshot_conn = sqlite3.connect(str(checkpoint_path))
    try:
        conn.backup(snapshot_conn)
    finally:
        snapshot_conn.close()
    return {
        "path": str(checkpoint_path),
        "filename": checkpoint_name,
        "created_at": created_at,
        "size_bytes": int(checkpoint_path.stat().st_size),
    }


def list_database_checkpoints(
    addon_dir: str,
    profile: str,
    *,
    limit: int = 10,
) -> list[dict[str, object]]:
    checkpoints_dir = get_db_checkpoint_dir(addon_dir, profile)
    if not checkpoints_dir.exists():
        return []
    rows: list[dict[str, object]] = []
    for path in sorted(
        checkpoints_dir.glob("*.sqlite3"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    ):
        try:
            size_bytes = int(path.stat().st_size)
            created_at = int(path.stem.split("_", 1)[0])
        except Exception:
            created_at = int(path.stat().st_mtime)
            size_bytes = int(path.stat().st_size)
        rows.append(
            {
                "path": str(path),
                "filename": path.name,
                "created_at": created_at,
                "size_bytes": size_bytes,
            }
        )
        if len(rows) >= max(1, int(limit)):
            break
    return rows


atexit.register(close_connection)


# ── Schema ────────────────────────────────────────────────────────────────────


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pdf_progress (
            card_id   INTEGER PRIMARY KEY,
            page      INTEGER NOT NULL DEFAULT 1,
            zoom      REAL    NOT NULL DEFAULT 1.0,
            read_page INTEGER NOT NULL DEFAULT 0,
            read_anchor_json TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS pdf_daily_limits (
            card_id          INTEGER PRIMARY KEY,
            daily_page_limit INTEGER NOT NULL DEFAULT 0,
            enforcement_mode TEXT    NOT NULL DEFAULT 'warning',
            updated_at       INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pdf_due_review_prompts (
            card_id    INTEGER PRIMARY KEY,
            enabled    INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pdf_daily_limit_usage (
            card_id          INTEGER NOT NULL,
            logical_date     TEXT    NOT NULL DEFAULT '',
            baseline_page    INTEGER NOT NULL DEFAULT 0,
            highest_page     INTEGER NOT NULL DEFAULT 0,
            override_enabled INTEGER NOT NULL DEFAULT 0,
            updated_at       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (card_id, logical_date)
        );
        CREATE INDEX IF NOT EXISTS idx_pdlu_date
            ON pdf_daily_limit_usage (logical_date, card_id);

        CREATE TABLE IF NOT EXISTS pdf_highlights (
            id      TEXT    NOT NULL,
            card_id INTEGER NOT NULL,
            page    INTEGER NOT NULL DEFAULT 1,
            color   TEXT    NOT NULL DEFAULT 'yellow',
            text    TEXT    NOT NULL DEFAULT '',
            note    TEXT    NOT NULL DEFAULT '',
            rects   TEXT    NOT NULL DEFAULT '[]',
            PRIMARY KEY (id, card_id)
        );

        CREATE TABLE IF NOT EXISTS epub_progress (
            card_id            INTEGER PRIMARY KEY,
            section_index      INTEGER NOT NULL DEFAULT 0,
            scroll_ratio       REAL    NOT NULL DEFAULT 0.0,
            is_finished        INTEGER NOT NULL DEFAULT 0,
            read_section_index INTEGER NOT NULL DEFAULT 0,
            font_scale         REAL    NOT NULL DEFAULT 1.0
        );

        CREATE TABLE IF NOT EXISTS epub_daily_limits (
            card_id             INTEGER PRIMARY KEY,
            daily_section_limit INTEGER NOT NULL DEFAULT 0,
            enforcement_mode    TEXT    NOT NULL DEFAULT 'warning',
            updated_at          INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS epub_due_review_prompts (
            card_id    INTEGER PRIMARY KEY,
            enabled    INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS epub_daily_limit_usage (
            card_id              INTEGER NOT NULL,
            logical_date         TEXT    NOT NULL DEFAULT '',
            baseline_section     INTEGER NOT NULL DEFAULT 0,
            highest_section      INTEGER NOT NULL DEFAULT 0,
            override_enabled     INTEGER NOT NULL DEFAULT 0,
            updated_at           INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (card_id, logical_date)
        );
        CREATE INDEX IF NOT EXISTS idx_edlu_date
            ON epub_daily_limit_usage (logical_date, card_id);

        CREATE TABLE IF NOT EXISTS epub_highlights (
            id            TEXT    NOT NULL,
            card_id       INTEGER NOT NULL,
            section_index INTEGER NOT NULL DEFAULT 0,
            color         TEXT    NOT NULL DEFAULT 'yellow',
            text          TEXT    NOT NULL DEFAULT '',
            note          TEXT    NOT NULL DEFAULT '',
            start_offset  INTEGER NOT NULL DEFAULT 0,
            end_offset    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (id, card_id)
        );

        CREATE TABLE IF NOT EXISTS writing_progress (
            card_id                INTEGER PRIMARY KEY,
            cursor_position        INTEGER NOT NULL DEFAULT 0,
            scroll_ratio           REAL    NOT NULL DEFAULT 0.0,
            font_scale             REAL    NOT NULL DEFAULT 1.0,
            wrap_enabled           INTEGER NOT NULL DEFAULT 1,
            focus_mode             INTEGER NOT NULL DEFAULT 0,
            preview_visible        INTEGER NOT NULL DEFAULT 1,
            highlight_current_line INTEGER NOT NULL DEFAULT 1,
            bookmark_block_number  INTEGER NOT NULL DEFAULT -1,
            updated_at             INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS writing_word_stats (
            card_id                 INTEGER PRIMARY KEY,
            current_word_count      INTEGER NOT NULL DEFAULT 0,
            daily_logical_date      TEXT    NOT NULL DEFAULT '',
            daily_baseline_words    INTEGER NOT NULL DEFAULT 0,
            updated_at              INTEGER NOT NULL DEFAULT 0
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

        CREATE TABLE IF NOT EXISTS reader_bookmarks (
            id            TEXT    PRIMARY KEY,
            card_id       INTEGER NOT NULL,
            reader_type   TEXT    NOT NULL DEFAULT '',
            label         TEXT    NOT NULL DEFAULT '',
            location_json TEXT    NOT NULL DEFAULT '{}',
            created_at    INTEGER NOT NULL DEFAULT 0,
            updated_at    INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_reader_bookmarks_card_reader
            ON reader_bookmarks (card_id, reader_type, created_at);

        CREATE TABLE IF NOT EXISTS browser_media_refs (
            card_id       INTEGER PRIMARY KEY,
            page_url      TEXT    NOT NULL DEFAULT '',
            media_url     TEXT    NOT NULL DEFAULT '',
            media_title   TEXT    NOT NULL DEFAULT '',
            media_seconds REAL    NOT NULL DEFAULT 0.0,
            updated_at    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS reviewer_recent_tags (
            normalized_tag TEXT PRIMARY KEY,
            display_tag    TEXT    NOT NULL DEFAULT '',
            used_at        INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_rrt_used_at
            ON reviewer_recent_tags (used_at DESC, normalized_tag);

        CREATE TABLE IF NOT EXISTS pdf_card_sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_card_id INTEGER NOT NULL,
            page        INTEGER NOT NULL,
            note_id     INTEGER NOT NULL,
            excerpt     TEXT    NOT NULL DEFAULT '',
            pdf_filename TEXT   NOT NULL DEFAULT ''
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

        CREATE TABLE IF NOT EXISTS note_ocr_index (
            note_id    INTEGER NOT NULL,
            card_id    INTEGER NOT NULL,
            image_name TEXT    NOT NULL DEFAULT '',
            text       TEXT    NOT NULL DEFAULT '',
            PRIMARY KEY (note_id, card_id, image_name)
        );
        CREATE INDEX IF NOT EXISTS idx_noi_note_card
            ON note_ocr_index (note_id, card_id);

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
            card_id          INTEGER PRIMARY KEY,
            a_factor         REAL    NOT NULL DEFAULT 3.5,
            interval         INTEGER NOT NULL DEFAULT 1,
            precise_interval REAL    NOT NULL DEFAULT 1.0
        );

        CREATE TABLE IF NOT EXISTS topic_postpones (
            card_id  INTEGER PRIMARY KEY,
            until_ts INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_topic_postpones_until
            ON topic_postpones (until_ts);

        CREATE TABLE IF NOT EXISTS item_postpones (
            card_id  INTEGER PRIMARY KEY,
            until_ts INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_item_postpones_until
            ON item_postpones (until_ts);

        CREATE TABLE IF NOT EXISTS custom_schedule_rules (
            card_id        INTEGER PRIMARY KEY,
            enabled        INTEGER NOT NULL DEFAULT 1,
            mode           TEXT    NOT NULL DEFAULT 'minimum_cadence',
            interval_value INTEGER NOT NULL DEFAULT 2,
            interval_unit  TEXT    NOT NULL DEFAULT 'days',
            preset_label   TEXT    NOT NULL DEFAULT '',
            created_at     INTEGER NOT NULL DEFAULT 0,
            updated_at     INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_csr_enabled_mode
            ON custom_schedule_rules (enabled, mode, interval_unit, interval_value);

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
    _ensure_column(
        conn,
        "pdf_progress",
        "read_page",
        "INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        conn,
        "pdf_progress",
        "read_anchor_json",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "epub_progress",
        "read_section_index",
        "INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        conn,
        "epub_progress",
        "font_scale",
        "REAL NOT NULL DEFAULT 1.0",
    )
    _ensure_column(
        conn,
        "web_progress",
        "scroll_ratio",
        "REAL NOT NULL DEFAULT 0.0",
    )
    _ensure_column(
        conn,
        "web_progress",
        "bookmark_url",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "web_progress",
        "bookmark_payload",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "web_progress",
        "media_url",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "web_progress",
        "media_title",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "web_progress",
        "media_seconds",
        "REAL NOT NULL DEFAULT 0.0",
    )
    _ensure_column(
        conn,
        "web_progress",
        "media_updated_at",
        "INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        conn,
        "topic_schedule",
        "precise_interval",
        "REAL NOT NULL DEFAULT 1.0",
    )
    _ensure_column(
        conn,
        "writing_progress",
        "preview_visible",
        "INTEGER NOT NULL DEFAULT 1",
    )
    _ensure_column(
        conn,
        "pdf_highlights",
        "note",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "epub_highlights",
        "note",
        "TEXT NOT NULL DEFAULT ''",
    )
    _ensure_column(
        conn,
        "pdf_card_sources",
        "pdf_filename",
        "TEXT NOT NULL DEFAULT ''",
    )


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_sql: str,
) -> None:
    try:
        columns = {
            str(row[1])
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
    except Exception:
        columns = set()
    if column_name in columns:
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
    conn.commit()
    # Add read_page/read_anchor_json to existing pdf_progress tables that predate them
    try:
        conn.execute(
            "ALTER TABLE pdf_progress ADD COLUMN read_page INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    except Exception:
        pass  # column already exists
    try:
        conn.execute(
            "ALTER TABLE pdf_progress ADD COLUMN read_anchor_json TEXT NOT NULL DEFAULT ''"
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


# ── Browser media refs ────────────────────────────────────────────────────────


_PDF_LIMIT_MODES = {"warning", "soft_lock", "hard_stop"}


def _default_pdf_daily_limit_config() -> dict:
    return {
        "daily_page_limit": 0,
        "enforcement_mode": "warning",
        "updated_at": 0,
    }


def _normalize_pdf_daily_limit(value) -> int:
    try:
        limit = int(value or 0)
    except Exception:
        limit = 0
    return max(0, limit)


def _normalize_pdf_limit_mode(value) -> str:
    mode = str(value or "warning").strip().lower()
    if mode not in _PDF_LIMIT_MODES:
        return "warning"
    return mode


def _default_pdf_daily_limit_usage(logical_date: str = "") -> dict:
    return {
        "logical_date": str(logical_date or "").strip(),
        "baseline_page": 0,
        "highest_page": 0,
        "override_enabled": False,
        "updated_at": 0,
    }


def _default_pdf_due_review_prompt_config() -> dict:
    return {
        "enabled": True,
        "updated_at": 0,
    }


def _default_epub_daily_limit_config() -> dict:
    return {
        "daily_section_limit": 0,
        "enforcement_mode": "warning",
        "updated_at": 0,
    }


def _default_epub_daily_limit_usage(logical_date: str) -> dict:
    return {
        "logical_date": str(logical_date or "").strip(),
        "baseline_section": 0,
        "highest_section": 0,
        "override_enabled": False,
        "updated_at": 0,
    }


def _default_epub_due_review_prompt_config() -> dict:
    return {
        "enabled": True,
        "updated_at": 0,
    }


def _default_writing_progress() -> dict:
    return {
        "cursor_position": 0,
        "scroll_ratio": 0.0,
        "font_scale": 1.0,
        "wrap_enabled": True,
        "focus_mode": False,
        "preview_visible": True,
        "highlight_current_line": True,
        "bookmark_block_number": -1,
        "updated_at": 0,
    }


def _default_writing_word_stats() -> dict:
    return {
        "current_word_count": 0,
        "daily_logical_date": "",
        "daily_baseline_words": 0,
        "updated_at": 0,
    }


def _normalize_pdf_daily_limit_page(value) -> int:
    try:
        page = int(value or 0)
    except Exception:
        page = 0
    return max(0, page)


def _normalize_epub_daily_limit_section(value) -> int:
    try:
        section = int(value or 0)
    except Exception:
        section = 0
    return max(0, section)


def _normalize_pdf_daily_limit_logical_date(value) -> str:
    return str(value or "").strip()[:32]


def _normalize_writing_progress_cursor_position(value) -> int:
    try:
        position = int(value or 0)
    except Exception:
        position = 0
    return max(0, position)


def _normalize_writing_progress_scroll_ratio(value) -> float:
    try:
        ratio = float(value or 0.0)
    except Exception:
        ratio = 0.0
    return max(0.0, min(ratio, 1.0))


def _normalize_writing_progress_font_scale(value) -> float:
    try:
        scale = float(value or 1.0)
    except Exception:
        scale = 1.0
    return max(0.7, min(scale, 2.4))


def _normalize_writing_progress_bookmark_block(value) -> int:
    try:
        block = int(value)
    except Exception:
        block = -1
    return max(-1, block)


def _normalize_writing_word_count(value) -> int:
    try:
        count = int(value or 0)
    except Exception:
        count = 0
    return max(0, count)


def _normalize_writing_logical_date(value) -> str:
    return str(value or "").strip()[:32]


def get_writing_progress(addon_dir: str, profile: str, card_id: int) -> dict:
    row = get_connection(addon_dir, profile).execute(
        "SELECT cursor_position, scroll_ratio, font_scale, wrap_enabled, focus_mode, "
        "preview_visible, highlight_current_line, bookmark_block_number, updated_at "
        "FROM writing_progress WHERE card_id = ?",
        (int(card_id),),
    ).fetchone()
    if not row:
        return _default_writing_progress()
    return {
        "cursor_position": _normalize_writing_progress_cursor_position(row[0]),
        "scroll_ratio": _normalize_writing_progress_scroll_ratio(row[1]),
        "font_scale": _normalize_writing_progress_font_scale(row[2]),
        "wrap_enabled": bool(row[3]),
        "focus_mode": bool(row[4]),
        "preview_visible": bool(row[5]),
        "highlight_current_line": bool(row[6]),
        "bookmark_block_number": _normalize_writing_progress_bookmark_block(row[7]),
        "updated_at": _normalize_browser_media_ref_updated_at(row[8]),
    }


def set_writing_progress(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    cursor_position: int,
    scroll_ratio: float,
    font_scale: float,
    wrap_enabled: bool,
    focus_mode: bool,
    preview_visible: bool,
    highlight_current_line: bool,
    bookmark_block_number: int,
) -> dict:
    payload = {
        "cursor_position": _normalize_writing_progress_cursor_position(cursor_position),
        "scroll_ratio": _normalize_writing_progress_scroll_ratio(scroll_ratio),
        "font_scale": _normalize_writing_progress_font_scale(font_scale),
        "wrap_enabled": bool(wrap_enabled),
        "focus_mode": bool(focus_mode),
        "preview_visible": bool(preview_visible),
        "highlight_current_line": bool(highlight_current_line),
        "bookmark_block_number": _normalize_writing_progress_bookmark_block(bookmark_block_number),
        "updated_at": int(time.time()),
    }
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO writing_progress "
        "(card_id, cursor_position, scroll_ratio, font_scale, wrap_enabled, focus_mode, "
        "preview_visible, highlight_current_line, bookmark_block_number, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "cursor_position = excluded.cursor_position, "
        "scroll_ratio = excluded.scroll_ratio, "
        "font_scale = excluded.font_scale, "
        "wrap_enabled = excluded.wrap_enabled, "
        "focus_mode = excluded.focus_mode, "
        "preview_visible = excluded.preview_visible, "
        "highlight_current_line = excluded.highlight_current_line, "
        "bookmark_block_number = excluded.bookmark_block_number, "
        "updated_at = excluded.updated_at",
        (
            int(card_id),
            payload["cursor_position"],
            payload["scroll_ratio"],
            payload["font_scale"],
            1 if payload["wrap_enabled"] else 0,
            1 if payload["focus_mode"] else 0,
            1 if payload["preview_visible"] else 0,
            1 if payload["highlight_current_line"] else 0,
            payload["bookmark_block_number"],
            payload["updated_at"],
        ),
    )
    conn.commit()
    return payload


def get_writing_word_stats(addon_dir: str, profile: str, card_id: int) -> dict:
    row = get_connection(addon_dir, profile).execute(
        "SELECT current_word_count, daily_logical_date, daily_baseline_words, updated_at "
        "FROM writing_word_stats WHERE card_id = ?",
        (int(card_id),),
    ).fetchone()
    if not row:
        return _default_writing_word_stats()
    return {
        "current_word_count": _normalize_writing_word_count(row[0]),
        "daily_logical_date": _normalize_writing_logical_date(row[1]),
        "daily_baseline_words": _normalize_writing_word_count(row[2]),
        "updated_at": _normalize_browser_media_ref_updated_at(row[3]),
    }


def set_writing_word_stats(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    current_word_count: int,
    daily_logical_date: str,
    daily_baseline_words: int,
) -> dict:
    payload = {
        "current_word_count": _normalize_writing_word_count(current_word_count),
        "daily_logical_date": _normalize_writing_logical_date(daily_logical_date),
        "daily_baseline_words": _normalize_writing_word_count(daily_baseline_words),
        "updated_at": int(time.time()),
    }
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO writing_word_stats "
        "(card_id, current_word_count, daily_logical_date, daily_baseline_words, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "current_word_count = excluded.current_word_count, "
        "daily_logical_date = excluded.daily_logical_date, "
        "daily_baseline_words = excluded.daily_baseline_words, "
        "updated_at = excluded.updated_at",
        (
            int(card_id),
            payload["current_word_count"],
            payload["daily_logical_date"],
            payload["daily_baseline_words"],
            payload["updated_at"],
        ),
    )
    conn.commit()
    return payload


def get_pdf_daily_limit_config(addon_dir: str, profile: str, card_id: int) -> dict:
    row = get_connection(addon_dir, profile).execute(
        "SELECT daily_page_limit, enforcement_mode, updated_at "
        "FROM pdf_daily_limits WHERE card_id = ?",
        (int(card_id),),
    ).fetchone()
    if not row:
        return _default_pdf_daily_limit_config()
    return {
        "daily_page_limit": _normalize_pdf_daily_limit(row[0]),
        "enforcement_mode": _normalize_pdf_limit_mode(row[1]),
        "updated_at": _normalize_browser_media_ref_updated_at(row[2]),
    }


def set_pdf_daily_limit_config(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    daily_page_limit: int,
    enforcement_mode: str = "warning",
    updated_at: int | None = None,
) -> None:
    cid = int(card_id)
    limit = _normalize_pdf_daily_limit(daily_page_limit)
    mode = _normalize_pdf_limit_mode(enforcement_mode)
    ts = _normalize_browser_media_ref_updated_at(
        int(time.time()) if updated_at is None else updated_at
    )
    conn = get_connection(addon_dir, profile)
    if limit <= 0:
        conn.execute("DELETE FROM pdf_daily_limits WHERE card_id = ?", (cid,))
        conn.commit()
        return
    conn.execute(
        "INSERT INTO pdf_daily_limits (card_id, daily_page_limit, enforcement_mode, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "daily_page_limit = excluded.daily_page_limit, "
        "enforcement_mode = excluded.enforcement_mode, "
        "updated_at = excluded.updated_at",
        (cid, limit, mode, ts),
    )
    conn.commit()


def get_pdf_daily_limit_usage(
    addon_dir: str,
    profile: str,
    card_id: int,
    logical_date: str,
) -> dict:
    date_key = _normalize_pdf_daily_limit_logical_date(logical_date)
    row = get_connection(addon_dir, profile).execute(
        "SELECT baseline_page, highest_page, override_enabled, updated_at "
        "FROM pdf_daily_limit_usage WHERE card_id = ? AND logical_date = ?",
        (int(card_id), date_key),
    ).fetchone()
    if not row:
        return _default_pdf_daily_limit_usage(date_key)
    baseline_page = _normalize_pdf_daily_limit_page(row[0])
    highest_page = max(baseline_page, _normalize_pdf_daily_limit_page(row[1]))
    return {
        "logical_date": date_key,
        "baseline_page": baseline_page,
        "highest_page": highest_page,
        "override_enabled": bool(int(row[2] or 0)),
        "updated_at": _normalize_browser_media_ref_updated_at(row[3]),
    }


def set_pdf_daily_limit_usage(
    addon_dir: str,
    profile: str,
    card_id: int,
    logical_date: str,
    *,
    baseline_page: int,
    highest_page: int,
    override_enabled: bool = False,
    updated_at: int | None = None,
) -> None:
    cid = int(card_id)
    date_key = _normalize_pdf_daily_limit_logical_date(logical_date)
    baseline = _normalize_pdf_daily_limit_page(baseline_page)
    highest = max(baseline, _normalize_pdf_daily_limit_page(highest_page))
    ts = _normalize_browser_media_ref_updated_at(
        int(time.time()) if updated_at is None else updated_at
    )
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_daily_limit_usage "
        "(card_id, logical_date, baseline_page, highest_page, override_enabled, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id, logical_date) DO UPDATE SET "
        "baseline_page = excluded.baseline_page, "
        "highest_page = excluded.highest_page, "
        "override_enabled = excluded.override_enabled, "
        "updated_at = excluded.updated_at",
        (cid, date_key, baseline, highest, 1 if override_enabled else 0, ts),
    )
    conn.commit()


def clear_pdf_daily_limit_usage(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    logical_date: str | None = None,
) -> None:
    cid = int(card_id)
    conn = get_connection(addon_dir, profile)
    if logical_date is None:
        conn.execute("DELETE FROM pdf_daily_limit_usage WHERE card_id = ?", (cid,))
    else:
        conn.execute(
            "DELETE FROM pdf_daily_limit_usage WHERE card_id = ? AND logical_date = ?",
            (cid, _normalize_pdf_daily_limit_logical_date(logical_date)),
        )
    conn.commit()


def get_pdf_due_review_prompt_config(addon_dir: str, profile: str, card_id: int) -> dict:
    row = get_connection(addon_dir, profile).execute(
        "SELECT enabled, updated_at FROM pdf_due_review_prompts WHERE card_id = ?",
        (int(card_id),),
    ).fetchone()
    if not row:
        return _default_pdf_due_review_prompt_config()
    return {
        "enabled": bool(int(row[0] or 0)),
        "updated_at": _normalize_browser_media_ref_updated_at(row[1]),
    }


def set_pdf_due_review_prompt_config(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
    updated_at: int | None = None,
) -> None:
    cid = int(card_id)
    ts = _normalize_browser_media_ref_updated_at(
        int(time.time()) if updated_at is None else updated_at
    )
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_due_review_prompts (card_id, enabled, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "enabled = excluded.enabled, "
        "updated_at = excluded.updated_at",
        (cid, 1 if enabled else 0, ts),
    )
    conn.commit()


def get_epub_daily_limit_config(addon_dir: str, profile: str, card_id: int) -> dict:
    row = get_connection(addon_dir, profile).execute(
        "SELECT daily_section_limit, enforcement_mode, updated_at "
        "FROM epub_daily_limits WHERE card_id = ?",
        (int(card_id),),
    ).fetchone()
    if not row:
        return _default_epub_daily_limit_config()
    return {
        "daily_section_limit": _normalize_epub_daily_limit_section(row[0]),
        "enforcement_mode": _normalize_pdf_limit_mode(row[1]),
        "updated_at": _normalize_browser_media_ref_updated_at(row[2]),
    }


def set_epub_daily_limit_config(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    daily_section_limit: int,
    enforcement_mode: str = "warning",
    updated_at: int | None = None,
) -> None:
    cid = int(card_id)
    limit = _normalize_epub_daily_limit_section(daily_section_limit)
    mode = _normalize_pdf_limit_mode(enforcement_mode)
    ts = _normalize_browser_media_ref_updated_at(
        int(time.time()) if updated_at is None else updated_at
    )
    conn = get_connection(addon_dir, profile)
    if limit <= 0:
        conn.execute("DELETE FROM epub_daily_limits WHERE card_id = ?", (cid,))
        conn.commit()
        return
    conn.execute(
        "INSERT INTO epub_daily_limits (card_id, daily_section_limit, enforcement_mode, updated_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "daily_section_limit = excluded.daily_section_limit, "
        "enforcement_mode = excluded.enforcement_mode, "
        "updated_at = excluded.updated_at",
        (cid, limit, mode, ts),
    )
    conn.commit()


def get_epub_daily_limit_usage(
    addon_dir: str,
    profile: str,
    card_id: int,
    logical_date: str,
) -> dict:
    date_key = _normalize_pdf_daily_limit_logical_date(logical_date)
    row = get_connection(addon_dir, profile).execute(
        "SELECT baseline_section, highest_section, override_enabled, updated_at "
        "FROM epub_daily_limit_usage WHERE card_id = ? AND logical_date = ?",
        (int(card_id), date_key),
    ).fetchone()
    if not row:
        return _default_epub_daily_limit_usage(date_key)
    baseline_section = _normalize_epub_daily_limit_section(row[0])
    highest_section = max(
        baseline_section,
        _normalize_epub_daily_limit_section(row[1]),
    )
    return {
        "logical_date": date_key,
        "baseline_section": baseline_section,
        "highest_section": highest_section,
        "override_enabled": bool(int(row[2] or 0)),
        "updated_at": _normalize_browser_media_ref_updated_at(row[3]),
    }


def set_epub_daily_limit_usage(
    addon_dir: str,
    profile: str,
    card_id: int,
    logical_date: str,
    *,
    baseline_section: int,
    highest_section: int,
    override_enabled: bool = False,
    updated_at: int | None = None,
) -> None:
    cid = int(card_id)
    date_key = _normalize_pdf_daily_limit_logical_date(logical_date)
    baseline = _normalize_epub_daily_limit_section(baseline_section)
    highest = max(baseline, _normalize_epub_daily_limit_section(highest_section))
    ts = _normalize_browser_media_ref_updated_at(
        int(time.time()) if updated_at is None else updated_at
    )
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO epub_daily_limit_usage "
        "(card_id, logical_date, baseline_section, highest_section, override_enabled, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id, logical_date) DO UPDATE SET "
        "baseline_section = excluded.baseline_section, "
        "highest_section = excluded.highest_section, "
        "override_enabled = excluded.override_enabled, "
        "updated_at = excluded.updated_at",
        (cid, date_key, baseline, highest, 1 if override_enabled else 0, ts),
    )
    conn.commit()


def clear_epub_daily_limit_usage(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    logical_date: str | None = None,
) -> None:
    cid = int(card_id)
    conn = get_connection(addon_dir, profile)
    if logical_date is None:
        conn.execute("DELETE FROM epub_daily_limit_usage WHERE card_id = ?", (cid,))
    else:
        conn.execute(
            "DELETE FROM epub_daily_limit_usage WHERE card_id = ? AND logical_date = ?",
            (cid, _normalize_pdf_daily_limit_logical_date(logical_date)),
        )
    conn.commit()


def get_epub_due_review_prompt_config(addon_dir: str, profile: str, card_id: int) -> dict:
    row = get_connection(addon_dir, profile).execute(
        "SELECT enabled, updated_at FROM epub_due_review_prompts WHERE card_id = ?",
        (int(card_id),),
    ).fetchone()
    if not row:
        return _default_epub_due_review_prompt_config()
    return {
        "enabled": bool(int(row[0] or 0)),
        "updated_at": _normalize_browser_media_ref_updated_at(row[1]),
    }


def set_epub_due_review_prompt_config(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool,
    updated_at: int | None = None,
) -> None:
    cid = int(card_id)
    ts = _normalize_browser_media_ref_updated_at(
        int(time.time()) if updated_at is None else updated_at
    )
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO epub_due_review_prompts (card_id, enabled, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "enabled = excluded.enabled, "
        "updated_at = excluded.updated_at",
        (cid, 1 if enabled else 0, ts),
    )
    conn.commit()


def _default_browser_media_ref() -> dict:
    return {
        "page_url": "",
        "media_url": "",
        "media_title": "",
        "media_seconds": 0.0,
        "updated_at": 0,
    }


def _normalize_browser_media_ref_url(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return raw


def _normalize_browser_media_ref_title(value) -> str:
    return " ".join(str(value or "").split()).strip()[:240]


def _normalize_browser_media_ref_seconds(value) -> float:
    try:
        seconds = float(value or 0.0)
    except Exception:
        seconds = 0.0
    if seconds < 0:
        seconds = 0.0
    return round(seconds, 1)


def _normalize_browser_media_ref_updated_at(value) -> int:
    try:
        ts = int(value or 0)
    except Exception:
        ts = 0
    return max(0, ts)


def _normalize_reviewer_recent_tag(value) -> str:
    return str(value or "").strip()


def _normalize_reviewer_recent_tag_key(value) -> str:
    return _normalize_reviewer_recent_tag(value).lower()


def get_card_browser_media_ref(addon_dir: str, profile: str, card_id: int) -> dict:
    row = get_connection(addon_dir, profile).execute(
        "SELECT page_url, media_url, media_title, media_seconds, updated_at "
        "FROM browser_media_refs WHERE card_id = ?",
        (int(card_id),),
    ).fetchone()
    if not row:
        return _default_browser_media_ref()
    return {
        "page_url": _normalize_browser_media_ref_url(row[0]),
        "media_url": _normalize_browser_media_ref_url(row[1]),
        "media_title": _normalize_browser_media_ref_title(row[2]),
        "media_seconds": _normalize_browser_media_ref_seconds(row[3]),
        "updated_at": _normalize_browser_media_ref_updated_at(row[4]),
    }


def set_card_browser_media_ref(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    page_url: str,
    media_seconds: float,
    media_url: str = "",
    media_title: str = "",
    updated_at: int | None = None,
) -> None:
    cid = int(card_id)
    if updated_at is None:
        updated_at = int(time.time())
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO browser_media_refs "
        "(card_id, page_url, media_url, media_title, media_seconds, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "page_url = excluded.page_url, "
        "media_url = excluded.media_url, "
        "media_title = excluded.media_title, "
        "media_seconds = excluded.media_seconds, "
        "updated_at = excluded.updated_at",
        (
            cid,
            _normalize_browser_media_ref_url(page_url),
            _normalize_browser_media_ref_url(media_url),
            _normalize_browser_media_ref_title(media_title),
            _normalize_browser_media_ref_seconds(media_seconds),
            _normalize_browser_media_ref_updated_at(updated_at),
        ),
    )
    conn.commit()


def get_recent_reviewer_tags(
    addon_dir: str,
    profile: str,
    *,
    limit: int = 10,
) -> list[str]:
    try:
        max_rows = max(1, int(limit or 10))
    except Exception:
        max_rows = 10
    rows = get_connection(addon_dir, profile).execute(
        "SELECT display_tag FROM reviewer_recent_tags "
        "ORDER BY used_at DESC, normalized_tag ASC "
        "LIMIT ?",
        (max_rows,),
    ).fetchall()
    tags: list[str] = []
    seen: set[str] = set()
    for row in rows:
        tag = _normalize_reviewer_recent_tag(row[0] if row else "")
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def touch_recent_reviewer_tags(
    addon_dir: str,
    profile: str,
    tags: list[str] | tuple[str, ...] | set[str] | str,
    *,
    limit: int = 10,
    used_at: int | None = None,
) -> None:
    if isinstance(tags, str):
        raw_tags = tags.replace("\n", " ").split()
    elif isinstance(tags, (list, tuple, set)):
        raw_tags = list(tags)
    else:
        raw_tags = []
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw_tags:
        tag = _normalize_reviewer_recent_tag(item)
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        cleaned.append(tag)
    if not cleaned:
        return

    try:
        max_rows = max(1, int(limit or 10))
    except Exception:
        max_rows = 10
    base_ts = _normalize_browser_media_ref_updated_at(
        int(time.time()) if used_at is None else used_at
    )
    conn = get_connection(addon_dir, profile)
    for offset, tag in enumerate(cleaned):
        conn.execute(
            "INSERT INTO reviewer_recent_tags (normalized_tag, display_tag, used_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(normalized_tag) DO UPDATE SET "
            "display_tag = excluded.display_tag, "
            "used_at = excluded.used_at",
            (
                _normalize_reviewer_recent_tag_key(tag),
                tag,
                max(1, base_ts + offset),
            ),
        )
    conn.execute(
        "DELETE FROM reviewer_recent_tags "
        "WHERE normalized_tag NOT IN ("
        "  SELECT normalized_tag FROM reviewer_recent_tags "
        "  ORDER BY used_at DESC, normalized_tag ASC LIMIT ?"
        ")",
        (max_rows,),
    )
    conn.commit()


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
        .execute(
            "SELECT card_id, page, zoom, read_page, read_anchor_json "
            "FROM pdf_progress ORDER BY card_id"
        )
        .fetchall()
    )
    result = {}
    for card_id, page, zoom, read_page, read_anchor_json in rows:
        item = {
            "page": page,
            "zoom": zoom,
            "read_page": read_page,
        }
        if str(read_anchor_json or "").strip():
            try:
                item["read_anchor"] = json.loads(read_anchor_json)
            except Exception:
                item["read_anchor"] = {}
        result[str(card_id)] = item
    return json.dumps(result, indent=2)


def export_highlights_json(addon_dir: str, profile: str) -> str:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT card_id, id, page, color, text, note, rects FROM pdf_highlights ORDER BY card_id"
        )
        .fetchall()
    )
    result: dict = {}
    for cid, hl_id, page, color, text, note, rects in rows:
        key = str(cid)
        result.setdefault(key, []).append(
            {
                "id": hl_id,
                "page": page,
                "color": color,
                "text": text,
                "note": note,
                "rects": json.loads(rects),
            }
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


def add_pdf_card_source(
    addon_dir: str,
    profile: str,
    pdf_card_id: int,
    page: int,
    note_id: int,
    excerpt: str = "",
    pdf_filename: str = "",
) -> None:
    """Record that note_id was created while reading pdf_card_id at page."""
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_card_sources (pdf_card_id, page, note_id, excerpt, pdf_filename) VALUES (?, ?, ?, ?, ?)",
        (pdf_card_id, page, note_id, excerpt, str(pdf_filename or "").strip()),
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


def delete_pdf_card_sources_for_note_ids(
    addon_dir: str,
    profile: str,
    pdf_card_id: int,
    note_ids: list[int] | set[int] | tuple[int, ...],
) -> int:
    normalized = sorted(
        {
            int(note_id or 0)
            for note_id in (note_ids or [])
            if int(note_id or 0) > 0
        }
    )
    if not normalized:
        return 0

    placeholders = ",".join("?" for _ in normalized)
    conn = get_connection(addon_dir, profile)
    cursor = conn.execute(
        f"DELETE FROM pdf_card_sources WHERE pdf_card_id = ? AND note_id IN ({placeholders})",
        (int(pdf_card_id), *normalized),
    )
    conn.commit()
    return int(cursor.rowcount or 0)


def get_pdf_card_sources_up_to_page(
    addon_dir: str,
    profile: str,
    pdf_card_id: int,
    max_page: int,
) -> list[dict]:
    """Return source-note rows for this PDF from page 1 through max_page."""
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT page, note_id, excerpt FROM pdf_card_sources "
            "WHERE pdf_card_id = ? AND page <= ? ORDER BY page, id",
            (int(pdf_card_id), int(max_page)),
        )
        .fetchall()
    )
    return [
        {
            "page": int(row[0]),
            "note_id": int(row[1]),
            "excerpt": row[2],
        }
        for row in rows
    ]


def get_pdf_card_source_filename(
    addon_dir: str,
    profile: str,
    pdf_card_id: int,
    page: int,
) -> str:
    row = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT pdf_filename FROM pdf_card_sources "
            "WHERE pdf_card_id = ? AND page = ? AND pdf_filename != '' "
            "ORDER BY id LIMIT 1",
            (int(pdf_card_id), int(page)),
        )
        .fetchone()
    )
    return str(row[0]).strip() if row and row[0] else ""


def get_pdf_referenced_filenames(addon_dir: str, profile: str) -> list[str]:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT DISTINCT pdf_filename FROM pdf_card_sources "
            "WHERE pdf_filename != '' ORDER BY pdf_filename"
        )
        .fetchall()
    )
    return [str(row[0]).strip() for row in rows if str(row[0]).strip()]


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


def get_pdf_document_source_note_ids(addon_dir: str, profile: str, pdf_card_id: int) -> list[int]:
    """Return distinct note ids created from this PDF, in creation order."""
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT note_id FROM pdf_card_sources WHERE pdf_card_id = ? ORDER BY id",
            (int(pdf_card_id),),
        )
        .fetchall()
    )
    seen: set[int] = set()
    ordered: list[int] = []
    for row in rows:
        try:
            note_id = int(row[0] or 0)
        except Exception:
            note_id = 0
        if note_id <= 0 or note_id in seen:
            continue
        seen.add(note_id)
        ordered.append(note_id)
    return ordered


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


def get_epub_card_sources_up_to_section(
    addon_dir: str,
    profile: str,
    epub_card_id: int,
    max_section_index: int,
) -> list[dict]:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT section_index, note_id, excerpt FROM epub_card_sources "
            "WHERE epub_card_id = ? AND section_index <= ? ORDER BY section_index, id",
            (int(epub_card_id), int(max_section_index)),
        )
        .fetchall()
    )
    return [
        {
            "section_index": int(row[0]),
            "note_id": int(row[1]),
            "excerpt": row[2],
        }
        for row in rows
    ]


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


def get_epub_document_source_note_ids(addon_dir: str, profile: str, epub_card_id: int) -> list[int]:
    """Return distinct note ids created from this EPUB, in creation order."""
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT note_id FROM epub_card_sources WHERE epub_card_id = ? ORDER BY id",
            (int(epub_card_id),),
        )
        .fetchall()
    )
    seen: set[int] = set()
    ordered: list[int] = []
    for row in rows:
        try:
            note_id = int(row[0] or 0)
        except Exception:
            note_id = 0
        if note_id <= 0 or note_id in seen:
            continue
        seen.add(note_id)
        ordered.append(note_id)
    return ordered


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
    try:
        from .statistics import _normalize_stats
    except Exception:
        try:
            from statistics import _normalize_stats  # type: ignore
        except Exception:
            _normalize_stats = lambda data: data if isinstance(data, dict) else {}

    stats_path = get_stats_path(addon_dir, profile)
    if stats_path.exists():
        try:
            with open(stats_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return json.dumps(_normalize_stats(data), indent=2, ensure_ascii=False)
        except Exception:
            pass

    rows = (
        get_connection(addon_dir, profile)
        .execute("SELECT scope, date, data FROM stats")
        .fetchall()
    )
    result: dict = {}
    for scope, date, data in rows:
        try:
            parsed = json.loads(data)
        except Exception:
            parsed = {}
        if scope == "daily":
            result["daily"] = {"date": date, "counts": parsed}
        elif scope == "time":
            result["time"] = parsed if isinstance(parsed, dict) else {}
        else:
            result[scope] = parsed
    return json.dumps(_normalize_stats(result), indent=2, ensure_ascii=False)


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


def replace_note_ocr_index(
    addon_dir: str,
    profile: str,
    note_id: int,
    card_ids: list[int],
    image_rows: list[tuple[str, str]],
    *,
    fallback_text: str = "",
) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute("DELETE FROM note_ocr_index WHERE note_id = ?", (note_id,))
    normalized_card_ids = sorted(
        {int(card_id) for card_id in list(card_ids or []) if int(card_id) > 0}
    )
    normalized_rows = [
        (str(image_name or "").strip(), (text or "").strip())
        for image_name, text in list(image_rows or [])
        if (text or "").strip()
    ]
    if not normalized_rows and str(fallback_text or "").strip():
        normalized_rows = [("", str(fallback_text or "").strip())]
    rows = [
        (int(note_id), int(card_id), image_name, text)
        for card_id in normalized_card_ids
        for image_name, text in normalized_rows
    ]
    if rows:
        conn.executemany(
            "INSERT INTO note_ocr_index (note_id, card_id, image_name, text) VALUES (?, ?, ?, ?)",
            rows,
        )
    conn.commit()


def search_note_ocr_index(
    addon_dir: str, profile: str, query: str, limit: int = 120
) -> list[tuple[int, int, str, str]]:
    query_terms = split_search_terms(query)
    if not query_terms:
        return []

    conn = get_connection(addon_dir, profile)
    pre = query_terms[0]
    rows = conn.execute(
        "SELECT note_id, card_id, image_name, text FROM note_ocr_index "
        "WHERE lower(text) LIKE lower(?) "
        "ORDER BY note_id, card_id, image_name LIMIT ?",
        (f"%{pre}%", max(500, limit * 25)),
    ).fetchall()

    ranked: list[tuple[tuple[int, int, int, int], int, int, str, str]] = []
    for note_id, card_id, image_name, text in rows:
        score = search_text_match_score(text or "", query)
        if score is None:
            continue
        ranked.append(
            (
                score,
                int(note_id),
                int(card_id),
                str(image_name or ""),
                str(text or ""),
            )
        )

    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    return [
        (note_id, card_id, image_name, text)
        for _, note_id, card_id, image_name, text in ranked[:limit]
    ]


def prune_note_ocr_index_rows(
    addon_dir: str,
    profile: str,
    *,
    live_note_ids: set[int],
    live_card_ids: set[int],
) -> dict[str, int]:
    conn = get_connection(addon_dir, profile)
    rows = conn.execute("SELECT note_id, card_id, image_name FROM note_ocr_index").fetchall()
    stale_rows: list[tuple[int, int, str]] = []
    stale_note_count = 0
    stale_card_count = 0

    for note_id, card_id, image_name in rows:
        normalized_note_id = int(note_id or 0)
        normalized_card_id = int(card_id or 0)
        normalized_image_name = str(image_name or "")
        if normalized_note_id not in live_note_ids:
            stale_rows.append((normalized_note_id, normalized_card_id, normalized_image_name))
            stale_note_count += 1
            continue
        if normalized_card_id not in live_card_ids:
            stale_rows.append((normalized_note_id, normalized_card_id, normalized_image_name))
            stale_card_count += 1

    if stale_rows:
        conn.executemany(
            "DELETE FROM note_ocr_index WHERE note_id = ? AND card_id = ? AND image_name = ?",
            stale_rows,
        )
        conn.commit()

    return {
        "note_ocr_index_missing_note": stale_note_count,
        "note_ocr_index_missing_card": stale_card_count,
        "note_ocr_index_total": stale_note_count + stale_card_count,
    }


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


def _normalize_topic_a_factor(value, default: float = _DEFAULT_TOPIC_A_FACTOR) -> float:
    try:
        a_factor = float(value)
    except Exception:
        a_factor = float(default)
    return round(max(_TOPIC_A_FACTOR_MIN, min(_TOPIC_A_FACTOR_MAX, a_factor)), 3)


def _normalize_topic_interval(value, default: float = 1.0) -> float:
    try:
        interval = float(value)
    except Exception:
        interval = float(default)
    return max(1.0, interval)


def _rounded_topic_interval(value, default: float = 1.0) -> int:
    return max(1, int(round(_normalize_topic_interval(value, default))))


def get_topic_schedule_state(
    addon_dir: str,
    profile: str,
    card_id: int,
    default_a_factor: float = _DEFAULT_TOPIC_A_FACTOR,
) -> tuple[float, float, int]:
    """Return (a_factor, precise_interval, rounded_interval) for a topic card."""
    row = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT a_factor, interval, precise_interval FROM topic_schedule WHERE card_id = ?",
            (card_id,),
        )
        .fetchone()
    )
    if not row:
        a_factor = _normalize_topic_a_factor(default_a_factor)
        return a_factor, 1.0, 1

    a_factor = _normalize_topic_a_factor(row[0])
    rounded_interval = _rounded_topic_interval(row[1], 1.0)
    precise_raw = row[2] if len(row) > 2 and row[2] is not None else row[1]
    precise_interval = _normalize_topic_interval(precise_raw, float(rounded_interval))
    return a_factor, precise_interval, _rounded_topic_interval(precise_interval, float(rounded_interval))


def get_topic_schedule(
    addon_dir: str,
    profile: str,
    card_id: int,
    default_a_factor: float = _DEFAULT_TOPIC_A_FACTOR,
) -> tuple[float, int]:
    """Return (a_factor, last_interval) for a topic card, or defaults if unseen."""
    a_factor, _precise_interval, rounded_interval = get_topic_schedule_state(
        addon_dir,
        profile,
        card_id,
        default_a_factor=default_a_factor,
    )
    return a_factor, rounded_interval


def set_topic_schedule(
    addon_dir: str,
    profile: str,
    card_id: int,
    a_factor: float,
    interval: int | float,
    *,
    precise_interval: float | None = None,
) -> None:
    normalized_precise = _normalize_topic_interval(
        interval if precise_interval is None else precise_interval
    )
    rounded_interval = _rounded_topic_interval(
        interval if precise_interval is None else normalized_precise
    )
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO topic_schedule (card_id, a_factor, interval, precise_interval) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "a_factor = excluded.a_factor, interval = excluded.interval, precise_interval = excluded.precise_interval",
        (
            card_id,
            _normalize_topic_a_factor(a_factor),
            rounded_interval,
            normalized_precise,
        ),
    )
    conn.commit()


# ── Custom schedule rules ────────────────────────────────────────────────────


def _default_custom_schedule_rule() -> dict:
    return {
        "card_id": 0,
        "enabled": True,
        "mode": "minimum_cadence",
        "interval_value": 2,
        "interval_unit": "days",
        "preset_label": "",
        "created_at": 0,
        "updated_at": 0,
    }


def _normalize_custom_schedule_mode(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"fixed_repeat", "minimum_cadence", "one_time"}:
        return raw
    return "minimum_cadence"


def _normalize_custom_schedule_unit(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"days", "weeks", "months"}:
        return raw
    return "days"


def _normalize_custom_schedule_interval_value(value) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 2
    return max(1, min(999, parsed))


def _normalize_custom_schedule_preset_label(value) -> str:
    return str(value or "").strip()[:120]


def get_custom_schedule_rule(addon_dir: str, profile: str, card_id: int) -> dict | None:
    row = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT card_id, enabled, mode, interval_value, interval_unit, preset_label, "
            "created_at, updated_at FROM custom_schedule_rules WHERE card_id = ?",
            (int(card_id),),
        )
        .fetchone()
    )
    if not row:
        return None
    return {
        "card_id": int(row[0] or 0),
        "enabled": bool(row[1]),
        "mode": _normalize_custom_schedule_mode(row[2]),
        "interval_value": _normalize_custom_schedule_interval_value(row[3]),
        "interval_unit": _normalize_custom_schedule_unit(row[4]),
        "preset_label": _normalize_custom_schedule_preset_label(row[5]),
        "created_at": int(row[6] or 0),
        "updated_at": int(row[7] or 0),
    }


def get_custom_schedule_rules(
    addon_dir: str,
    profile: str,
    card_ids: list[int] | tuple[int, ...] | set[int],
) -> dict[int, dict]:
    normalized_ids = sorted(
        {
            int(card_id)
            for card_id in (card_ids or [])
            if str(card_id).strip()
        }
    )
    if not normalized_ids:
        return {}
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT card_id, enabled, mode, interval_value, interval_unit, preset_label, "
            "created_at, updated_at FROM custom_schedule_rules "
            f"WHERE card_id IN ({','.join('?' for _ in normalized_ids)})",
            tuple(normalized_ids),
        )
        .fetchall()
    )
    return {
        int(row[0]): {
            "card_id": int(row[0] or 0),
            "enabled": bool(row[1]),
            "mode": _normalize_custom_schedule_mode(row[2]),
            "interval_value": _normalize_custom_schedule_interval_value(row[3]),
            "interval_unit": _normalize_custom_schedule_unit(row[4]),
            "preset_label": _normalize_custom_schedule_preset_label(row[5]),
            "created_at": int(row[6] or 0),
            "updated_at": int(row[7] or 0),
        }
        for row in rows
    }


def set_custom_schedule_rule(
    addon_dir: str,
    profile: str,
    card_id: int,
    *,
    enabled: bool = True,
    mode: str = "minimum_cadence",
    interval_value: int = 2,
    interval_unit: str = "days",
    preset_label: str = "",
) -> dict:
    now = int(time.time())
    card_id = int(card_id)
    existing = get_custom_schedule_rule(addon_dir, profile, card_id) or {}
    created_at = int(existing.get("created_at") or now)
    normalized = {
        "card_id": card_id,
        "enabled": bool(enabled),
        "mode": _normalize_custom_schedule_mode(mode),
        "interval_value": _normalize_custom_schedule_interval_value(interval_value),
        "interval_unit": _normalize_custom_schedule_unit(interval_unit),
        "preset_label": _normalize_custom_schedule_preset_label(preset_label),
        "created_at": created_at,
        "updated_at": now,
    }
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO custom_schedule_rules "
        "(card_id, enabled, mode, interval_value, interval_unit, preset_label, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET "
        "enabled = excluded.enabled, "
        "mode = excluded.mode, "
        "interval_value = excluded.interval_value, "
        "interval_unit = excluded.interval_unit, "
        "preset_label = excluded.preset_label, "
        "updated_at = excluded.updated_at",
        (
            normalized["card_id"],
            1 if normalized["enabled"] else 0,
            normalized["mode"],
            normalized["interval_value"],
            normalized["interval_unit"],
            normalized["preset_label"],
            normalized["created_at"],
            normalized["updated_at"],
        ),
    )
    conn.commit()
    return dict(normalized)


def clear_custom_schedule_rule(addon_dir: str, profile: str, card_id: int) -> bool:
    conn = get_connection(addon_dir, profile)
    cursor = conn.execute(
        "DELETE FROM custom_schedule_rules WHERE card_id = ?",
        (int(card_id),),
    )
    conn.commit()
    return int(getattr(cursor, "rowcount", 0) or 0) > 0


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
