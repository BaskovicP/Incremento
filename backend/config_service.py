"""Versioned normalization and persistence for Incremento add-on config."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Mapping

try:
    from .i18n import normalize_language_choice
except ImportError:
    from i18n import normalize_language_choice

try:
    from .backup_schedule import normalize_policy
except ImportError:
    from backup_schedule import normalize_policy


CONFIG_SCHEMA_VERSION = 3
DOCUMENT_MIX_VERSION = 2
DEFAULT_TOPIC_DONE_TAG = "topic/done"
DEFAULT_REVIEWER_BUTTON_VISIBILITY = {
    "done": True,
    "postpone": True,
    "extract": True,
}
_DAY_END_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

_BOOLEAN_DEFAULTS = {
    "priority_lower_is_more_important": True,
    "reviewer_button_group_visible": True,
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

_NUMBER_LIMITS: dict[
    str,
    tuple[int | float, int | float, int | float, type[int] | type[float]],
] = {
    "onboarding_completed_version": (0, 0, 1_000, int),
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


def normalize_document_mix(raw: Any) -> dict:
    """Migrate the old whole-session document share to a share within Topics.

    Keep the old three-way target as closely as whole-percent sliders allow.
    A per-setup marker protects saved presets and repeated reads from conversion.
    """
    dialog = copy.deepcopy(dict(raw)) if isinstance(raw, Mapping) else {}
    if "pdf_slider" not in dialog:
        return dialog
    if _number(dialog.get("document_mix_version"), 1, 1, 1_000, int) >= DOCUMENT_MIX_VERSION:
        return dialog
    old_items = _number(dialog.get("topics_slider"), 10, 0, 100, float) / 100
    documents = 1 - _number(dialog.get("pdf_slider"), 100, 0, 100, float) / 100
    topics = 1 - old_items * (1 - documents)
    dialog["topics_slider"] = round(100 * (1 - topics))
    dialog["pdf_slider"] = round(100 * (1 - documents / topics)) if topics > 0 else 100
    dialog["document_mix_version"] = DOCUMENT_MIX_VERSION
    return dialog


def _normalize_dialog(raw: Any) -> dict:
    dialog: dict[str, Any] = normalize_document_mix(raw)
    if "session_card_count" in dialog:
        dialog["session_card_count"] = _number(
            dialog.get("session_card_count"), 50, 1, 9999, int
        )
    for key, boolean_default in (
        ("auto_refill_session", False),
        ("include_new", True),
        ("include_learning", True),
        ("include_due", True),
        ("preserve_order", True),
        ("show_debug", False),
        ("use_live_preview", False),
    ):
        if key in dialog:
            dialog[key] = _bool(dialog.get(key), boolean_default)
    if "day_end_time" in dialog:
        day_end = str(dialog.get("day_end_time") or "04:00").strip()
        dialog["day_end_time"] = day_end if _DAY_END_RE.fullmatch(day_end) else "04:00"
    if "scheduler_scope" in dialog:
        scope = str(dialog.get("scheduler_scope") or "session").strip().casefold()
        dialog["scheduler_scope"] = scope if scope in {"session", "daily", "lifetime"} else "session"
    if "setup_mode" in dialog:
        setup_mode = str(dialog.get("setup_mode") or "basic").strip().casefold()
        dialog["setup_mode"] = setup_mode if setup_mode in {"basic", "advanced"} else "basic"
    return dialog


def normalize_topic_done_tag(value: object) -> str:
    """Validate one note tag; an empty setting uses the shipped default."""
    if value is None:
        return DEFAULT_TOPIC_DONE_TAG
    if not isinstance(value, str):
        raise ValueError("Done tag must be a single text tag.")
    tag = value.strip() or DEFAULT_TOPIC_DONE_TAG
    if (
        len(tag) > 255
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in tag)
        or not tag.strip(":")
        or any(not part for part in tag.split("::"))
    ):
        raise ValueError("Enter one valid Done tag, up to 255 characters, without spaces or empty :: levels.")
    return tag


def configured_topic_done_tag(config: Mapping[str, Any] | None = None) -> str:
    try:
        return normalize_topic_done_tag((config or {}).get("topic_done_tag"))
    except ValueError:
        return DEFAULT_TOPIC_DONE_TAG


def configured_reviewer_button_visibility(
    config: Mapping[str, Any] | None = None,
) -> dict[str, bool]:
    raw = (config or {}).get("reviewer_button_visibility")
    values = raw if isinstance(raw, Mapping) else {}
    return {
        name: _bool(values.get(name), default)
        for name, default in DEFAULT_REVIEWER_BUTTON_VISIBILITY.items()
    }


def configured_reviewer_button_group_visible(
    config: Mapping[str, Any] | None = None,
) -> bool:
    return _bool((config or {}).get("reviewer_button_group_visible"), True)


def normalize_config(raw: Mapping[str, Any] | None) -> dict:
    """Return a validated config while preserving forward-compatible keys."""
    config = copy.deepcopy(dict(raw or {}))
    config["ui_language"] = normalize_language_choice(config.get("ui_language"))
    config["config_schema_version"] = CONFIG_SCHEMA_VERSION
    config["topic_done_tag"] = configured_topic_done_tag(config)
    backup_profiles = config.get("automatic_backups")
    config["automatic_backups"] = {
        str(profile): normalize_policy(policy)
        for profile, policy in (
            backup_profiles.items() if isinstance(backup_profiles, Mapping) else []
        )
        if isinstance(profile, str) and profile and isinstance(policy, Mapping)
    }

    for key, boolean_default in _BOOLEAN_DEFAULTS.items():
        if key in config:
            config[key] = _bool(config.get(key), boolean_default)
    if "reviewer_priority_badge_card_types" in config:
        raw_badge_types = config["reviewer_priority_badge_card_types"]
        badge_types = (
            copy.deepcopy(dict(raw_badge_types))
            if isinstance(raw_badge_types, Mapping)
            else {}
        )
        for kind in ("topics", "items"):
            badge_types[kind] = _bool(badge_types.get(kind), True)
        config["reviewer_priority_badge_card_types"] = badge_types
    if "reviewer_button_visibility" in config:
        raw_visibility = config["reviewer_button_visibility"]
        config["reviewer_button_visibility"] = {
            **(copy.deepcopy(dict(raw_visibility)) if isinstance(raw_visibility, Mapping) else {}),
            **configured_reviewer_button_visibility(config),
        }
    for key, (number_default, minimum, maximum, cast) in _NUMBER_LIMITS.items():
        if key in config:
            config[key] = _number(
                config.get(key), number_default, minimum, maximum, cast
            )

    config["dialog"] = _normalize_dialog(config.get("dialog"))

    # "profiles" was the historical name for scheduler presets and was often
    # confused with Anki profiles. Keep a synchronized compatibility alias
    # while new code and exported config use the explicit name.
    presets = config.get("scheduler_presets")
    if not isinstance(presets, Mapping):
        presets = config.get("profiles")
    normalized_presets = {
        str(name): _normalize_dialog(values)
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
