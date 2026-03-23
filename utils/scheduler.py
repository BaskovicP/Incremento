import random
from typing import NamedTuple

import cards as card_utils

# Synthetic key used when soft_pick selects the "other cards" bucket (the
# untagged remainder).  Returned as result.tag so the caller can track its
# debt correctly, but must be filtered before writing to persistent stats.
NO_TAGS_KEY = "__no_tags__"


class SchedulerResult(NamedTuple):
    card: object
    card_type: str        # "topics" | "items" | "pdf"  (actual, after fallbacks)
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
        force_card_type=None,   # "topics" | "items" | "pdf" | None — skips soft_pick for type
        force_mode=None,        # "random" | "priority" | None — skips soft_pick for mode
        topics_filter: str = "deck:Topics",
        items_filter: str = "-deck:Topics",
        ready_filter: str = "(is:due OR is:learn OR is:new)",
        pdf_rate: float = 0.0,
        pdf_filter: str = 'note:"Incremento PDF"',
):
    if counts is None:
        counts = {"type": {}, "tags": {}, "mode": {}}
    exclude = set(exclude_ids) if exclude_ids else set()

    # 1. Decisions
    if force_card_type is not None:
        card_type = force_card_type
    elif pdf_rate > 0:
        # Three-way pick: pdf vs topics vs items
        card_type = soft_pick({
            "pdf":    pdf_rate,
            "topics": topics_rate * (1 - pdf_rate),
            "items":  (1 - topics_rate) * (1 - pdf_rate),
        }, counts["type"], alpha, epsilon)
    else:
        card_type = soft_pick(
            {"topics": topics_rate, "items": 1 - topics_rate}, counts["type"], alpha, epsilon)

    mode = force_mode if force_mode is not None else soft_pick(
        {"random": random_rate, "priority": 1 - random_rate}, counts["mode"], alpha, epsilon)

    # 2. Fetch with fallbacks (track what we actually used)
    actual_type = card_type
    actual_tag = None

    def available(raw):
        return [c for c in raw if c not in exclude]

    # When PDF cards are scheduled separately, exclude them from topics/items pools
    pdf_exclusion = f" -({pdf_filter})" if pdf_rate > 0 else ""
    effective_topics_filter = topics_filter + pdf_exclusion
    effective_items_filter  = items_filter  + pdf_exclusion

    # 2a. PDF pick path — no ready_filter, always eligible
    if card_type == "pdf":
        pdf_cards = available(card_utils.get_all_pdf_cards(pdf_filter=pdf_filter))
        if pdf_cards:
            card = random.choice(pdf_cards) if mode == "random" else pdf_cards[0]
            return SchedulerResult(card=card, card_type="pdf", tag=None, mode=mode)
        # Fallback: treat as topics or items
        actual_type = "topics" if topics_rate >= 0.5 else "items"
        card_type = actual_type

    if use_tags:
        # Build extended weights: add an "other cards" bucket for the
        # unallocated fraction (e.g. tags sum to 0.20 → other = 0.80).
        remainder = max(0.0, 1.0 - sum(tag_weights.values()))
        extended = dict(tag_weights)
        if remainder > 1e-6:
            extended[NO_TAGS_KEY] = remainder

        tag = soft_pick(extended, counts["tags"], alpha, epsilon)
        actual_tag = tag

        if tag == NO_TAGS_KEY:
            # "Other" bucket selected — fetch from the general pool (no tag filter).
            if card_type == "topics":
                cards = available(card_utils.get_all_topic_cards(
                    topics_filter=effective_topics_filter, ready_filter=ready_filter))
            else:
                cards = available(card_utils.get_all_item_cards(
                    items_filter=effective_items_filter, ready_filter=ready_filter))
            if not cards:
                actual_type = "items" if card_type == "topics" else "topics"
                if card_type == "topics":
                    cards = available(card_utils.get_all_item_cards(
                        items_filter=effective_items_filter, ready_filter=ready_filter))
                else:
                    cards = available(card_utils.get_all_topic_cards(
                        topics_filter=effective_topics_filter, ready_filter=ready_filter))
            if not cards:
                return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)
        else:
            # Tag-constrained pick.
            # Primary: requested type + tag
            if card_type == "topics":
                cards = available(card_utils.get_topic_cards_by_tag(
                    tag, topics_filter=effective_topics_filter, ready_filter=ready_filter))
            else:
                cards = available(card_utils.get_item_cards_by_tag(
                    tag, items_filter=effective_items_filter, ready_filter=ready_filter))

            # Type fallback: try the other type, but STAY within the tag
            if not cards:
                actual_type = "items" if card_type == "topics" else "topics"
                if card_type == "topics":
                    cards = available(card_utils.get_item_cards_by_tag(
                        tag, items_filter=effective_items_filter, ready_filter=ready_filter))
                else:
                    cards = available(card_utils.get_topic_cards_by_tag(
                        tag, topics_filter=effective_topics_filter, ready_filter=ready_filter))

            # No cards at all for this tag → caller handles it (next tag or Phase 2)
            if not cards:
                return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    else:
        # No tag constraint — fetch all cards of the chosen type
        if card_type == "topics":
            cards = available(card_utils.get_all_topic_cards(
                topics_filter=effective_topics_filter, ready_filter=ready_filter))
        else:
            cards = available(card_utils.get_all_item_cards(
                items_filter=effective_items_filter, ready_filter=ready_filter))

        # Type fallback across all cards
        if not cards:
            actual_type = "items" if card_type == "topics" else "topics"
            if card_type == "topics":
                cards = available(card_utils.get_all_item_cards(
                    items_filter=effective_items_filter, ready_filter=ready_filter))
            else:
                cards = available(card_utils.get_all_topic_cards(
                    topics_filter=effective_topics_filter, ready_filter=ready_filter))

        if not cards:
            return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    card = random.choice(cards) if mode == "random" else cards[0]
    return SchedulerResult(card=card, card_type=actual_type, tag=actual_tag, mode=mode)