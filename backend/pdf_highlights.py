import json

try:
    from .db import get_connection
except ImportError:
    from db import get_connection  # test environment (backend/ on sys.path)


def load_highlights(addon_dir: str, profile: str, card_id: int) -> list:
    rows = get_connection(addon_dir, profile).execute(
        "SELECT id, page, color, text, rects FROM pdf_highlights WHERE card_id = ?",
        (card_id,),
    ).fetchall()
    return [
        {"id": r[0], "page": r[1], "color": r[2], "text": r[3], "rects": json.loads(r[4])}
        for r in rows
    ]


def add_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT OR REPLACE INTO pdf_highlights (id, card_id, page, color, text, rects) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            hl["id"],
            card_id,
            hl.get("page", 1),
            hl.get("color", "yellow"),
            hl.get("text", ""),
            json.dumps(hl.get("rects", [])),
        ),
    )
    conn.commit()


def remove_highlight(addon_dir: str, profile: str, card_id: int, hl_id: str) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "DELETE FROM pdf_highlights WHERE card_id = ? AND id = ?",
        (card_id, hl_id),
    )
    conn.commit()
