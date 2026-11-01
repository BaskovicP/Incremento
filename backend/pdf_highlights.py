import json

try:
    from .db import get_connection
    from .annotation_notes import normalize_note
    from .highlight_colors import normalize_highlight_color
    from .annotation_styles import pdf_style_metadata
except ImportError:
    from annotation_notes import normalize_note
    from highlight_colors import normalize_highlight_color
    from annotation_styles import pdf_style_metadata
    from db import get_connection  # test environment (backend/ on sys.path)


RESIZE_REVISION_KEY = "incremento_resize_revision"


def load_highlights(addon_dir: str, profile: str, card_id: int) -> list:
    rows = get_connection(addon_dir, profile).execute(
        "SELECT id, page, color, text, note, rects, annotation_json, note_html FROM pdf_highlights WHERE card_id = ?",
        (card_id,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "page": r[1],
            "color": r[2],
            "text": r[3],
            "note": r[4],
            **({'note_html': html} if (html := normalize_note(r[4], r[7])[1]) else {}),
            "rects": json.loads(r[5]),
            **({'pdf_annotation': json.loads(r[6])} if r[6] != '{}' else {}),
        }
        for r in rows
    ]


def add_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> None:
    color = normalize_highlight_color(hl.get("color", "yellow"), allow_snapshot=True)
    note, note_html = normalize_note(hl.get('note'), hl.get('note_html'))
    annotation = hl.get('pdf_annotation', {})
    if 'style' in hl:
        annotation = pdf_style_metadata(annotation, hl['style'])
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT OR REPLACE INTO pdf_highlights (id, card_id, page, color, text, note, rects, annotation_json, note_html) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            hl["id"],
            card_id,
            hl.get("page", 1),
            color,
            hl.get("text", ""),
            note,
            json.dumps(hl.get("rects", [])),
            json.dumps(annotation),
            note_html,
        ),
    )
    conn.commit()


def update_highlight(addon_dir: str, profile: str, card_id: int, hl: dict) -> bool:
    """Update geometry/color; independently edited notes must survive stale views."""
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
    if 'style' in hl:
        annotation = pdf_style_metadata(annotation, hl['style'])
    else:
        # A range/color edit from a stale pane must retain a newer style.
        # Style changes carry an explicit intent separate from native metadata.
        for key in ('kind', 'incremento_style', 'opacity'):
            if key in existing_annotation:
                annotation[key] = existing_annotation[key]
    # Resizing invalidates native geometry. The annotation synchronizer will
    # rebuild it while retaining the stable annotation identity and style.
    annotation.pop("quads", None)
    annotation.pop("xref", None)
    revision = existing_annotation.get(RESIZE_REVISION_KEY, 0)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        revision = 0
    annotation[RESIZE_REVISION_KEY] = revision + 1
    cursor = conn.execute(
        "UPDATE pdf_highlights SET page = ?, color = ?, text = ?, "
        "rects = ?, annotation_json = ? WHERE id = ? AND card_id = ?",
        (
            hl.get("page", 1),
            color,
            hl.get("text", ""),
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
    *,
    note_html: str = '',
    expected_note: tuple[str, str] | None = None,
) -> dict | None:
    target_id = str(hl_id or "")
    updated_note, markup = normalize_note(note, note_html)
    conn = get_connection(addon_dir, profile)
    expected_values = ()
    condition = ''
    if expected_note is not None:
        previous = conn.execute('SELECT note, note_html FROM pdf_highlights WHERE card_id=? AND id=?',
                                (int(card_id), target_id)).fetchone()
        if previous is None or normalize_note(*previous) != normalize_note(*expected_note):
            return None
        condition, expected_values = ' AND note=? AND note_html=?', tuple(previous)
    with conn:
        changed = conn.execute('UPDATE pdf_highlights SET note=?, note_html=? WHERE card_id=? AND id=?' + condition,
                               (updated_note, markup, int(card_id), target_id, *expected_values)).rowcount
    if not changed:
        return None
    return next((row for row in load_highlights(addon_dir, profile, int(card_id)) if row['id'] == target_id), None)


def remove_highlight(addon_dir: str, profile: str, card_id: int, hl_id: str) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "DELETE FROM pdf_highlights WHERE card_id = ? AND id = ?",
        (card_id, hl_id),
    )
    conn.commit()
