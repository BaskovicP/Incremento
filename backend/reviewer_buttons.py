from __future__ import annotations

from typing import Literal

try:
    from .topic_scheduler import is_topic_card
except ImportError:
    from topic_scheduler import is_topic_card  # type: ignore


_DEFAULT_USE_FAIL_PASS_ON_ITEMS = False


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        from aqt import mw

        addon_name = __name__.split(".")[0]
        return mw.addonManager.getConfig(addon_name) or {}
    except Exception:
        return {}


def configured_use_fail_pass_on_items(config: dict | None = None) -> bool:
    cfg = _resolved_config(config)
    return bool(cfg.get("use_fail_pass_on_items", _DEFAULT_USE_FAIL_PASS_ON_ITEMS))


def item_pass_ease_for_button_count(button_count: int) -> int:
    try:
        count = int(button_count)
    except Exception:
        count = 4
    return 2 if count <= 3 else 3


def item_fail_pass_buttons(button_count: int) -> tuple[tuple[int, str], ...]:
    return (
        (1, "Fail"),
        (item_pass_ease_for_button_count(button_count), "Pass"),
    )


def reviewer_button_mode(
    card,
    *,
    use_fail_pass_on_items: bool | None = None,
) -> Literal["topic", "items_fail_pass", "standard"]:
    if card is None:
        return "standard"
    if is_topic_card(card):
        return "topic"
    if use_fail_pass_on_items is None:
        use_fail_pass_on_items = configured_use_fail_pass_on_items()
    if use_fail_pass_on_items:
        return "items_fail_pass"
    return "standard"
