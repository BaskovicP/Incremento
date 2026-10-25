"""Versioned normalization and persistence for Incremento add-on config."""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping

try:
    from .i18n import normalize_language_choice
except ImportError:
    from i18n import normalize_language_choice

try:
    from .backup_schedule import normalize_policy
    from .workspace_layouts import normalize_workspaces
except ImportError:
    from backup_schedule import normalize_policy
    from workspace_layouts import normalize_workspaces


CONFIG_SCHEMA_VERSION = 3
DOCUMENT_MIX_VERSION = 2
DEFAULT_TOPIC_DONE_TAG = "topic/done"
DEFAULT_LEARNING_LEECH_TAG = "learning_leech"
DEFAULT_REVIEWER_BUTTON_VISIBILITY = {
    "done": True,
    "postpone": True,
    "extract": True,
}
PDF_APPEARANCE_MODES = frozenset({"original", "dark", "night"})
MAX_PDF_SNAPSHOT_AUTO_FIELDS = 50
MAX_PDF_SNAPSHOT_FIELD_NAME_LENGTH = 255
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
    "pdf_force_default_appearance": False,
    "pdf_focus_mode": False,
    "epub_focus_mode": False,
    "pdf_link_hover_preview_enabled": True,
    "pdf_show_highlight_delete_buttons": True,
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
    "pdf_context_rows": (5, 1, 20, int),
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


def normalize_pdf_controls_preferences(value: Any) -> dict:
    """Missing choices retain the reader's automatic initial layout."""
    result: dict[str, dict[str, bool]] = {}
    if not isinstance(value, Mapping):
        return result
    for profile, readers in value.items():
        if not isinstance(profile, str) or not profile or len(profile) > 255 or not isinstance(readers, Mapping):
            continue
        choices = {key: readers[key] for key in ('main', 'side') if type(readers.get(key)) is bool}
        if choices:
            result[profile] = choices
    return result


def configured_pdf_controls_collapsed(
    config: Mapping[str, Any] | None, profile: str, *, reading_only: bool = False,
) -> bool | None:
    preferences = normalize_pdf_controls_preferences((config or {}).get('pdf_controls_collapsed_by_profile'))
    return preferences.get(profile, {}).get('side' if reading_only else 'main')


def configured_epub_controls_collapsed(config: Mapping[str, Any] | None, profile: str) -> bool | None:
    preferences = normalize_pdf_controls_preferences((config or {}).get('epub_controls_collapsed_by_profile'))
    return preferences.get(profile, {}).get('main')


def _number(value: Any, default, minimum, maximum, cast):
    try:
        resolved = float(value)
    except Exception:
        resolved = float(default)
    if resolved != resolved:
        resolved = float(default)
    bounded = min(float(maximum), max(float(minimum), resolved))
    return cast(bounded)


def configured_extract_default_type(config: Mapping[str, Any] | None = None) -> str:
    config = config or {}
    if "extract_default_type" not in config and "extract_mark_topic" in config:
        return "topic" if _bool(config["extract_mark_topic"], False) else "none"
    value = config.get("extract_default_type")
    kind = value.strip().casefold() if isinstance(value, str) else ""
    return kind if kind in {"item", "topic", "none"} else "item"


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


def configured_day_end_time(config: Mapping[str, Any] | None = None) -> str:
    """Resolve the shared study-day cutoff, retaining the old dialog value.

    The shipped default is null because Anki merges defaults before reading
    user config. This lets an existing dialog cutoff migrate on the first read.
    Session presets no longer own this setting.
    """
    config = config or {}
    value = config.get("day_end_time")
    if value is None:
        dialog = config.get("dialog")
        value = dialog.get("day_end_time") if isinstance(dialog, Mapping) else None
    text = value.strip() if isinstance(value, str) else ""
    return text if _DAY_END_RE.fullmatch(text) else "04:00"


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


