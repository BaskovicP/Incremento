import json
import os
from pathlib import Path

from PyQt6.QtPdf import QPdfDocument

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

def _progress_path(addon_dir: str) -> Path:
    path = Path(addon_dir) / "user_files" / "pdf_progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_pdf_progress(addon_dir: str) -> dict:
    path = _progress_path(addon_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_pdf_progress(addon_dir: str, data: dict) -> None:
    path = _progress_path(addon_dir)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, path)


def _card_progress(data: dict, card_id: int) -> dict:
    """Return the progress dict for a card, migrating old int-only format."""
    val = data.get(str(card_id))
    if val is None:
        return {"page": 1, "zoom": 1.0}
    if isinstance(val, int):
        return {"page": val, "zoom": 1.0}
    return val


def get_page(addon_dir: str, card_id: int) -> int:
    return _card_progress(load_pdf_progress(addon_dir), card_id).get("page", 1)


def get_zoom(addon_dir: str, card_id: int) -> float:
    return _card_progress(load_pdf_progress(addon_dir), card_id).get("zoom", 1.0)


def set_page(addon_dir: str, card_id: int, page: int) -> None:
    data = load_pdf_progress(addon_dir)
    prog = _card_progress(data, card_id)
    prog["page"] = page
    data[str(card_id)] = prog
    save_pdf_progress(addon_dir, data)


def set_zoom(addon_dir: str, card_id: int, zoom: float) -> None:
    data = load_pdf_progress(addon_dir)
    prog = _card_progress(data, card_id)
    prog["zoom"] = round(float(zoom), 2)
    data[str(card_id)] = prog
    save_pdf_progress(addon_dir, data)


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
