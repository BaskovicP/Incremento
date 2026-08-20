"""Pure shortcut helpers for the Browser quick-tag picker."""

from __future__ import annotations


QUICK_TAG_SLOT_COUNT = 9


def quick_tag_shortcut_keys(slot_index: int) -> tuple[str, str]:
    """Return the number and letter shortcuts for a zero-based picker slot."""
    try:
        index = int(slot_index)
    except Exception as exc:
        raise ValueError("Quick-tag slot index must be an integer.") from exc
    if not 0 <= index < QUICK_TAG_SLOT_COUNT:
        raise ValueError("Quick-tag slot index must be between 0 and 8.")
    return str(index + 1), chr(ord("A") + index)
