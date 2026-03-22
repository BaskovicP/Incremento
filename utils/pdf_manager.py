import os
from pathlib import Path

from PyQt6.QtPdf import QPdfDocument

try:
    from .db import get_connection
except ImportError:
    from db import get_connection  # test environment (utils/ on sys.path)

PDF_NOTE_TYPE = "Incremento PDF"

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">PDF open in sidebar &nbsp;·&nbsp; select text → ⌘C → ⌘1–4 to fill fields</div>
</div>
{{PDF_Filename}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


# ---------------------------------------------------------------------------
# Page progress I/O
# ---------------------------------------------------------------------------

def get_page(addon_dir: str, card_id: int) -> int:
    row = get_connection(addon_dir).execute(
        "SELECT page FROM pdf_progress WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row[0] if row else 1


def get_zoom(addon_dir: str, card_id: int) -> float:
    row = get_connection(addon_dir).execute(
        "SELECT zoom FROM pdf_progress WHERE card_id = ?", (card_id,)
    ).fetchone()
    return row[0] if row else 1.0


def set_page(addon_dir: str, card_id: int, page: int) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, ?, 1.0) "
        "ON CONFLICT(card_id) DO UPDATE SET page = excluded.page",
        (card_id, page),
    )
    conn.commit()


def set_zoom(addon_dir: str, card_id: int, zoom: float) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, 1, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET zoom = excluded.zoom",
        (card_id, round(float(zoom), 2)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Note type management
# ---------------------------------------------------------------------------

def extract_pdf_text(pdf_path: str) -> str:
    """Extract all text from a PDF using Qt's QPdfDocument. Returns empty string on failure."""
    doc = QPdfDocument(None)
    try:
        if doc.load(pdf_path) != QPdfDocument.Status.Ready:
            return ""
        pages = []
        for i in range(doc.pageCount()):
            sel = doc.getAllText(i)
            if sel.isValid():
                t = sel.text().strip()
                if t:
                    pages.append(t)
        return "\n\n".join(pages)
    except Exception:
        return ""
    finally:
        doc.close()


def ensure_pdf_note_type(col) -> None:
    """Create the Incremento PDF note type, or update its template/fields if it already exists."""
    models = col.models
    m = models.by_name(PDF_NOTE_TYPE)

    if m is None:
        m = models.new(PDF_NOTE_TYPE)
        for field_name in ("Title", "PDF_Filename", "Content"):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        changed = False
        # Add Content field if missing (migration for existing note types)
        existing_names = [f["name"] for f in m["flds"]]
        if "Content" not in existing_names:
            fld = models.new_field("Content")
            models.add_field(m, fld)
            changed = True
        # Sync template
        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            changed = True
        if changed:
            models.update_dict(m)


# ---------------------------------------------------------------------------
# Card creation
# ---------------------------------------------------------------------------

def add_pdf_card(addon_dir: str, col, pdf_path: str, title: str,
                 deck_name: str = "Topics") -> int:
    """Copy PDF to media, create note, return card id."""
    ensure_pdf_note_type(col)

    # Copy file to Anki media folder; returns (possibly deduplicated) filename
    media_filename = col.media.add_file(pdf_path)

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(PDF_NOTE_TYPE)
    note = col.new_note(model)
    note["Title"] = title
    note["PDF_Filename"] = media_filename
    note["Content"] = extract_pdf_text(pdf_path)
    note.note_type()["did"] = deck_id
    col.add_note(note, deck_id)

    # Return the id of the first (and only) card created
    return col.find_cards(f"nid:{note.id}")[0]
