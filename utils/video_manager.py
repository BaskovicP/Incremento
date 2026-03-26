import re

try:
    from .db import get_connection
except ImportError:
    from db import get_connection

VIDEO_NOTE_TYPE = "Incremento Video"

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">Video open in sidebar &nbsp;&middot;&nbsp; use &ldquo;Add Card&rdquo; button to bookmark moments</div>
</div>
{{YouTube_URL}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


def extract_video_id(url: str) -> str | None:
    """Return the 11-char YouTube video ID from any common YouTube URL format."""
    m = re.search(r'(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})', url)
    return m.group(1) if m else None


def fmt_time(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    t = int(seconds)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def get_video_position(addon_dir: str, card_id: int) -> float:
    row = get_connection(addon_dir).execute(
        "SELECT position FROM video_progress WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row[0] if row else 0.0


def set_video_position(addon_dir: str, card_id: int, position: float) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO video_progress (card_id, position) VALUES (?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET position = excluded.position",
        (card_id, round(float(position), 1)),
    )
    conn.commit()


def ensure_video_note_type(col) -> None:
    """Create the Incremento Video note type, or sync its template if it already exists."""
    models = col.models
    m = models.by_name(VIDEO_NOTE_TYPE)
    if m is None:
        m = models.new(VIDEO_NOTE_TYPE)
        for field_name in ("Title", "YouTube_URL"):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            models.update_dict(m)


def add_video_card(
    col,
    youtube_url: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
) -> int:
    """Create an Incremento Video note, return the card id."""
    ensure_video_note_type(col)
    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]
    model = col.models.by_name(VIDEO_NOTE_TYPE)
    note = col.new_note(model)
    note["Title"] = title
    note["YouTube_URL"] = youtube_url
    for tag in tags or []:
        if not tag:
            continue
        if hasattr(note, "add_tag"):
            note.add_tag(tag)
        elif hasattr(note, "tags"):
            note.tags.append(tag)
    note.note_type()["did"] = deck_id
    col.add_note(note, deck_id)
    return col.find_cards(f"nid:{note.id}")[0]
