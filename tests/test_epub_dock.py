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
