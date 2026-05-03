from __future__ import annotations

try:
    from .note_metadata import visible_field_names
except ImportError:
    from note_metadata import visible_field_names  # type: ignore


def visible_note_field_values(note) -> dict[str, str]:
    note_type = note.note_type() or {}
    visible_fields = visible_field_names(
        [field.get("name") for field in list(note_type.get("flds") or [])]
    )
    values: dict[str, str] = {}
    for field_name in visible_fields:
        try:
            values[field_name] = str(note[field_name] or "")
        except Exception:
            values[field_name] = ""
    return values


def initial_extract_field_values(note, selected_text: str) -> dict[str, str]:
    text = str(selected_text or "")
    visible_values = visible_note_field_values(note)
    if not text:
        return visible_values
    if not visible_values:
        return {}
    first_field_name = next(iter(visible_values.keys()))
    return {first_field_name: text}


def extract_default_notetype_name(
    *,
    selected_text: str,
    configured_notetype: str,
    parent_notetype: str,
    available_notetype_names: list[str],
) -> str:
    if not str(selected_text or "").strip():
        return str(parent_notetype or "").strip()
    candidate = str(configured_notetype or "").strip()
    if candidate and candidate in list(available_notetype_names or []):
        return candidate
    return str(parent_notetype or "").strip()


def knowledge_tree_link_state(parent_in_tree: bool) -> dict[str, object]:
    return {
        "enabled": False,
        "checked": True,
        "tooltip": (
            "Extract lineage is added to the knowledge tree automatically. "
            "New extract cards are placed beneath their source parent when available."
        ),
    }
