from aqt import mw

try:
    from .priority_manager import get_all_priorities
    from .epub_manager import DOCUMENT_FILTER, EPUB_NOTE_TYPE
    from .topic_scheduler import is_topic_card, resolve_topic_card_classifier
    from .paths import get_active_profile as _active_profile
except ImportError:
    from priority_manager import get_all_priorities  # type: ignore
    from epub_manager import DOCUMENT_FILTER, EPUB_NOTE_TYPE  # type: ignore
    from topic_scheduler import is_topic_card, resolve_topic_card_classifier  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore

all_ready_cards_filter = "(is:new OR (is:learn is:due) OR (is:review is:due)) -is:suspended"
PDF_NOTE_TYPE = "Incremento PDF"
_TOPIC_ITEM_CACHE: dict[tuple, tuple[int, ...]] = {}
_SQL_VARIABLE_CHUNK_SIZE = 900


def _collection(col=None):
    return col if col is not None else mw.col


def _card_due_map(card_ids, *, col=None) -> dict[int, int]:
    """Return due values for card_ids without exceeding SQLite variable limits."""
    due_map: dict[int, int] = {}
    ids = list(card_ids)
    for start in range(0, len(ids), _SQL_VARIABLE_CHUNK_SIZE):
        chunk = ids[start : start + _SQL_VARIABLE_CHUNK_SIZE]
        if not chunk:
            continue
        placeholders = ",".join("?" * len(chunk))
        rows = _collection(col).db.all(
            f"SELECT id, due FROM cards WHERE id IN ({placeholders})", *chunk
        )
        due_map.update({row[0]: row[1] for row in rows})
    return due_map


def _sort_by_due(card_ids, *, col=None):
    """Return card_ids sorted by ascending due date (most overdue first).

    Fetches due dates in bounded chunks to avoid SQLite's variable limit.
    """
    if not card_ids:
        return list(card_ids)
    ids = list(card_ids)
    due_map = _card_due_map(ids, col=col)
    ids.sort(key=lambda cid: due_map.get(cid, 0))
    return ids


def clear_topic_item_cache() -> None:
    _TOPIC_ITEM_CACHE.clear()


def sort_cards_for_priority_mode(
    card_ids,
    addon_dir: str | None = None,
    lower_is_more_important: bool = True,
    *,
    col=None,
    profile: str | None = None,
):
    """Return card_ids ordered for priority mode using priority first, due second."""
    if not card_ids:
        return list(card_ids)

    ids = list(card_ids)
    due_map = _card_due_map(ids, col=col)
    priority_map = {}
    if addon_dir:
        resolved_profile = profile if profile is not None else _active_profile()
        priority_map = get_all_priorities(addon_dir, resolved_profile)

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


def get_all_ready_card_ids(*, col=None):
    return _collection(col).find_cards(all_ready_cards_filter)


def _normalized_query(*parts: str) -> str:
    return " ".join(str(part or "").strip() for part in parts if str(part or "").strip()).strip()


def _classified_ready_cards(
    kind: str,
    *,
    extra_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    col=None,
    topic_classifier=None,
):
    if kind not in {"topics", "items"}:
        raise ValueError(f"Unsupported classified kind: {kind}")

    collection = _collection(col)
    classifier = topic_classifier or resolve_topic_card_classifier()
    query = _normalized_query(extra_filter, ready_filter)
    classifier_key = getattr(classifier, "cache_key", None)
    cache_base = (
        id(collection),
        query,
        classifier_key,
    )
    cache_key = cache_base + (kind,)
    cached = _TOPIC_ITEM_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    candidate_ids = _sort_by_due(collection.find_cards(query), col=collection)
    topic_ids: list[int] = []
    item_ids: list[int] = []
    for card_id in candidate_ids:
        try:
            card = collection.get_card(card_id)
        except Exception:
            continue
        if card is None:
            continue
        try:
            try:
                is_topic = bool(
                    is_topic_card(card, classifier=classifier, col=collection)
                )
            except TypeError:
                # Keep compatibility with test/third-party wrappers that
                # still expose the historical one-argument callable.
                is_topic = bool(is_topic_card(card))
        except Exception:
            is_topic = False
        if is_topic:
            topic_ids.append(int(card_id))
        else:
            item_ids.append(int(card_id))

    _TOPIC_ITEM_CACHE[cache_base + ("topics",)] = tuple(topic_ids)
    _TOPIC_ITEM_CACHE[cache_base + ("items",)] = tuple(item_ids)
    return list(topic_ids if kind == "topics" else item_ids)


