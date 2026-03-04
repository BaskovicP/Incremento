import json
from typing import Any, Sequence

from anki.cards import Card, CardId
from aqt import mw

all_ready_cards_filter = "is:due OR is:learn OR is:new"

def get_all_ready_card_ids():
    return mw.col.find_cards(all_ready_cards_filter)

def get_all_topic_cards():
    # TODO: Extract topics into a variable
    return mw.col.find_cards(all_ready_cards_filter + " decks:topics")

def get_all_item_cards():
    return mw.col.find_cards(all_ready_cards_filter + '-deck:"Topics::*"')




# Potentialy useful
def get_all_ready_cards_custom_data():
    result = {}
    for cid in get_all_ready_card_ids():
        card = mw.col.get_card(cid)
        if card.custom_data:
           try:
               result[cid] = json.loads(card.custom_data)
           except:
               result[cid] = {}
    return result
def change_custom_data(card_id: CardId, custom_data: dict) -> Card:
    card = mw.col.get_card(card_id)
    try:
        original_custom_data = json.loads(card.custom_data)
        card.custom_data = {**original_custom_data, **custom_data}
    except:
        print("Filling custom data failed")

    return card

def batch_update_card_custom_data(card_ids: Sequence[CardId], custom_data: dict) -> list[Any]:
    changed_cards = []
    undo_id = mw.col.add_custom_undo_entry('Batch add cards')

    for card_id in card_ids:
        changed_cards.append(change_custom_data(card_id, custom_data))

    mw.col.update_cards(changed_cards)
    mw.col.merge_undo_entries(undo_id)
    return changed_cards


