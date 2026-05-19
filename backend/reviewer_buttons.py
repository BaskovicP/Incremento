from __future__ import annotations

from typing import Literal

try:
    from .topic_scheduler import is_topic_card
except ImportError:
    from topic_scheduler import is_topic_card  # type: ignore


_DEFAULT_USE_FAIL_PASS_ON_ITEMS = True


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
    # Anki's Good button is not always ease 3: active learning steps can expose
    # only two or three answer buttons, where ease 2 is the Good/pass choice.
    return 2 if count <= 3 else 3


def _card_is_new(card) -> bool:
    if card is None:
        return False
    for attr in ("type", "queue"):
        try:
            if int(getattr(card, attr, -1) or 0) == 0:
                return True
        except Exception:
            continue
    return False


def _card_is_learning(card) -> bool:
    if card is None:
        return False
    for attr in ("type", "queue"):
        try:
            if int(getattr(card, attr, -1) or 0) in {1, 3}:
                return True
        except Exception:
            continue
    return False


def _card_is_review(card) -> bool:
    if card is None:
        return False
    for attr in ("type", "queue"):
        try:
            if int(getattr(card, attr, -1) or 0) == 2:
                return True
        except Exception:
            continue
    return False


def remap_item_fail_pass_ease(card, ease: int) -> int:
    try:
        value = int(ease)
    except Exception:
        return 2
    if value != 2:
        return value
    if _card_is_learning(card):
        return 2
    if _card_is_new(card) or _card_is_review(card):
        return 3
    return 2


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
