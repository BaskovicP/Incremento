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
        use_tags=False,
        counts=None,
        alpha=0.2,
        epsilon=0.05,
        exclude_ids=None,
):
    if counts is None:
        counts = {"type": {}, "tags": {}, "mode": {}}
    exclude = set(exclude_ids) if exclude_ids else set()

    # 1. Decisions
    card_type = soft_pick({"topics": topics_rate, "items": 1 - topics_rate}, counts["type"], alpha, epsilon)
    mode = soft_pick({"random": random_rate, "priority": 1 - random_rate}, counts["mode"], alpha, epsilon)

    # 2. Fetch with fallbacks (track what we actually used)
    actual_type = card_type
    actual_tag = None

    def available(raw):
        return [c for c in raw if c not in exclude]

    if use_tags:
        tag = soft_pick(tag_weights, counts["tags"], alpha, epsilon)
        actual_tag = tag

        # Primary: requested type + tag
        fetch_primary = (card_utils.get_topic_cards_by_tag if card_type == "topics"
                         else card_utils.get_item_cards_by_tag)
        cards = available(fetch_primary(tag))

        # Type fallback: try the other type, but STAY within the tag
        if not cards:
            actual_type = "items" if card_type == "topics" else "topics"
            fetch_alt = (card_utils.get_item_cards_by_tag if card_type == "topics"
                         else card_utils.get_topic_cards_by_tag)
            cards = available(fetch_alt(tag))

        # No cards at all for this tag → caller handles it (next tag or Phase 2)
        if not cards:
            return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    else:
        # No tag constraint — fetch all cards of the chosen type
        cards = available(card_utils.get_all_topic_cards() if card_type == "topics"
                          else card_utils.get_all_item_cards())

        # Type fallback across all cards
        if not cards:
            actual_type = "items" if card_type == "topics" else "topics"
            cards = available(card_utils.get_all_item_cards() if card_type == "topics"
                              else card_utils.get_all_topic_cards())

        if not cards:
            return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    card = random.choice(cards) if mode == "random" else cards[0]
    return SchedulerResult(card=card, card_type=actual_type, tag=actual_tag, mode=mode)