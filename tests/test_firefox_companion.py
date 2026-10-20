"""Local Firefox build keeps the Chrome source and permission boundaries intact."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def builder():
    spec = importlib.util.spec_from_file_location("prepare_firefox", ROOT / "scripts/prepare_firefox_companion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_local_firefox_build_has_working_entry_points_and_no_private_inputs(tmp_path):
    source = ROOT / "chrome_extensions/incremento_companion"
    before = (source / "manifest.json").read_bytes()
    destination = tmp_path / "firefox"
    builder().prepare(source, destination)
    manifest = json.loads((destination / "manifest.json").read_text())
    chrome = json.loads(before)
    assert manifest["background"] == {"scripts": ["dist/background.js"], "type": "module"}
    assert manifest["permissions"] == [p for p in chrome["permissions"] if p != "offscreen"]
    assert set(manifest["host_permissions"]) == {
        "*://*.youtube.com/*", "*://*.youtu.be/*", "*://*.vimeo.com/*", "http://127.0.0.1/*"}
    assert manifest["optional_host_permissions"] == chrome["optional_host_permissions"]
    assert manifest["content_scripts"] == chrome["content_scripts"]
    assert all("global" not in command for command in manifest["commands"].values())
    assert manifest["browser_specific_settings"]["gecko"]["strict_min_version"] == "140.0"
    for name in ("dist/background.js", "dist/content.js", "popup.html", "bookmarks.html",
                 "content-loader.js", "firefox-help.html", "icons/icon-128.png", "_locales/en/messages.json"):
        assert (destination / name).is_file()
    assert (destination / "dist/background.js").read_bytes() == (source / "dist/background.js").read_bytes()
    assert not any(p.name in {"src", "tests", "node_modules", "user_files", "package.json"} or p.suffix == ".map"
                   for p in destination.rglob("*"))
    assert (source / "manifest.json").read_bytes() == before


def test_build_refuses_to_overwrite_existing_files(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    keep = destination / "important.txt"
    keep.write_text("keep me")
    with pytest.raises(FileExistsError):
        builder().prepare(ROOT / "chrome_extensions/incremento_companion", destination)
    assert keep.read_text() == "keep me"


def test_build_rejects_symlinked_runtime_inputs_without_leaking_content(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    secret = tmp_path / "secret"
    secret.write_text("private")
    (source / "manifest.json").symlink_to(secret)
    destination = tmp_path / "output"
    with pytest.raises(ValueError, match="symlink"):
        builder().prepare(source, destination)
    assert not destination.exists()


def test_export_produces_a_loadable_private_data_free_xpi_without_changing_chrome(tmp_path):
    import companion_install
    from zipfile import ZipFile
    source = ROOT / "chrome_extensions/incremento_companion"
    original = (source / "manifest.json").read_bytes()
    target = tmp_path / "companion.xpi"
    companion_install.export_firefox(source, target)
    with ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["background"]["scripts"] == ["dist/background.js"]
        assert "LICENSE" in archive.namelist()
        assert archive.read("dist/background.js") == (source / "dist/background.js").read_bytes()
        assert not any(name.startswith(("user_files/", "src/", "tests/")) for name in archive.namelist())
    assert (source / "manifest.json").read_bytes() == original
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        companion_install.export_firefox(source, target)
    assert target.read_bytes() == before


def test_export_rejects_runtime_data_destination_and_symlink_without_changes(tmp_path, monkeypatch):
    import companion_install
    monkeypatch.setattr(companion_install, "ROOT", tmp_path)
    private = tmp_path / "user_files"
    private.mkdir()
    with pytest.raises(ValueError):
        companion_install.export_firefox(ROOT / "chrome_extensions/incremento_companion", private / "test.xpi")
    assert not list(private.iterdir())
    original = tmp_path / "keep.xpi"
    original.write_bytes(b"keep")
    link = tmp_path / "link.xpi"
    link.symlink_to(original)
    with pytest.raises(FileExistsError):
        companion_install.export_firefox(ROOT / "chrome_extensions/incremento_companion", link)
    assert original.read_bytes() == b"keep"


def test_folder_build_rejects_runtime_data_destination_before_writing(tmp_path, monkeypatch):
    import companion_install
    monkeypatch.setattr(companion_install, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="runtime user data"):
        companion_install.prepare(ROOT / "chrome_extensions/incremento_companion", tmp_path / "user_files" / "extension")
    assert not (tmp_path / "user_files").exists()


def test_failed_export_removes_partial_archive_and_preserves_existing_files(tmp_path, monkeypatch):
    import companion_install
    from zipfile import ZipFile
    original = tmp_path / "keep.txt"
    original.write_text("keep")
    def fail_write(*_args):
        raise OSError("Synthetic disk failure")
    monkeypatch.setattr(ZipFile, "write", fail_write)
    with pytest.raises(OSError, match="Synthetic"):
        companion_install.export_firefox(ROOT / "chrome_extensions/incremento_companion", tmp_path / "extension.xpi")
    assert list(tmp_path.iterdir()) == [original]
    assert original.read_text() == "keep"
