import sys
import types
from unittest.mock import MagicMock

sys.modules.setdefault("session", MagicMock())
import aqt

import epub_dock


def test_browse_note_ids_in_browser_builds_deduplicated_query(monkeypatch):
    searches = []

    class _FakeBrowser:
        def search_for(self, query):
            searches.append(query)

    fake_dialogs = types.SimpleNamespace(open=lambda name, parent: _FakeBrowser())
    monkeypatch.setitem(sys.modules, "aqt.dialogs", fake_dialogs)
    monkeypatch.setattr(aqt, "dialogs", fake_dialogs, raising=False)

    assert epub_dock._browse_note_ids_in_browser([21, 22, 21, 0, -1]) is True
    assert searches == ["nid:21 OR nid:22"]


def test_browse_note_ids_in_browser_shows_empty_tooltip(monkeypatch):
    tooltips = []
    monkeypatch.setattr(epub_dock, "tooltip", lambda message: tooltips.append(message))

    assert epub_dock._browse_note_ids_in_browser([], empty_message="No cards yet.") is False
    assert tooltips == ["No cards yet."]


def test_add_card_source_for_new_note_prefers_pending_extract_source(monkeypatch):
    fake_add_card_dock = types.SimpleNamespace(
        pending_extract_options=lambda: {"source": "reviewer"},
        recent_fill_source=lambda: "epub",
    )
    monkeypatch.setitem(sys.modules, "add_card_dock", fake_add_card_dock)

    assert epub_dock._add_card_source_for_new_note() == "reviewer"


def test_on_add_cards_did_add_note_ignores_reviewer_extract(monkeypatch):
    calls = []
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 55)
    monkeypatch.setattr(epub_dock, "_add_card_source_for_new_note", lambda: "reviewer")
    monkeypatch.setattr(
        epub_dock,
        "add_epub_card_source",
        lambda *args, **kwargs: calls.append(args),
    )

    epub_dock.on_add_cards_did_add_note(types.SimpleNamespace(id=123, fields=["Front"]))

    assert calls == []


def test_regenerate_epub_cover_reloads_active_reviewer_card_in_place(monkeypatch):
    tooltips = []
    shown = []
    resets = []

    class _FakeReviewerCard:
        def __init__(self):
            self.id = 66
            self.timer_started = 456.0
            self.load_calls = 0

        def load(self):
            self.load_calls += 1

    current_card = _FakeReviewerCard()
    reviewer = types.SimpleNamespace(
        card=current_card,
        _showQuestion=lambda: shown.append(True),
    )
    fake_col = types.SimpleNamespace(
        reset=lambda: resets.append(True),
        get_card=lambda card_id: (_ for _ in ()).throw(
            AssertionError("reviewer card should be reloaded in place")
        ),
    )
    monkeypatch.setattr(epub_dock, "mw", types.SimpleNamespace(col=fake_col, reviewer=reviewer))
    monkeypatch.setattr(epub_dock, "_current_epub_card_id", 66)
    monkeypatch.setattr(epub_dock, "regenerate_epub_card_cover", lambda addon_dir, col, card_id: "cover.png")
    monkeypatch.setattr(epub_dock, "tooltip", lambda message: tooltips.append(message))

    epub_dock._regenerate_epub_cover()

    assert resets == [True]
    assert reviewer.card is current_card
    assert current_card.load_calls == 1
    assert current_card.timer_started == 456.0
    assert shown == [True]
    assert tooltips == ["EPUB cover regenerated from book metadata."]