def normalize_learning_leech_tag(value: object) -> str:
    """Validate a single learning-leech tag, retaining its stored spelling."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_LEARNING_LEECH_TAG
    try:
        return normalize_topic_done_tag(value)
    except ValueError as exc:
        raise ValueError("Enter one valid learning-leech tag.") from exc


def configured_learning_leech(config: Mapping[str, Any] | None = None) -> tuple[bool, int, str]:
    values = config or {}
    try:
        tag = normalize_learning_leech_tag(values.get("learning_leech_tag"))
    except ValueError:
        tag = DEFAULT_LEARNING_LEECH_TAG
    return (
        _bool(values.get("learning_leech_enabled"), False),
        _number(values.get("learning_leech_threshold"), 5, 1, 9999, int),
        tag,
    )


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


def normalize_pdf_appearance_mode(value: Any) -> str:
    """Return one supported PDF page appearance, defaulting safely to original."""
    if not isinstance(value, str):
        return "original"
    normalized = value.strip().casefold()
    return normalized if normalized in PDF_APPEARANCE_MODES else "original"


def configured_companion_browser(config: Mapping[str, Any] | None = None) -> str:
    value = (config or {}).get("companion_browser")
    browser = value.strip().casefold() if isinstance(value, str) else ""
    return browser if browser in {"chrome", "firefox"} else "chrome"


def configured_web_search_engine(config: Mapping[str, Any] | None = None) -> str:
    value = (config or {}).get("web_search_engine")
    engine = value.strip().casefold() if isinstance(value, str) else ""
    return engine if engine in {"google", "duckduckgo"} else "google"


def configured_search_remember_logins(config: Mapping[str, Any] | None = None) -> bool:
    return _bool((config or {}).get("search_remember_logins"), False)


def configured_pdf_default_appearance(
    config: Mapping[str, Any] | None = None,
) -> str:
    return normalize_pdf_appearance_mode((config or {}).get("pdf_default_appearance"))


def normalize_pdf_link_preview_zoom(raw: Any) -> float:
    try:
        zoom = float(raw) if not isinstance(raw, bool) else 1.5
    except (TypeError, ValueError, OverflowError):
        zoom = 1.5
    if not math.isfinite(zoom):
        zoom = 1.5
    return math.floor(min(4.0, max(1.0, zoom)) * 4 + 0.5) / 4


def configured_pdf_link_preview_zoom(config: Mapping[str, Any] | None, profile: str) -> float:
    values = (config or {}).get("pdf_link_preview_zoom_by_profile")
    return normalize_pdf_link_preview_zoom(values.get(profile) if isinstance(values, Mapping) else None)


def configured_pdf_force_default_appearance(
    config: Mapping[str, Any] | None = None,
) -> bool:
    return _bool((config or {}).get("pdf_force_default_appearance"), False)


def configured_pdf_snapshot_auto_field_enabled(
    config: Mapping[str, Any] | None = None,
) -> bool:
    return _bool((config or {}).get("pdf_snapshot_auto_field_enabled"), False)


def configured_pdf_context_rows(config: Mapping[str, Any] | None = None) -> int:
    """Return the shared before/after row count for PDF context previews."""
    return _number((config or {}).get("pdf_context_rows"), 5, 1, 20, int)


def configured_pdf_citation_page_numbering(config: Mapping[str, Any] | None = None) -> str:
    value = (config or {}).get("pdf_citation_page_numbering")
    mode = value.strip().casefold() if isinstance(value, str) else "printed"
    return mode if mode in {"printed", "pdf", "both"} else "printed"


def normalize_pdf_snapshot_auto_fields(value: Any) -> dict[str, str]:
    """Return a bounded note-type-to-field preference map."""
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, str] = {}
    for raw_note_type, raw_field in value.items():
        if len(normalized) >= MAX_PDF_SNAPSHOT_AUTO_FIELDS:
            break
        if not isinstance(raw_note_type, str) or not isinstance(raw_field, str):
            continue
        note_type = raw_note_type.strip()[:MAX_PDF_SNAPSHOT_FIELD_NAME_LENGTH]
        field_name = raw_field.strip()[:MAX_PDF_SNAPSHOT_FIELD_NAME_LENGTH]
        if note_type and field_name:
            normalized[note_type] = field_name
    return normalized


def normalize_config(raw: Mapping[str, Any] | None) -> dict:
    """Return a validated config while preserving forward-compatible keys."""
    config = copy.deepcopy(dict(raw or {}))
    config["companion_browser"] = configured_companion_browser(config)
    config["web_search_engine"] = configured_web_search_engine(config)
    config["search_remember_logins"] = configured_search_remember_logins(config)
    config["day_end_time"] = configured_day_end_time(config)
    config["ui_language"] = normalize_language_choice(config.get("ui_language"))
    config["config_schema_version"] = CONFIG_SCHEMA_VERSION
    config["extract_default_type"] = configured_extract_default_type(config)
    config["topic_done_tag"] = configured_topic_done_tag(config)
    (
        config["learning_leech_enabled"],
        config["learning_leech_threshold"],
        config["learning_leech_tag"],
    ) = configured_learning_leech(config)
    config["pdf_default_appearance"] = configured_pdf_default_appearance(config)
    config['pdf_controls_collapsed_by_profile'] = normalize_pdf_controls_preferences(
        config.get('pdf_controls_collapsed_by_profile'))
    config['epub_controls_collapsed_by_profile'] = normalize_pdf_controls_preferences(
        config.get('epub_controls_collapsed_by_profile'))
    config['workspace_layouts'] = normalize_workspaces(config.get('workspace_layouts'))
    preview_zooms = config.get("pdf_link_preview_zoom_by_profile")
    config["pdf_link_preview_zoom_by_profile"] = {
        profile: normalize_pdf_link_preview_zoom(value)
        for profile, value in (preview_zooms.items() if isinstance(preview_zooms, Mapping) else [])
        if isinstance(profile, str) and profile and len(profile) <= 255
    }
    config["pdf_citation_page_numbering"] = configured_pdf_citation_page_numbering(config)
    config["pdf_force_default_appearance"] = configured_pdf_force_default_appearance(config)
    config.setdefault("pdf_focus_mode", False)
    config["pdf_snapshot_auto_field_enabled"] = (
        configured_pdf_snapshot_auto_field_enabled(config)
    )
    config["pdf_snapshot_auto_fields"] = normalize_pdf_snapshot_auto_fields(
        config.get("pdf_snapshot_auto_fields")
    )
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
