import json
import sqlite3
from pathlib import Path


def _db_path(addon_dir: str) -> Path:
    p = Path(addon_dir) / "user_files" / "priorities.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _connect(addon_dir: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path(addon_dir)))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS priorities "
        "(card_id INTEGER PRIMARY KEY, priority REAL NOT NULL)"
    )
    conn.commit()
    _migrate_json(addon_dir, conn)
    return conn


def _migrate_json(addon_dir: str, conn: sqlite3.Connection) -> None:
    """One-time import of legacy priorities.json, then delete it."""
    json_path = Path(addon_dir) / "user_files" / "priorities.json"
    if not json_path.exists():
        return
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        conn.executemany(
            "INSERT OR IGNORE INTO priorities (card_id, priority) VALUES (?, ?)",
            ((int(k), round(float(v), 4)) for k, v in data.items()),
        )
        conn.commit()
        json_path.unlink()
    except Exception:
        pass  # migration is best-effort; don't break startup


def get_priority(addon_dir: str, card_id: int) -> float:
    """Return card priority (0.0 = most important, 100.0 = least). Default 50.0."""
    with _connect(addon_dir) as conn:
        row = conn.execute(
            "SELECT priority FROM priorities WHERE card_id = ?", (card_id,)
        ).fetchone()
    return row[0] if row else 50.0


def set_priority(addon_dir: str, card_id: int, priority: float) -> None:
    """Persist priority (0.0–100.0, stored to 4 decimal places)."""
    with _connect(addon_dir) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO priorities (card_id, priority) VALUES (?, ?)",
            (card_id, round(float(priority), 4)),
        )


def get_all_priorities(addon_dir: str) -> dict[int, float]:
    """Return all stored priorities as {card_id: priority}. Useful for bulk scheduler reads."""
    with _connect(addon_dir) as conn:
        rows = conn.execute("SELECT card_id, priority FROM priorities").fetchall()
    return {r[0]: r[1] for r in rows}
