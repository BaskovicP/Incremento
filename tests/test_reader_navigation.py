"""Returning across documents restores the visit, without writing resume state."""
from frontend.reader_navigation import ReaderReturnHistory


def test_return_history_is_profile_scoped_bounded_and_keeps_exact_locations():
    history = ReaderReturnHistory()
    for page in range(1, 60):
        history.push('A', dict(card_id=7, filename='book.pdf', page=page, scroll_ratio=.37, zoom=1.4))
    assert len(history.entries) == 50
    assert history.pop('B') is None
    assert not history.available('A')
    history.push('A', dict(card_id=7, filename='book.pdf', page=3, scroll_ratio=.37, zoom=1.4))
    assert history.pop('A') == dict(card_id=7, filename='book.pdf', page=3, scroll_ratio=.37, zoom=1.4)
    assert not history.available('A')
