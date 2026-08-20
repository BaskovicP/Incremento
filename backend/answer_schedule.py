"""Shared helpers for interval overrides attached to an Anki answer.

Review-time overrides must update the post-answer card and merge that update
into Anki's existing Answer Card undo step.  They must never call
``set_due_date()`` after an answer, because that creates a manual revlog row
and a second undo operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aqt import mw

try:
    from anki.consts import CARD_TYPE_REV, QUEUE_TYPE_REV
except Exception:  # pragma: no cover - compatibility with lightweight test stubs
    CARD_TYPE_REV = 2
    QUEUE_TYPE_REV = 2


_CARD_SCHEDULE_FIELDS = (
    "did",
    "odid",
    "odue",
    "type",
    "queue",
    "due",
    "ivl",
    "left",
)


def answer_revlog_snapshot(card_id: int, *, collection=None) -> tuple[bool, int]:
    """Return ``(query_succeeded, latest_answer_revlog_id)``.

    Zero is a valid snapshot for a never-reviewed card, so callers must retain
    the success flag instead of conflating an empty history with a DB failure.
    """
    try:
        col = collection or mw.col
        value = col.db.scalar(
            "SELECT id FROM revlog WHERE cid = ? AND ease > 0 ORDER BY id DESC LIMIT 1",
            int(card_id),
        )
        return True, max(0, int(value or 0))
    except Exception:
        return False, 0


def new_answer_revlog_id(
    card_id: int,
    previous_revlog_id: int,
    *,
    collection=None,
) -> int:
    """Return the new answer revlog, rejecting a stale pre-answer row."""
    succeeded, latest = answer_revlog_snapshot(card_id, collection=collection)
    if not succeeded:
        return 0
    if latest <= 0 or latest == max(0, int(previous_revlog_id or 0)):
        return 0
    return latest


def current_answer_undo_step(*, collection=None) -> int:
    try:
        col = collection or mw.col
        value = getattr(col.undo_status(), "last_step", 0)
        return int(value) if isinstance(value, int) else 0
    except Exception:
        return 0


def card_schedule_snapshot(card) -> dict[str, int]:
    return {
        field_name: int(getattr(card, field_name, 0) or 0)
        for field_name in _CARD_SCHEDULE_FIELDS
    }


def is_nonrescheduling_filtered_card(card, *, collection=None) -> bool:
    """Return whether *card* is being answered in Anki Preview mode.

    A card in a filtered deck has ``odid`` set to its home deck and ``did``
    set to the filtered deck.  When that deck has rescheduling disabled, Anki
    records the preview answer but deliberately leaves the home schedule
    unchanged.  Answer-linked Incremento schedulers must preserve that
    contract as well.
    """
    try:
        if int(getattr(card, "odid", 0) or 0) <= 0:
            return False
        col = collection or mw.col
        deck = col.decks.get(int(getattr(card, "did", 0) or 0))
        if not deck:
            return False
        return bool(deck.get("dyn", True)) and not bool(deck.get("resched", True))
    except Exception:
        return False


def apply_review_interval(
    card_id: int,
    interval_days: int,
    *,
    answer_undo_step: int,
    collection=None,
):
    """Apply an interval without adding a manual revlog or separate undo."""
    if int(answer_undo_step) <= 0:
        raise RuntimeError("Anki answer undo step is unavailable")

    normalized_card_id = int(card_id)
    normalized_interval = max(1, int(interval_days))
    col = collection or mw.col
    card = col.get_card(normalized_card_id)

    # A rescheduling filtered-deck answer returns to its home deck.  Keeping
    # odid/odue here would leave the card stranded in a filtered-deck state.
    original_deck_id = int(getattr(card, "odid", 0) or 0)
    if original_deck_id:
        card.did = original_deck_id
        card.odid = 0
        card.odue = 0

    card.type = CARD_TYPE_REV
    card.queue = QUEUE_TYPE_REV
    card.due = int(col.sched.today) + normalized_interval
    card.ivl = normalized_interval
    card.left = 0
    col.update_card(card)
    col.merge_undo_entries(int(answer_undo_step))
    return card


def restore_card_schedule(
    card_id: int,
    snapshot: dict[str, int],
    *,
    answer_undo_step: int,
    collection=None,
) -> None:
    """Roll back a failed override while retaining the Answer Card undo."""
    col = collection or mw.col
    card = col.get_card(int(card_id))
    for field_name in _CARD_SCHEDULE_FIELDS:
        if field_name in snapshot:
            setattr(card, field_name, int(snapshot[field_name]))
    col.update_card(card)
    if int(answer_undo_step) > 0:
        col.merge_undo_entries(int(answer_undo_step))


def _existing_revlog_ids(revlog_ids, *, collection=None) -> frozenset[int]:
    col = collection or mw.col
    normalized = sorted(
        {int(value) for value in revlog_ids if int(value or 0) > 0}
    )
    existing: set[int] = set()
    for start in range(0, len(normalized), 900):
        chunk = normalized[start : start + 900]
        if not chunk:
            continue
        placeholders = ",".join("?" for _value in chunk)
        existing.update(
            int(value)
            for value in col.db.list(
                f"SELECT id FROM revlog WHERE id IN ({placeholders})",
                *chunk,
            )
        )
    return frozenset(existing)


@dataclass
class _TrackedCard:
    linked: set[int] = field(default_factory=set)
    existing: frozenset[int] = field(default_factory=frozenset)


class ReviewRevlogTracker:
    """Track only answer revlogs created during the current profile session.

    Removed rows are considered Undo only when Anki exposes a redo action.
    Rows are considered Redo only after this tracker observed their Undo.  This
    prevents forget/delete/sync changes from being interpreted as review undo.
    """

    def __init__(self) -> None:
        self._cards: dict[tuple[str, int], _TrackedCard] = {}
        self._undone: set[int] = set()

    def clear(self) -> None:
        self._cards.clear()
        self._undone.clear()

    def track(self, profile: str, card_id: int, revlog_id: int) -> None:
        normalized_revlog_id = int(revlog_id)
        if normalized_revlog_id <= 0:
            return
        key = (str(profile), int(card_id))
        tracked = self._cards.setdefault(key, _TrackedCard())
        tracked.linked.add(normalized_revlog_id)
        tracked.existing = frozenset(set(tracked.existing) | {normalized_revlog_id})
        self._undone.discard(normalized_revlog_id)

    def transitions(self, undo_info=None, *, collection=None):
        """Yield profile/card snapshots for genuine Undo or Redo transitions."""
        all_linked = {
            revlog_id
            for tracked in self._cards.values()
            for revlog_id in tracked.linked
        }
        try:
            existing = _existing_revlog_ids(all_linked, collection=collection)
        except Exception:
            return

        can_redo = bool(getattr(undo_info, "can_redo", False))
        allow_direct = undo_info is None

        # Anki clears its Redo stack as soon as a different operation occurs.
        # Such an operation can leave the tracked revlog snapshot unchanged,
        # so retire the candidates here instead of waiting for a DB delta.  A
        # real final Redo is distinguishable because its missing revlog is
        # already present again in this callback.
        if not allow_direct and not can_redo and self._undone:
            restored_undone = {
                revlog_id
                for tracked in self._cards.values()
                for revlog_id in (set(existing) - set(tracked.existing))
                if revlog_id in tracked.linked and revlog_id in self._undone
            }
            if not restored_undone:
                stale = set(self._undone)
                self._undone.clear()
                for key, tracked in list(self._cards.items()):
                    tracked.linked.difference_update(stale)
                    tracked.existing = frozenset(
                        revlog_id
                        for revlog_id in tracked.existing
                        if revlog_id in tracked.linked
                    )
                    if not tracked.linked:
                        self._cards.pop(key, None)

        for key, tracked in list(self._cards.items()):
            current = frozenset(
                revlog_id for revlog_id in tracked.linked if revlog_id in existing
            )
            previous = tracked.existing
            if current == previous:
                continue

            removed = set(previous - current)
            added = set(current - previous)
            valid_removed = removed if (allow_direct or can_redo) else set()
            valid_added = added if allow_direct else (added & self._undone)

            # A disappeared row without a redo action was removed by something
            # other than Undo (forget/delete/sync). Stop tracking it permanently.
            ignored_removed = removed - valid_removed
            if ignored_removed:
                tracked.linked.difference_update(ignored_removed)
                self._undone.difference_update(ignored_removed)
                current = frozenset(
                    revlog_id
                    for revlog_id in tracked.linked
                    if revlog_id in existing
                )

            if valid_removed:
                self._undone.update(valid_removed)
            if valid_added:
                self._undone.difference_update(valid_added)

            if valid_removed or valid_added:
                yield key[0], key[1], current, previous

            tracked.existing = current
            if not tracked.linked:
                self._cards.pop(key, None)
