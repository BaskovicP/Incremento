from aqt import mw

try:
    from .priority_manager import get_all_priorities
    from .epub_manager import DOCUMENT_FILTER
    from .paths import get_active_profile as _active_profile
except ImportError:
    from priority_manager import get_all_priorities  # type: ignore
    from epub_manager import DOCUMENT_FILTER  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore

all_ready_cards_filter = "(is:due OR is:learn OR is:new)"


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


def get_all_topic_cards(
    topics_filter: str = "deck:Topics", ready_filter: str = all_ready_cards_filter
):
    return _sort_by_due(mw.col.find_cards(f"{topics_filter} {ready_filter}"))


def get_all_item_cards(
    items_filter: str = "-deck:Topics", ready_filter: str = all_ready_cards_filter
):
    return _sort_by_due(mw.col.find_cards(f"{items_filter} {ready_filter}"))

def get_topic_cards_by_tag(
    tag: str,
    topics_filter: str = "deck:Topics",
    ready_filter: str = all_ready_cards_filter,
):
    return _sort_by_due(mw.col.find_cards(f"{topics_filter} tag:{tag} {ready_filter}"))


def get_item_cards_by_tag(
    tag: str,
    items_filter: str = "-deck:Topics",
    ready_filter: str = all_ready_cards_filter,
):
    return _sort_by_due(mw.col.find_cards(f"{items_filter} tag:{tag} {ready_filter}"))


def get_all_pdf_cards(pdf_filter: str = DOCUMENT_FILTER):
    """Return all non-suspended document cards, always eligible regardless of due state."""
    return _sort_by_due(mw.col.find_cards(f"{pdf_filter} -is:suspended"))


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
