from __future__ import annotations

from datetime import datetime

INCREMENTO_SOURCE_TYPE_FIELD = "Incremento_Source_Type"
INCREMENTO_SOURCE_TITLE_FIELD = "Incremento_Source_Title"
INCREMENTO_SOURCE_LINK_FIELD = "Incremento_Source_Link"
INCREMENTO_SOURCE_AUTHOR_FIELD = "Incremento_Source_Author"
INCREMENTO_IMPORTED_AT_FIELD = "Incremento_Imported_At"
INCREMENTO_PARENT_FIELD = "Incremento_Parent"
INCREMENTO_PARENT_CARD_ID_FIELD = "Incremento_Parent_Card_ID"

INCREMENTO_METADATA_FIELDS = (
    INCREMENTO_SOURCE_TYPE_FIELD,
    INCREMENTO_SOURCE_TITLE_FIELD,
    INCREMENTO_SOURCE_LINK_FIELD,
    INCREMENTO_SOURCE_AUTHOR_FIELD,
    INCREMENTO_IMPORTED_AT_FIELD,
    INCREMENTO_PARENT_FIELD,
    INCREMENTO_PARENT_CARD_ID_FIELD,
)
_METADATA_FIELD_SET = {field.casefold() for field in INCREMENTO_METADATA_FIELDS}


def metadata_timestamp(value: datetime | None = None) -> str:
    current = value or datetime.now()
    return current.strftime("%Y-%m-%d %H:%M:%S")


def is_incremento_metadata_field(field_name: str) -> bool:
    return str(field_name or "").strip().casefold() in _METADATA_FIELD_SET


def visible_field_names(field_names: list[str] | tuple[str, ...]) -> list[str]:
    return [
        str(field_name or "").strip()
        for field_name in list(field_names or [])
        if str(field_name or "").strip()
        and not is_incremento_metadata_field(str(field_name or "").strip())
    ]


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


def ensure_incremento_metadata_fields(models, model) -> bool:
    fields = _model_fields(model)
    if fields is None:
        return False

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
    return changed


def build_incremento_metadata(
    *,
    source_type: str = "",
    source_title: str = "",
    source_link: str = "",
    source_author: str = "",
    imported_at: str | None = None,
    parent: str = "",
    parent_card_id: int | str | None = None,
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
    }


def apply_incremento_metadata(note, metadata: dict[str, str] | None) -> None:
    for field_name in INCREMENTO_METADATA_FIELDS:
        value = str((metadata or {}).get(field_name) or "").strip()
        try:
            note[field_name] = value
        except Exception:
            continue


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
