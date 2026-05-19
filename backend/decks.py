from aqt import mw


def create_topics_deck(deck_name: str = "Topics") -> bool:
    """Ensure the requested normal deck exists.

    Returns True when the deck was created and False when it already existed
    or no collection is currently available.
    """
    col = getattr(mw, "col", None)
    if col is None:
        return False
    if col.decks.by_name(deck_name):
        return False
    normalized_name = str(deck_name or "").strip().casefold()
    try:
        for deck in col.decks.all_names_and_ids() or []:
            existing_name = str(getattr(deck, "name", "") or "").strip().casefold()
            if existing_name == normalized_name:
                return False
    except Exception:
        pass
    col.decks.add_normal_deck_with_name(deck_name)
    return True
