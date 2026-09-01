"""Pure keyboard-shortcut identity and conflict detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


_ALIASES = {
    "control": "ctrl",
    "ctl": "ctrl",
    "option": "alt",
    "command": "meta",
    "cmd": "meta",
}
_MODIFIER_ORDER = {"ctrl": 0, "alt": 1, "meta": 2, "shift": 3}


@dataclass(frozen=True)
class ShortcutConflict:
    shortcut: str
    action_ids: tuple[str, ...]


def _normalize_chord(raw_chord: str) -> str:
    parts: list[str] = []
    for raw_part in str(raw_chord or "").split("+"):
        part = raw_part.strip().casefold()
        if not part:
            continue
        parts.append(_ALIASES.get(part, part))
    modifiers = sorted(
        {part for part in parts if part in _MODIFIER_ORDER},
        key=lambda part: _MODIFIER_ORDER[part],
    )
    keys = [part for part in parts if part not in _MODIFIER_ORDER]
    return "+".join((*modifiers, *keys))


def normalize_shortcut_identity(shortcut: str | None) -> str:
    chords = [
        _normalize_chord(chord)
        for chord in str(shortcut or "").split(",")
    ]
    return ",".join(chord for chord in chords if chord)


def find_shortcut_conflicts(
    shortcuts: Mapping[str, str] | None,
) -> list[ShortcutConflict]:
    by_shortcut: dict[str, list[str]] = {}
    for raw_action_id, raw_shortcut in dict(shortcuts or {}).items():
        action_id = str(raw_action_id or "").strip()
        identity = normalize_shortcut_identity(raw_shortcut)
        if not action_id or not identity:
            continue
        by_shortcut.setdefault(identity, []).append(action_id)
    return [
        ShortcutConflict(shortcut, tuple(action_ids))
        for shortcut, action_ids in sorted(by_shortcut.items())
        if len(action_ids) > 1
    ]
