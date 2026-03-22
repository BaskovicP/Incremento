"""
Central SQLite database for all Incremento user data.

One connection is kept open per addon_dir (re-initialised if the path changes).
WAL mode + NORMAL synchronous gives fast writes while staying crash-safe.

Tables
------
pdf_progress   — reading position and zoom per card
pdf_highlights — highlighted passages per card
stats          — daily and lifetime review statistics (JSON blobs per scope)
priorities     — card priority values
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
        _migrate(conn, addon_dir)
        _connection = conn
        _initialized_for = addon_dir
    return _connection


# ── Schema ────────────────────────────────────────────────────────────────────

def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pdf_progress (
            card_id INTEGER PRIMARY KEY,
            page    INTEGER NOT NULL DEFAULT 1,
            zoom    REAL    NOT NULL DEFAULT 1.0
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
    """)


# ── One-time JSON / legacy SQLite migration ───────────────────────────────────

def _migrate(conn: sqlite3.Connection, addon_dir: str) -> None:
    user_files = Path(addon_dir) / "user_files"

    # priorities.db (legacy separate SQLite) → priorities table
    old_db = user_files / "priorities.db"
    if old_db.exists():
        try:
            old = sqlite3.connect(str(old_db))
            rows = old.execute("SELECT card_id, priority FROM priorities").fetchall()
            old.close()
            conn.executemany(
                "INSERT OR IGNORE INTO priorities (card_id, priority) VALUES (?, ?)", rows
            )
            conn.commit()
            old_db.unlink()
        except Exception:
            pass

    # priorities.json → priorities table
    _migrate_json_file(
        conn, user_files / "priorities.json",
        lambda data: conn.executemany(
            "INSERT OR IGNORE INTO priorities (card_id, priority) VALUES (?, ?)",
            ((int(k), round(float(v), 4)) for k, v in data.items()),
        ),
    )

    # pdf_progress.json → pdf_progress table
    def _import_progress(data):
        rows = []
        for k, v in data.items():
            cid = int(k)
            if isinstance(v, int):
                rows.append((cid, v, 1.0))
            elif isinstance(v, dict):
                rows.append((cid, v.get("page", 1), v.get("zoom", 1.0)))
        conn.executemany(
            "INSERT OR IGNORE INTO pdf_progress (card_id, page, zoom) VALUES (?, ?, ?)", rows
        )
    _migrate_json_file(conn, user_files / "pdf_progress.json", _import_progress)

    # pdf_highlights.json → pdf_highlights table
    def _import_highlights(data):
        rows = []
        for k, hls in data.items():
            cid = int(k)
            for hl in hls:
                rows.append((
                    hl.get("id", ""),
                    cid,
                    hl.get("page", 1),
                    hl.get("color", "yellow"),
                    hl.get("text", ""),
                    json.dumps(hl.get("rects", [])),
                ))
        conn.executemany(
            "INSERT OR IGNORE INTO pdf_highlights (id, card_id, page, color, text, rects) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    _migrate_json_file(conn, user_files / "pdf_highlights.json", _import_highlights)

    # custom_learn_stats.json → stats table
    def _import_stats(raw):
        if "daily" in raw:
            d = raw["daily"]
            conn.execute(
                "INSERT OR IGNORE INTO stats (scope, date, data) VALUES (?, ?, ?)",
                ("daily", d.get("date"), json.dumps(d.get("counts", {}))),
            )
        if "lifetime" in raw:
            conn.execute(
                "INSERT OR IGNORE INTO stats (scope, date, data) VALUES (?, ?, ?)",
                ("lifetime", None, json.dumps(raw["lifetime"])),
            )
    _migrate_json_file(conn, user_files / "custom_learn_stats.json", _import_stats)


def _migrate_json_file(conn, path: Path, importer) -> None:
    """Load a JSON file, call importer(data), commit, delete the file. Best-effort."""
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        importer(data)
        conn.commit()
        path.unlink()
    except Exception:
        pass


# ── Export helpers (called by the export function in __init__.py) ─────────────

def export_priorities_json(addon_dir: str) -> str:
    rows = get_connection(addon_dir).execute(
        "SELECT card_id, priority FROM priorities ORDER BY card_id"
    ).fetchall()
    return json.dumps({str(r[0]): r[1] for r in rows}, indent=2)


def export_pdf_progress_json(addon_dir: str) -> str:
    rows = get_connection(addon_dir).execute(
        "SELECT card_id, page, zoom FROM pdf_progress ORDER BY card_id"
    ).fetchall()
    return json.dumps({str(r[0]): {"page": r[1], "zoom": r[2]} for r in rows}, indent=2)


def export_highlights_json(addon_dir: str) -> str:
    rows = get_connection(addon_dir).execute(
        "SELECT card_id, id, page, color, text, rects FROM pdf_highlights ORDER BY card_id"
    ).fetchall()
    result: dict = {}
    for cid, hl_id, page, color, text, rects in rows:
        key = str(cid)
        result.setdefault(key, []).append(
            {"id": hl_id, "page": page, "color": color,
             "text": text, "rects": json.loads(rects)}
        )
    return json.dumps(result, indent=2, ensure_ascii=False)


def export_stats_json(addon_dir: str) -> str:
    rows = get_connection(addon_dir).execute(
        "SELECT scope, date, data FROM stats"
    ).fetchall()
    result: dict = {}
    for scope, date, data in rows:
        if scope == "daily":
            result["daily"] = {"date": date, "counts": json.loads(data)}
        else:
            result[scope] = json.loads(data)
    return json.dumps(result, indent=2, ensure_ascii=False)
