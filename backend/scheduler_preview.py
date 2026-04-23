try:
    from .scheduler_config import NO_TAGS_KEY
except ImportError:
    from scheduler_config import NO_TAGS_KEY  # type: ignore


def _apportion_counts(total: int, shares: dict[str, float]) -> dict[str, int]:
    """Map fractional shares to integer counts that sum to total."""
    if total <= 0:
        return {k: 0 for k in shares}

    raw = {k: max(0.0, v) * total for k, v in shares.items()}
    counts = {k: int(raw[k]) for k in shares}
    remainder = total - sum(counts.values())
    if remainder <= 0:
        return counts

    # Largest-remainder allocation with key-order tie-break for determinism.
    ranked = sorted(
        shares.keys(),
        key=lambda k: (raw[k] - counts[k], k),
        reverse=True,
    )
    for i in range(remainder):
        counts[ranked[i % len(ranked)]] += 1
    return counts


def compute_expected_mix(
    session_card_count: int,
    topics_slider: int,
    pdf_slider: int,
    random_slider: int,
) -> dict:
    """Compute the combined per-axis target mix shown in scheduler settings."""
    topics_rate = 1.0 - (topics_slider / 100.0)
    pdf_rate = 1.0 - (pdf_slider / 100.0)
    random_rate = random_slider / 100.0

    content_shares = {
        "pdf": pdf_rate,
        "topics": topics_rate * (1.0 - pdf_rate),
        "items": (1.0 - topics_rate) * (1.0 - pdf_rate),
    }
    mode_shares = {
        "random": random_rate,
        "priority": 1.0 - random_rate,
    }

    return {
        "content_shares": content_shares,
        "content_counts": _apportion_counts(session_card_count, content_shares),
        "mode_shares": mode_shares,
        "mode_counts": _apportion_counts(session_card_count, mode_shares),
    }


def summarize_selected_mix(selected_ids: list[int], picked_meta: dict[int, dict]) -> dict:
    """Summarize one real scheduler run for UI surfaces that should match it."""
    content_counts = {"pdf": 0, "topics": 0, "items": 0}
    mode_counts: dict[str, int] = {}
    tag_content_counts: dict[str, dict[str, int]] = {}
    other_type_counts: dict[str, int] = {}

    content_labels = {
        "pdf": "PDF",
        "topics": "Topics",
        "items": "Items",
    }

    for card_id in selected_ids:
        meta = picked_meta.get(card_id, {}) or {}
        raw_card_type = str(meta.get("card_type") or "").strip().lower()
        card_type = raw_card_type if raw_card_type in content_counts else None
        mode = str(meta.get("mode") or "?").strip().lower() or "?"
        raw_tag = meta.get("tag")
        if raw_tag in (None, "", NO_TAGS_KEY):
            tag = "Other"
        else:
            tag = str(raw_tag).strip() or "Other"

        mode_counts[mode] = mode_counts.get(mode, 0) + 1
        tag_content_counts.setdefault(tag, {"PDF": 0, "Topics": 0, "Items": 0})

        if card_type is None:
            key = raw_card_type or "unknown"
            other_type_counts[key] = other_type_counts.get(key, 0) + 1
            continue

        content_counts[card_type] += 1
        tag_content_counts[tag][content_labels[card_type]] += 1

    for tag_counts in tag_content_counts.values():
        tag_counts["Total"] = tag_counts["PDF"] + tag_counts["Topics"] + tag_counts["Items"]

    ordered_tag_counts = dict(
        sorted(
            tag_content_counts.items(),
            key=lambda item: (-item[1]["Total"], item[0].lower()),
        )
    )

    return {
        "content_counts": content_counts,
        "mode_counts": mode_counts,
        "tag_content_counts": ordered_tag_counts,
        "other_type_counts": other_type_counts,
        "selected_total": len(selected_ids),
    }
