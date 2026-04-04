import os
import re
import uuid
from pathlib import Path

try:
    from . import paths as _paths
except ImportError:
    import paths as _paths


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
_INVISIBLE_DUPLICATE_MARK = "\u200b"


def get_writing_dir() -> str:
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    d = str(_paths.get_writing_dir(addon_dir, _paths.get_active_profile()))
    os.makedirs(d, exist_ok=True)
    return d


def _sanitize_filename(raw: str, fallback: str = "writing-note") -> str:
    base = (raw or "").strip()
    if not base:
        base = fallback
    base = base.replace("\\", "/").split("/")[-1]
    stem, ext = os.path.splitext(base)
    stem = _SAFE_NAME_RE.sub("_", stem).strip("._-")
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


def writing_file_abspath(addon_dir: str, relpath: str) -> str:
    rel = (relpath or "").strip().replace("\\", "/")
    # Strip any user_files/…/writing/ prefix (handles both legacy and new paths)
    _, found, after = rel.partition("writing/")
    if found:
        rel = after
    rel = os.path.basename(rel)
    rel = _sanitize_filename(rel, fallback="writing-note")
    writing_dir = _paths.get_writing_dir(addon_dir, _paths.get_active_profile())
    path = (writing_dir / rel).resolve()
    return str(path)


def ensure_writing_file(addon_dir: str, relpath: str, initial_text: str = "") -> str:
    path = writing_file_abspath(addon_dir, relpath)
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


def write_writing_text(addon_dir: str, relpath: str, text: str) -> None:
    path = writing_file_abspath(addon_dir, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text or "")
    os.replace(tmp, path)


def ensure_writing_note_type(col) -> None:
    models = col.models
    m = models.by_name(WRITING_NOTE_TYPE)
    if m is None:
        m = models.new(WRITING_NOTE_TYPE)
        for field_name in ("Title", WRITING_FILE_FIELD):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
        return

    changed = False
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
) -> int:
    ensure_writing_note_type(col)

    relpath = build_writing_relpath(title=title, preferred_filename=preferred_filename or None)
    default_text = initial_markdown if initial_markdown else f"# {title}\n\n"
    ensure_writing_file(addon_dir, relpath, initial_text=default_text)

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(WRITING_NOTE_TYPE)
    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note[WRITING_FILE_FIELD] = relpath
        for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
            if not tag:
                continue
            if hasattr(note, "add_tag"):
                note.add_tag(tag)
            elif hasattr(note, "tags"):
                note.tags.append(tag)
        note.note_type()["did"] = deck_id
        return note

    for attempt in range(6):
        stored_title = title if attempt == 0 else f"{title}{_INVISIBLE_DUPLICATE_MARK * attempt}"
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            return cards[0]
    raise RuntimeError("Failed to add writing card. Anki rejected the note.")
