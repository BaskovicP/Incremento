"""Independent reference views never share identity or accept retired messages."""
import pytest

from pdf_reader_state import PdfReaderState


def test_two_readers_of_the_same_pdf_keep_independent_positions_and_nonces():
    left = PdfReaderState("A", 7, "book.pdf", page=2)
    right = PdfReaderState("A", 7, "book.pdf", page=40)
    assert left.nonce != right.nonce
    assert right.receive({"page": 41, "scroll_ratio": .5}, profile="A", nonce=right.nonce)
    assert (left.page, left.scroll_ratio) == (2, 0)
    assert (right.page, right.scroll_ratio) == (41, .5)


@pytest.mark.parametrize("profile,nonce,payload", [
    ("B", None, {"page": 3}), ("A", "stale", {"page": 3}),
    ("A", None, {"page": -1}), ("A", None, {"page": True}),
    ("A", None, {"page": 6}), ("A", None, {"page": 3, "scroll_ratio": float("nan")}),
    ("A", None, {"page": 3, "zoom": 100}),
])
def test_invalid_or_stale_message_cannot_change_reader(profile, nonce, payload):
    state = PdfReaderState("A", 7, "book.pdf", page=2, max_page=5)
    assert not state.receive(payload, profile=profile, nonce=nonce or state.nonce)
    assert (state.page, state.scroll_ratio, state.zoom) == (2, 0, 1)


def test_closing_a_reader_invalidates_pending_callbacks():
    state = PdfReaderState("A", 7, "book.pdf")
    nonce = state.nonce
    state.close()
    assert not state.is_current("A", nonce)
    assert not state.receive({"page": 2}, profile="A", nonce=nonce)
