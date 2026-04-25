import os
import re
import shutil
import uuid

try:
    from . import paths as _paths
    from .note_metadata import (
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )
except ImportError:
    import paths as _paths
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )


LOCAL_FILE_NOTE_TYPE = "Incremento Local File"
LOCAL_FILE_NAME_FIELD = "Local_File_Name"
LOCAL_FILE_PATH_FIELD = "Local_File_Path"
LOCAL_FILE_MODE_FIELD = "Local_File_Mode"
LOCAL_FILE_NOTE_FIELD = "Local_File_Note"

LOCAL_FILE_MODE_REFERENCE = "reference"
LOCAL_FILE_MODE_MANAGED_COPY = "managed_copy"
LOCAL_FILE_MODES = {
    LOCAL_FILE_MODE_REFERENCE,
    LOCAL_FILE_MODE_MANAGED_COPY,
}

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:36px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:8px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.95em; margin-bottom:10px;">{{Local_File_Name}}</div>
  <div style="font-size:0.8em; margin-bottom:12px;">{{Local_File_Path}}</div>
  <div style="font-size:0.85em; margin-bottom:12px;">{{Local_File_Mode}}</div>
  <div style="font-size:0.9em; color:#aaa;">{{Local_File_Note}}</div>
</div>
""".strip()

CARD_TEMPLATE_BACK = "{{FrontSide}}"

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_FILENAME_STEM = 80


def normalize_local_file_mode(mode: str | None) -> str:
    raw = str(mode or "").strip().lower()
    if raw == LOCAL_FILE_MODE_MANAGED_COPY:
        return LOCAL_FILE_MODE_MANAGED_COPY
    return LOCAL_FILE_MODE_REFERENCE


def _sanitize_filename(raw: str, fallback: str = "local-file") -> str:
    base = (raw or "").strip()
    if not base:
        base = fallback
    base = base.replace("\\", "/").split("/")[-1]
    stem, ext = os.path.splitext(base)
    stem = _SAFE_NAME_RE.sub("_", stem).strip("._-")
    stem = stem[:_MAX_FILENAME_STEM].strip("._-")
    if not stem:
        stem = fallback
    ext = _SAFE_NAME_RE.sub("", ext or "")[:32]
    return f"{stem}{ext}"


def _uuid_filename(filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    return f"{stem}-{uuid.uuid4().hex}{ext}"


def get_local_files_dir(addon_dir: str, profile: str) -> str:
    path = str(_paths.get_local_files_dir(addon_dir, profile))
    os.makedirs(path, exist_ok=True)
    return path


def build_managed_local_file_relpath(source_path: str) -> str:
    safe_name = _sanitize_filename(os.path.basename(source_path or ""), fallback="local-file")
    return f"files/{_uuid_filename(safe_name)}"


def managed_local_file_abspath(addon_dir: str, profile: str, relpath: str) -> str:
    rel = str(relpath or "").strip().replace("\\", "/")
    _, found, after = rel.partition("files/")
    if found:
        rel = after
    rel = os.path.basename(rel)
    rel = _sanitize_filename(rel, fallback="local-file")
    return str((_paths.get_local_files_dir(addon_dir, profile) / rel).resolve())


def resolve_local_file_abspath(addon_dir: str, profile: str, stored_path: str, mode: str) -> str:
    normalized_mode = normalize_local_file_mode(mode)
    if normalized_mode == LOCAL_FILE_MODE_MANAGED_COPY:
        return managed_local_file_abspath(addon_dir, profile, stored_path)
    return os.path.normpath(os.path.abspath(str(stored_path or "").strip()))


def local_file_exists(addon_dir: str, profile: str, stored_path: str, mode: str) -> bool:
    resolved = resolve_local_file_abspath(addon_dir, profile, stored_path, mode)
    return bool(resolved) and os.path.isfile(resolved)


def import_local_file_copy(addon_dir: str, profile: str, source_path: str) -> str:
    src = os.path.abspath(str(source_path or "").strip())
    if not os.path.isfile(src):
        raise FileNotFoundError("Selected file does not exist.")
    relpath = build_managed_local_file_relpath(src)
    dest = managed_local_file_abspath(addon_dir, profile, relpath)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    return relpath


def prepare_local_file_storage(addon_dir: str, profile: str, source_path: str, mode: str) -> tuple[str, str]:
    normalized_mode = normalize_local_file_mode(mode)
    src = os.path.abspath(str(source_path or "").strip())
    if not os.path.isfile(src):
        raise FileNotFoundError("Selected file does not exist.")
    if normalized_mode == LOCAL_FILE_MODE_MANAGED_COPY:
        stored_path = import_local_file_copy(addon_dir, profile, src)
    else:
        stored_path = src
    return stored_path, os.path.basename(src)


def relink_local_file(
    addon_dir: str,
    profile: str,
    note,
    *,
    new_source_path: str,
) -> tuple[str, str]:
    try:
        raw_mode = note[LOCAL_FILE_MODE_FIELD]
    except Exception:
        raw_mode = ""
    mode = normalize_local_file_mode(raw_mode)
    stored_path, filename = prepare_local_file_storage(addon_dir, profile, new_source_path, mode)
    note[LOCAL_FILE_PATH_FIELD] = stored_path
    note[LOCAL_FILE_NAME_FIELD] = filename
    return stored_path, filename


def _stored_local_file_title(title: str, attempt: int) -> str:
    base_title = str(title or "").strip() or "Untitled"
    if attempt <= 0:
        return base_title
    return f"{base_title} [{attempt + 1}]"


def ensure_local_file_note_type(col) -> None:
    models = col.models
    model = models.by_name(LOCAL_FILE_NOTE_TYPE)
    required_fields = (
        "Title",
        LOCAL_FILE_NAME_FIELD,
        LOCAL_FILE_PATH_FIELD,
        LOCAL_FILE_MODE_FIELD,
        LOCAL_FILE_NOTE_FIELD,
    )
    if model is None:
        model = models.new(LOCAL_FILE_NOTE_TYPE)
        for field_name in required_fields:
            fld = models.new_field(field_name)
            models.add_field(model, fld)
        ensure_incremento_metadata_fields(models, model)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(model, tmpl)
        models.add(model)
        return

    changed = False
    existing = {
        str(field.get("name") or "").strip()
        for field in model.get("flds", [])
        if isinstance(field, dict)
    }
    for field_name in required_fields:
        if field_name in existing:
            continue
        fld = models.new_field(field_name)
        models.add_field(model, fld)
        changed = True
    if ensure_incremento_metadata_fields(models, model):
        changed = True
    tmpl = model["tmpls"][0]
    if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        changed = True
    if changed:
        models.update_dict(model)


def add_local_file_card(
    addon_dir: str,
    profile: str,
    col,
    *,
    source_path: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
    mode: str = LOCAL_FILE_MODE_REFERENCE,
    note_text: str = "",
    metadata: dict[str, str] | None = None,
) -> int:
    ensure_local_file_note_type(col)
    stored_path, filename = prepare_local_file_storage(addon_dir, profile, source_path, mode)
    normalized_mode = normalize_local_file_mode(mode)

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(LOCAL_FILE_NOTE_TYPE)

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note[LOCAL_FILE_NAME_FIELD] = filename
        note[LOCAL_FILE_PATH_FIELD] = stored_path
        note[LOCAL_FILE_MODE_FIELD] = normalized_mode
        note[LOCAL_FILE_NOTE_FIELD] = str(note_text or "").strip()
        apply_incremento_metadata(
            note,
            metadata
            or build_incremento_metadata(
                source_type="Local File",
                source_title=title,
                source_link=stored_path,
            ),
        )
        for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
            if not tag:
                continue
            if hasattr(note, "add_tag"):
                note.add_tag(tag)
            elif hasattr(note, "tags"):
                note.tags.append(tag)
        note.note_type()["did"] = deck_id
        return note

    for attempt in range(25):
        stored_title = _stored_local_file_title(title, attempt)
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            return cards[0]
    raise RuntimeError("Failed to add local file card. Anki rejected the note.")
