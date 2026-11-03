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


def compute_content_counts(total: int, topics_rate: float, document_rate: float) -> dict[str, int]:
    """Round the Topic/Item split first, then divide only the Topic allocation."""
    parent = _apportion_counts(total, {"topics": topics_rate, "items": 1.0 - topics_rate})
    children = _apportion_counts(parent["topics"], {"pdf": document_rate, "topics": 1.0 - document_rate})
    return {**children, "items": parent["items"]}


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
        "pdf": topics_rate * pdf_rate,
        "topics": topics_rate * (1.0 - pdf_rate),
        "items": 1.0 - topics_rate,
    }
    mode_shares = {
        "random": random_rate,
        "priority": 1.0 - random_rate,
    }

    return {
        "content_shares": content_shares,
        "content_counts": compute_content_counts(session_card_count, topics_rate, pdf_rate),
        "mode_shares": mode_shares,
        "mode_counts": _apportion_counts(session_card_count, mode_shares),
    }
