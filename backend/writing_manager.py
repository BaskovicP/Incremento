import os
import re
import shutil
import time
import uuid
import hashlib
from pathlib import Path

try:
    from . import paths as _paths
    from .operation_journal import ImportOperation
    from .note_metadata import (
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        INCREMENTO_CONTENT_ID_FIELD,
    )
except ImportError:
    import paths as _paths
    from operation_journal import ImportOperation  # type: ignore
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
        INCREMENTO_CONTENT_ID_FIELD,
    )


WRITING_NOTE_TYPE = "Incremento Writing"
WRITING_FILE_FIELD = "Markdown_File"

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">Writing editor open in sidebar &nbsp;&middot;&nbsp; autosaves while typing</div>
</div>
{{Markdown_File}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_FILENAME_STEM = 80
_BACKUP_SLOTS = (
    ("1m", 60, "1 minute"),
    ("5m", 5 * 60, "5 minutes"),
    ("15m", 15 * 60, "15 minutes"),
    ("30m", 30 * 60, "30 minutes"),
    ("1h", 60 * 60, "1 hour"),
    ("6h", 6 * 60 * 60, "6 hours"),
    ("1d", 24 * 60 * 60, "1 day"),
    ("7d", 7 * 24 * 60 * 60, "7 days"),
)
_DEFAULT_BACKUP_TIER_KEYS = ("1m", "30m", "1d")
_BACKUP_SLOT_MAP = {tier_key: (seconds, label) for tier_key, seconds, label in _BACKUP_SLOTS}


def normalize_writing_backup_tiers(tier_keys) -> tuple[str, ...]:
    raw_values = tier_keys
    if raw_values is None:
        raw_values = _DEFAULT_BACKUP_TIER_KEYS
    elif isinstance(raw_values, str):
        raw_values = [raw_values]
    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        tier_key = str(value or "").strip().lower()
        if tier_key not in _BACKUP_SLOT_MAP or tier_key in seen:
            continue
        normalized.append(tier_key)
        seen.add(tier_key)
    return tuple(normalized)


def get_writing_dir() -> str:
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    d = str(_paths.get_writing_dir(addon_dir, _paths.get_active_profile()))
    os.makedirs(d, exist_ok=True)
    return d


def _writing_backup_dir(addon_dir: str) -> str:
    path = str(_paths.get_writing_backup_dir(addon_dir, _paths.get_active_profile()))
    os.makedirs(path, exist_ok=True)
    return path


def _sanitize_filename(raw: str, fallback: str = "writing-note") -> str:
    base = (raw or "").strip()
    if not base:
        base = fallback
    base = base.replace("\\", "/").split("/")[-1]
    stem, ext = os.path.splitext(base)
    stem = _SAFE_NAME_RE.sub("_", stem).strip("._-")
    stem = stem[:_MAX_FILENAME_STEM].strip("._-")
    if not stem:
        stem = fallback
    if ext.lower() != ".md":
        ext = ".md"
    return f"{stem}{ext}"


def _uuid_filename(filename: str) -> str:
    stem, ext = os.path.splitext(filename)
    return f"{stem}-{uuid.uuid4().hex}{ext}"


def build_writing_relpath(title: str, preferred_filename: str | None = None) -> str:
    base = preferred_filename if preferred_filename else title
    cleaned = _sanitize_filename(base, fallback="writing-note")
    unique = _uuid_filename(cleaned)
    return f"writing/{unique}"


def _stored_writing_title(title: str, attempt: int) -> str:
    base_title = str(title or "").strip() or "Untitled"
    if attempt <= 0:
        return base_title
    return f"{base_title} [{attempt + 1}]"


def writing_file_abspath(
    addon_dir: str,
    relpath: str,
    *,
    profile: str | None = None,
) -> str:
    rel = (relpath or "").strip().replace("\\", "/")
    # Strip any user_files/…/writing/ prefix (handles both legacy and new paths)
    _, found, after = rel.partition("writing/")
    if found:
        rel = after
    rel = os.path.basename(rel)
    rel = _sanitize_filename(rel, fallback="writing-note")
    writing_dir = _paths.get_writing_dir(
        addon_dir,
        profile or _paths.get_active_profile(),
    )
    path = (writing_dir / rel).resolve()
    return str(path)


def _backup_base_name(relpath: str) -> str:
    rel = (relpath or "").strip().replace("\\", "/")
    base = os.path.basename(rel) or "writing-note.md"
    stem, ext = os.path.splitext(_sanitize_filename(base, fallback="writing-note"))
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
    return f"{stem}-{digest}{ext or '.md'}"


def _backup_slot_path(addon_dir: str, relpath: str, tier_key: str) -> str:
    base_name = _backup_base_name(relpath)
    stem, ext = os.path.splitext(base_name)
    return os.path.join(_writing_backup_dir(addon_dir), f"{stem}.{tier_key}{ext or '.md'}")


def _backup_meta(path: str, tier_key: str, label: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return {
        "tier_key": tier_key,
        "label": label,
        "path": path,
        "created_at": float(stat.st_mtime),
        "size_bytes": int(stat.st_size),
    }


def list_writing_backups(addon_dir: str, relpath: str) -> list[dict]:
    rows: list[dict] = []
    for tier_key, _threshold_seconds, label in _BACKUP_SLOTS:
        meta = _backup_meta(_backup_slot_path(addon_dir, relpath, tier_key), tier_key, label)
        if meta:
            rows.append(meta)
    return rows


def _refresh_due_backups(
    addon_dir: str,
    relpath: str,
    source_path: str,
    *,
    backup_tiers=None,
    now: float | None = None,
) -> list[dict]:
    if not os.path.exists(source_path):
        return []
    current_now = float(now if now is not None else time.time())
    created: list[dict] = []
    for tier_key in normalize_writing_backup_tiers(backup_tiers):
        threshold_seconds, label = _BACKUP_SLOT_MAP[tier_key]
        backup_path = _backup_slot_path(addon_dir, relpath, tier_key)
        should_refresh = True
        if os.path.exists(backup_path):
            try:
                age = current_now - float(os.path.getmtime(backup_path))
                should_refresh = age >= float(threshold_seconds)
            except OSError:
                should_refresh = True
        if not should_refresh:
            continue
        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
        shutil.copy2(source_path, backup_path)
        os.utime(backup_path, (current_now, current_now))
        meta = _backup_meta(backup_path, tier_key, label)
        if meta:
            created.append(meta)
    return created


def ensure_writing_file(
    addon_dir: str,
    relpath: str,
    initial_text: str = "",
    *,
    profile: str | None = None,
) -> str:
    path = writing_file_abspath(addon_dir, relpath, profile=profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(initial_text or "")
    return path


def read_writing_text(addon_dir: str, relpath: str) -> str:
    path = writing_file_abspath(addon_dir, relpath)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def write_writing_text(
    addon_dir: str,
    relpath: str,
    text: str,
    *,
    backups_enabled: bool = True,
    backup_tiers=None,
    now: float | None = None,
) -> list[dict]:
    path = writing_file_abspath(addon_dir, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    selected_tiers = normalize_writing_backup_tiers(backup_tiers)
    if backups_enabled and selected_tiers and os.path.exists(path):
        _refresh_due_backups(addon_dir, relpath, path, backup_tiers=selected_tiers, now=now)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text or "")
    os.replace(tmp, path)
    return list_writing_backups(addon_dir, relpath)


def restore_writing_backup(addon_dir: str, relpath: str, tier_key: str) -> dict:
    normalized_tier = str(tier_key or "").strip().lower()
    selected_meta = _BACKUP_SLOT_MAP.get(normalized_tier)
    selected_label = selected_meta[1] if selected_meta else None
    if not selected_label:
        raise ValueError("Unknown writing backup tier.")
    backup_path = _backup_slot_path(addon_dir, relpath, normalized_tier)
    if not os.path.exists(backup_path):
        raise FileNotFoundError("Requested writing backup does not exist.")
    live_path = writing_file_abspath(addon_dir, relpath)
    os.makedirs(os.path.dirname(live_path), exist_ok=True)
    tmp = f"{live_path}.tmp"
    shutil.copyfile(backup_path, tmp)
    os.replace(tmp, live_path)
    meta = _backup_meta(backup_path, normalized_tier, selected_label)
    return meta or {"tier_key": normalized_tier, "label": selected_label, "path": backup_path}


def ensure_writing_note_type(col) -> None:
    models = col.models
    m = models.by_name(WRITING_NOTE_TYPE)
    if m is None:
        m = models.new(WRITING_NOTE_TYPE)
        for field_name in ("Title", WRITING_FILE_FIELD):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        ensure_incremento_metadata_fields(models, m)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
        return

    changed = False
    if ensure_incremento_metadata_fields(models, m):
        changed = True
    tmpl = m["tmpls"][0]
    if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        changed = True
    if changed:
        models.update_dict(m)


def add_writing_card(
    addon_dir: str,
    col,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
    initial_markdown: str = "",
    preferred_filename: str = "",
    metadata: dict[str, str] | None = None,
) -> int:
    ensure_writing_note_type(col)
    profile = _paths.get_active_profile()
    with ImportOperation(addon_dir, profile, "writing") as operation:
        return _create_new_writing_card(
            addon_dir,
            col,
            title=title,
            deck_name=deck_name,
            tags=tags,
            initial_markdown=initial_markdown,
            preferred_filename=preferred_filename,
            metadata=metadata,
            operation=operation,
        )


def _create_new_writing_card(
    addon_dir: str,
    col,
    *,
    title: str,
    deck_name: str,
    tags: list[str] | None,
    initial_markdown: str,
    preferred_filename: str,
    metadata: dict[str, str] | None,
    operation: ImportOperation,
) -> int:

    relpath = build_writing_relpath(title=title, preferred_filename=preferred_filename or None)
    default_text = initial_markdown if initial_markdown else f"# {title}\n\n"
    operation.track_created_relpath(relpath)
    ensure_writing_file(
        addon_dir,
        relpath,
        initial_text=default_text,
        profile=operation.profile,
    )

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(WRITING_NOTE_TYPE)
    resolved_metadata = dict(
        metadata
        or build_incremento_metadata(
            source_type="Writing",
            source_title=title,
            source_link=relpath,
            content_id=operation.content_id,
        )
    )
    resolved_metadata[INCREMENTO_CONTENT_ID_FIELD] = operation.content_id

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note[WRITING_FILE_FIELD] = relpath
        apply_incremento_metadata(note, resolved_metadata)
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
        stored_title = _stored_writing_title(title, attempt)
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            card_id = cards[0]
            operation.bind_anki(card_id=card_id, note_id=getattr(note, "id", None))
            operation.commit(storage_key=relpath)
            return card_id
    raise RuntimeError("Failed to add writing card. Anki rejected the note.")
