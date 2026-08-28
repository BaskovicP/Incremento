from __future__ import annotations

from typing import Literal

try:
    from .config_service import load_addon_config
    from .topic_scheduler import is_topic_card
except ImportError:
    from config_service import load_addon_config  # type: ignore
    from topic_scheduler import is_topic_card  # type: ignore


_DEFAULT_USE_FAIL_PASS_ON_ITEMS = True


def _resolved_config(config: dict | None = None) -> dict:
    if config is not None:
        return config or {}
    try:
        from aqt import mw

        addon_name = __name__.split(".")[0]
        return load_addon_config(mw.addonManager, addon_name)
    except Exception:
        return {}


def configured_use_fail_pass_on_items(config: dict | None = None) -> bool:
    cfg = _resolved_config(config)
    return bool(cfg.get("use_fail_pass_on_items", _DEFAULT_USE_FAIL_PASS_ON_ITEMS))


def item_pass_ease_for_button_count(button_count: int) -> int:
    del button_count
    return 3


def remap_item_fail_pass_ease(card, ease: int) -> int:
    del card
    try:
        value = int(ease)
    except Exception:
        return 3
    # Item buttons have fixed semantics in every Anki card state:
    # Fail is Again (1), while Pass is Good (3). In particular, Pass must not
    # become Hard (2) on learning/relearning cards or they can loop forever.
    return 3 if value == 2 else value


def item_pass_ease_for_card(card, button_count: int) -> int:
    del button_count
    return remap_item_fail_pass_ease(card, 2)


def item_fail_pass_buttons(button_count: int, card=None) -> tuple[tuple[int, str], ...]:
    del button_count, card
    return (
        (1, "Fail"),
        (2, "Pass"),
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
