try:
    from .db import get_connection
except ImportError:
    from db import get_connection

WEB_NOTE_TYPE = "Incremento Web"

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">Web page open in sidebar</div>
</div>
{{URL}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


def get_web_url(addon_dir: str, card_id: int) -> str:
    """Return the last visited URL for this card, or '' if never saved."""
    row = get_connection(addon_dir).execute(
        "SELECT url FROM web_progress WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row[0] if row else ""


def set_web_url(addon_dir: str, card_id: int, url: str) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO web_progress (card_id, url) VALUES (?, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET url = excluded.url",
        (card_id, url),
    )
    conn.commit()


def ensure_web_note_type(col) -> None:
    """Create the Incremento Web note type, or sync its template if it already exists."""
    models = col.models
    m = models.by_name(WEB_NOTE_TYPE)
    if m is None:
        m = models.new(WEB_NOTE_TYPE)
        for field_name in ("Title", "URL"):
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


def add_web_card(
    col,
    url: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
) -> int:
    """Create an Incremento Web note, return the card id."""
    ensure_web_note_type(col)
    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]
    model = col.models.by_name(WEB_NOTE_TYPE)
    note = col.new_note(model)
    note["Title"] = title
    note["URL"] = url
    for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
        if not tag:
            continue
        if hasattr(note, "add_tag"):
            note.add_tag(tag)
        elif hasattr(note, "tags"):
            note.tags.append(tag)
    note.note_type()["did"] = deck_id
    col.add_note(note, deck_id)
    return col.find_cards(f"nid:{note.id}")[0]
