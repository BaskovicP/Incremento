import os
import re
from pathlib import Path


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


def get_writing_dir() -> str:
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    out = os.path.join(addon_dir, "user_files", "writing")
    os.makedirs(out, exist_ok=True)
    return out


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


def _unique_filename_in_writing_dir(filename: str) -> str:
    writing_dir = get_writing_dir()
    stem, ext = os.path.splitext(filename)
    candidate = filename
    i = 1
    while os.path.exists(os.path.join(writing_dir, candidate)):
        candidate = f"{stem} ({i}){ext}"
        i += 1
    return candidate


def build_writing_relpath(title: str, preferred_filename: str | None = None) -> str:
    base = preferred_filename if preferred_filename else title
    cleaned = _sanitize_filename(base, fallback="writing-note")
    unique = _unique_filename_in_writing_dir(cleaned)
    return f"writing/{unique}"


def writing_file_abspath(addon_dir: str, relpath: str) -> str:
    rel = (relpath or "").strip().replace("\\", "/")
    if rel.startswith("user_files/"):
        rel = rel[len("user_files/") :]
    if rel.startswith("writing/"):
        rel = rel[len("writing/") :]
    rel = os.path.basename(rel)
    rel = _sanitize_filename(rel, fallback="writing-note")
    path = (Path(addon_dir) / "user_files" / "writing" / rel).resolve()
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
    note = col.new_note(model)
    note["Title"] = title
    note[WRITING_FILE_FIELD] = relpath
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
