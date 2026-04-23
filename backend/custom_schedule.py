"""Custom recurring schedule rules for browser-selected cards."""

from __future__ import annotations

import os
from datetime import date
from calendar import monthrange

from aqt import mw

try:
    from .db import (
        clear_custom_schedule_rule,
        get_custom_schedule_rule,
        get_topic_schedule,
        set_custom_schedule_rule,
        set_topic_schedule,
    )
    from .paths import get_active_profile as _active_profile
    from .topic_scheduler import is_topic_card
except ImportError:
    from db import (  # type: ignore
        clear_custom_schedule_rule,
        get_custom_schedule_rule,
        get_topic_schedule,
        set_custom_schedule_rule,
        set_topic_schedule,
    )
    from paths import get_active_profile as _active_profile  # type: ignore
    from topic_scheduler import is_topic_card  # type: ignore

_ADDON_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)

MODE_FIXED_REPEAT = "fixed_repeat"
MODE_MINIMUM_CADENCE = "minimum_cadence"
MODE_ONE_TIME = "one_time"
VALID_MODES = {MODE_FIXED_REPEAT, MODE_MINIMUM_CADENCE, MODE_ONE_TIME}

UNIT_DAYS = "days"
UNIT_WEEKS = "weeks"
UNIT_MONTHS = "months"
VALID_UNITS = {UNIT_DAYS, UNIT_WEEKS, UNIT_MONTHS}

_DEFAULT_MODE = MODE_MINIMUM_CADENCE
_DEFAULT_PRESETS = [
    {"label": "Daily", "interval_value": 1, "interval_unit": UNIT_DAYS},
    {"label": "Every 2 days", "interval_value": 2, "interval_unit": UNIT_DAYS},
    {"label": "Every 3 days", "interval_value": 3, "interval_unit": UNIT_DAYS},
    {"label": "Weekly", "interval_value": 1, "interval_unit": UNIT_WEEKS},
    {"label": "Every 2 weeks", "interval_value": 2, "interval_unit": UNIT_WEEKS},
    {"label": "Monthly", "interval_value": 1, "interval_unit": UNIT_MONTHS},
]


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        addon_name = __name__.split(".")[0]
        return mw.addonManager.getConfig(addon_name) or {}
    except Exception:
        return {}


