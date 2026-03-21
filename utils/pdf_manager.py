import json
import os
from pathlib import Path

PDF_NOTE_TYPE = "Incremento PDF"

CARD_TEMPLATE_FRONT = r"""
<script src="/_addons/incremento/user_files/pdfjs/pdf.min.js"></script>
<style>
#pdf-text-layer {
  user-select: text !important;
  -webkit-user-select: text !important;
}
#pdf-text-layer span {
  color: transparent; position: absolute; white-space: pre; cursor: text;
  transform-origin: 0% 0%;
  user-select: text !important;
  -webkit-user-select: text !important;
}
#pdf-text-layer ::selection { background: rgba(0,100,255,0.3); color: transparent; }
</style>
<div id="incremento-pdf-meta"
     data-filename="{{PDF_Filename}}"
     data-title="{{Title}}"
     style="display:none">{{PDF_Filename}}</div>
<div id="pdf-react-root"></div>
<script src="/_addons/incremento/user_files/dist/pdf_viewer.js"></script>
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


def get_page(addon_dir: str, card_id: int) -> int:
    data = load_pdf_progress(addon_dir)
    return data.get(str(card_id), 1)


def set_page(addon_dir: str, card_id: int, page: int) -> None:
    data = load_pdf_progress(addon_dir)
    data[str(card_id)] = page
    save_pdf_progress(addon_dir, data)


# ---------------------------------------------------------------------------
# Note type management
# ---------------------------------------------------------------------------

def ensure_pdf_note_type(col) -> None:
    """Create the Incremento PDF note type, or update its template if it already exists."""
    models = col.models
    m = models.by_name(PDF_NOTE_TYPE)

    if m is None:
        m = models.new(PDF_NOTE_TYPE)
        for field_name in ("Title", "PDF_Filename"):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        # Always sync the template so code changes take effect without manual DB edits.
        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
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
    note.note_type()["did"] = deck_id
    col.add_note(note, deck_id)

    # Return the id of the first (and only) card created
    return col.find_cards(f"nid:{note.id}")[0]
