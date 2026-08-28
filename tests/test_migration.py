"""Tests for backend/migration.py"""
import os
from pathlib import Path

import pytest

import migration as m


def _make_legacy(root: Path, *names):
    """Create stub legacy items in root/user_files/."""
    uf = root / "user_files"
    uf.mkdir(parents=True, exist_ok=True)
    for name in names:
        item = uf / name
        if name.endswith("/") or "." not in name:
            item.mkdir(exist_ok=True)
            (item / "stub.txt").write_text("data")
        else:
            item.write_text("data")


class TestMigrateToProfileDir:
    def test_moves_db_to_profile_subdir(self, tmp_path):
        _make_legacy(tmp_path, "incremento.db")
        m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        assert (tmp_path / "user_files" / "MyProfile" / "incremento.db").exists()
        assert not (tmp_path / "user_files" / "incremento.db").exists()

    def test_moves_stats_json(self, tmp_path):
        _make_legacy(tmp_path, "custom_learn_stats.json")
        m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        assert (tmp_path / "user_files" / "MyProfile" / "custom_learn_stats.json").exists()

    def test_moves_directories(self, tmp_path):
        _make_legacy(tmp_path, "pdfs", "videos", "writing")
        m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        profile_dir = tmp_path / "user_files" / "MyProfile"
        assert (profile_dir / "pdfs").is_dir()
        assert (profile_dir / "videos").is_dir()
        assert (profile_dir / "writing").is_dir()

    def test_is_idempotent(self, tmp_path):
        _make_legacy(tmp_path, "incremento.db")
        m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        # Second call checks for unfinished items but changes no migrated data.
        report = m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        assert (tmp_path / "user_files" / "MyProfile" / "incremento.db").exists()
        assert report["completed"] is True
        assert report["moved"] == []

    def test_fresh_install_creates_profile_dir(self, tmp_path):
        (tmp_path / "user_files").mkdir()
        m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        assert (tmp_path / "user_files" / "MyProfile").is_dir()

    def test_truly_fresh_install_no_user_files_dir(self, tmp_path):
        """Migration must work even when user_files/ doesn't exist yet."""
        assert not (tmp_path / "user_files").exists()
        m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        assert (tmp_path / "user_files" / "MyProfile").is_dir()

    def test_partial_source_moves_only_existing(self, tmp_path):
        _make_legacy(tmp_path, "incremento.db")
        # pdfs/ does not exist
        m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        profile_dir = tmp_path / "user_files" / "MyProfile"
        assert (profile_dir / "incremento.db").exists()
        assert not (profile_dir / "pdfs").exists()

    def test_sanitizes_profile_name(self, tmp_path):
        _make_legacy(tmp_path, "incremento.db")
        m.migrate_to_profile_dir(str(tmp_path), "My:Profile")
        assert (tmp_path / "user_files" / "My_Profile" / "incremento.db").exists()

    def test_does_not_overwrite_existing_dst(self, tmp_path):
        _make_legacy(tmp_path, "incremento.db")
        profile_dir = tmp_path / "user_files" / "MyProfile"
        profile_dir.mkdir(parents=True)
        existing = profile_dir / "incremento.db"
        existing.write_text("existing")
        # src also exists; dst should not be overwritten
        report = m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        assert existing.read_text() == "existing"
        assert report["completed"] is False
        assert report["conflicts"] == ["incremento.db"]

    def test_resumes_when_profile_directory_already_exists(self, tmp_path):
        profile_dir = tmp_path / "user_files" / "MyProfile"
        profile_dir.mkdir(parents=True)
        (profile_dir / "already-moved.txt").write_text("safe")
        _make_legacy(tmp_path, "custom_learn_stats.json")

        report = m.migrate_to_profile_dir(str(tmp_path), "MyProfile")

        assert report["completed"] is True
        assert (profile_dir / "custom_learn_stats.json").read_text() == "data"
        assert (profile_dir / "already-moved.txt").read_text() == "safe"

    def test_merges_partially_moved_directory_without_overwrite(self, tmp_path):
        legacy_pdfs = tmp_path / "user_files" / "pdfs"
        legacy_pdfs.mkdir(parents=True)
        (legacy_pdfs / "remaining.pdf").write_text("remaining")
        (legacy_pdfs / "conflict.pdf").write_text("legacy")
        profile_pdfs = tmp_path / "user_files" / "MyProfile" / "pdfs"
        profile_pdfs.mkdir(parents=True)
        (profile_pdfs / "moved.pdf").write_text("moved")
        (profile_pdfs / "conflict.pdf").write_text("profile")

        report = m.migrate_to_profile_dir(str(tmp_path), "MyProfile")

        assert (profile_pdfs / "remaining.pdf").read_text() == "remaining"
        assert (profile_pdfs / "moved.pdf").read_text() == "moved"
        assert (profile_pdfs / "conflict.pdf").read_text() == "profile"
        assert (legacy_pdfs / "conflict.pdf").read_text() == "legacy"
        assert report["completed"] is False
        assert report["conflicts"] == ["pdfs/conflict.pdf"]

    def test_writes_atomic_completion_marker(self, tmp_path):
        report = m.migrate_to_profile_dir(str(tmp_path), "MyProfile")
        marker = (
            tmp_path
            / "user_files"
            / "MyProfile"
            / ".incremento_profile_migration.json"
        )

        assert marker.exists()
        assert not marker.with_suffix(marker.suffix + ".tmp").exists()
        assert report["completed"] is True
