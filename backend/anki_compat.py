"""Narrow compatibility boundary around version-sensitive Anki APIs."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable


REQUIRED_REVIEWER_METHODS = (
    "_after_answering",
    "_answerCard",
    "_buttonTime",
    "_defaultEase",
    "_shortcutKeys",
    "onEnterKey",
    "nextCard",
    "op_executed",
    "_showAnswerButton",
    "_showEaseButtons",
    "_linkHandler",
    "_get_next_v3_card",
    "_initWeb",
    "_showQuestion",
)


class AnkiCompatibilityError(RuntimeError):
    pass


def start_native_sync(main_window) -> None:
    """Invoke Anki's native sync action across supported naming generations."""
    for method_name in ("on_sync_button_clicked", "onSync"):
        method = getattr(main_window, method_name, None)
        if callable(method):
            method()
            return
    raise AnkiCompatibilityError("Anki's native sync action is unavailable")


@dataclass(frozen=True)
class CompatibilityReport:
    required_methods: int
    missing_methods: int
    private_scheduler_available: bool
    custom_next_card_supported: bool


_NEXT_CARD_DEPENDENCIES = (
    "nextCard",
    "_get_next_v3_card",
    "_initWeb",
    "_showQuestion",
)


def original_reviewer_method(reviewer_cls, method_name: str):
    current = getattr(reviewer_cls, str(method_name), None)
    if current is None:
        return None
    return getattr(current, "_incremento_original", current)


def install_reviewer_patch(reviewer_cls, method_name: str, replacement) -> bool:
    original = original_reviewer_method(reviewer_cls, method_name)
    if original is None:
        return False
    replacement._incremento_original = original
    setattr(reviewer_cls, method_name, replacement)
    return True


def custom_next_card_supported(reviewer_cls) -> bool:
    return all(
        callable(getattr(reviewer_cls, method_name, None))
        for method_name in _NEXT_CARD_DEPENDENCIES
    )


def compatibility_report(reviewer_cls, collection=None) -> CompatibilityReport:
    missing = sum(
        1 for method_name in REQUIRED_REVIEWER_METHODS
        if not callable(getattr(reviewer_cls, method_name, None))
    )
    backend = getattr(collection, "_backend", None) if collection is not None else None
    private_scheduler = callable(getattr(backend, "get_scheduling_states", None))
    return CompatibilityReport(
        required_methods=len(REQUIRED_REVIEWER_METHODS),
        missing_methods=missing,
        private_scheduler_available=private_scheduler,
        custom_next_card_supported=custom_next_card_supported(reviewer_cls),
    )


def build_direct_review_v3_info(collection, card, queued_card_ids: list[int]):
    """Build Anki's private V3 queue wrapper in one compatibility module."""
    try:
        from aqt.reviewer import QueuedCards, SchedulingContext, V3CardInfo
    except Exception as exc:
        raise AnkiCompatibilityError("Anki V3 reviewer queue types are unavailable") from exc

    backend = getattr(collection, "_backend", None)
    get_states = getattr(backend, "get_scheduling_states", None)
    if not callable(get_states):
        raise AnkiCompatibilityError("Anki scheduling-state API is unavailable")

    def queue_kind(candidate) -> int:
        try:
            queue = int(getattr(candidate, "queue", 0) or 0)
        except Exception:
            queue = 0
        try:
            card_type = int(getattr(candidate, "type", 0) or 0)
        except Exception:
            card_type = 0
        if queue == 0 or card_type == 0:
            return QueuedCards.NEW
        if queue in (1, 3) or card_type in (1, 3):
            return QueuedCards.LEARNING
        return QueuedCards.REVIEW

    counts = [0, 0, 0]
    for raw_card_id in queued_card_ids:
        try:
            candidate = collection.get_card(int(raw_card_id))
            if candidate is None or int(getattr(candidate, "queue", 0) or 0) < 0:
                continue
        except Exception:
            continue
        kind = queue_kind(candidate)
        if kind == QueuedCards.NEW:
            counts[0] += 1
        elif kind == QueuedCards.LEARNING:
            counts[1] += 1
        else:
            counts[2] += 1

    states = get_states(int(card.id))
    try:
        deck_name = str(collection.decks.name(getattr(card, "did", 0)) or "")
    except Exception:
        deck_name = ""
    queued_cards = QueuedCards(
        cards=[
            QueuedCards.QueuedCard(
                card=card._to_backend_card(),
                queue=queue_kind(card),
                states=states,
                context=SchedulingContext(deck_name=deck_name),
            )
        ],
        new_count=counts[0],
        learning_count=counts[1],
        review_count=counts[2],
    )
    return V3CardInfo.from_queue(queued_cards)


def fetch_next_v3_card(reviewer) -> None:
    method = getattr(reviewer, "_get_next_v3_card", None)
    if not callable(method):
        raise AnkiCompatibilityError("Reviewer._get_next_v3_card is unavailable")
    method()


def advance_reviewer(reviewer) -> None:
    method = getattr(reviewer, "nextCard", None)
    if not callable(method):
        raise AnkiCompatibilityError("Reviewer.nextCard is unavailable")
    method()


def answer_reviewer_card(reviewer, ease: int) -> None:
    method = getattr(reviewer, "_answerCard", None)
    if not callable(method):
        raise AnkiCompatibilityError("Reviewer._answerCard is unavailable")
    method(int(ease))


def install_one_shot_next_card_override(
    reviewer,
    replacement_factory: Callable[[Callable[[], None], Callable[[], None]], Callable[[], None]],
) -> bool:
    """Install a temporary instance override without leaking private mechanics.

    ``replacement_factory`` receives the currently bound next-card method and
    an idempotent restore callback. This is used while a filtered-deck refill
    operation finishes, then the class-level Incremento/Anki method resumes.
    """
    try:
        original_next = getattr(reviewer, "nextCard")
        if not callable(original_next):
            return False
        instance_dict = getattr(reviewer, "__dict__", {})
        had_instance_override = "nextCard" in instance_dict
        previous_instance_value = instance_dict.get("nextCard")
    except Exception:
        return False

    restored = False

    def restore() -> None:
        nonlocal restored
        if restored:
            return
        restored = True
        try:
            if had_instance_override:
                setattr(reviewer, "nextCard", previous_instance_value)
            else:
                delattr(reviewer, "nextCard")
        except Exception:
            try:
                setattr(reviewer, "nextCard", original_next)
            except Exception:
                pass

    try:
        replacement = replacement_factory(original_next, restore)
        if not callable(replacement):
            return False
        setattr(reviewer, "nextCard", replacement)
    except Exception:
        restore()
        return False
    return True


def update_reviewer_card_info(reviewer) -> None:
    previous_info = getattr(reviewer, "_previous_card_info", None)
    current_info = getattr(reviewer, "_card_info", None)
    if previous_info is None or current_info is None:
        raise AnkiCompatibilityError("Reviewer card-info holders are unavailable")
    previous_info.set_card(getattr(reviewer, "previous_card", None))
    current_info.set_card(getattr(reviewer, "card", None))


def initialize_reviewer_web(reviewer) -> None:
    method = getattr(reviewer, "_initWeb", None)
    if not callable(method):
        raise AnkiCompatibilityError("Reviewer._initWeb is unavailable")
    method()


def show_reviewer_question(reviewer) -> None:
    method = getattr(reviewer, "_showQuestion", None)
    if not callable(method):
        raise AnkiCompatibilityError("Reviewer._showQuestion is unavailable")
    method()
