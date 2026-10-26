from types import SimpleNamespace
from unittest.mock import Mock
import writing_dock


def test_typing_does_not_copy_or_parse_the_whole_document(monkeypatch):
    editor = SimpleNamespace(toPlainText=Mock(side_effect=AssertionError("typing copied document")))
    dock = SimpleNamespace(_editor=editor, _preview_timer=SimpleNamespace(start=Mock()))
    monkeypatch.setattr(writing_dock, "_writing_dock", dock)
    monkeypatch.setattr(writing_dock, "_loading_editor", False)
    monkeypatch.setattr(writing_dock, "_current_writing_relpath", "writing/a.md")
    for name in ("_set_status", "_update_editor_highlights", "_schedule_state_save"):
        monkeypatch.setattr(writing_dock, name, Mock())
    monkeypatch.setattr(writing_dock, "_autosave_timer", SimpleNamespace(start=Mock()))
    writing_dock._on_editor_text_changed()
    dock._preview_timer.start.assert_called_once()
    editor.toPlainText.assert_not_called()


def test_hidden_markdown_preview_does_not_parse(monkeypatch):
    preview = SimpleNamespace(setMarkdown=Mock(), setPlainText=Mock())
    editor = SimpleNamespace(toPlainText=Mock(return_value="long text"))
    monkeypatch.setattr(
        writing_dock, "_writing_dock", SimpleNamespace(_preview=preview, _editor=editor, _preview_visible=False)
    )
    writing_dock._refresh_markdown_preview()
    preview.setMarkdown.assert_not_called()
    editor.toPlainText.assert_not_called()


def test_switching_writing_cards_keeps_unsaved_editor_after_failed_flush(monkeypatch):
    monkeypatch.setattr(writing_dock, "_writing_dock", SimpleNamespace())
    monkeypatch.setattr(writing_dock, "_current_writing_card_id", 7)
    monkeypatch.setattr(writing_dock, "_current_writing_relpath", "writing/old.md")
    monkeypatch.setattr(writing_dock, "_writing_profile", "A")
    monkeypatch.setattr(writing_dock, "_active_profile", lambda: "A")
    monkeypatch.setattr(writing_dock, "_flush_editor_state", lambda: False)
    read = Mock(side_effect=AssertionError("unsaved editor was replaced"))
    monkeypatch.setattr(writing_dock, "read_writing_text", read)
    writing_dock.show_writing_in_dock(8, "Next", "writing/next.md")
    assert writing_dock._current_writing_card_id == 7
    assert writing_dock._current_writing_relpath == "writing/old.md"
    read.assert_not_called()


def test_profile_teardown_invalidates_saved_file_cache(monkeypatch):
    monkeypatch.setattr(writing_dock, "_writing_persisted_state", {"identity": ("A", 7, "writing/a.md"), "text": "old"})
    monkeypatch.setattr(writing_dock, "_writing_profile", None)
    monkeypatch.setattr(writing_dock, "_writing_dock", None)
    monkeypatch.setattr(writing_dock, "_writing_writer", None)
    monkeypatch.setattr(writing_dock, "_autosave_timer", None)
    monkeypatch.setattr(writing_dock, "_state_save_timer", None)
    writing_dock.reset_for_profile_switch()
    assert writing_dock._writing_persisted_state == {}


def test_snapshot_writes_capture_profile_and_skip_unchanged_text(monkeypatch):
    monkeypatch.setattr(writing_dock, "_writing_persisted_state", {})
    write, stats, progress = Mock(), Mock(), Mock()
    monkeypatch.setattr(writing_dock, "write_writing_text", write)
    monkeypatch.setattr(writing_dock, "set_writing_word_stats", stats)
    monkeypatch.setattr(writing_dock, "set_writing_progress", progress)
    monkeypatch.setattr(writing_dock, "_active_profile", lambda: "Other")
    snapshot = (
        "Captured",
        7,
        "writing/a.md",
        "two words",
        {},
        "2026-10-26",
        "2026-10-26",
        0,
        {"cursor_position": 2},
        1,
    )
    assert writing_dock._write_writing_snapshot(snapshot)[0] == 2
    writing_dock._write_writing_snapshot(snapshot)
    write.assert_called_once()
    assert write.call_args.kwargs["profile"] == "Captured"
    stats.assert_called_once()
    assert stats.call_args.args[1] == "Captured"
    progress.assert_called_once()


def test_queued_snapshots_keep_first_baseline_across_midnight(monkeypatch):
    monkeypatch.setattr(writing_dock, "_writing_persisted_state", {})
    for name in ("write_writing_text", "set_writing_word_stats", "set_writing_progress"):
        monkeypatch.setattr(writing_dock, name, Mock())
    snapshot = ("Captured", 7, "writing/a.md", "two words", {}, "2026-10-26", "2026-10-25", 0, {}, 1)
    assert writing_dock._write_writing_snapshot(snapshot) == (2, "2026-10-26", 2)
    newer = (*snapshot[:3], "three new words", *snapshot[4:])
    assert writing_dock._write_writing_snapshot(newer) == (3, "2026-10-26", 2)


def test_unchanged_text_recounts_after_word_count_setting_changes(monkeypatch):
    monkeypatch.setattr(writing_dock, "_writing_persisted_state", {})
    for name in ("write_writing_text", "set_writing_word_stats", "set_writing_progress"):
        monkeypatch.setattr(writing_dock, name, Mock())
    snapshot = ("Captured", 7, "writing/a.md", "Hello --- world", {}, "2026-10-26", "2026-10-26", 0, {}, 1)
    assert writing_dock._write_writing_snapshot(snapshot)[0] == 3
    changed = (*snapshot[:4], {"writing_word_count_mode": "word_like"}, *snapshot[5:])
    assert writing_dock._write_writing_snapshot(changed)[0] == 2
    assert writing_dock.set_writing_word_stats.call_count == 2
    assert writing_dock.write_writing_text.call_count == 1


def test_failed_flush_does_not_offer_backup_restore_over_unsaved_text(monkeypatch):
    monkeypatch.setattr(writing_dock, "_current_writing_card_id", 7)
    monkeypatch.setattr(writing_dock, "_current_writing_relpath", "writing/a.md")
    monkeypatch.setattr(writing_dock, "_flush_editor_state", lambda: False)
    backups = Mock(return_value=[])
    monkeypatch.setattr(writing_dock, "list_writing_backups", backups)
    writing_dock._open_backup_restore_dialog()
    backups.assert_not_called()
