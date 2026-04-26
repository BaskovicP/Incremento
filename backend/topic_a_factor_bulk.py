"""Bulk helpers for topic-card A-factor updates."""

try:
    from .db import get_topic_schedule, set_topic_schedule
except ImportError:
    from db import get_topic_schedule, set_topic_schedule  # type: ignore


def apply_bulk_topic_a_factor(
    addon_dir: str,
    profile: str,
    card_ids,
    a_factor: float,
    *,
    get_card,
    is_topic_card,
) -> dict[str, int]:
    """Set one A-factor for the selected topic cards.

    Non-topic cards are intentionally skipped because Incremento only uses
    A-factor scheduling for topic cards.
    """
    value = round(float(a_factor), 3)
    if value < 1.1 or value > 100.0:
        raise ValueError("A-Factor must be between 1.1 and 100.0")

    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_card_id in card_ids or []:
        try:
            card_id = int(raw_card_id)
        except Exception:
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        normalized_ids.append(card_id)

    updated = 0
    skipped = 0
    errors = 0
    for card_id in normalized_ids:
        try:
            card = get_card(card_id)
        except Exception:
            errors += 1
            continue

        try:
            eligible = bool(is_topic_card(card))
        except Exception:
            eligible = False

        if not eligible:
            skipped += 1
            continue

        try:
            _current_a_factor, interval = get_topic_schedule(addon_dir, profile, card_id)
            set_topic_schedule(addon_dir, profile, card_id, value, interval)
            updated += 1
        except Exception:
            errors += 1

    return {
        "selected": len(normalized_ids),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
    }
