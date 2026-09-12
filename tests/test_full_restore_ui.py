from pathlib import Path

from frontend.full_restore import default_backup_folder


def test_restore_picker_starts_in_configured_automatic_backup_folder(tmp_path):
    folder = tmp_path / "automatic"
    folder.mkdir()
    assert default_backup_folder({"directory": str(folder)}, tmp_path) == folder


def test_restore_picker_falls_back_when_automatic_folder_is_unavailable(tmp_path):
    assert default_backup_folder({"directory": str(tmp_path / "missing")}, tmp_path) == tmp_path
