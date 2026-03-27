import json
from typing import Any, Sequence

from anki.cards import Card, CardId
from aqt import mw

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


# Potentialy useful
def get_all_ready_cards_custom_data():
    result = {}
    for cid in get_all_ready_card_ids():
        card = mw.col.get_card(cid)
        if card.custom_data:
            try:
                result[cid] = json.loads(card.custom_data)
            except Exception as e:
                print(
                    f"[Incremento] cards: failed to parse custom_data for cid {cid}: {e}"
                )
                result[cid] = {}
    return result


def change_custom_data(card_id: CardId, custom_data: dict) -> Card:
    card = mw.col.get_card(card_id)
    try:
        original_custom_data = json.loads(card.custom_data)
        card.custom_data = {**original_custom_data, **custom_data}
    except Exception as e:
        print(
            f"[Incremento] cards: change_custom_data failed for card_id {card_id}: {e}"
        )

    return card


def batch_update_card_custom_data(
    card_ids: Sequence[CardId], custom_data: dict
) -> list[Any]:
    changed_cards = []
    undo_id = mw.col.add_custom_undo_entry("Batch add cards")

    for card_id in card_ids:
        changed_cards.append(change_custom_data(card_id, custom_data))

    mw.col.update_cards(changed_cards)
    mw.col.merge_undo_entries(undo_id)
    return changed_cards


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


def get_all_pdf_cards(pdf_filter: str = 'note:"Incremento PDF"'):
    """Return all non-suspended PDF cards, always eligible regardless of due state."""
    return _sort_by_due(mw.col.find_cards(f"{pdf_filter} -is:suspended"))


def get_all_youtube_cards(youtube_filter: str = 'note:"Incremento Video"'):
    """Return all non-suspended YouTube/video cards, always eligible regardless of due state."""
    return _sort_by_due(mw.col.find_cards(f"{youtube_filter} -is:suspended"))


def get_all_webpage_cards(webpage_filter: str = 'note:"Incremento Web"'):
    """Return all non-suspended webpage cards, always eligible regardless of due state."""
    return _sort_by_due(mw.col.find_cards(f"{webpage_filter} -is:suspended"))


def get_pdf_cards_by_tag(tag: str, pdf_filter: str = 'note:"Incremento PDF"'):
    return _sort_by_due(mw.col.find_cards(f"{pdf_filter} tag:{tag} -is:suspended"))


def get_youtube_cards_by_tag(tag: str, youtube_filter: str = 'note:"Incremento Video"'):
    return _sort_by_due(mw.col.find_cards(f"{youtube_filter} tag:{tag} -is:suspended"))


def get_webpage_cards_by_tag(tag: str, webpage_filter: str = 'note:"Incremento Web"'):
    return _sort_by_due(mw.col.find_cards(f"{webpage_filter} tag:{tag} -is:suspended"))
