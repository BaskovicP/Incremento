from __future__ import annotations

try:
    from .db import get_connection
except ImportError:
    from db import get_connection  # type: ignore


def load_highlights(addon_dir: str, profile: str, card_id: int) -> list[dict]:
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT id, section_index, color, text, note, start_offset, end_offset "
            "FROM epub_highlights WHERE card_id = ? ORDER BY section_index, start_offset, id",
            (card_id,),
        )
        .fetchall()
    )
    return [
        {
            "id": r[0],
            "sectionIndex": int(r[1]),
            "color": r[2],
            "text": r[3],
            "note": r[4],
            "startOffset": int(r[5]),
            "endOffset": int(r[6]),
        }
        for r in rows
    ]


def add_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT OR REPLACE INTO epub_highlights "
        "(id, card_id, section_index, color, text, note, start_offset, end_offset) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(hl.get("id") or ""),
            int(card_id),
            int(hl.get("sectionIndex", 0) or 0),
            str(hl.get("color") or "yellow"),
            str(hl.get("text") or ""),
            str(hl.get("note") or ""),
            int(hl.get("startOffset", 0) or 0),
            int(hl.get("endOffset", 0) or 0),
        ),
    )
    conn.commit()


def update_highlight_note(
    addon_dir: str,
    profile: str,
    card_id: int,
    hl_id: str,
    note: str,
) -> dict | None:
    rows = load_highlights(addon_dir, profile, int(card_id))
    target_id = str(hl_id or "")
    updated_note = str(note or "")
    for highlight in rows:
        if str(highlight.get("id") or "") != target_id:
            continue
        highlight["note"] = updated_note
        add_highlight(addon_dir, profile, int(card_id), highlight)
        return highlight
    return None


def remove_highlight(addon_dir: str, profile: str, card_id: int, hl_id: str) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "DELETE FROM epub_highlights WHERE card_id = ? AND id = ?",
        (int(card_id), str(hl_id or "")),
    )
    conn.commit()
