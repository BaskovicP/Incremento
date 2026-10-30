from __future__ import annotations

try:
    from .db import get_connection
    from .annotation_notes import normalize_note
    from .highlight_colors import normalize_highlight_color
    from .annotation_styles import normalize_annotation_style
except ImportError:
    from annotation_notes import normalize_note
    from highlight_colors import normalize_highlight_color
    from annotation_styles import normalize_annotation_style
    from db import get_connection  # type: ignore


def load_highlights(
    addon_dir: str, profile: str, card_id: int, *, section_index: int | None = None,
) -> list[dict]:
    section_filter = " AND section_index = ?" if section_index is not None else ""
    params = (card_id, int(section_index)) if section_index is not None else (card_id,)
    rows = (
        get_connection(addon_dir, profile)
        .execute(
            "SELECT id, section_index, color, text, note, start_offset, end_offset, note_html, style "
            "FROM epub_highlights WHERE card_id = ?" + section_filter + " ORDER BY section_index, start_offset, id",
            params,
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
            **({'note_html': html} if (html := normalize_note(r[4], r[7])[1]) else {}),
            "startOffset": int(r[5]),
            "endOffset": int(r[6]),
            **({'style': r[8]} if r[8] != 'highlight' else {}),
        }
        for r in rows
    ]


def count_highlights(addon_dir: str, profile: str, card_id: int, *, section_index: int | None = None) -> int:
    section_filter = " AND section_index = ?" if section_index is not None else ""
    params = (card_id, int(section_index)) if section_index is not None else (card_id,)
    return int(get_connection(addon_dir, profile).execute(
        "SELECT COUNT(*) FROM epub_highlights WHERE card_id = ?" + section_filter, params,
    ).fetchone()[0])


def add_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> None:
    color = normalize_highlight_color(str(hl.get("color") or "yellow"), allow_snapshot=False)
    style = normalize_annotation_style(hl.get('style', 'highlight'))
    note, note_html = normalize_note(hl.get('note'), hl.get('note_html'))
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT OR REPLACE INTO epub_highlights "
        "(id, card_id, section_index, color, text, note, start_offset, end_offset, note_html, style) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(hl.get("id") or ""),
            int(card_id),
            int(hl.get("sectionIndex", 0) or 0),
            color,
            str(hl.get("text") or ""),
            note,
            int(hl.get("startOffset", 0) or 0),
            int(hl.get("endOffset", 0) or 0),
            note_html,
            style,
        ),
    )
    conn.commit()


def update_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> bool:
    """Update geometry/color; independently edited notes/styles survive stale views."""
    color = normalize_highlight_color(str(hl.get("color") or "yellow"), allow_snapshot=False)
    conn = get_connection(addon_dir, profile)
    cursor = conn.execute(
        "UPDATE epub_highlights SET section_index = ?, color = ?, text = ?, "
        "start_offset = ?, end_offset = ? WHERE id = ? AND card_id = ?",
        (
            int(hl.get("sectionIndex", 0) or 0),
            color,
            str(hl.get("text") or ""),
            int(hl.get("startOffset", 0) or 0),
            int(hl.get("endOffset", 0) or 0),
            str(hl.get("id") or ""),
            int(card_id),
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def update_highlight_note(
    addon_dir: str,
    profile: str,
    card_id: int,
    hl_id: str,
    note: str,
    *,
    note_html: str = '',
) -> dict | None:
    target_id = str(hl_id or "")
    updated_note, markup = normalize_note(note, note_html)
    conn = get_connection(addon_dir, profile)
    with conn:
        changed = conn.execute('UPDATE epub_highlights SET note=?, note_html=? WHERE card_id=? AND id=?',
                               (updated_note, markup, int(card_id), target_id)).rowcount
    if not changed:
        return None
    return next((row for row in load_highlights(addon_dir, profile, int(card_id)) if row['id'] == target_id), None)


def remove_highlight(addon_dir: str, profile: str, card_id: int, hl_id: str) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "DELETE FROM epub_highlights WHERE card_id = ? AND id = ?",
        (int(card_id), str(hl_id or "")),
    )
    conn.commit()


def update_highlight_color(addon_dir: str, profile: str, card_id: int, hl_id: str, color: str) -> bool:
    """Recolor in place: preserve identity, notes, ranges, and attached cards."""
    color = normalize_highlight_color(color, allow_snapshot=False)
    conn = get_connection(addon_dir, profile)
    with conn:
        return conn.execute("UPDATE epub_highlights SET color=? WHERE card_id=? AND id=?",
                            (color, card_id, hl_id)).rowcount > 0


def update_highlight_style(addon_dir: str, profile: str, card_id: int, hl_id: str, style: str) -> bool:
    style = normalize_annotation_style(style)
    conn = get_connection(addon_dir, profile)
    with conn:
        return conn.execute('UPDATE epub_highlights SET style=? WHERE card_id=? AND id=?',
                            (style, card_id, hl_id)).rowcount > 0
