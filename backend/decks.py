# Check if deck topics exists if not create one
from aqt import mw

def create_topics_deck():
    mw.col.decks.add_normal_deck_with_name('Topics')
