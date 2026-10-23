import json
import os
from pathlib import Path
import stat

import pytest

import simpletex_credentials as credentials
from paths import get_simpletex_credentials_path


def test_saved_credentials_survive_reload_and_stay_in_the_selected_profile(tmp_path):
    credentials.save_credentials(str(tmp_path), "A", ("personal-app", "private-secret"))
    assert credentials.load_credentials(str(tmp_path), "A") == ("personal-app", "private-secret")
    assert credentials.load_credentials(str(tmp_path), "B") == ("", "")
    path = get_simpletex_credentials_path(str(tmp_path), "A")
    assert path == tmp_path / "user_files" / "A" / "simpletex_credentials.json"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    credentials.save_credentials(str(tmp_path), "A", ("", ""))
    assert credentials.load_credentials(str(tmp_path), "A") == ("", "")
    assert not path.exists()


@pytest.mark.parametrize("values", [("app", ""), ("", "secret"), ("bad\napp", "secret"), ("app", "x" * 513)])
def test_invalid_edits_preserve_the_previously_saved_credentials(tmp_path, values):
    credentials.save_credentials(str(tmp_path), "A", ("app", "secret"))
    with pytest.raises(ValueError):
        credentials.save_credentials(str(tmp_path), "A", values)
    assert credentials.load_credentials(str(tmp_path), "A") == ("app", "secret")


@pytest.mark.parametrize("body", [b"[]", b"broken", b"\xff", b"x" * 4097,
    b'{"version":2,"app_id":"app","app_secret":"secret"}',
    b'{"version":1,"app_id":"app","app_secret":""}'], ids=["array", "json", "utf8", "size", "future", "partial"])
def test_damaged_or_future_credential_files_fail_closed(tmp_path, body):
    path = get_simpletex_credentials_path(str(tmp_path), "A")
    path.parent.mkdir(parents=True)
    path.write_bytes(body)
    assert credentials.load_credentials(str(tmp_path), "A") == ("", "")


@pytest.mark.parametrize("part", ["user_files", "profile", "file"])
def test_symlinks_cannot_read_or_replace_outside_credentials(tmp_path, part):
    outside = tmp_path / "outside"
    outside.mkdir()
    original = b'{"version":1,"app_id":"outside-app","app_secret":"outside-secret"}'
    victim = outside / "simpletex_credentials.json"
    victim.write_bytes(original)
    path = get_simpletex_credentials_path(str(tmp_path), "A")
    if part == "user_files":
        (tmp_path / "user_files").symlink_to(outside, target_is_directory=True)
    elif part == "profile":
        path.parent.parent.mkdir()
        path.parent.symlink_to(outside, target_is_directory=True)
    else:
        path.parent.mkdir(parents=True)
        path.symlink_to(victim)
    assert credentials.load_credentials(str(tmp_path), "A") == ("", "")
    with pytest.raises(ValueError):
        credentials.save_credentials(str(tmp_path), "A", ("app", "secret"))
    assert victim.read_bytes() == original


def test_failed_atomic_replace_keeps_old_credentials_and_removes_the_temporary_file(tmp_path, monkeypatch):
    credentials.save_credentials(str(tmp_path), "A", ("app", "old-secret"))
    def fail(*args, **kwargs):
        raise OSError("synthetic failure")
    monkeypatch.setattr(credentials.os, "replace", fail)
    with pytest.raises(ValueError):
        credentials.save_credentials(str(tmp_path), "A", ("app", "new-secret"))
    assert credentials.load_credentials(str(tmp_path), "A") == ("app", "old-secret")
    assert [p.name for p in get_simpletex_credentials_path(str(tmp_path), "A").parent.iterdir()] == ["simpletex_credentials.json"]


def test_support_bundle_does_not_contain_saved_credentials(tmp_path):
    import zipfile
    import diagnostics

    credentials.save_credentials(str(tmp_path), 'A', ('personal-app', 'private-secret'))
    recorder = diagnostics.DiagnosticRecorder(str(tmp_path), 'A')
    destination = tmp_path / 'support.zip'
    try:
        diagnostics.build_support_bundle(destination, addon_dir=str(tmp_path), profile='A', recorder=recorder,
            config={}, default_config={}, environment={}, runtime_state={})
        with zipfile.ZipFile(destination) as archive:
            assert not any('simpletex_credentials' in name for name in archive.namelist())
            contents = b'\n'.join(archive.read(name) for name in archive.namelist())
            assert b'private-secret' not in contents
            assert b'personal-app' not in contents
    finally:
        recorder.close()
