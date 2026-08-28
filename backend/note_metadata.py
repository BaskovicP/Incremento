from __future__ import annotations

import copy
import os
import re
import uuid
from datetime import datetime
from html import unescape

INCREMENTO_SOURCE_TYPE_FIELD = "Incremento_Source_Type"
INCREMENTO_SOURCE_TITLE_FIELD = "Incremento_Source_Title"
INCREMENTO_SOURCE_LINK_FIELD = "Incremento_Source_Link"
INCREMENTO_SOURCE_AUTHOR_FIELD = "Incremento_Source_Author"
INCREMENTO_IMPORTED_AT_FIELD = "Incremento_Imported_At"
INCREMENTO_PARENT_FIELD = "Incremento_Parent"
INCREMENTO_PARENT_CARD_ID_FIELD = "Incremento_Parent_Card_ID"
INCREMENTO_CONTENT_ID_FIELD = "Incremento_Content_ID"
INCREMENTO_OCR_TEXT_FIELD = "Incremento_OCR_Text"

INCREMENTO_METADATA_FIELDS = (
    INCREMENTO_SOURCE_TYPE_FIELD,
    INCREMENTO_SOURCE_TITLE_FIELD,
    INCREMENTO_SOURCE_LINK_FIELD,
    INCREMENTO_SOURCE_AUTHOR_FIELD,
    INCREMENTO_IMPORTED_AT_FIELD,
    INCREMENTO_PARENT_FIELD,
    INCREMENTO_PARENT_CARD_ID_FIELD,
    INCREMENTO_CONTENT_ID_FIELD,
)
INCREMENTO_HIDDEN_FIELDS = INCREMENTO_METADATA_FIELDS + (INCREMENTO_OCR_TEXT_FIELD,)
_METADATA_FIELD_SET = {field.casefold() for field in INCREMENTO_METADATA_FIELDS}
_HIDDEN_FIELD_SET = {field.casefold() for field in INCREMENTO_HIDDEN_FIELDS}
_INLINE_PDF_FILENAME_RE = re.compile(
    r'(?:\\?"|")filename(?:\\?"|")\s*:\s*(?:=\s*""\s*)?(?:\\?"|")(?P<filename>[^"]+?)(?:\\?"|")',
    re.IGNORECASE,
)
_INLINE_PDF_PAGE_RE = re.compile(
    r'(?:\\?"|")page(?:\\?"|")\s*:\s*(?:=\s*""\s*)?(?P<page>\d+)',
    re.IGNORECASE,
)
_INLINE_PDF_CARD_ID_RE = re.compile(
    r'(?:\\?"|")card_id(?:\\?"|")\s*:\s*(?:=\s*""\s*)?(?P<card_id>\d+)',
    re.IGNORECASE,
)


def metadata_timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%Y-%m-%d %H:%M:%S")


def is_incremento_metadata_field(field_name: str) -> bool:
    return str(field_name or "").strip().casefold() in _METADATA_FIELD_SET


def is_incremento_hidden_field(field_name: str) -> bool:
    return str(field_name or "").strip().casefold() in _HIDDEN_FIELD_SET


def matches_hidden_field_reference(field_name: str) -> bool:
    raw = str(field_name or "").strip()
    if not raw:
        return False
    if is_incremento_hidden_field(raw):
        return True

    lowered = raw.casefold()
    for prefix in ("field_", "field:", "field ", "fld_", "fld:", "fld "):
        if lowered.startswith(prefix):
            return is_incremento_hidden_field(raw[len(prefix) :].strip())

    for separator in (":", "/", ".", "|"):
        head, found, tail = lowered.rpartition(separator)
        if found and head and is_incremento_hidden_field(tail.strip()):
            return True
    return False


def visible_field_names(field_names: list[str] | tuple[str, ...]) -> list[str]:
    return [
        str(field_name or "").strip()
        for field_name in list(field_names or [])
        if str(field_name or "").strip()
        and not is_incremento_hidden_field(str(field_name or "").strip())
    ]


def hidden_field_values(note) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    fields = []
    try:
        fields = list(getattr(note, "note_type", lambda: {})().get("flds") or [])
    except Exception:
        fields = []
    for field in fields:
        field_name = str((field or {}).get("name") or "").strip()
        if not field_name or not is_incremento_hidden_field(field_name):
            continue
        try:
            value = str(note[field_name] or "")
        except Exception:
            value = ""
        values.append((field_name, value))
    return values


