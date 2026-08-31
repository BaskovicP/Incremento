"""Resolve, classify, filter, and order cards linked to reader media."""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Mapping
from html import unescape

try:
    from .db import (
        get_epub_document_source_rows,
        get_knowledge_tree_nodes,
        get_pdf_document_source_rows,
    )
    from .note_metadata import (
        INCREMENTO_PARENT_CARD_ID_FIELD,
        inline_pdf_reference,
    )
    from .scheduler_config import build_ready_filter
    from .topic_scheduler import is_topic_card, resolve_topic_card_classifier
except ImportError:
    from db import (  # type: ignore
        get_epub_document_source_rows,
        get_knowledge_tree_nodes,
        get_pdf_document_source_rows,
    )
    from note_metadata import (  # type: ignore
        INCREMENTO_PARENT_CARD_ID_FIELD,
        inline_pdf_reference,
    )
    from scheduler_config import build_ready_filter  # type: ignore
    from topic_scheduler import is_topic_card, resolve_topic_card_classifier  # type: ignore


MEDIA_KIND_PDF = "pdf"
MEDIA_KIND_EPUB = "epub"
MEDIA_KIND_VIDEO = "video"

MEDIA_REVIEW_ORDER_ATTACHED = "attached"
MEDIA_REVIEW_ORDER_MEDIA_POSITION = "media_position"
MEDIA_REVIEW_ORDER_CREATED_OLDEST = "created_oldest"
MEDIA_REVIEW_ORDER_CREATED_NEWEST = "created_newest"
MEDIA_REVIEW_ORDER_DUE_FIRST = "due_first"
MEDIA_REVIEW_ORDER_INTERVAL_SHORTEST = "interval_shortest"
MEDIA_REVIEW_ORDER_INTERVAL_LONGEST = "interval_longest"
MEDIA_REVIEW_ORDER_RANDOM = "random"

MEDIA_REVIEW_ORDER_OPTIONS: tuple[tuple[str, str], ...] = (
    (MEDIA_REVIEW_ORDER_ATTACHED, "Attached order"),
    (MEDIA_REVIEW_ORDER_MEDIA_POSITION, "Media position — beginning to end"),
    (MEDIA_REVIEW_ORDER_CREATED_OLDEST, "Creation date — oldest first"),
    (MEDIA_REVIEW_ORDER_CREATED_NEWEST, "Creation date — newest first"),
    (MEDIA_REVIEW_ORDER_DUE_FIRST, "Due / learning cards first"),
    (MEDIA_REVIEW_ORDER_INTERVAL_SHORTEST, "Interval — shortest first"),
    (MEDIA_REVIEW_ORDER_INTERVAL_LONGEST, "Interval — longest first"),
    (MEDIA_REVIEW_ORDER_RANDOM, "Random"),
)

MEDIA_REVIEW_CARD_KIND_BOTH = "both"
MEDIA_REVIEW_CARD_KIND_TOPICS = "topics"
MEDIA_REVIEW_CARD_KIND_ITEMS = "items"
MEDIA_REVIEW_CARD_KIND_OPTIONS: tuple[tuple[str, str], ...] = (
    (MEDIA_REVIEW_CARD_KIND_BOTH, "Topics and items"),
    (MEDIA_REVIEW_CARD_KIND_TOPICS, "Topics only"),
    (MEDIA_REVIEW_CARD_KIND_ITEMS, "Items only"),
)

MEDIA_REVIEW_TREE_DIRECT = "direct"
MEDIA_REVIEW_TREE_NESTED = "nested"
MEDIA_REVIEW_TREE_OPTIONS: tuple[tuple[str, str], ...] = (
    (MEDIA_REVIEW_TREE_NESTED, "Direct and nested cards"),
    (MEDIA_REVIEW_TREE_DIRECT, "Direct attachments only"),
)

MEDIA_REVIEW_RANGE_ALL = "all"
MEDIA_REVIEW_RANGE_TO_CURRENT = "to_current"
MEDIA_REVIEW_RANGE_OPTIONS: tuple[tuple[str, str], ...] = (
    (MEDIA_REVIEW_RANGE_ALL, "Entire media"),
    (MEDIA_REVIEW_RANGE_TO_CURRENT, "Up to current position"),
)

