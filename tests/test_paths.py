"""Tests for backend/paths.py"""
import pytest
from pathlib import Path

import paths as p


class TestSanitizeProfileName:
    def test_strips_unsafe_chars(self):
        assert p.sanitize_profile_name("My:Profile") == "My_Profile"

    def test_strips_slash(self):
        assert p.sanitize_profile_name("My/Profile") == "My_Profile"

    def test_strips_backslash(self):
        assert p.sanitize_profile_name("My\\Profile") == "My_Profile"

    def test_strips_quotes(self):
        assert p.sanitize_profile_name('My"Profile') == "My_Profile"

    def test_empty_falls_back_to_default(self):
        assert p.sanitize_profile_name("") == "Default"

    def test_none_equivalent_falls_back(self):
        assert p.sanitize_profile_name("   ") == "Default"

    def test_safe_name_unchanged(self):
        assert p.sanitize_profile_name("MyProfile") == "MyProfile"

    def test_unicode_safe(self):
        assert p.sanitize_profile_name("Paulo") == "Paulo"


class TestActiveProfileRegistry:
    def test_set_and_get(self):
        p.set_active_profile("TestUser")
        assert p.get_active_profile() == "TestUser"

    def test_sanitizes_on_set(self):
        p.set_active_profile("Bad:Name")
        assert p.get_active_profile() == "Bad_Name"

    def test_empty_sets_default(self):
        p.set_active_profile("")
        assert p.get_active_profile() == "Default"


class TestDirectoryHelpers:
    def test_user_files_dir_includes_profile(self, tmp_path):
        result = p.get_user_files_dir(str(tmp_path), "MyProfile")
        assert result == tmp_path / "user_files" / "MyProfile"

    def test_user_files_dir_sanitizes_profile(self, tmp_path):
        result = p.get_user_files_dir(str(tmp_path), "My:Profile")
        assert result == tmp_path / "user_files" / "My_Profile"

    def test_all_dirs_under_user_files(self, tmp_path):
        base = tmp_path / "user_files" / "P"
        assert p.get_db_path(str(tmp_path), "P") == base / "incremento.db"
        assert p.get_stats_path(str(tmp_path), "P") == base / "custom_learn_stats.json"
        assert p.get_diagnostics_dir(str(tmp_path), "P") == base / "diagnostics"
        assert p.get_diagnostic_events_path(str(tmp_path), "P") == base / "diagnostics" / "events.jsonl"
        assert p.get_pdf_dir(str(tmp_path), "P") == base / "pdfs"
        assert p.get_epub_dir(str(tmp_path), "P") == base / "epubs"
        assert p.get_epub_extract_root(str(tmp_path), "P") == base / "epub_extracted"
        assert p.get_videos_dir(str(tmp_path), "P") == base / "videos"
        assert p.get_writing_dir(str(tmp_path), "P") == base / "writing"
        assert p.get_writing_backup_dir(str(tmp_path), "P") == base / "writing_backups"
        assert p.get_local_files_dir(str(tmp_path), "P") == base / "files"
        assert p.get_video_profile_dir(str(tmp_path), "P") == base / "video_profile"
        assert p.get_web_profile_dir(str(tmp_path), "P") == base / "web_profile"

    def test_different_profiles_give_different_dirs(self, tmp_path):
        a = p.get_user_files_dir(str(tmp_path), "Alice")
        b = p.get_user_files_dir(str(tmp_path), "Bob")
        assert a != b
