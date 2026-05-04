from aqt import mw

try:
    from .priority_manager import get_all_priorities
    from .epub_manager import DOCUMENT_FILTER, EPUB_NOTE_TYPE
    from .topic_scheduler import is_topic_card
    from .paths import get_active_profile as _active_profile
except ImportError:
    from priority_manager import get_all_priorities  # type: ignore
    from epub_manager import DOCUMENT_FILTER, EPUB_NOTE_TYPE  # type: ignore
    from topic_scheduler import is_topic_card  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore

all_ready_cards_filter = "(is:due OR is:learn OR is:new)"
PDF_NOTE_TYPE = "Incremento PDF"
_TOPIC_ITEM_CACHE: dict[tuple[int, str, str, str], tuple[int, ...]] = {}


def _sort_by_due(card_ids):
    """Return card_ids sorted by ascending due date (most overdue first).

    Uses a single bulk SQL query instead of one get_card() call per card,
    reducing N individual DB round-trips to one.
    """
    if not card_ids:
        return list(card_ids)
    ids = list(card_ids)
    placeholders = ",".join("?" * len(ids))
    rows = mw.col.db.all(
        f"SELECT id, due FROM cards WHERE id IN ({placeholders})", *ids
    )
    due_map = {row[0]: row[1] for row in rows}
    ids.sort(key=lambda cid: due_map.get(cid, 0))
    return ids


def clear_topic_item_cache() -> None:
    _TOPIC_ITEM_CACHE.clear()


def sort_cards_for_priority_mode(
    card_ids,
    addon_dir: str | None = None,
    lower_is_more_important: bool = True,
):
    """Return card_ids ordered for priority mode using priority first, due second."""
    if not card_ids:
        return list(card_ids)

    ids = list(card_ids)
    placeholders = ",".join("?" * len(ids))
    rows = mw.col.db.all(
        f"SELECT id, due FROM cards WHERE id IN ({placeholders})", *ids
    )
    due_map = {row[0]: row[1] for row in rows}
    priority_map = get_all_priorities(addon_dir, _active_profile()) if addon_dir else {}

    if lower_is_more_important:
        ids.sort(
            key=lambda cid: (
                priority_map.get(cid, 50.0),
                due_map.get(cid, 0),
                cid,
            )
        )
    else:
        ids.sort(
            key=lambda cid: (
                -priority_map.get(cid, 50.0),
                due_map.get(cid, 0),
                cid,
            )
        )
    return ids


def get_all_ready_card_ids():
    return mw.col.find_cards(all_ready_cards_filter)


def _normalized_query(*parts: str) -> str:
    return " ".join(str(part or "").strip() for part in parts if str(part or "").strip()).strip()


def _classified_ready_cards(
    kind: str,
    *,
    extra_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
):
    query = _normalized_query(extra_filter, ready_filter)
    cache_key = (
        id(getattr(mw, "col", None)),
        kind,
        str(extra_filter or "").strip(),
        str(ready_filter or "").strip(),
    )
    cached = _TOPIC_ITEM_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    candidate_ids = _sort_by_due(mw.col.find_cards(query))
    matched: list[int] = []
    for card_id in candidate_ids:
        try:
            card = mw.col.get_card(card_id)
        except Exception:
            continue
        if card is None:
            continue
        try:
            is_topic = bool(is_topic_card(card))
        except Exception:
            is_topic = False
        if kind == "topics":
            if is_topic:
                matched.append(int(card_id))
            continue
        if kind == "items":
            if not is_topic:
                matched.append(int(card_id))
            continue
        raise ValueError(f"Unsupported classified kind: {kind}")

    _TOPIC_ITEM_CACHE[cache_key] = tuple(matched)
    return list(matched)


def get_all_topic_cards(
    topics_filter: str = "", ready_filter: str = all_ready_cards_filter
):
    return _classified_ready_cards("topics", extra_filter=topics_filter, ready_filter=ready_filter)


def get_all_item_cards(
    items_filter: str = "", ready_filter: str = all_ready_cards_filter
):
    return _classified_ready_cards("items", extra_filter=items_filter, ready_filter=ready_filter)

def get_topic_cards_by_tag(
    tag: str,
    topics_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
):
    return _classified_ready_cards(
        "topics",
        extra_filter=_normalized_query(topics_filter, f"tag:{tag}"),
        ready_filter=ready_filter,
    )


def get_item_cards_by_tag(
    tag: str,
    items_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
):
    return _classified_ready_cards(
        "items",
        extra_filter=_normalized_query(items_filter, f"tag:{tag}"),
        ready_filter=ready_filter,
    )


def count_ready_topic_cards(
    topics_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
) -> int:
    return len(get_all_topic_cards(topics_filter=topics_filter, ready_filter=ready_filter))


def count_ready_item_cards(
    items_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
) -> int:
    return len(get_all_item_cards(items_filter=items_filter, ready_filter=ready_filter))


def count_ready_topic_cards_by_tag(
    tag: str,
    topics_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
) -> int:
    return len(get_topic_cards_by_tag(tag, topics_filter=topics_filter, ready_filter=ready_filter))


def count_ready_item_cards_by_tag(
    tag: str,
    items_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
) -> int:
    return len(get_item_cards_by_tag(tag, items_filter=items_filter, ready_filter=ready_filter))


def get_all_pdf_cards(pdf_filter: str = DOCUMENT_FILTER):
    """Return all non-suspended document cards, always eligible regardless of due state."""
    return _sort_by_due(mw.col.find_cards(f"{pdf_filter} -is:suspended"))


def get_document_card_type(card_id: int) -> str | None:
    """Return the concrete Incremento document type for a card id."""
    try:
        card = mw.col.get_card(int(card_id))
        note = mw.col.get_note(card.nid)
        model = mw.col.models.get(note.mid)
        name = model.get("name") if model else ""
    except Exception:
        return None
    if name == EPUB_NOTE_TYPE:
        return "epub"
    if name == PDF_NOTE_TYPE:
        return "pdf"
    return None


def get_all_youtube_cards(youtube_filter: str = 'note:"Incremento Video"'):
    """Return all non-suspended YouTube/video cards, always eligible regardless of due state."""
    return _sort_by_due(mw.col.find_cards(f"{youtube_filter} -is:suspended"))


def get_all_webpage_cards(webpage_filter: str = 'note:"Incremento Web"'):
    """Return all non-suspended webpage cards, always eligible regardless of due state."""
    return _sort_by_due(mw.col.find_cards(f"{webpage_filter} -is:suspended"))


def get_pdf_cards_by_tag(tag: str, pdf_filter: str = DOCUMENT_FILTER):
    return _sort_by_due(mw.col.find_cards(f"{pdf_filter} tag:{tag} -is:suspended"))


def get_youtube_cards_by_tag(tag: str, youtube_filter: str = 'note:"Incremento Video"'):
    return _sort_by_due(mw.col.find_cards(f"{youtube_filter} tag:{tag} -is:suspended"))


def get_webpage_cards_by_tag(tag: str, webpage_filter: str = 'note:"Incremento Web"'):
    return _sort_by_due(mw.col.find_cards(f"{webpage_filter} tag:{tag} -is:suspended"))
