import random
from typing import NamedTuple

import cards as card_utils


class SchedulerResult(NamedTuple):
    card: object
    card_type: str        # "topics" | "items"  (actual, after fallbacks)
    tag: str | None       # tag used, or None if fallback ignored it
    mode: str             # "random" | "priority"


def soft_pick(weights: dict, counts: dict, alpha=0.2, epsilon=0.05) -> str:
    """Debt-based weighted random selection"""
    n = sum(counts.values())
    probs = {k: max(w * n - counts.get(k, 0) + alpha, epsilon) for k, w in weights.items()}
    total = sum(probs.values())

    r = random.random()
    for key, p in probs.items():
        r -= p / total
        if r <= 0:
            return key
    return key


def get_card_from_scheduler(
        topics_rate=0.3,
        random_rate=0.5,
        tag_weights={"health": 0.5, "psych": 0.3, "other": 0.2},
        use_tags=True,
        counts=None,
        alpha=0.2,
        epsilon=0.05
):
    if counts is None:
        counts = {"type": {}, "tags": {}, "mode": {}}

    # 1. Decisions
    card_type = soft_pick({"topics": topics_rate, "items": 1 - topics_rate}, counts["type"], alpha, epsilon)
    mode = soft_pick({"random": random_rate, "priority": 1 - random_rate}, counts["mode"], alpha, epsilon)

    # 2. Fetch with fallbacks (track what we actually used)
    actual_type = card_type
    actual_tag = None

    if use_tags:
        tag = soft_pick(tag_weights, counts["tags"], alpha, epsilon)
        actual_tag = tag
        fetch = card_utils.get_topic_cards_by_tag if card_type == "topics" else card_utils.get_item_cards_by_tag
        cards = fetch(tag)

        if not cards:
            actual_tag = None  # tag ignored
            cards = card_utils.get_all_topic_cards() if card_type == "topics" else card_utils.get_all_item_cards()
    else:
        cards = card_utils.get_all_topic_cards() if card_type == "topics" else card_utils.get_all_item_cards()

    if not cards:
        actual_type = "items" if card_type == "topics" else "topics"
        cards = card_utils.get_all_item_cards() if card_type == "topics" else card_utils.get_all_topic_cards()

    if not cards:
        return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    # 3. Update counts based on what we ACTUALLY used
    counts["type"][actual_type] = counts["type"].get(actual_type, 0) + 1
    counts["mode"][mode] = counts["mode"].get(mode, 0) + 1
    if actual_tag:
        counts["tags"][actual_tag] = counts["tags"].get(actual_tag, 0) + 1

    card = random.choice(cards) if mode == "random" else cards[0]
    return SchedulerResult(card=card, card_type=actual_type, tag=actual_tag, mode=mode)