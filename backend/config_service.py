"""Versioned normalization and persistence for Incremento add-on config."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Mapping


CONFIG_SCHEMA_VERSION = 2
_DAY_END_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

_BOOLEAN_DEFAULTS = {
    "priority_lower_is_more_important": True,
    "remember_browser_card_scroll": True,
    "show_priority_dialog_after_answer": False,
    "show_incremento_fields": False,
    "auto_timer_enabled": False,
    "use_fail_pass_on_items": False,
    "item_skip_enabled": False,
    "writing_wrap_enabled": True,
    "writing_focus_mode": False,
    "writing_highlight_current_line": True,
    "writing_restore_bookmark": True,
    "writing_backups_enabled": True,
    "writing_progress_visible": True,
    "auto_create_topics_deck": True,
    "topic_postpone_enabled": False,
}

_NUMBER_LIMITS = {
    "item_skip_minutes": (30, 1, 525_600, int),
    "topic_more_adjustment_percent": (10.0, 0.0, 100.0, float),
    "topic_less_adjustment_percent": (10.0, 0.0, 100.0, float),
    "topic_maximum_interval_days": (36_500, 1, 365_000, int),
    "default_topic_a_factor": (3.5, 1.1, 100.0, float),
}


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(default)


def _number(value: Any, default, minimum, maximum, cast):
    try:
        resolved = float(value)
    except Exception:
        resolved = float(default)
    if resolved != resolved:
        resolved = float(default)
    bounded = min(float(maximum), max(float(minimum), resolved))
    return cast(bounded)


def _normalize_dialog(raw: Any) -> dict:
    dialog = copy.deepcopy(raw) if isinstance(raw, Mapping) else {}
    if "session_card_count" in dialog:
        dialog["session_card_count"] = _number(
            dialog.get("session_card_count"), 50, 1, 9999, int
        )
    for key, default in (
        ("auto_refill_session", False),
        ("include_new", True),
        ("include_learning", True),
        ("include_due", True),
        ("preserve_order", True),
        ("show_debug", False),
        ("use_live_preview", False),
    ):
        if key in dialog:
            dialog[key] = _bool(dialog.get(key), default)
    if "day_end_time" in dialog:
        day_end = str(dialog.get("day_end_time") or "04:00").strip()
        dialog["day_end_time"] = day_end if _DAY_END_RE.fullmatch(day_end) else "04:00"
    if "scheduler_scope" in dialog:
        scope = str(dialog.get("scheduler_scope") or "session").strip().casefold()
        dialog["scheduler_scope"] = scope if scope in {"session", "daily", "lifetime"} else "session"
    return dialog


def normalize_config(raw: Mapping[str, Any] | None) -> dict:
    """Return a validated config while preserving forward-compatible keys."""
    config = copy.deepcopy(dict(raw or {}))
    config["config_schema_version"] = CONFIG_SCHEMA_VERSION

    for key, default in _BOOLEAN_DEFAULTS.items():
        if key in config:
            config[key] = _bool(config.get(key), default)
    for key, (default, minimum, maximum, cast) in _NUMBER_LIMITS.items():
        if key in config:
            config[key] = _number(
                config.get(key), default, minimum, maximum, cast
            )

    config["dialog"] = _normalize_dialog(config.get("dialog"))

    # "profiles" was the historical name for scheduler presets and was often
    # confused with Anki profiles. Keep a synchronized compatibility alias
    # while new code and exported config use the explicit name.
    presets = config.get("scheduler_presets")
    if not isinstance(presets, Mapping):
        presets = config.get("profiles")
    normalized_presets = {
        str(name): copy.deepcopy(dict(values))
        for name, values in (presets.items() if isinstance(presets, Mapping) else [])
        if str(name).strip() and isinstance(values, Mapping)
    }
    config["scheduler_presets"] = normalized_presets
    config["profiles"] = copy.deepcopy(normalized_presets)
    return config


@dataclass(frozen=True)
class ConfigSnapshot:
    raw: dict

    @property
    def dialog(self) -> dict:
        return copy.deepcopy(self.raw.get("dialog") or {})

    @property
    def scheduler_presets(self) -> dict[str, dict]:
        return copy.deepcopy(self.raw.get("scheduler_presets") or {})


def load_addon_config(addon_manager, addon_package: str) -> dict:
    current = addon_manager.getConfig(addon_package) or {}
    normalized = normalize_config(current)
    if isinstance(current, dict):
        current.clear()
        current.update(normalized)
        return current
    return normalized


def save_addon_config(addon_manager, addon_package: str, config: Mapping[str, Any]) -> dict:
    normalized = normalize_config(config)
    if isinstance(config, dict):
        config.clear()
        config.update(normalized)
        addon_manager.writeConfig(addon_package, config)
        return config
    addon_manager.writeConfig(addon_package, normalized)
    return normalized


def migrate_persisted_config(addon_manager, addon_package: str) -> tuple[dict, bool]:
    current = copy.deepcopy(addon_manager.getConfig(addon_package) or {})
    normalized = normalize_config(current)
    changed = normalized != current
    if changed:
        addon_manager.writeConfig(addon_package, normalized)
    return normalized, changed