def get_all_topic_cards(
    topics_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
):
    return _classified_ready_cards(
        "topics",
        extra_filter=topics_filter,
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    )


def get_all_item_cards(
    items_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
):
    return _classified_ready_cards(
        "items",
        extra_filter=items_filter,
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    )

def get_topic_cards_by_tag(
    tag: str,
    topics_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
):
    return _classified_ready_cards(
        "topics",
        extra_filter=_normalized_query(topics_filter, f"tag:{tag}"),
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    )


def get_item_cards_by_tag(
    tag: str,
    items_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
):
    return _classified_ready_cards(
        "items",
        extra_filter=_normalized_query(items_filter, f"tag:{tag}"),
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    )


def count_ready_topic_cards(
    topics_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
) -> int:
    return len(get_all_topic_cards(
        topics_filter=topics_filter,
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    ))


def count_ready_item_cards(
    items_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
) -> int:
    return len(get_all_item_cards(
        items_filter=items_filter,
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    ))


def count_ready_topic_cards_by_tag(
    tag: str,
    topics_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
) -> int:
    return len(get_topic_cards_by_tag(
        tag,
        topics_filter=topics_filter,
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    ))


def count_ready_item_cards_by_tag(
    tag: str,
    items_filter: str = "",
    ready_filter: str = all_ready_cards_filter,
    *,
    col=None,
    topic_classifier=None,
) -> int:
    return len(get_item_cards_by_tag(
        tag,
        items_filter=items_filter,
        ready_filter=ready_filter,
        col=col,
        topic_classifier=topic_classifier,
    ))


def get_all_pdf_cards(pdf_filter: str = DOCUMENT_FILTER, *, col=None):
    """Return all non-suspended document cards, always eligible regardless of due state."""
    collection = _collection(col)
    return _sort_by_due(collection.find_cards(f"{pdf_filter} -is:suspended"), col=collection)


def get_document_card_type(card_id: int, *, col=None) -> str | None:
    """Return the concrete Incremento document type for a card id."""
    try:
        collection = _collection(col)
        card = collection.get_card(int(card_id))
        note = collection.get_note(card.nid)
        model = collection.models.get(note.mid)
        name = model.get("name") if model else ""
    except Exception:
        return None
    if name == EPUB_NOTE_TYPE:
        return "epub"
    if name == PDF_NOTE_TYPE:
        return "pdf"
    return None


def get_all_youtube_cards(youtube_filter: str = 'note:"Incremento Video"', *, col=None):
    """Return all non-suspended YouTube/video cards, always eligible regardless of due state."""
    collection = _collection(col)
    return _sort_by_due(collection.find_cards(f"{youtube_filter} -is:suspended"), col=collection)


def get_all_webpage_cards(webpage_filter: str = 'note:"Incremento Web"', *, col=None):
    """Return all non-suspended webpage cards, always eligible regardless of due state."""
    collection = _collection(col)
    return _sort_by_due(collection.find_cards(f"{webpage_filter} -is:suspended"), col=collection)


def get_pdf_cards_by_tag(tag: str, pdf_filter: str = DOCUMENT_FILTER, *, col=None):
    collection = _collection(col)
    return _sort_by_due(
        collection.find_cards(f"{pdf_filter} tag:{tag} -is:suspended"),
        col=collection,
    )


def get_youtube_cards_by_tag(
    tag: str,
    youtube_filter: str = 'note:"Incremento Video"',
    *,
    col=None,
):
    collection = _collection(col)
    return _sort_by_due(
        collection.find_cards(f"{youtube_filter} tag:{tag} -is:suspended"),
        col=collection,
    )


def get_webpage_cards_by_tag(
    tag: str,
    webpage_filter: str = 'note:"Incremento Web"',
    *,
    col=None,
):
    collection = _collection(col)
    return _sort_by_due(
        collection.find_cards(f"{webpage_filter} tag:{tag} -is:suspended"),
        col=collection,
    )
