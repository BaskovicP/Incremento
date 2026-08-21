import random
from typing import NamedTuple

try:
    from . import cards as card_utils  # package context
    from .epub_manager import DOCUMENT_FILTER
except ImportError:
    import cards as card_utils          # sys.path context (tests)
    from epub_manager import DOCUMENT_FILTER  # type: ignore

# Synthetic key used when soft_pick selects the "other cards" bucket (the
# untagged remainder).  Returned as result.tag so the caller can track its
# debt correctly, but must be filtered before writing to persistent stats.
NO_TAGS_KEY = "__no_tags__"


class SchedulerResult(NamedTuple):
    card: object
    card_type: str        # "topics" | "items" | "pdf" | "epub" | "youtube" | "webpage"
    tag: str | None       # tag used, or None if fallback ignored it
    mode: str             # "random" | "priority"


def soft_pick(weights: dict, counts: dict, alpha=0.2, epsilon=0.05) -> str:
    """Debt-based weighted random selection.

    A zero weight means that the bucket is disabled.  It must not receive the
    epsilon floor used to keep *enabled* but over-represented buckets
    selectable; otherwise endpoint settings such as 100% Topics or 100%
    Priority occasionally leak cards from the 0% bucket.
    """
    positive_weights = {key: weight for key, weight in weights.items() if weight > 0}
    if not positive_weights:
        # Invalid callers are safer with the historical uniform fallback than
        # with a crash in the middle of session construction.
        positive_weights = {key: 1.0 for key in weights}
    if len(positive_weights) == 1:
        return next(iter(positive_weights))

    n = sum(counts.values())
    probs = {
        key: max(weight * n - counts.get(key, 0) + alpha, epsilon)
        for key, weight in positive_weights.items()
    }
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
        include_rest: bool = True,
        counts=None,
        alpha=0.2,
        epsilon=0.05,
        exclude_ids=None,
        force_card_type=None,   # "topics" | "items" | "pdf" | "youtube" | "webpage" | None
        force_mode=None,        # "random" | "priority" | None — skips soft_pick for mode
        topics_filter: str = "deck:Topics",
        items_filter: str = "-deck:Topics",
        ready_filter: str = "(is:new OR (is:learn is:due) OR (is:review is:due)) -is:suspended",
        pdf_rate: float = 0.0,
        pdf_filter: str = DOCUMENT_FILTER,
        youtube_filter: str = 'note:"Incremento Video"',
        webpage_filter: str = 'note:"Incremento Web"',
        addon_dir: str | None = None,
        priority_lower_is_more_important: bool = True,
        allow_content_tag_fallback: bool = False,
        pool_cache: dict | None = None,
        col=None,
        topic_classifier=None,
        profile: str | None = None,
):
    if counts is None:
        counts = {"type": {}, "tags": {}, "mode": {}}
    exclude = exclude_ids if isinstance(exclude_ids, set) else set(exclude_ids or ())

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

    # 2. Fetch with fallbacks (track what we actually used).  A forced type is
    # a strict quota request: if that pool is empty, report a miss so the
    # session picker can advance to the next phase without consuming another
    # type's cards under the wrong quota.
    allow_type_fallback = force_card_type is None
    actual_type = card_type
    actual_tag = None

    def cached_pool(key, loader):
        if pool_cache is None:
            return loader()
        cache_key = ("scheduler_pool",) + tuple(key)
        if cache_key not in pool_cache:
            pool_cache[cache_key] = tuple(loader())
        return pool_cache[cache_key]

    def priority_available(raw):
        if pool_cache is None:
            sort_kwargs = {
                "addon_dir": addon_dir,
                "lower_is_more_important": priority_lower_is_more_important,
            }
            if col is not None:
                sort_kwargs["col"] = col
            if profile is not None:
                sort_kwargs["profile"] = profile
            return card_utils.sort_cards_for_priority_mode(
                [c for c in raw if c not in exclude], **sort_kwargs
            )

        order_key = (
            "scheduler_priority_order",
            id(raw),
            str(addon_dir or ""),
            bool(priority_lower_is_more_important),
        )
        if order_key not in pool_cache:
            sort_kwargs = {
                "addon_dir": addon_dir,
                "lower_is_more_important": priority_lower_is_more_important,
            }
            if col is not None:
                sort_kwargs["col"] = col
            if profile is not None:
                sort_kwargs["profile"] = profile
            pool_cache[order_key] = tuple(
                card_utils.sort_cards_for_priority_mode(raw, **sort_kwargs)
            )
        ordered = pool_cache[order_key]
        cursor_key = ("scheduler_priority_cursor",) + order_key[1:]
        cursor = max(0, int(pool_cache.get(cursor_key, 0) or 0))
        while cursor < len(ordered) and ordered[cursor] in exclude:
            cursor += 1
        pool_cache[cursor_key] = cursor
        if cursor >= len(ordered):
            return []
        # Priority mode only ever consumes the first available candidate.  Do
        # not rebuild a shrinking list of every remaining card on each pick.
        return [ordered[cursor]]

    def random_available(raw):
        if pool_cache is None:
            return [c for c in raw if c not in exclude]

        order_key = ("scheduler_random_order", id(raw))
        if order_key not in pool_cache:
            shuffled = list(raw)
            random.shuffle(shuffled)
            pool_cache[order_key] = tuple(shuffled)
        ordered = pool_cache[order_key]
        cursor_key = ("scheduler_random_cursor", id(raw))
        cursor = max(0, int(pool_cache.get(cursor_key, 0) or 0))
        while cursor < len(ordered) and ordered[cursor] in exclude:
            cursor += 1
        pool_cache[cursor_key] = cursor
        if cursor >= len(ordered):
            return []
        # A cached random pool is shuffled once. Returning its next candidate
        # avoids rebuilding an ever-shrinking list for every session pick.
        return [ordered[cursor]]

    def available(raw):
        if mode == "priority":
            return priority_available(raw)
        return random_available(raw)

    # When PDF cards are scheduled separately, exclude them from topics/items pools
    pdf_exclusion = f" -({pdf_filter})" if pdf_rate > 0 else ""
    effective_topics_filter = topics_filter + pdf_exclusion
    effective_items_filter  = items_filter  + pdf_exclusion

    def _ct_pick(cache_prefix, all_fn, tag_fn, fn_kwargs):
        """Tag-aware pick within a content-type pool (pdf / youtube / webpage).

        If use_tags is on, does a soft_pick over tag weights first then fetches
        only cards matching that tag.  Falls back to the full pool if the tag
        has no cards of this type.  Returns (cards, resolved_tag).
        """
        loader_kwargs = dict(fn_kwargs)
        if col is not None:
            loader_kwargs["col"] = col
        if use_tags and tag_weights:
            remainder = max(0.0, 1.0 - sum(tag_weights.values())) if include_rest else 0.0
            extended = dict(tag_weights)
            if remainder > 1e-6:
                extended[NO_TAGS_KEY] = remainder
            tag = soft_pick(extended, counts["tags"], alpha, epsilon)
            if tag != NO_TAGS_KEY:
                tagged = available(
                    cached_pool(
                        (cache_prefix, "tag", tag, tuple(sorted(fn_kwargs.items()))),
                        lambda: tag_fn(tag, **loader_kwargs),
                    )
                )
                if tagged:
                    return tagged, tag
                if not allow_content_tag_fallback:
                    return [], tag
                # Tag has no cards of this content type — fall back to full pool
            return available(
                cached_pool(
                    (cache_prefix, "all", tuple(sorted(fn_kwargs.items()))),
                    lambda: all_fn(**loader_kwargs),
                )
            ), None
        return available(
            cached_pool(
                (cache_prefix, "all", tuple(sorted(fn_kwargs.items()))),
                lambda: all_fn(**loader_kwargs),
            )
        ), None

    def all_topics():
        kwargs = {
            "topics_filter": effective_topics_filter,
            "ready_filter": ready_filter,
        }
        if col is not None:
            kwargs["col"] = col
        if topic_classifier is not None:
            kwargs["topic_classifier"] = topic_classifier
        return cached_pool(
            ("topics", "all", effective_topics_filter, ready_filter),
            lambda: card_utils.get_all_topic_cards(**kwargs),
        )

    def all_items():
        kwargs = {
            "items_filter": effective_items_filter,
            "ready_filter": ready_filter,
        }
        if col is not None:
            kwargs["col"] = col
        if topic_classifier is not None:
            kwargs["topic_classifier"] = topic_classifier
        return cached_pool(
            ("items", "all", effective_items_filter, ready_filter),
            lambda: card_utils.get_all_item_cards(**kwargs),
        )

    def tagged_topics(tag):
        kwargs = {
            "topics_filter": effective_topics_filter,
            "ready_filter": ready_filter,
        }
        if col is not None:
            kwargs["col"] = col
        if topic_classifier is not None:
            kwargs["topic_classifier"] = topic_classifier
        return cached_pool(
            ("topics", "tag", tag, effective_topics_filter, ready_filter),
            lambda: card_utils.get_topic_cards_by_tag(tag, **kwargs),
        )

    def tagged_items(tag):
        kwargs = {
            "items_filter": effective_items_filter,
            "ready_filter": ready_filter,
        }
        if col is not None:
            kwargs["col"] = col
        if topic_classifier is not None:
            kwargs["topic_classifier"] = topic_classifier
        return cached_pool(
            ("items", "tag", tag, effective_items_filter, ready_filter),
            lambda: card_utils.get_item_cards_by_tag(tag, **kwargs),
        )

    # 2a. PDF pick path — no ready_filter, always eligible
    if card_type == "pdf":
        pdf_cards, pdf_tag = _ct_pick(
            "pdf",
            card_utils.get_all_pdf_cards,
            card_utils.get_pdf_cards_by_tag,
            {"pdf_filter": pdf_filter},
        )
        if pdf_cards:
            card = random.choice(pdf_cards) if mode == "random" else pdf_cards[0]
            doc_kwargs = {"col": col} if col is not None else {}
            doc_type = card_utils.get_document_card_type(card, **doc_kwargs) or "pdf"
            return SchedulerResult(card=card, card_type=doc_type, tag=pdf_tag, mode=mode)
        if not allow_type_fallback:
            return SchedulerResult(card=None, card_type="pdf", tag=pdf_tag, mode=mode)
        actual_type = "topics" if topics_rate >= 0.5 else "items"
        card_type = actual_type

    # 2b. YouTube pick path — no ready_filter, always eligible
    if card_type == "youtube":
        yt_cards, yt_tag = _ct_pick(
            "youtube",
            card_utils.get_all_youtube_cards,
            card_utils.get_youtube_cards_by_tag,
            {"youtube_filter": youtube_filter},
        )
        if yt_cards:
            card = random.choice(yt_cards) if mode == "random" else yt_cards[0]
            return SchedulerResult(card=card, card_type="youtube", tag=yt_tag, mode=mode)
        if not allow_type_fallback:
            return SchedulerResult(card=None, card_type="youtube", tag=yt_tag, mode=mode)
        actual_type = "topics" if topics_rate >= 0.5 else "items"
        card_type = actual_type

    # 2c. Webpage pick path — no ready_filter, always eligible
    if card_type == "webpage":
        wp_cards, wp_tag = _ct_pick(
            "webpage",
            card_utils.get_all_webpage_cards,
            card_utils.get_webpage_cards_by_tag,
            {"webpage_filter": webpage_filter},
        )
        if wp_cards:
            card = random.choice(wp_cards) if mode == "random" else wp_cards[0]
            return SchedulerResult(card=card, card_type="webpage", tag=wp_tag, mode=mode)
        if not allow_type_fallback:
            return SchedulerResult(card=None, card_type="webpage", tag=wp_tag, mode=mode)
        actual_type = "topics" if topics_rate >= 0.5 else "items"
        card_type = actual_type

    if use_tags:
        # Build extended weights: add an "other cards" bucket for the
        # unallocated fraction (e.g. tags sum to 0.20 → other = 0.80).
        remainder = max(0.0, 1.0 - sum(tag_weights.values())) if include_rest else 0.0
        extended = dict(tag_weights)
        if remainder > 1e-6:
            extended[NO_TAGS_KEY] = remainder

        tag = soft_pick(extended, counts["tags"], alpha, epsilon)
        actual_tag = tag

        if tag == NO_TAGS_KEY:
            # "Other" bucket selected — fetch from the general pool (no tag filter).
            if card_type == "topics":
                cards = available(all_topics())
            else:
                cards = available(all_items())
            if not cards and allow_type_fallback:
                actual_type = "items" if card_type == "topics" else "topics"
                if card_type == "topics":
                    cards = available(all_items())
                else:
                    cards = available(all_topics())
            if not cards:
                return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)
        else:
            # Tag-constrained pick.
            # Primary: requested type + tag
            if card_type == "topics":
                cards = available(tagged_topics(tag))
            else:
                cards = available(tagged_items(tag))

            # Type fallback: try the other type, but STAY within the tag
            if not cards and allow_type_fallback:
                actual_type = "items" if card_type == "topics" else "topics"
                if card_type == "topics":
                    cards = available(tagged_items(tag))
                else:
                    cards = available(tagged_topics(tag))

            # No cards at all for this tag → caller handles it (next tag or Phase 2)
            if not cards:
                return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    else:
        # No tag constraint — fetch all cards of the chosen type
        if card_type == "topics":
            cards = available(all_topics())
        else:
            cards = available(all_items())

        # Type fallback across all cards
        if not cards and allow_type_fallback:
            actual_type = "items" if card_type == "topics" else "topics"
            if card_type == "topics":
                cards = available(all_items())
            else:
                cards = available(all_topics())

        if not cards:
            return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    card = random.choice(cards) if mode == "random" else cards[0]
    return SchedulerResult(card=card, card_type=actual_type, tag=actual_tag, mode=mode)
