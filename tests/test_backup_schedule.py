"""Contracts for opt-in profile-scoped full-backup scheduling and rotation."""

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
