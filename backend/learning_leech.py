"""Tag difficult learning cards using Anki's canonical answer history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .answer_schedule import (
    answer_revlog_snapshot,
    current_answer_undo_step,
    is_nonrescheduling_filtered_card,
    new_answer_revlog_id,
)
from .config_service import configured_learning_leech


@dataclass(frozen=True)
class _PendingAnswer:
    collection: Any
    profile: str
    card_id: int
    previous_revlog_id: int
    threshold: int
    tag: str


class LearningLeechTracker:
    """Keep only the current answer in memory; counts always come from Anki."""

    def __init__(self) -> None:
        self._pending: _PendingAnswer | None = None

    def clear(self) -> None:
        self._pending = None

    def prepare_answer(self, collection, profile: str, card, ease: int, config) -> None:
        self.clear()
        enabled, threshold, tag = configured_learning_leech(config)
        if not enabled or ease != 1 or int(card.type) not in (0, 1):
            return
        if is_nonrescheduling_filtered_card(card, collection=collection):
            return
        succeeded, revlog_id = answer_revlog_snapshot(card.id, collection=collection)
        if succeeded:
            self._pending = _PendingAnswer(
                collection, profile, int(card.id), revlog_id, threshold, tag,
            )

    def finish_answer(self, collection, profile: str, card, ease: int) -> bool:
        pending = self._pending
        self.clear()
        if (
            pending is None or collection is not pending.collection
            or profile != pending.profile or int(card.id) != pending.card_id or ease != 1
        ):
            return False
        revlog_id = new_answer_revlog_id(
            pending.card_id, pending.previous_revlog_id, collection=collection,
        )
        if not revlog_id:
            return False
        # Check the committed answer, not the reviewer's possibly stale card.
        if not collection.db.scalar(
            "SELECT count() FROM revlog WHERE id = ? AND cid = ? AND ease = 1 AND type = 0",
            revlog_id, pending.card_id,
        ):
            return False
        failures = collection.db.scalar(
            "SELECT count() FROM revlog WHERE cid = ? AND ease = 1 AND type = 0",
            pending.card_id,
        )
        if int(failures or 0) < pending.threshold:
            return False
        undo_step = current_answer_undo_step(collection=collection)
        if undo_step <= 0:
            return False
        note = collection.get_card(pending.card_id).note()
        if note.has_tag(pending.tag):
            return False
        note.add_tag(pending.tag)
        collection.update_note(note)
        collection.merge_undo_entries(undo_step)
        return True
