"""Contracts for opt-in profile-scoped full-backup scheduling and rotation."""

import os
import zipfile

import pytest

from backend import backup_schedule


def test_normalize_policy_disables_invalid_destination_and_bounds_retention():
    policy = backup_schedule.normalize_policy({
        "enabled": True, "directory": "bad\x00folder", "on_open": True,
        "interval_hours": -10, "versions": 1000,
    })
    assert policy == {
        "enabled": False, "directory": "", "on_open": True, "on_close": False,
        "interval_hours": 0, "versions": 20, "last_success": 0.0,
        "last_close_failed": False,
    }


def test_new_automatic_backup_policy_defaults_to_five_versions():
    assert backup_schedule.normalize_policy({})["versions"] == 5


def test_due_on_open_and_interval_use_only_successful_backup_time():
    policy = backup_schedule.normalize_policy({
        "enabled": True, "directory": "/backup", "on_open": True,
        "interval_hours": 2, "last_success": 1000,
    })
    assert backup_schedule.is_due(policy, "open", 1001)
    assert not backup_schedule.is_due(policy, "interval", 8199)
    assert backup_schedule.is_due(policy, "interval", 8200)
    assert not backup_schedule.is_due(policy, "close", 1001)


def test_close_trigger_runs_only_when_explicitly_enabled():
    policy = backup_schedule.normalize_policy({
        "enabled": True, "directory": "/backup", "on_close": True,
    })
    assert policy["on_close"] is True
    assert backup_schedule.is_due(policy, "close", 1000)
    assert not backup_schedule.is_due(policy, "open", 1000)


def test_close_failure_marker_is_boolean_and_profile_policy_local():
    assert backup_schedule.normalize_policy({"last_close_failed": True})["last_close_failed"] is True
    assert backup_schedule.normalize_policy({"last_close_failed": "true"})["last_close_failed"] is False


def test_destination_rejects_profile_tree_including_symlink_alias(tmp_path):
    profile = tmp_path / "addon" / "user_files" / "P"
    profile.mkdir(parents=True)
    (profile / "backups").mkdir()
    with pytest.raises(ValueError, match="profile"):
        backup_schedule.validate_destination(str(profile / "backups"), profile)
    alias = tmp_path / "alias"
    alias.symlink_to(profile, target_is_directory=True)
    with pytest.raises(ValueError, match="profile"):
        backup_schedule.validate_destination(str(alias), profile)
    other_profile = profile.parent / "Other" / "backups"
    other_profile.mkdir(parents=True)
    with pytest.raises(ValueError, match="profile"):
        backup_schedule.validate_destination(str(other_profile), profile)
    assert backup_schedule.validate_destination(str(tmp_path), profile) == tmp_path


def test_rotation_only_removes_owned_older_zips_after_success(tmp_path):
    profile = "P"
    names = [backup_schedule.backup_filename(profile, t) for t in (1, 2, 3)]
    for name in names:
        with zipfile.ZipFile(tmp_path / name, "w") as zf:
            zf.writestr("restore.txt", "ok")
    (tmp_path / "incremento_P_full_backup_2026-01-01.zip").write_text("manual")
    (tmp_path / "incremento_P_auto_backup_bad.zip").write_text("other")
    (tmp_path / backup_schedule.backup_filename("Another", 1)).write_text("other")
    removed = backup_schedule.prune_backups(tmp_path, profile, 2)
    assert removed == [tmp_path / names[0]]
    assert set(p.name for p in tmp_path.iterdir()) == set(names[1:]) | {
        "incremento_P_full_backup_2026-01-01.zip",
        "incremento_P_auto_backup_bad.zip",
        backup_schedule.backup_filename("Another", 1),
    }


def test_rotation_keeps_just_verified_archive_when_clock_moved_back(tmp_path):
    names = [backup_schedule.backup_filename("P", t) for t in (10, 20, 30)]
    for name in names:
        (tmp_path / name).write_bytes(b"zip")
    removed = backup_schedule.prune_backups(
        tmp_path, "P", 2, protected=tmp_path / names[0]
    )
    assert removed == [tmp_path / names[1]]
    assert (tmp_path / names[0]).exists()
    assert (tmp_path / names[2]).exists()


def test_rotation_keeps_selected_five_versions_after_sixth_success(tmp_path):
    names = [backup_schedule.backup_filename("P", t) for t in range(1, 7)]
    for name in names:
        (tmp_path / name).write_bytes(b"zip")
    manual = tmp_path / "incremento_P_full_backup_manual.zip"
    manual.write_bytes(b"manual")
    other = tmp_path / backup_schedule.backup_filename("Q", 1)
    other.write_bytes(b"other")

    removed = backup_schedule.prune_backups(
        tmp_path, "P", 5, protected=tmp_path / names[-1]
    )

    assert removed == [tmp_path / names[0]]
    assert {path.name for path in tmp_path.iterdir()} == set(names[1:]) | {
        manual.name, other.name,
    }