MEDIA_REVIEW_STATE_ALL = "all"
MEDIA_REVIEW_STATE_DUE = "due"
MEDIA_REVIEW_STATE_OPTIONS: tuple[tuple[str, str], ...] = (
    (MEDIA_REVIEW_STATE_ALL, "All available cards"),
    (MEDIA_REVIEW_STATE_DUE, "Due / learning now only"),
)

MEDIA_REVIEW_AVAILABILITY_AVAILABLE = "available"
MEDIA_REVIEW_AVAILABILITY_SUSPENDED = "suspended"
MEDIA_REVIEW_AVAILABILITY_BURIED = "buried"
MEDIA_REVIEW_AVAILABILITY_FILTERED = "filtered"
MEDIA_REVIEW_AVAILABILITY_MISSING = "missing"

_VALID_MEDIA_KINDS = {MEDIA_KIND_PDF, MEDIA_KIND_EPUB, MEDIA_KIND_VIDEO}
_VALID_MEDIA_REVIEW_ORDERS = {value for value, _label in MEDIA_REVIEW_ORDER_OPTIONS}
_VALID_MEDIA_REVIEW_CARD_KINDS = {
    value for value, _label in MEDIA_REVIEW_CARD_KIND_OPTIONS
}
_VALID_MEDIA_REVIEW_TREE_SCOPES = {
    value for value, _label in MEDIA_REVIEW_TREE_OPTIONS
}
_VALID_MEDIA_REVIEW_RANGES = {value for value, _label in MEDIA_REVIEW_RANGE_OPTIONS}
_VALID_MEDIA_REVIEW_STATES = {value for value, _label in MEDIA_REVIEW_STATE_OPTIONS}
_SEARCH_NOTE_CHUNK_SIZE = 200
_SEARCH_CARD_CHUNK_SIZE = 500
_EPUB_POSITION_RE = re.compile(
    r"incremento_open_epub:(?P<card_id>\d+):(?P<position>-?\d+):",
    re.IGNORECASE,
)
_VIDEO_POSITION_RE = re.compile(
    r"incremento_open_video:(?P<card_id>\d+):(?P<position>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_LEGACY_PDF_POSITION_RE = re.compile(
    r"incremento_open_pdf:(?P<card_id>\d+):(?P<position>\d+)",
    re.IGNORECASE,
)