def _model_fields(model) -> list[dict] | None:
    fields = None
    if isinstance(model, dict):
        fields = model.get("flds")
    else:
        try:
            fields = model["flds"]
        except Exception:
            fields = None
    return fields if isinstance(fields, list) else None


def _persist_model_schema(models, model) -> bool:
    try:
        model_id = model.get("id") if isinstance(model, dict) else model["id"]
    except Exception:
        model_id = None
    if not model_id or not hasattr(models, "update_dict"):
        return False

    try:
        models.update_dict(model)
    except Exception:
        return False

    try:
        updated = models.get(model_id)
    except Exception:
        updated = None
    if isinstance(updated, dict) and isinstance(model, dict):
        model.clear()
        model.update(updated)
    return True


def ensure_incremento_metadata_fields(models, model, *, save: bool = False) -> bool:
    fields = _model_fields(model)
    if fields is None:
        return False

    original_fields = copy.deepcopy(fields)
    existing = {
        str(field.get("name") or "").strip()
        for field in fields
        if isinstance(field, dict) and str(field.get("name") or "").strip()
    }
    changed = False
    for field_name in INCREMENTO_METADATA_FIELDS:
        if field_name in existing:
            continue
        fld = models.new_field(field_name)
        models.add_field(model, fld)
        changed = True
    if changed and save and not _persist_model_schema(models, model):
        try:
            fields[:] = original_fields
        except Exception:
            pass
        return False
    return changed


def ensure_incremento_ocr_field(models, model, *, save: bool = False) -> bool:
    fields = _model_fields(model)
    if fields is None:
        return False

    original_fields = copy.deepcopy(fields)
    existing = {
        str(field.get("name") or "").strip()
        for field in fields
        if isinstance(field, dict) and str(field.get("name") or "").strip()
    }
    if INCREMENTO_OCR_TEXT_FIELD in existing:
        return False

    fld = models.new_field(INCREMENTO_OCR_TEXT_FIELD)
    models.add_field(model, fld)
    if save and not _persist_model_schema(models, model):
        try:
            fields[:] = original_fields
        except Exception:
            pass
        return False
    return True


def build_incremento_metadata(
    *,
    source_type: str = "",
    source_title: str = "",
    source_link: str = "",
    source_author: str = "",
    imported_at: str | None = None,
    parent: str = "",
    parent_card_id: int | str | None = None,
    content_id: str | None = None,
) -> dict[str, str]:
    parent_card_text = ""
    if parent_card_id not in (None, ""):
        parent_card_text = str(parent_card_id).strip()

    return {
        INCREMENTO_SOURCE_TYPE_FIELD: str(source_type or "").strip(),
        INCREMENTO_SOURCE_TITLE_FIELD: str(source_title or "").strip(),
        INCREMENTO_SOURCE_LINK_FIELD: str(source_link or "").strip(),
        INCREMENTO_SOURCE_AUTHOR_FIELD: str(source_author or "").strip(),
        INCREMENTO_IMPORTED_AT_FIELD: str(imported_at or metadata_timestamp()).strip(),
        INCREMENTO_PARENT_FIELD: str(parent or "").strip(),
        INCREMENTO_PARENT_CARD_ID_FIELD: parent_card_text,
        INCREMENTO_CONTENT_ID_FIELD: str(content_id or uuid.uuid4().hex).strip(),
    }


def apply_incremento_metadata(note, metadata: dict[str, str] | None) -> None:
    for field_name in INCREMENTO_METADATA_FIELDS:
        value = str((metadata or {}).get(field_name) or "").strip()
        if field_name == INCREMENTO_CONTENT_ID_FIELD and not value:
            value = uuid.uuid4().hex
        try:
            note[field_name] = value
        except Exception:
            continue


def ensure_note_content_id(note) -> str:
    """Return a stable Incremento UUID, assigning one to a compatible note."""
    try:
        current = str(note[INCREMENTO_CONTENT_ID_FIELD] or "").strip()
    except Exception:
        current = ""
    if current:
        return current
    generated = uuid.uuid4().hex
    try:
        note[INCREMENTO_CONTENT_ID_FIELD] = generated
    except Exception:
        return ""
    return generated


def _note_value(note, field_name: str) -> str:
    try:
        return str(note[field_name] or "").strip()
    except Exception:
        return ""


