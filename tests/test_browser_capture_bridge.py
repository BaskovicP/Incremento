"""Capture preview/create transitions with isolated supplemental storage."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import browser_bridge as bridge
import db
import paths
import pytest


@pytest.fixture
def capture_env(tmp_path, monkeypatch):
    col = MagicMock()
    model = {"name": "Basic", "flds": [{"name": "Front"}, {"name": "Back"}]}
    col.models.by_name.return_value = model
    col.decks.by_name.return_value = {"id": 1}
    notes = {}
    cards = {}

    class Note(dict):
        tags = None

        def __init__(self):
            super().__init__()
            self.tags = []
            self.id = 0

        def note_type(self):
            return model

    def add_note(note, deck):
        note.id = len(notes) + 1
        notes[note.id] = note
        cards[note.id + 100] = SimpleNamespace(id=note.id + 100, nid=note.id, note=lambda: note)
        return 1

    col.new_note.side_effect = lambda model: Note()
    col.add_note.side_effect = add_note
    col.find_cards.side_effect = lambda query: [int(query.split(":")[1]) + 100]
    col.get_card.side_effect = lambda cid: cards[cid]
    col.find_notes.return_value = []
    monkeypatch.setitem(sys.modules, "aqt", SimpleNamespace(mw=SimpleNamespace(col=col)))
    monkeypatch.setitem(sys.modules, "priority_manager", SimpleNamespace(set_priority=lambda *args: None))
    monkeypatch.setattr(bridge, "_addon_dir", str(tmp_path))
    monkeypatch.setattr(paths, "get_active_profile", lambda: "CaptureProfile")
    yield col, cards, tmp_path
    db.close_connection()


def payload(**overrides):
    return bridge.normalize_browser_capture_payload({
        "url": "https://example.com/article", "title": "An <article>",
        "noteTypeName": "Basic", "deckName": "Research", "selectedText": "A passage",
        "selectedHtml": "<p>A <strong>passage</strong></p>", "sourceText": "Original passage",
        "linkToPassage": True, "fieldMappings": {"selectedTextField": "Front", "urlField": "Back"},
        **overrides,
    })


def test_preview_shows_final_safe_fields_and_source_without_writes(capture_env):
    col, _, root = capture_env
    result = bridge._create_browser_capture_note_on_main(payload(action="preview"))
    assert result["preview"] is True
    assert result["fields"]["Front"] == "<p>A <strong>passage</strong></p>"
    assert 'href="https://example.com/article#:~:text=Original%20passage"' in result["fields"]["Back"]
    assert "An &lt;article&gt;" in result["fields"]["Back"]
    col.add_note.assert_not_called()
    col.new_note.assert_not_called()
    col.models.add_field.assert_not_called()
    col.models.update_dict.assert_not_called()
    col.decks.add_normal_deck_with_name.assert_not_called()
    col.media.add_file.assert_not_called()
    assert not (root / "user_files").exists()


def test_repeated_capture_warns_without_creating_and_can_be_explicitly_duplicated(capture_env):
    col, _, root = capture_env
    first = bridge._create_browser_capture_note_on_main(payload())
    duplicate = bridge._create_browser_capture_note_on_main(payload(title="Renamed title"))
    assert duplicate["duplicate"] is True
    assert duplicate["noteId"] == first["noteId"]
    assert col.add_note.call_count == 1
    second = bridge._create_browser_capture_note_on_main(payload(allowDuplicate=True))
    assert second["noteId"] != first["noteId"]
    assert col.add_note.call_count == 2
    conn = db.get_connection(str(root), "CaptureProfile")
    assert conn.execute("SELECT state FROM import_journal").fetchall() == [("committed",), ("committed",)]


def test_deleted_capture_is_not_reported_as_duplicate(capture_env):
    _, cards, _ = capture_env
    bridge._create_browser_capture_note_on_main(payload())
    cards.clear()
    assert bridge._create_browser_capture_note_on_main(payload())["ok"] is True


def test_legacy_capture_is_detected_without_a_new_identity_registry(capture_env):
    col, cards, root = capture_env
    note = {"Front": "A passage<br><br>https://example.com/article", "Back": "Old title",
            "Incremento_Source_Link": "https://example.com/article",
            "Incremento_Source_Type": "Browser Capture", "Incremento_Source_Title": "Old title"}
    col.find_notes.return_value = [77]
    col.get_note.return_value = note
    cards[177] = SimpleNamespace(id=177, nid=77)
    result = bridge._create_browser_capture_note_on_main(payload())
    assert result["duplicate"] is True
    assert result["noteId"] == 77
    col.add_note.assert_not_called()
    assert not (root / "user_files").exists()


def test_legacy_capture_of_a_longer_passage_is_not_a_duplicate(capture_env):
    col, _, _ = capture_env
    col.find_notes.return_value = [77]
    col.get_note.return_value = {"Front": "A passage with more context",
        "Incremento_Source_Link": "https://example.com/article",
        "Incremento_Source_Type": "Browser Capture", "Incremento_Source_Title": "Old title"}
    assert bridge._create_browser_capture_note_on_main(payload()).get("duplicate") is not True


def test_rejected_note_rolls_back_journal_and_does_not_register_capture(capture_env):
    col, _, root = capture_env
    col.add_note.side_effect = RuntimeError("Synthetic failure")
    with pytest.raises(RuntimeError, match="Synthetic"):
        bridge._create_browser_capture_note_on_main(payload())
    conn = db.get_connection(str(root), "CaptureProfile")
    assert conn.execute("SELECT state FROM import_journal").fetchall() == [("rolled_back",)]
    assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone() == (0,)


def test_failure_after_note_creation_keeps_identity_so_retry_cannot_duplicate_it(capture_env, monkeypatch):
    col, cards, root = capture_env
    priority = sys.modules["priority_manager"]
    monkeypatch.setattr(priority, "set_priority", MagicMock(side_effect=RuntimeError("Synthetic priority failure")))
    with pytest.raises(RuntimeError, match="priority"):
        bridge._create_browser_capture_note_on_main(payload())
    assert len(cards) == 1
    result = bridge._create_browser_capture_note_on_main(payload())
    assert result["duplicate"] is True
    assert col.add_note.call_count == 1


def test_capture_without_metadata_fields_still_saves_clickable_mapped_source_and_leaves_model_alone(capture_env):
    col, _, _ = capture_env
    result = bridge._create_browser_capture_note_on_main(payload())
    assert result["ok"]
    col.models.add_field.assert_not_called()
    col.models.update_dict.assert_not_called()


def test_non_png_snapshot_is_rejected_before_preview_or_media_write():
    import base64

    with pytest.raises(ValueError, match="PNG"):
        payload(action="preview", snapshots=[{"mimeType": "image/png", "base64": base64.b64encode(b"<svg>not PNG</svg>").decode()}])


def test_combined_snapshot_budget_is_enforced_at_backend_boundary(monkeypatch):
    import base64

    png = b"\x89PNG\r\n\x1a\nfake"
    image = {"mimeType": "image/png", "base64": base64.b64encode(png).decode()}
    monkeypatch.setattr(bridge, "_MAX_BROWSER_CAPTURE_TOTAL_IMAGE_BYTES", len(png) * 2, raising=False)
    assert len(payload(action="preview", snapshots=[image, image])["snapshots"]) == 2
    monkeypatch.setattr(bridge, "_MAX_BROWSER_CAPTURE_TOTAL_IMAGE_BYTES", len(png) * 2 - 1)
    with pytest.raises(ValueError, match="Combined"):
        payload(action="preview", snapshots=[image, image])


def test_open_existing_requires_a_live_matching_capture_and_only_runs_explicit_action(capture_env, monkeypatch):
    col, _, _ = capture_env
    opened = []
    monkeypatch.setattr(bridge, "_browser_capture_open_note", opened.append, raising=False)
    first = bridge._create_browser_capture_note_on_main(payload())
    assert opened == []
    result = bridge._create_browser_capture_note_on_main(payload(action="open_existing"))
    assert result["opened"] is True
    assert opened == [first["noteId"]]
    assert col.add_note.call_count == 1


def test_stale_profile_capture_fails_before_any_collection_write(capture_env, monkeypatch):
    col, _, _ = capture_env
    monkeypatch.setattr(bridge, "_bridge_token", "session")
    token = bridge._browser_capture_meta_on_main()["profileToken"]
    monkeypatch.setattr(paths, "get_active_profile", lambda: "AnotherProfile")
    with pytest.raises(ValueError, match="profile changed"):
        bridge._create_browser_capture_note_on_main(payload(profileToken=token))
    col.add_note.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"selectedHtml": "x" * 200_001}, {"selectedText": "x" * 200_001},
    {"sourceText": "x" * 200_001}, {"action": "delete"},
    {"allowDuplicate": "true"}, {"linkToPassage": "false"},
])
def test_capture_rejects_invalid_or_oversized_payloads(overrides):
    with pytest.raises(ValueError):
        payload(**overrides)