def normalize_custom_schedule_mode(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in VALID_MODES:
        return raw
    return _DEFAULT_MODE


def normalize_custom_schedule_unit(value) -> str:
    raw = str(value or "").strip().lower()
    if raw in VALID_UNITS:
        return raw
    return UNIT_DAYS


def normalize_custom_schedule_interval_value(value) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = 2
    return max(1, min(999, parsed))


def normalize_custom_schedule_preset(raw: dict | None, index: int = 0) -> dict:
    raw = raw or {}
    interval_value = normalize_custom_schedule_interval_value(raw.get("interval_value"))
    interval_unit = normalize_custom_schedule_unit(raw.get("interval_unit"))
    label = str(raw.get("label") or "").strip()
    if not label:
        label = format_custom_schedule_value(interval_value, interval_unit)
    return {
        "label": label[:120],
        "interval_value": interval_value,
        "interval_unit": interval_unit,
        "sort_order": max(0, int(raw.get("sort_order", index) or index)),
    }


def configured_custom_schedule_default_mode(config: dict | None = None) -> str:
    cfg = _resolved_config(config)
    return normalize_custom_schedule_mode(cfg.get("custom_schedule_default_mode"))


def configured_custom_schedule_presets(config: dict | None = None) -> list[dict]:
    cfg = _resolved_config(config)
    raw = cfg.get("custom_schedule_presets")
    if not isinstance(raw, list):
        raw = list(_DEFAULT_PRESETS)
    normalized: list[dict] = []
    seen: set[tuple[str, int, str]] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        preset = normalize_custom_schedule_preset(item, index=index)
        key = (
            str(preset["label"]).strip().lower(),
            int(preset["interval_value"]),
            str(preset["interval_unit"]),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(preset)
    if not normalized:
        normalized = [normalize_custom_schedule_preset(item, index=i) for i, item in enumerate(_DEFAULT_PRESETS)]
    normalized.sort(key=lambda item: (int(item["sort_order"]), str(item["label"]).lower()))
    return normalized


def normalize_custom_schedule_rule(rule: dict | None) -> dict:
    base = rule or {}
    return {
        "card_id": int(base.get("card_id") or 0),
        "enabled": bool(base.get("enabled", True)),
        "mode": normalize_custom_schedule_mode(base.get("mode")),
        "interval_value": normalize_custom_schedule_interval_value(base.get("interval_value")),
        "interval_unit": normalize_custom_schedule_unit(base.get("interval_unit")),
        "preset_label": str(base.get("preset_label") or "").strip()[:120],
        "created_at": int(base.get("created_at") or 0),
        "updated_at": int(base.get("updated_at") or 0),
    }


def format_custom_schedule_value(interval_value: int, interval_unit: str) -> str:
    interval_value = normalize_custom_schedule_interval_value(interval_value)
    interval_unit = normalize_custom_schedule_unit(interval_unit)
    singular = {
        UNIT_DAYS: "day",
        UNIT_WEEKS: "week",
        UNIT_MONTHS: "month",
    }[interval_unit]
    plural = singular + "s"
    noun = singular if interval_value == 1 else plural
    return f"Every {interval_value} {noun}"


def format_custom_schedule_mode(mode: str) -> str:
    mode = normalize_custom_schedule_mode(mode)
    if mode == MODE_FIXED_REPEAT:
        return "Repeat exactly"
    if mode == MODE_ONE_TIME:
        return "One-time set due"
    return "Minimum cadence"


def format_custom_schedule_rule(rule: dict | None) -> str:
    if not rule:
        return ""
    normalized = normalize_custom_schedule_rule(rule)
    if not normalized.get("enabled"):
        return ""
    label = str(normalized.get("preset_label") or "").strip()
    if not label:
        label = format_custom_schedule_value(
            int(normalized["interval_value"]),
            str(normalized["interval_unit"]),
        )
    return f"{label} · {format_custom_schedule_mode(str(normalized['mode']))}"


def add_calendar_months(start: date, months: int) -> date:
    months = max(1, int(months))
    total_month = (start.month - 1) + months
    year = start.year + total_month // 12
    month = (total_month % 12) + 1
    day = min(start.day, monthrange(year, month)[1])
    return date(year, month, day)


def rule_days_from_today(
    interval_value: int,
    interval_unit: str,
    *,
    today: date | None = None,
) -> int:
    today = today or date.today()
    interval_value = normalize_custom_schedule_interval_value(interval_value)
    interval_unit = normalize_custom_schedule_unit(interval_unit)
    if interval_unit == UNIT_DAYS:
        return interval_value
    if interval_unit == UNIT_WEEKS:
        return interval_value * 7
    target = add_calendar_months(today, interval_value)
    return max(1, (target - today).days)


def _current_card_interval_days(card) -> int | None:
    try:
        interval = int(getattr(card, "ivl", 0) or 0)
    except Exception:
        interval = 0
    if interval > 0:
        return interval
    return None


def apply_rule_now_to_card(card_id: int, rule: dict | None = None, *, today: date | None = None) -> bool:
    normalized = normalize_custom_schedule_rule(
        rule or get_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card_id))
    )
    if not normalized.get("enabled"):
        return False
    try:
        card = mw.col.get_card(int(card_id))
    except Exception:
        card = None
    if card is None:
        return False

    target_days = rule_days_from_today(
        int(normalized["interval_value"]),
        str(normalized["interval_unit"]),
        today=today,
    )
    mode = str(normalized["mode"])
    if mode == MODE_MINIMUM_CADENCE:
        current_days = _current_card_interval_days(card)
        if current_days is not None and current_days <= target_days:
            return False

    mw.col.sched.set_due_date([int(card_id)], str(target_days))
    if mode == MODE_FIXED_REPEAT and is_topic_card(card):
        try:
            a_factor, _interval = get_topic_schedule(_ADDON_DIR, _active_profile(), int(card_id))
            set_topic_schedule(_ADDON_DIR, _active_profile(), int(card_id), a_factor, target_days)
        except Exception:
            pass
    if mode == MODE_ONE_TIME:
        clear_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card_id))
    return True


def apply_custom_schedule_after_answer(reviewer, card, ease: int) -> None:
    del reviewer, ease
    if card is None:
        return
    rule = get_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card.id))
    if not rule or not bool(rule.get("enabled")):
        return

    normalized = normalize_custom_schedule_rule(rule)
    target_days = rule_days_from_today(
        int(normalized["interval_value"]),
        str(normalized["interval_unit"]),
    )
    mode = str(normalized["mode"])
    try:
        latest_card = mw.col.get_card(int(card.id))
    except Exception:
        latest_card = card

    if mode == MODE_MINIMUM_CADENCE:
        current_days = _current_card_interval_days(latest_card)
        if current_days is not None and current_days <= target_days:
            return

    mw.col.sched.set_due_date([int(card.id)], str(target_days))
    if mode == MODE_FIXED_REPEAT and is_topic_card(latest_card):
        try:
            a_factor, _interval = get_topic_schedule(_ADDON_DIR, _active_profile(), int(card.id))
            set_topic_schedule(_ADDON_DIR, _active_profile(), int(card.id), a_factor, target_days)
        except Exception:
            pass
    if mode == MODE_ONE_TIME:
        clear_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card.id))


def save_custom_schedule_rule(
    card_ids: list[int] | tuple[int, ...] | set[int],
    *,
    mode: str,
    interval_value: int,
    interval_unit: str,
    preset_label: str = "",
) -> int:
    normalized_ids = sorted({int(card_id) for card_id in (card_ids or [])})
    if not normalized_ids:
        return 0
    for card_id in normalized_ids:
        set_custom_schedule_rule(
            _ADDON_DIR,
            _active_profile(),
            int(card_id),
            enabled=True,
            mode=mode,
            interval_value=interval_value,
            interval_unit=interval_unit,
            preset_label=preset_label,
        )
    return len(normalized_ids)


def clear_custom_schedule_rules(card_ids: list[int] | tuple[int, ...] | set[int]) -> int:
    deleted = 0
    for card_id in sorted({int(card_id) for card_id in (card_ids or [])}):
        if clear_custom_schedule_rule(_ADDON_DIR, _active_profile(), int(card_id)):
            deleted += 1
    return deleted