@pytest.mark.parametrize("keep", [1, 5])
def test_slot_target_fills_selected_count_then_reuses_oldest_path(
    tmp_path, keep,
):
    slots = []
    for number in range(1, keep + 1):
        target = backup_schedule.next_backup_path(tmp_path, "P", keep)
        assert target.name == f"incremento_P_auto_backup_slot_{number:02d}.zip"
        target.write_bytes(f"verified backup {number}".encode())
        timestamp = number * 1_000_000_000
        os.utime(target, ns=(timestamp, timestamp))
        slots.append(target)

    target = backup_schedule.next_backup_path(tmp_path, "P", keep)
    assert target == slots[0]
    assert target.read_bytes() == b"verified backup 1"

    staged = tmp_path / ".staged.zip"
    staged.write_bytes(b"new verified backup")
    os.replace(staged, target)
    assert target.read_bytes() == b"new verified backup"
    assert not staged.exists()
    for number, other in enumerate(slots[1:], start=2):
        assert other.read_bytes() == f"verified backup {number}".encode()
    assert backup_schedule.prune_backups(tmp_path, "P", keep, protected=target) == []
    assert len(list(tmp_path.glob("*.zip"))) == keep
    assert backup_schedule.next_backup_path(tmp_path, "P", keep) == slots[
        1 if keep > 1 else 0
    ]


def test_existing_legacy_backups_are_reused_before_creating_more_files(tmp_path):
    legacy = [backup_schedule.backup_filename("P", t) for t in range(1, 5)]
    for index, name in enumerate(legacy, start=1):
        (tmp_path / name).write_bytes(b"old")
        os.utime(tmp_path / name, ns=(index * 1_000_000_000,) * 2)

    target = backup_schedule.next_backup_path(tmp_path, "P", 3)
    assert target == tmp_path / legacy[0]
    staged = tmp_path / ".staged.zip"
    staged.write_bytes(b"new verified backup")
    os.replace(staged, target)
    removed = backup_schedule.prune_backups(tmp_path, "P", 3, protected=target)

    assert removed == [tmp_path / legacy[1]]
    assert {path.name for path in tmp_path.glob("*.zip")} == {
        legacy[0], legacy[2], legacy[3],
    }


def test_reusable_backup_slot_rejects_symlink_without_touching_target(tmp_path):
    outside = tmp_path / "user-document.zip"
    outside.write_bytes(b"user content")
    slot = tmp_path / "incremento_P_auto_backup_slot_01.zip"
    slot.symlink_to(outside)

    with pytest.raises(ValueError, match="regular file"):
        backup_schedule.next_backup_path(tmp_path, "P", 1)

    assert outside.read_bytes() == b"user content"
    assert slot.is_symlink()


def test_legacy_backup_names_rotate_in_place_without_new_slot_uploads(tmp_path):
    legacy = [
        backup_schedule.backup_filename("P", 4_102_444_800 + offset)
        for offset in range(3)
    ]
    for index, name in enumerate(legacy, start=1):
        (tmp_path / name).write_bytes(b"legacy")
        os.utime(tmp_path / name, ns=(index * 1_000_000_000,) * 2)

    for number in range(1, 4):
        target = backup_schedule.next_backup_path(tmp_path, "P", 3)
        staged = tmp_path / f".staged-{number}.zip"
        staged.write_bytes(f"new {number}".encode())
        os.replace(staged, target)
        backup_schedule.prune_backups(tmp_path, "P", 3, protected=target)

    assert {path.name for path in tmp_path.glob("*.zip")} == set(legacy)
    assert {path.read_bytes() for path in tmp_path.glob("*.zip")} == {
        b"new 1", b"new 2", b"new 3",
    }


def test_automatic_backup_stages_outside_destination_on_same_volume(tmp_path):
    destination = tmp_path / "synced"
    system_temp = tmp_path / "system-temp"
    destination.mkdir()
    system_temp.mkdir()

    selected = backup_schedule.backup_staging_directory(
        destination, automatic=True, system_temp=system_temp,
    )

    assert selected == system_temp.resolve()


def test_manual_backup_stages_in_selected_destination(tmp_path):
    destination = tmp_path / "manual"
    system_temp = tmp_path / "system-temp"
    destination.mkdir()
    system_temp.mkdir()

    selected = backup_schedule.backup_staging_directory(
        destination, automatic=False, system_temp=system_temp,
    )

    assert selected == destination
