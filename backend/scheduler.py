import random
from collections.abc import Iterable
from typing import NamedTuple

try:
    from . import cards as card_utils  # package context
    from .epub_manager import DOCUMENT_FILTER
except ImportError:
    import cards as card_utils          # sys.path context (tests)
    from epub_manager import DOCUMENT_FILTER  # type: ignore

# Synthetic key used when soft_pick selects the "other cards" bucket (the
# remainder outside selected tags). Returned as result.tag so the caller can track its
# debt correctly, but must be filtered before writing to persistent stats.
NO_TAGS_KEY = "__no_tags__"


def exclude_tags_from_filter(query: str, tags: Iterable[str]) -> str:
    """Restrict an Anki pool to cards outside every active tag group."""
    normalized = sorted({
        str(tag).strip() for tag in tags
        if str(tag).strip() and str(tag).strip() != NO_TAGS_KEY
    })
    if not normalized:
        return query
    terms = []
    for tag in normalized:
        escaped = tag.replace("\\", "\\\\").replace('"', '\\"')
        terms.append(f'tag:"{escaped}"')
    exclusion = "-(" + " OR ".join(terms) + ")"
    return f"({query}) {exclusion}" if str(query).strip() else exclusion


class SchedulerResult(NamedTuple):
    card: object
    card_type: str        # "topics" | "items" | "pdf" | "epub" | "youtube" | "webpage"
    tag: str | None       # tag used, or None if fallback ignored it
    mode: str             # "random" | "priority"
    study_kind: str | None = None  # semantic Topic/Item kind for an Item-classified document


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
        topics_filter: str = "",
        items_filter: str = "",
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

    # Treat endpoint ratios as hard exclusions, including during availability
    # fallback.  The UI/config boundary already normalizes these values, but
    # clamping here keeps direct callers from creating negative bucket weights.
    document_share = max(0.0, min(1.0, float(pdf_rate)))
    topic_share = max(0.0, min(1.0, float(topics_rate)))
    type_weights = {
        "pdf": topic_share * document_share,
        "topics": topic_share * (1.0 - document_share),
        "items": 1.0 - topic_share,
    }
    type_counts = dict(counts["type"])
    type_counts["pdf"] = type_counts.get("pdf", 0) + type_counts.pop("epub", 0)

    def enabled_standard_fallback(card_type: str) -> str | None:
        """Return an enabled Topics/Items fallback without crossing 0% endpoints."""
        if card_type == "topics":
            candidates = ("items",)
        elif card_type == "items":
            candidates = ("topics",)
        elif topic_share >= 0.5:
            candidates = ("topics", "items")
        else:
            candidates = ("items", "topics")
        return next((key for key in candidates if type_weights[key] > 0), None)

    # 1. Decisions
    if force_card_type is not None:
        card_type = force_card_type
    else:
        # Balance Topics/Items first, including documents in the Topic total.
        # A frontloaded document reservation must not inflate the Topic share.
        card_type = soft_pick(
            {"topics": topic_share, "items": 1.0 - topic_share},
            {"topics": type_counts.get("topics", 0) + type_counts["pdf"],
             "items": type_counts.get("items", 0)},
            alpha,
            epsilon,
        )
    if card_type == "topics" and document_share > 0:
        # Normal picks and strict Topic quotas share the same conditional mix.
        card_type = soft_pick(
            {"pdf": document_share, "topics": 1.0 - document_share},
            {kind: type_counts.get(kind, 0) for kind in ("pdf", "topics")}, alpha, epsilon,
        )

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

    # Documents cannot leak through the non-document Topic branch at Docs=0.
    # Item-classified documents remain Items, regardless of the Docs setting.
    pdf_exclusion = f" -({DOCUMENT_FILTER})"
    effective_topics_filter = topics_filter + pdf_exclusion
    effective_items_filter = items_filter
    topic_document_filter = f"({pdf_filter}) ({topics_filter})" if topics_filter.strip() else pdf_filter

    def _ct_pick(cache_prefix, all_fn, tag_fn, fn_kwargs, *, topic_only=False, fixed_tag=None):
        """Tag-aware pick within a content-type pool (pdf / youtube / webpage).

        If use_tags is on, does a soft_pick over tag weights first then fetches
        only cards matching that tag, or outside all active tags for Other.
        A missing real tag permits full-pool fallback only when opted in.
        Returns (cards, resolved_tag).
        """
        loader_kwargs = dict(fn_kwargs)
        if topic_only:
            cache_prefix += "_topics"
        if col is not None:
            loader_kwargs["col"] = col
        if topic_only:
            loader_kwargs.update(topic_only=True, topic_classifier=topic_classifier)
        if use_tags and tag_weights:
            remainder = max(0.0, 1.0 - sum(tag_weights.values())) if include_rest else 0.0
            extended = dict(tag_weights)
            if remainder > 1e-6:
                extended[NO_TAGS_KEY] = remainder
            tag = fixed_tag if fixed_tag is not None else soft_pick(extended, counts["tags"], alpha, epsilon)
            if tag == NO_TAGS_KEY:
                other_filters = {
                    key: exclude_tags_from_filter(value, tag_weights)
                    for key, value in fn_kwargs.items()
                }
                other_kwargs = dict(other_filters)
                if col is not None:
                    other_kwargs["col"] = col
                if topic_only:
                    other_kwargs.update(topic_only=True, topic_classifier=topic_classifier)
                return available(
                    cached_pool(
                        (cache_prefix, "other", tuple(sorted(other_filters.items()))),
                        lambda: all_fn(**other_kwargs),
                    )
                ), NO_TAGS_KEY
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

    def all_topics(*, other_only=False):
        pool_filter = (
            exclude_tags_from_filter(effective_topics_filter, tag_weights)
            if other_only else effective_topics_filter
        )
        kwargs = {
            "topics_filter": pool_filter,
            "ready_filter": ready_filter,
        }
        if col is not None:
            kwargs["col"] = col
        if topic_classifier is not None:
            kwargs["topic_classifier"] = topic_classifier
        return cached_pool(
            ("topics", "all", pool_filter, ready_filter),
            lambda: card_utils.get_all_topic_cards(**kwargs),
        )

    def all_items(*, other_only=False):
        pool_filter = (
            exclude_tags_from_filter(effective_items_filter, tag_weights)
            if other_only else effective_items_filter
        )
        kwargs = {
            "items_filter": pool_filter,
            "ready_filter": ready_filter,
        }
        if col is not None:
            kwargs["col"] = col
        if topic_classifier is not None:
            kwargs["topic_classifier"] = topic_classifier
        return cached_pool(
            ("items", "all", pool_filter, ready_filter),
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

    def document_topic_fallback(tag=None):
        """Exhaust an enabled sibling subtype without changing semantic kind/tag."""
        if document_share <= 0 or (topic_share <= 0 and force_card_type != "topics"):
            return None
        cards, resolved_tag = _ct_pick(
            "pdf", card_utils.get_all_pdf_cards, card_utils.get_pdf_cards_by_tag,
            {"pdf_filter": topic_document_filter}, topic_only=True, fixed_tag=tag,
        )
        if not cards:
            return None
        card = random.choice(cards) if mode == "random" else cards[0]
        doc_kwargs = {"col": col} if col is not None else {}
        doc_type = card_utils.get_document_card_type(card, **doc_kwargs) or "pdf"
        return SchedulerResult(card=card, card_type=doc_type, tag=resolved_tag, mode=mode)

    # 2a. PDF pick path — no ready_filter, always eligible
    if card_type == "pdf":
        pdf_cards, pdf_tag = _ct_pick(
            "pdf",
            card_utils.get_all_pdf_cards,
            card_utils.get_pdf_cards_by_tag,
            {"pdf_filter": topic_document_filter if force_card_type in (None, "topics") else pdf_filter},
            topic_only=force_card_type in (None, "topics"),
        )
        if pdf_cards:
            card = random.choice(pdf_cards) if mode == "random" else pdf_cards[0]
            doc_kwargs = {"col": col} if col is not None else {}
            doc_type = card_utils.get_document_card_type(card, **doc_kwargs) or "pdf"
            return SchedulerResult(card=card, card_type=doc_type, tag=pdf_tag, mode=mode)
        if force_card_type == "topics" and document_share < 1:
            # Exhaustion may cross subtypes within a forced Topic quota, but
            # must not borrow an Item or revive a 0% non-document subtype.
            actual_type = card_type = "topics"
        elif not allow_type_fallback:
            return SchedulerResult(card=None, card_type="pdf", tag=pdf_tag, mode=mode)
        else:
            fallback_type = enabled_standard_fallback(card_type)
            if fallback_type is None:
                return SchedulerResult(card=None, card_type="pdf", tag=pdf_tag, mode=mode)
            actual_type = fallback_type
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
        fallback_type = enabled_standard_fallback(card_type)
        if fallback_type is None:
            return SchedulerResult(card=None, card_type="youtube", tag=yt_tag, mode=mode)
        actual_type = fallback_type
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
        fallback_type = enabled_standard_fallback(card_type)
        if fallback_type is None:
            return SchedulerResult(card=None, card_type="webpage", tag=wp_tag, mode=mode)
        actual_type = fallback_type
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
            # Other excludes every selected tag, including across type fallback.
            if card_type == "topics":
                cards = available(all_topics(other_only=True))
            else:
                cards = available(all_items(other_only=True))
            if not cards and card_type == "topics":
                sibling = document_topic_fallback(NO_TAGS_KEY)
                if sibling is not None:
                    return sibling
            if not cards and allow_type_fallback:
                fallback_type = enabled_standard_fallback(card_type)
                if fallback_type == "items":
                    actual_type = fallback_type
                    cards = available(all_items(other_only=True))
                elif fallback_type == "topics":
                    actual_type = fallback_type
                    cards = available(all_topics(other_only=True))
            if not cards and card_type == "items" and allow_type_fallback:
                sibling = document_topic_fallback(NO_TAGS_KEY)
                if sibling is not None:
                    return sibling
            if not cards:
                return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)
        else:
            # Tag-constrained pick.
            # Primary: requested type + tag
            if card_type == "topics":
                cards = available(tagged_topics(tag))
            else:
                cards = available(tagged_items(tag))
            if not cards and card_type == "topics":
                sibling = document_topic_fallback(tag)
                if sibling is not None:
                    return sibling

            # Type fallback: try the other type, but STAY within the tag
            if not cards and allow_type_fallback:
                fallback_type = enabled_standard_fallback(card_type)
                if fallback_type == "items":
                    actual_type = fallback_type
                    cards = available(tagged_items(tag))
                elif fallback_type == "topics":
                    actual_type = fallback_type
                    cards = available(tagged_topics(tag))
            if not cards and card_type == "items" and allow_type_fallback:
                sibling = document_topic_fallback(tag)
                if sibling is not None:
                    return sibling

            # No cards at all for this tag → caller handles it (next tag or Phase 2)
            if not cards:
                return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    else:
        # No tag constraint — fetch all cards of the chosen type
        if card_type == "topics":
            cards = available(all_topics())
        else:
            cards = available(all_items())
        if not cards and card_type == "topics":
            sibling = document_topic_fallback()
            if sibling is not None:
                return sibling

        # Type fallback across all cards
        if not cards and allow_type_fallback:
            fallback_type = enabled_standard_fallback(card_type)
            if fallback_type == "items":
                actual_type = fallback_type
                cards = available(all_items())
            elif fallback_type == "topics":
                actual_type = fallback_type
                cards = available(all_topics())
        if not cards and card_type == "items" and allow_type_fallback:
            sibling = document_topic_fallback()
            if sibling is not None:
                return sibling

        if not cards:
            return SchedulerResult(card=None, card_type=actual_type, tag=actual_tag, mode=mode)

    card = random.choice(cards) if mode == "random" else cards[0]
    if actual_type == "items":
        doc_kwargs = {"col": col} if col is not None else {}
        doc_type = card_utils.get_document_card_type(card, **doc_kwargs)
        if doc_type:
            return SchedulerResult(card=card, card_type=doc_type, tag=actual_tag, mode=mode, study_kind="items")
    return SchedulerResult(card=card, card_type=actual_type, tag=actual_tag, mode=mode)