def _normalize_choice(value, valid: set[str], default: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in valid else default


def normalize_media_kind(value: str | None) -> str:
    return _normalize_choice(value, _VALID_MEDIA_KINDS, "")


def normalize_media_review_order(value: str | None) -> str:
    return _normalize_choice(
        value,
        _VALID_MEDIA_REVIEW_ORDERS,
        MEDIA_REVIEW_ORDER_ATTACHED,
    )


def normalize_media_review_card_kind(value: str | None) -> str:
    return _normalize_choice(
        value,
        _VALID_MEDIA_REVIEW_CARD_KINDS,
        MEDIA_REVIEW_CARD_KIND_BOTH,
    )


def normalize_media_review_tree_scope(value: str | None) -> str:
    return _normalize_choice(
        value,
        _VALID_MEDIA_REVIEW_TREE_SCOPES,
        MEDIA_REVIEW_TREE_NESTED,
    )


def normalize_media_review_range(value: str | None) -> str:
    return _normalize_choice(
        value,
        _VALID_MEDIA_REVIEW_RANGES,
        MEDIA_REVIEW_RANGE_ALL,
    )


def normalize_media_review_state(value: str | None) -> str:
    return _normalize_choice(
        value,
        _VALID_MEDIA_REVIEW_STATES,
        MEDIA_REVIEW_STATE_ALL,
    )


def normalize_media_review_limit(value) -> int:
    try:
        parsed = int(value or 0)
    except Exception:
        parsed = 0
    return max(0, min(9999, parsed))


def _normalized_position(value) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _positive_unique(values: Iterable[int] | None) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw_value in list(values or []):
        try:
            value = int(raw_value)
        except Exception:
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _note_fields(note) -> list[str]:
    try:
        return [str(value or "") for value in list(getattr(note, "fields", []) or [])]
    except Exception:
        return []


def _media_position_from_note(
    note,
    media_kind: str,
    source_card_id: int,
) -> float | None:
    """Read a persisted reader link when no legacy source row is available."""
    normalized_kind = normalize_media_kind(media_kind)
    if normalized_kind == MEDIA_KIND_PDF:
        try:
            reference = inline_pdf_reference(note) or {}
            reference_card_id = int(reference.get("card_id", 0) or 0)
            if reference_card_id in {0, int(source_card_id)}:
                return _normalized_position(reference.get("page"))
        except Exception:
            pass
        pattern = _LEGACY_PDF_POSITION_RE
    elif normalized_kind == MEDIA_KIND_EPUB:
        pattern = _EPUB_POSITION_RE
    elif normalized_kind == MEDIA_KIND_VIDEO:
        pattern = _VIDEO_POSITION_RE
    else:
        return None

    for field in _note_fields(note):
        text = unescape(field).replace('\\"', '"')
        for match in pattern.finditer(text):
            try:
                if int(match.group("card_id")) != int(source_card_id):
                    continue
            except Exception:
                continue
            return _normalized_position(match.group("position"))
    return None


def _legacy_source_rows(
    addon_dir: str,
    profile: str,
    media_kind: str,
    source_card_id: int,
) -> list[dict]:
    try:
        if media_kind == MEDIA_KIND_PDF:
            return list(
                get_pdf_document_source_rows(
                    addon_dir,
                    profile,
                    int(source_card_id),
                )
                or []
            )
        if media_kind == MEDIA_KIND_EPUB:
            return list(
                get_epub_document_source_rows(
                    addon_dir,
                    profile,
                    int(source_card_id),
                )
                or []
            )
    except Exception:
        return []
    return []


def _metadata_child_note_ids(col, source_card_id: int) -> list[int]:
    """Return direct children whose canonical parent metadata matches exactly."""
    query = f"{INCREMENTO_PARENT_CARD_ID_FIELD}:{int(source_card_id)}"
    try:
        candidates = _positive_unique(col.find_notes(query))
    except Exception:
        return []

    matching: list[int] = []
    expected = str(int(source_card_id))
    for note_id in candidates:
        try:
            note = col.get_note(int(note_id))
            parent_value = str(note[INCREMENTO_PARENT_CARD_ID_FIELD] or "").strip()
        except Exception:
            continue
        if parent_value == expected:
            matching.append(int(note_id))
    matching.sort()
    return matching


def _knowledge_tree_descendant_links(
    addon_dir: str,
    profile: str,
    source_card_id: int,
    *,
    directly_linked_card_ids: Iterable[int] | None = None,
) -> list[dict]:
    """Return tree links reachable from the media card or its direct attachments."""
    try:
        rows = list(get_knowledge_tree_nodes(addon_dir, profile) or [])
    except Exception:
        return []

    row_by_card_id: dict[int, dict] = {}
    grouped: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        try:
            card_id = int(row.get("card_id", 0) or 0)
            if card_id <= 0:
                continue
            row_by_card_id[card_id] = row
            parent_card_id = row.get("parent_card_id")
            if parent_card_id is None:
                continue
            grouped[int(parent_card_id)].append(row)
        except Exception:
            continue
    for children in grouped.values():
        children.sort(
            key=lambda row: (
                int(row.get("sort_order", 0) or 0),
                int(row.get("created_at", 0) or 0),
                int(row.get("card_id", 0) or 0),
            )
        )

    source_card_id = int(source_card_id)
    direct_card_ids = [
        card_id
        for card_id in _positive_unique(directly_linked_card_ids)
        if card_id != source_card_id
    ]

    # The PDF/EPUB/video card is one level above direct attachments. A direct
    # attachment can also be a standalone knowledge-tree root, so use both as
    # traversal anchors. Queue every depth-zero anchor before walking children
    # so a directly linked nested node keeps its shortest media-relative depth.
    pending = deque(
        (row, source_card_id, 1)
        for row in grouped.get(source_card_id, [])
    )
    for card_id in direct_card_ids:
        row = row_by_card_id.get(card_id)
        if row is not None:
            pending.append((row, row.get("parent_card_id"), 1))
        else:
            pending.extend(
                (child, card_id, 2)
                for child in grouped.get(card_id, [])
            )

    descendants: list[dict] = []
    seen = {source_card_id}
    while pending:
        row, parent_card_id, edge_depth = pending.popleft()
        try:
            card_id = int(row.get("card_id", 0) or 0)
        except Exception:
            continue
        if card_id <= 0 or card_id in seen:
            continue
        seen.add(card_id)
        descendants.append(
            {
                "card_id": card_id,
                "parent_card_id": (
                    None if parent_card_id is None else int(parent_card_id)
                ),
                "source_depth": max(0, int(edge_depth) - 1),
                "node_kind": str(row.get("node_kind") or "").strip().lower(),
            }
        )
        pending.extend(
            (child, card_id, int(edge_depth) + 1)
            for child in grouped.get(card_id, [])
        )
    return descendants


def _card_ids_for_note_ids(col, note_ids: list[int]) -> list[int]:
    card_ids: list[int] = []
    seen: set[int] = set()
    for start in range(0, len(note_ids), _SEARCH_NOTE_CHUNK_SIZE):
        chunk = note_ids[start : start + _SEARCH_NOTE_CHUNK_SIZE]
        if not chunk:
            continue
        query = " OR ".join(f"nid:{note_id}" for note_id in chunk)
        try:
            found = list(col.find_cards(query) or [])
        except Exception:
            found = []
        for raw_card_id in found:
            try:
                card_id = int(raw_card_id)
            except Exception:
                continue
            if card_id <= 0 or card_id in seen:
                continue
            seen.add(card_id)
            card_ids.append(card_id)
    return card_ids


def _due_card_ids(col, card_ids: Iterable[int]) -> set[int]:
    ready_filter = build_ready_filter(
        include_new=False,
        include_learning=True,
        include_due=True,
    )
    due_ids: set[int] = set()
    normalized_ids = _positive_unique(card_ids)
    for start in range(0, len(normalized_ids), _SEARCH_CARD_CHUNK_SIZE):
        chunk = normalized_ids[start : start + _SEARCH_CARD_CHUNK_SIZE]
        if not chunk:
            continue
        query = "cid:" + ",".join(str(card_id) for card_id in chunk)
        try:
            found = col.find_cards(f"{query} {ready_filter}")
        except Exception:
            found = []
        due_ids.update(_positive_unique(found))
    return due_ids


def _target_filtered_deck_id(col, deck_name: str) -> int | None:
    name = str(deck_name or "").strip()
    if not name:
        return None
    try:
        deck = col.decks.by_name(name)
    except Exception:
        return None
    if not deck or not deck.get("dyn"):
        return None
    try:
        return int(deck.get("id"))
    except Exception:
        return None


def _card_availability(card, *, target_deck_id: int | None) -> str:
    try:
        queue = int(getattr(card, "queue", 0) or 0)
    except Exception:
        queue = 0
    if queue == -1:
        return MEDIA_REVIEW_AVAILABILITY_SUSPENDED
    if queue < -1:
        return MEDIA_REVIEW_AVAILABILITY_BURIED

    try:
        original_deck_id = int(getattr(card, "odid", 0) or 0)
        current_deck_id = int(getattr(card, "did", 0) or 0)
    except Exception:
        original_deck_id = 0
        current_deck_id = 0
    if original_deck_id > 0 and (
        target_deck_id is None or current_deck_id != int(target_deck_id)
    ):
        return MEDIA_REVIEW_AVAILABILITY_FILTERED
    return MEDIA_REVIEW_AVAILABILITY_AVAILABLE


def inspect_linked_media_review_rows(
    addon_dir: str,
    profile: str,
    source_card_id: int,
    *,
    col,
    media_kind: str = "",
    linked_source_rows: Iterable[dict] | None = None,
    linked_note_ids: Iterable[int] | None = None,
    linked_card_ids: Iterable[int] | None = None,
    linked_card_positions: Mapping[int, float] | None = None,
    include_tree_descendants: bool = True,
    target_deck_name: str = "",
    topic_classifier=None,
) -> list[dict]:
    """Inspect every linked card, retaining exclusion data for the preview UI."""
    source_card_id = int(source_card_id)
    if source_card_id <= 0:
        return []
    normalized_media_kind = normalize_media_kind(media_kind)

    raw_source_rows = list(linked_source_rows or [])
    raw_source_rows.extend(
        _legacy_source_rows(
            addon_dir,
            profile,
            normalized_media_kind,
            source_card_id,
        )
    )

    note_info: dict[int, dict] = {}

    def _append_note(raw_note_id, raw_position=None) -> None:
        try:
            note_id = int(raw_note_id)
        except Exception:
            return
        if note_id <= 0:
            return
        position = _normalized_position(raw_position)
        existing = note_info.get(note_id)
        if existing is None:
            note_info[note_id] = {
                "attached_rank": len(note_info),
                "media_position": position,
            }
            return
        previous_position = _normalized_position(existing.get("media_position"))
        if position is not None and (
            previous_position is None or position < previous_position
        ):
            existing["media_position"] = position

    for source_row in raw_source_rows:
        if not isinstance(source_row, dict):
            continue
        _append_note(
            source_row.get("note_id"),
            source_row.get(
                "position",
                source_row.get("page", source_row.get("section_index")),
            ),
        )
    for note_id in _positive_unique(linked_note_ids):
        _append_note(note_id)
    for note_id in _metadata_child_note_ids(col, source_card_id):
        _append_note(note_id)

    note_ids = list(note_info)
    note_rank = {
        note_id: int(info.get("attached_rank", index) or index)
        for index, (note_id, info) in enumerate(note_info.items())
    }
    note_card_ids = _card_ids_for_note_ids(col, note_ids)
    note_cards: list[tuple[int, int, int]] = []
    for card_id in note_card_ids:
        try:
            card = col.get_card(int(card_id))
            note_id = int(getattr(card, "nid", 0) or 0)
        except Exception:
            continue
        note_cards.append((note_rank.get(note_id, len(note_rank)), note_id, int(card_id)))
    note_cards.sort(key=lambda item: (item[0], item[2]))

    candidate_info: dict[int, dict] = {}

    def _append_card(
        raw_card_id,
        *,
        position=None,
        source_depth: int = 0,
        parent_card_id: int | None = None,
        tree_kind: str = "",
    ) -> None:
        try:
            card_id = int(raw_card_id)
        except Exception:
            return
        if card_id <= 0 or card_id == source_card_id:
            return
        normalized_position = _normalized_position(position)
        existing = candidate_info.get(card_id)
        if existing is None:
            candidate_info[card_id] = {
                "attached_rank": len(candidate_info),
                "media_position": normalized_position,
                "source_depth": max(0, int(source_depth or 0)),
                "parent_card_id": parent_card_id,
                "tree_kind": str(tree_kind or "").strip().lower(),
            }
            return
        existing["source_depth"] = min(
            int(existing.get("source_depth", 0) or 0),
            max(0, int(source_depth or 0)),
        )
        if existing.get("media_position") is None and normalized_position is not None:
            existing["media_position"] = normalized_position
        if not existing.get("parent_card_id") and parent_card_id is not None:
            existing["parent_card_id"] = int(parent_card_id)
        if not existing.get("tree_kind") and tree_kind:
            existing["tree_kind"] = str(tree_kind).strip().lower()

    for _rank, note_id, card_id in note_cards:
        _append_card(
            card_id,
            position=note_info.get(note_id, {}).get("media_position"),
            source_depth=0,
        )

    normalized_position_map: dict[int, float] = {}
    for raw_card_id, raw_position in dict(linked_card_positions or {}).items():
        try:
            card_id = int(raw_card_id)
        except Exception:
            continue
        position = _normalized_position(raw_position)
        if card_id > 0 and position is not None:
            normalized_position_map[card_id] = position
    for card_id in _positive_unique(linked_card_ids):
        _append_card(
            card_id,
            position=normalized_position_map.get(card_id),
            source_depth=0,
        )

    tree_links = (
        _knowledge_tree_descendant_links(
            addon_dir,
            profile,
            source_card_id,
            directly_linked_card_ids=tuple(candidate_info),
        )
        if include_tree_descendants
        else []
    )
    for link in tree_links:
        _append_card(
            link.get("card_id"),
            source_depth=int(link.get("source_depth", 0) or 0),
            parent_card_id=link.get("parent_card_id"),
            tree_kind=str(link.get("node_kind") or ""),
        )

    cards: dict[int, object] = {}
    notes: dict[int, object] = {}
    for card_id, info in candidate_info.items():
        try:
            card = col.get_card(int(card_id))
        except Exception:
            continue
        if card is None:
            continue
        cards[card_id] = card
        try:
            note_id = int(getattr(card, "nid", 0) or 0)
        except Exception:
            note_id = 0
        if note_id > 0 and note_id not in notes:
            try:
                notes[note_id] = col.get_note(note_id)
            except Exception:
                pass
        if info.get("media_position") is None:
            note = notes.get(note_id)
            if note is not None:
                info["media_position"] = _media_position_from_note(
                    note,
                    normalized_media_kind,
                    source_card_id,
                )

    # Nested cards inherit the nearest positioned ancestor. This keeps a
    # question extracted from another extracted card beside its media context.
    position_by_card_id = {
        card_id: _normalized_position(info.get("media_position"))
        for card_id, info in candidate_info.items()
    }
    for link in tree_links:
        try:
            card_id = int(link.get("card_id", 0) or 0)
            parent_card_id = int(link.get("parent_card_id", 0) or 0)
        except Exception:
            continue
        info = candidate_info.get(card_id)
        if info is None or int(info.get("source_depth", 0) or 0) <= 0:
            continue
        if position_by_card_id.get(card_id) is None:
            position_by_card_id[card_id] = position_by_card_id.get(parent_card_id)
            info["media_position"] = position_by_card_id.get(card_id)

    due_ids = _due_card_ids(col, candidate_info)
    target_deck_id = _target_filtered_deck_id(col, target_deck_name)
    try:
        classifier = topic_classifier or resolve_topic_card_classifier()
    except Exception:
        classifier = None

    rows: list[dict] = []
    for card_id, info in candidate_info.items():
        card = cards.get(card_id)
        if card is None:
            rows.append(
                {
                    "card_id": int(card_id),
                    "note_id": 0,
                    "queue": 0,
                    "due": 0,
                    "interval": 0,
                    "attached_rank": int(info.get("attached_rank", 0) or 0),
                    "created_at": int(card_id),
                    "media_position": _normalized_position(info.get("media_position")),
                    "source_depth": int(info.get("source_depth", 0) or 0),
                    "is_topic": str(info.get("tree_kind") or "") == "topic",
                    "is_due": False,
                    "availability": MEDIA_REVIEW_AVAILABILITY_MISSING,
                }
            )
            continue
        try:
            note_id = int(getattr(card, "nid", 0) or 0)
        except Exception:
            note_id = 0
        try:
            queue = int(getattr(card, "queue", 0) or 0)
        except Exception:
            queue = 0
        try:
            due = int(getattr(card, "due", 0) or 0)
        except Exception:
            due = 0
        try:
            interval = max(0, int(getattr(card, "ivl", 0) or 0))
        except Exception:
            interval = 0
        try:
            if classifier is None:
                raise RuntimeError("topic classifier unavailable")
            topic = bool(
                is_topic_card(
                    card,
                    classifier=classifier,
                    col=col,
                )
            )
        except Exception:
            topic = str(info.get("tree_kind") or "") == "topic"
        rows.append(
            {
                "card_id": int(card_id),
                "note_id": note_id,
                "queue": queue,
                "due": due,
                "interval": interval,
                "attached_rank": int(info.get("attached_rank", 0) or 0),
                # Anki card ids are time-based and provide a stable creation
                # ordering even for legacy notes without imported-at metadata.
                "created_at": int(card_id),
                "media_position": _normalized_position(info.get("media_position")),
                "source_depth": int(info.get("source_depth", 0) or 0),
                "is_topic": topic,
                "is_due": int(card_id) in due_ids,
                "availability": _card_availability(
                    card,
                    target_deck_id=target_deck_id,
                ),
            }
        )
    return rows


def resolve_linked_media_review_rows(
    addon_dir: str,
    profile: str,
    source_card_id: int,
    *,
    col,
    media_kind: str = "",
    linked_source_rows: Iterable[dict] | None = None,
    linked_note_ids: Iterable[int] | None = None,
    linked_card_ids: Iterable[int] | None = None,
    linked_card_positions: Mapping[int, float] | None = None,
    include_tree_descendants: bool = True,
    include_filtered: bool = False,
    target_deck_name: str = "",
    topic_classifier=None,
) -> list[dict]:
    """Return linked cards that Anki can put into this filtered review."""
    allowed_availability = {MEDIA_REVIEW_AVAILABILITY_AVAILABLE}
    if include_filtered:
        allowed_availability.add(MEDIA_REVIEW_AVAILABILITY_FILTERED)
    return [
        row
        for row in inspect_linked_media_review_rows(
            addon_dir,
            profile,
            source_card_id,
            col=col,
            media_kind=media_kind,
            linked_source_rows=linked_source_rows,
            linked_note_ids=linked_note_ids,
            linked_card_ids=linked_card_ids,
            linked_card_positions=linked_card_positions,
            include_tree_descendants=include_tree_descendants,
            target_deck_name=target_deck_name,
            topic_classifier=topic_classifier,
        )
        if str(row.get("availability") or "") in allowed_availability
    ]


def _due_order_key(row: dict) -> tuple[int, int, int]:
    if "is_due" in row:
        if bool(row.get("is_due")):
            state_rank = 0
        else:
            queue = int(row.get("queue", 0) or 0)
            state_rank = 2 if queue == 0 else 1
    else:
        queue = int(row.get("queue", 0) or 0)
        if queue == 1:
            state_rank = 0
        elif queue in {2, 3}:
            state_rank = 1
        elif queue == 0:
            state_rank = 2
        else:
            state_rank = 3
    return state_rank, int(row.get("due", 0) or 0), int(row.get("card_id", 0) or 0)


def _media_position_order_key(row: dict) -> tuple[int, float, int, int]:
    position = _normalized_position(row.get("media_position"))
    return (
        1 if position is None else 0,
        float("inf") if position is None else float(position),
        int(row.get("attached_rank", 0) or 0),
        int(row.get("card_id", 0) or 0),
    )


def order_linked_media_review_rows(
    rows: Iterable[dict] | None,
    order: str | None,
    *,
    shuffle: Callable[[list[dict]], None] | None = None,
    random_seed: int | None = None,
) -> list[dict]:
    ordered = [dict(row) for row in list(rows or [])]
    normalized_order = normalize_media_review_order(order)
    if normalized_order == MEDIA_REVIEW_ORDER_RANDOM:
        if shuffle is not None:
            shuffle(ordered)
        elif random_seed is not None:
            random.Random(int(random_seed)).shuffle(ordered)
        else:
            random.shuffle(ordered)
        return ordered
    if normalized_order == MEDIA_REVIEW_ORDER_MEDIA_POSITION:
        ordered.sort(key=_media_position_order_key)
    elif normalized_order == MEDIA_REVIEW_ORDER_CREATED_OLDEST:
        ordered.sort(
            key=lambda row: (
                int(row.get("created_at", 0) or 0),
                int(row.get("card_id", 0) or 0),
            )
        )
    elif normalized_order == MEDIA_REVIEW_ORDER_CREATED_NEWEST:
        ordered.sort(
            key=lambda row: (
                -int(row.get("created_at", 0) or 0),
                -int(row.get("card_id", 0) or 0),
            )
        )
    elif normalized_order == MEDIA_REVIEW_ORDER_DUE_FIRST:
        ordered.sort(key=_due_order_key)
    elif normalized_order == MEDIA_REVIEW_ORDER_INTERVAL_SHORTEST:
        ordered.sort(
            key=lambda row: (
                int(row.get("interval", 0) or 0),
                int(row.get("card_id", 0) or 0),
            )
        )
    elif normalized_order == MEDIA_REVIEW_ORDER_INTERVAL_LONGEST:
        ordered.sort(
            key=lambda row: (
                -int(row.get("interval", 0) or 0),
                int(row.get("card_id", 0) or 0),
            )
        )
    else:
        ordered.sort(
            key=lambda row: (
                int(row.get("attached_rank", 0) or 0),
                int(row.get("card_id", 0) or 0),
            )
        )
    return ordered


def select_linked_media_review_rows(
    rows: Iterable[dict] | None,
    *,
    order: str | None = None,
    card_kind: str | None = None,
    tree_scope: str | None = None,
    media_range: str | None = None,
    current_position=None,
    state: str | None = None,
    limit=0,
    random_seed: int | None = None,
    include_filtered: bool = False,
) -> dict:
    """Apply Review All choices and return selected rows plus exclusive counts."""
    normalized_kind = normalize_media_review_card_kind(card_kind)
    normalized_tree_scope = normalize_media_review_tree_scope(tree_scope)
    normalized_range = normalize_media_review_range(media_range)
    normalized_state = normalize_media_review_state(state)
    normalized_limit = normalize_media_review_limit(limit)
    normalized_current_position = _normalized_position(current_position)
    if normalized_current_position is None:
        normalized_range = MEDIA_REVIEW_RANGE_ALL

    exclusions = {
        MEDIA_REVIEW_AVAILABILITY_SUSPENDED: 0,
        MEDIA_REVIEW_AVAILABILITY_BURIED: 0,
        MEDIA_REVIEW_AVAILABILITY_FILTERED: 0,
        MEDIA_REVIEW_AVAILABILITY_MISSING: 0,
        "nested": 0,
        "beyond_current": 0,
        "unknown_position": 0,
        "other_kind": 0,
        "not_due": 0,
        "limit": 0,
    }
    eligible: list[dict] = []
    all_rows = [dict(row) for row in list(rows or [])]
    for row in all_rows:
        availability = str(
            row.get("availability") or MEDIA_REVIEW_AVAILABILITY_AVAILABLE
        ).strip().lower()
        if availability != MEDIA_REVIEW_AVAILABILITY_AVAILABLE and not (
            bool(include_filtered)
            and availability == MEDIA_REVIEW_AVAILABILITY_FILTERED
        ):
            key = (
                availability
                if availability in exclusions
                else MEDIA_REVIEW_AVAILABILITY_MISSING
            )
            exclusions[key] += 1
            continue
        if (
            normalized_tree_scope == MEDIA_REVIEW_TREE_DIRECT
            and int(row.get("source_depth", 0) or 0) > 0
        ):
            exclusions["nested"] += 1
            continue
        if normalized_range == MEDIA_REVIEW_RANGE_TO_CURRENT:
            position = _normalized_position(row.get("media_position"))
            if position is None:
                exclusions["unknown_position"] += 1
                continue
            if position > float(normalized_current_position):
                exclusions["beyond_current"] += 1
                continue
        is_topic = bool(row.get("is_topic"))
        if (
            normalized_kind == MEDIA_REVIEW_CARD_KIND_TOPICS
            and not is_topic
        ) or (
            normalized_kind == MEDIA_REVIEW_CARD_KIND_ITEMS
            and is_topic
        ):
            exclusions["other_kind"] += 1
            continue
        if normalized_state == MEDIA_REVIEW_STATE_DUE and not bool(row.get("is_due")):
            exclusions["not_due"] += 1
            continue
        eligible.append(row)

    ordered = order_linked_media_review_rows(
        eligible,
        order,
        random_seed=random_seed,
    )
    if normalized_limit > 0 and len(ordered) > normalized_limit:
        exclusions["limit"] = len(ordered) - normalized_limit
        ordered = ordered[:normalized_limit]

    selected_topic_count = sum(1 for row in ordered if bool(row.get("is_topic")))
    selected_filtered_count = sum(
        1
        for row in ordered
        if str(row.get("availability") or "").strip().lower()
        == MEDIA_REVIEW_AVAILABILITY_FILTERED
    )
    return {
        "rows": ordered,
        "card_ids": [int(row.get("card_id", 0) or 0) for row in ordered],
        "total_count": len(all_rows),
        "selected_count": len(ordered),
        "topic_count": selected_topic_count,
        "item_count": len(ordered) - selected_topic_count,
        "selected_filtered_count": selected_filtered_count,
        "exclusions": exclusions,
        "order": normalize_media_review_order(order),
        "card_kind": normalized_kind,
        "tree_scope": normalized_tree_scope,
        "media_range": normalized_range,
        "state": normalized_state,
        "limit": normalized_limit,
        "include_filtered": bool(include_filtered),
    }


def linked_media_review_card_ids(
    addon_dir: str,
    profile: str,
    source_card_id: int,
    *,
    col,
    media_kind: str = "",
    order: str | None = None,
    card_kind: str | None = None,
    tree_scope: str | None = None,
    media_range: str | None = None,
    current_position=None,
    state: str | None = None,
    limit=0,
    random_seed: int | None = None,
    linked_source_rows: Iterable[dict] | None = None,
    linked_note_ids: Iterable[int] | None = None,
    linked_card_ids: Iterable[int] | None = None,
    linked_card_positions: Mapping[int, float] | None = None,
    include_tree_descendants: bool = True,
    include_filtered: bool = False,
    target_deck_name: str = "",
    topic_classifier=None,
) -> list[int]:
    rows = resolve_linked_media_review_rows(
        addon_dir,
        profile,
        source_card_id,
        col=col,
        media_kind=media_kind,
        linked_source_rows=linked_source_rows,
        linked_note_ids=linked_note_ids,
        linked_card_ids=linked_card_ids,
        linked_card_positions=linked_card_positions,
        include_tree_descendants=include_tree_descendants,
        include_filtered=include_filtered,
        target_deck_name=target_deck_name,
        topic_classifier=topic_classifier,
    )
    return list(
        select_linked_media_review_rows(
            rows,
            order=order,
            card_kind=card_kind,
            tree_scope=tree_scope,
            media_range=media_range,
            current_position=current_position,
            state=state,
            limit=limit,
            random_seed=random_seed,
            include_filtered=include_filtered,
        )["card_ids"]
    )
