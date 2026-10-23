"""Read-only resolution for reference readers; no repair or import side effects."""
from pathlib import Path

try:
    from .paths import get_pdf_dir
except ImportError:
    from paths import get_pdf_dir


def resolve_pdf_reference(addon_dir, profile, collection, card_id):
    if type(card_id) is not int or card_id <= 0:
        raise ValueError("Invalid PDF card")
    try:
        card = collection.get_card(card_id)
        note = collection.get_note(card.nid)
        filename = str(note["PDF_Filename"] or "").strip()
        title = str(note["Title"] or "").strip()
    except Exception as error:
        raise ValueError("PDF card unavailable") from error
    root = get_pdf_dir(addon_dir, profile).resolve()
    raw = filename.replace("\\", "/")
    if raw.startswith("user_files/") and "/pdfs/" in raw:
        raw = raw.split("/pdfs/", 1)[1]
    elif raw.startswith("pdfs/"):
        raw = raw[5:]
    candidate = Path(raw)
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if not raw or not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Managed PDF unavailable")
    return {"card_id": card_id, "filename": filename, "path": str(path), "title": title or path.stem}
