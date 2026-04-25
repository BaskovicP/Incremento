import os

import writing_manager


def test_write_writing_text_creates_all_backup_slots_on_first_overwrite(tmp_path):
    addon_dir = str(tmp_path)
    relpath = writing_manager.build_writing_relpath("My note", "my-note.md")
    path = writing_manager.ensure_writing_file(addon_dir, relpath, initial_text="old text")

    backups = writing_manager.write_writing_text(
        addon_dir,
        relpath,
        "new text",
        backups_enabled=True,
        now=100.0,
    )

    assert os.path.exists(path)
    assert writing_manager.read_writing_text(addon_dir, relpath) == "new text"
    assert [row["tier_key"] for row in backups] == ["1m", "30m", "1d"]
    for row in backups:
        with open(row["path"], "r", encoding="utf-8") as handle:
            assert handle.read() == "old text"


def test_write_writing_text_only_refreshes_due_backup_slots(tmp_path):
    addon_dir = str(tmp_path)
    relpath = writing_manager.build_writing_relpath("Timed note", "timed.md")
    writing_manager.ensure_writing_file(addon_dir, relpath, initial_text="v0")

    writing_manager.write_writing_text(addon_dir, relpath, "v1", backups_enabled=True, now=100.0)
    writing_manager.write_writing_text(addon_dir, relpath, "v2", backups_enabled=True, now=120.0)
    slots = {row["tier_key"]: row for row in writing_manager.list_writing_backups(addon_dir, relpath)}
    mtimes_after_120 = {key: os.path.getmtime(row["path"]) for key, row in slots.items()}

    writing_manager.write_writing_text(addon_dir, relpath, "v3", backups_enabled=True, now=200.0)
    slots = {row["tier_key"]: row for row in writing_manager.list_writing_backups(addon_dir, relpath)}
    assert os.path.getmtime(slots["1m"]["path"]) == 200.0
    assert os.path.getmtime(slots["30m"]["path"]) == mtimes_after_120["30m"]
    assert os.path.getmtime(slots["1d"]["path"]) == mtimes_after_120["1d"]
    with open(slots["1m"]["path"], "r", encoding="utf-8") as handle:
        assert handle.read() == "v2"

    writing_manager.write_writing_text(addon_dir, relpath, "v4", backups_enabled=True, now=2000.0)
    slots = {row["tier_key"]: row for row in writing_manager.list_writing_backups(addon_dir, relpath)}
    assert os.path.getmtime(slots["1m"]["path"]) == 2000.0
    assert os.path.getmtime(slots["30m"]["path"]) == 2000.0
    assert os.path.getmtime(slots["1d"]["path"]) == mtimes_after_120["1d"]
    with open(slots["30m"]["path"], "r", encoding="utf-8") as handle:
        assert handle.read() == "v3"


def test_write_writing_text_only_creates_selected_backup_slots(tmp_path):
    addon_dir = str(tmp_path)
    relpath = writing_manager.build_writing_relpath("Custom note", "custom.md")
    writing_manager.ensure_writing_file(addon_dir, relpath, initial_text="v0")

    backups = writing_manager.write_writing_text(
        addon_dir,
        relpath,
        "v1",
        backups_enabled=True,
        backup_tiers=("5m", "1h", "7d"),
        now=100.0,
    )

    assert [row["tier_key"] for row in backups] == ["5m", "1h", "7d"]
    for row in backups:
        with open(row["path"], "r", encoding="utf-8") as handle:
            assert handle.read() == "v0"


def test_restore_writing_backup_replaces_live_file(tmp_path):
    addon_dir = str(tmp_path)
    relpath = writing_manager.build_writing_relpath("Restore note", "restore.md")
    writing_manager.ensure_writing_file(addon_dir, relpath, initial_text="before")
    writing_manager.write_writing_text(addon_dir, relpath, "after", backups_enabled=True, now=100.0)

    restored = writing_manager.restore_writing_backup(addon_dir, relpath, "1m")

    assert restored["tier_key"] == "1m"
    assert writing_manager.read_writing_text(addon_dir, relpath) == "before"


def test_list_writing_backups_keeps_disabled_slots_restorable(tmp_path):
    addon_dir = str(tmp_path)
    relpath = writing_manager.build_writing_relpath("Restore disabled", "restore-disabled.md")
    writing_manager.ensure_writing_file(addon_dir, relpath, initial_text="before")
    writing_manager.write_writing_text(
        addon_dir,
        relpath,
        "after",
        backups_enabled=True,
        backup_tiers=("5m",),
        now=100.0,
    )

    listed = writing_manager.list_writing_backups(addon_dir, relpath)

    assert [row["tier_key"] for row in listed] == ["5m"]
    restored = writing_manager.restore_writing_backup(addon_dir, relpath, "5m")
    assert restored["tier_key"] == "5m"
    assert writing_manager.read_writing_text(addon_dir, relpath) == "before"
