"""Explicit topic completion/defer actions using Anki's native undo stack."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json

try:
    from .config_service import DEFAULT_TOPIC_DONE_TAG, normalize_topic_done_tag
    from .custom_schedule import add_calendar_months, anki_logical_today
except ImportError:
    from config_service import DEFAULT_TOPIC_DONE_TAG, normalize_topic_done_tag
    from custom_schedule import add_calendar_months, anki_logical_today


class StaleTopicAction(RuntimeError):
    """The originating card/profile or undo step is no longer current."""


REVISIT_DATA_KEY = "incrv"  # Anki custom-data keys are limited to eight bytes.


def reader_revisit_filter(collection) -> str:
    """Only explicit Revisit pauses override normally due-independent readers."""
    # Negating a missing numeric custom-data key yields SQL NULL, so explicitly
    # include cards without our key (including cards with other add-ons' data).
    return (
        f"(-has-cd:{REVISIT_DATA_KEY} OR "
        f"prop:cdn:{REVISIT_DATA_KEY}<={int(collection.sched.today)} OR -prop:due>0)"
    )


@dataclass(frozen=True)
class TopicActionResult:
    changes: object
    undo_step: int
    message: str


def _available_card(collection, card_id: int):
    card = collection.get_card(int(card_id))
    if card is None or int(card.queue) < 0:
        raise StaleTopicAction("This topic is no longer available for review.")
    return card


def _result(collection, changes, message: str) -> TopicActionResult:
    return TopicActionResult(
        changes=getattr(changes, "changes", changes),
        undo_step=int(collection.undo_status().last_step),
        message=message,
    )


def complete_topic(
    collection, card_id: int, *, done_tag: str = DEFAULT_TOPIC_DONE_TAG,
) -> TopicActionResult:
    """Suspend this card and tag its note together in one native Undo step."""
    done_tag = normalize_topic_done_tag(done_tag)
    card = _available_card(collection, card_id)
    changes = collection.sched.suspend_cards([int(card_id)])
    suspend_step = int(collection.undo_status().last_step)
    tag_step = suspend_step
    try:
        # Native bulk_add preserves existing tags and deduplicates case-insensitively.
        collection.tags.bulk_add([int(card.nid)], done_tag)
        tag_step = int(collection.undo_status().last_step)
        changes = collection.merge_undo_entries(suspend_step)
    except Exception:
        # Serialized collection work: undo only the steps owned by this action.
        # last_step is monotonic, so after undoing the tag write the immediately
        # preceding entry is our suspension, regardless of its reported counter.
        if tag_step != suspend_step and int(collection.undo_status().last_step) == tag_step:
            collection.undo()
            collection.undo()
        elif int(collection.undo_status().last_step) == suspend_step:
            collection.undo()
        raise
    return _result(collection, changes, "Topic marked as done.")


def revisit_topic(
    collection,
    card_id: int,
    *,
    months: int | None = None,
    on_date: date | None = None,
    today: date | None = None,
) -> TopicActionResult:
    """Move the next review only, without answering or replacing custom rules."""
    today = today or anki_logical_today(collection=collection)
    if months is not None:
        if months not in (3, 6, 12) or on_date is not None:
            raise ValueError("Choose 3, 6 or 12 months, or a future date.")
        on_date = add_calendar_months(today, months)
    if on_date is None or not 1 <= (on_date - today).days <= 36500:
        raise ValueError("Choose a future date within the next 100 years.")
    _available_card(collection, card_id)
    card = collection.get_card(int(card_id))
    custom_data = json.loads(card.custom_data or "{}")
    if not isinstance(custom_data, dict):
        raise ValueError("The card's custom scheduling data is invalid.")
    custom_data[REVISIT_DATA_KEY] = int(collection.sched.today) + (on_date - today).days
    encoded_data = json.dumps(custom_data, separators=(",", ":"))
    # This is a manual action, separate from More/Same/Less and answer hooks.
    # No ! suffix: preserve the existing interval/cadence on review cards.
    changes = collection.sched.set_due_date([int(card_id)], str((on_date - today).days))
    due_step = int(collection.undo_status().last_step)
    data_step = due_step
    try:
        card = collection.get_card(int(card_id))
        card.custom_data = encoded_data
        collection.update_card(card)
        data_step = int(collection.undo_status().last_step)
        changes = collection.merge_undo_entries(due_step)
    except Exception:
        # Both operations use Anki's undo API on the serialized collection
        # worker. Roll back only steps owned by this operation.
        if data_step != due_step and int(collection.undo_status().last_step) == data_step:
            collection.undo()
            # last_step is a monotonic counter, not the top undo entry ID.
            # The immediately preceding step is our Set Due Date operation.
            collection.undo()
        elif int(collection.undo_status().last_step) == due_step:
            collection.undo()
        raise
    return _result(collection, changes, f"Topic scheduled for {on_date.isoformat()}.")


def undo_topic_action(collection, undo_step: int):
    """A toast must never undo an intervening answer or unrelated operation."""
    status = collection.undo_status()
    if (
        undo_step <= 0 or int(status.last_step) != undo_step
        or not status.undo or getattr(status, "redo", "")
    ):
        raise StaleTopicAction("This action is no longer the latest change. Use Edit → Undo to review recent changes.")
    return collection.undo()