def derive_note_source_metadata(note) -> dict[str, str]:
    title = ""
    try:
        fields = list(getattr(note, "fields", []) or [])
        if fields:
            title = str(fields[0] or "").strip()
    except Exception:
        title = ""

    source_type = _note_value(note, INCREMENTO_SOURCE_TYPE_FIELD)
    source_title = _note_value(note, INCREMENTO_SOURCE_TITLE_FIELD) or title
    source_link = _note_value(note, INCREMENTO_SOURCE_LINK_FIELD)
    source_author = _note_value(note, INCREMENTO_SOURCE_AUTHOR_FIELD)

    if source_type or source_link or source_author:
        return {
            "source_type": source_type,
            "source_title": source_title,
            "source_link": source_link,
            "source_author": source_author,
        }

    pdf_filename = _note_value(note, "PDF_Filename")
    if pdf_filename:
        return {
            "source_type": "PDF",
            "source_title": source_title,
            "source_link": f"pdfs/{pdf_filename}",
            "source_author": "",
        }

    epub_filename = _note_value(note, "EPUB_Filename")
    if epub_filename:
        return {
            "source_type": "EPUB",
            "source_title": source_title,
            "source_link": f"epubs/{epub_filename}",
            "source_author": "",
        }

    markdown_file = _note_value(note, "Markdown_File")
    if markdown_file:
        return {
            "source_type": "Writing",
            "source_title": source_title,
            "source_link": markdown_file,
            "source_author": "",
        }

    url = _note_value(note, "URL")
    if url:
        return {
            "source_type": "Web",
            "source_title": source_title,
            "source_link": url,
            "source_author": "",
        }

    local_video = _note_value(note, "Local_Video_File")
    youtube_url = _note_value(note, "YouTube_URL")
    if local_video or youtube_url:
        return {
            "source_type": "Video",
            "source_title": source_title,
            "source_link": local_video or youtube_url,
            "source_author": "",
        }

    return {
        "source_type": "",
        "source_title": source_title,
        "source_link": "",
        "source_author": "",
    }


def _inline_pdf_reference_from_text(text: str) -> dict[str, int | str] | None:
    raw = str(text or "")
    if "incremento_open_pdf_ref:" not in raw:
        return None

    snippet = unescape(raw)
    marker_index = snippet.find("incremento_open_pdf_ref:")
    if marker_index < 0:
        return None
    snippet = snippet[marker_index:]

    filename_match = _INLINE_PDF_FILENAME_RE.search(snippet)
    if not filename_match:
        return None
    filename = os.path.basename(str(filename_match.group("filename") or "").strip())
    if not filename:
        return None

    page_match = _INLINE_PDF_PAGE_RE.search(snippet)
    card_id_match = _INLINE_PDF_CARD_ID_RE.search(snippet)

    try:
        page = max(1, int(page_match.group("page"))) if page_match else 1
    except Exception:
        page = 1
    try:
        card_id = max(0, int(card_id_match.group("card_id"))) if card_id_match else 0
    except Exception:
        card_id = 0

    return {
        "filename": filename,
        "page": page,
        "card_id": card_id,
    }


def inline_pdf_reference(note) -> dict[str, int | str] | None:
    try:
        values = list(getattr(note, "fields", []) or [])
    except Exception:
        values = []
    for raw_value in values:
        reference = _inline_pdf_reference_from_text(str(raw_value or ""))
        if reference is not None:
            return reference
    return None


def inline_pdf_reference_filename(note) -> str:
    reference = inline_pdf_reference(note) or {}
    return os.path.basename(str(reference.get("filename") or "").strip())


def source_document_reference(note) -> dict[str, str | bool]:
    source = derive_note_source_metadata(note)
    source_link = str((source or {}).get("source_link") or "").strip()
    source_title = str((source or {}).get("source_title") or "").strip()
    source_author = str((source or {}).get("source_author") or "").strip()
    normalized_link = source_link.replace("\\", "/")
    filename = ""
    kind = ""
    if normalized_link.startswith("pdfs/"):
        kind = "pdf"
        filename = os.path.basename(normalized_link)
    elif normalized_link.startswith("epubs/"):
        kind = "epub"
        filename = os.path.basename(normalized_link)

    inline_reference = inline_pdf_reference(note) or {}
    inline_pdf_filename = os.path.basename(str(inline_reference.get("filename") or "").strip())
    if not kind and inline_pdf_filename:
        kind = "pdf"
        filename = inline_pdf_filename
        source_link = f"pdfs/{inline_pdf_filename}"
        source_title = ""
        source_author = ""

    return {
        "kind": kind,
        "title": source_title,
        "link": source_link,
        "author": source_author,
        "filename": filename,
        "has_inline_pdf_reference": bool(inline_pdf_filename),
    }
