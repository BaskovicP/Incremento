import json

try:
    from .db import get_connection
    from .highlight_colors import normalize_highlight_color
except ImportError:
    from highlight_colors import normalize_highlight_color
    from db import get_connection  # test environment (backend/ on sys.path)


RESIZE_REVISION_KEY = "incremento_resize_revision"


def load_highlights(addon_dir: str, profile: str, card_id: int) -> list:
    rows = get_connection(addon_dir, profile).execute(
        "SELECT id, page, color, text, note, rects, annotation_json FROM pdf_highlights WHERE card_id = ?",
        (card_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "page": r[1],
            "color": r[2],
            "text": r[3],
            "note": r[4],
            "rects": json.loads(r[5]),
            **({'pdf_annotation': json.loads(r[6])} if r[6] != '{}' else {}),
        }
        for r in rows
    ]


def add_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> None:
    color = normalize_highlight_color(hl.get("color", "yellow"), allow_snapshot=True)
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT OR REPLACE INTO pdf_highlights (id, card_id, page, color, text, note, rects, annotation_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            hl["id"],
            card_id,
            hl.get("page", 1),
            color,
            hl.get("text", ""),
            hl.get("note", ""),
            json.dumps(hl.get("rects", [])),
            json.dumps(hl.get('pdf_annotation', {})),
        ),
    )
    conn.commit()


def update_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> bool:
    """Update an existing highlight without ever creating a replacement row."""
    color = normalize_highlight_color(hl.get("color", "yellow"), allow_snapshot=True)
    conn = get_connection(addon_dir, profile)
    existing = conn.execute(
        "SELECT annotation_json FROM pdf_highlights WHERE id = ? AND card_id = ?",
        (hl["id"], card_id),
    ).fetchone()
    if existing is None:
        return False
    try:
        existing_annotation = json.loads(existing[0])
    except (TypeError, ValueError):
        existing_annotation = {}
    if not isinstance(existing_annotation, dict):
        existing_annotation = {}
    incoming_annotation = hl.get("pdf_annotation", {})
    if not isinstance(incoming_annotation, dict):
        incoming_annotation = {}
    annotation = {**existing_annotation, **incoming_annotation}
    # Resizing invalidates native geometry. The annotation synchronizer will
    # rebuild it while retaining the stable annotation identity and style.
    annotation.pop("quads", None)
    annotation.pop("xref", None)
    revision = existing_annotation.get(RESIZE_REVISION_KEY, 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        revision = 0
    annotation[RESIZE_REVISION_KEY] = revision + 1
    cursor = conn.execute(
        "UPDATE pdf_highlights SET page = ?, color = ?, text = ?, note = ?, "
        "rects = ?, annotation_json = ? WHERE id = ? AND card_id = ?",
        (
            hl.get("page", 1),
            color,
            hl.get("text", ""),
            hl.get("note", ""),
            json.dumps(hl.get("rects", [])),
            json.dumps(annotation),
            hl["id"],
            card_id,
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
        "DELETE FROM pdf_highlights WHERE card_id = ? AND id = ?",
        (card_id, hl_id),
    )
    conn.commit()
