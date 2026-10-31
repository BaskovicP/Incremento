"""Disposable cover pixels: bounded, atomic, isolated, and safe to discard."""

import importlib
import os
from pathlib import Path

import pytest


def cache_module():
    return importlib.import_module("bookshelf_cover_cache")


@pytest.mark.parametrize("portable", [False, True], ids=["directory-fd", "portable-paths"])
def test_pixels_survive_module_reload_and_are_isolated_by_profile(tmp_path, monkeypatch, portable):
    cache = cache_module()
    if portable:
        monkeypatch.setattr(cache, "_FD", False)
    pixels = b"\xff\x00\x00\xff" * 6
    assert cache.write(str(tmp_path), "A", ("source", 1), 2, 3, pixels)
    cache = importlib.reload(cache)
    if portable:
        monkeypatch.setattr(cache, "_FD", False)
    assert cache.read(str(tmp_path), "A", ("source", 1)) == (2, 3, pixels)
    assert cache.read(str(tmp_path), "A", ("source", 2)) is None
    assert cache.read(str(tmp_path), "B", ("source", 1)) is None
    assert not (tmp_path / "user_files" / "B").exists()
    if os.name != "nt":
        root = tmp_path / "user_files" / "A" / "bookshelf_cover_cache"
        assert root.stat().st_mode & 0o777 == 0o700
        assert next(root.glob("*.rgba")).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("width,height,pixels", [(0, 1, b""), (161, 1, b"x" * 644),
    (1, 321, b"x" * 1284), (2, 3, b"too short")])
def test_invalid_pixel_shapes_do_not_create_cache_files(tmp_path, width, height, pixels):
    assert not cache_module().write(str(tmp_path), "A", (1,), width, height, pixels)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("damage", ["truncated", "checksum", "dimensions", "oversized", "symlink"])
def test_damaged_or_unsafe_cache_entries_are_misses(tmp_path, damage):
    cache = cache_module()
    assert cache.write(str(tmp_path), "A", (1,), 1, 2, b"rgba" * 2)
    target = next((tmp_path / "user_files" / "A" / "bookshelf_cover_cache").glob("*.rgba"))
    outside = tmp_path / "outside"
    original = target.read_bytes()
    if damage == "truncated":
        target.write_bytes(original[:8])
    elif damage == "checksum":
        target.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    elif damage == "dimensions":
        magic, _width, _height, checksum = cache.HEADER.unpack(original[:cache.HEADER.size])
        target.write_bytes(cache.HEADER.pack(magic, 2, 1, checksum) + original[cache.HEADER.size:])
    elif damage == "oversized":
        target.write_bytes(b"x" * (cache.MAX_ENTRY_BYTES + 1))
    else:
        outside.write_bytes(original)
        target.unlink()
        target.symlink_to(outside)
    assert cache.read(str(tmp_path), "A", (1,)) is None
    if damage == "symlink":
        assert not cache.write(str(tmp_path), "A", (1,), 1, 1, b"new!")
        assert outside.read_bytes() == original


@pytest.mark.parametrize("component", ["user_files", "profile", "cache"])
def test_cache_never_follows_storage_directory_symlinks(tmp_path, component):
    cache = cache_module()
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "user_files" / "A" / "bookshelf_cover_cache"
    target = {"user_files": root.parent.parent, "profile": root.parent, "cache": root}[component]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    assert cache.read(str(tmp_path), "A", (1,)) is None
    assert not cache.write(str(tmp_path), "A", (1,), 1, 1, b"rgba")
    assert list(outside.iterdir()) == []


def test_failed_publish_preserves_previous_pixels_and_cleans_staging(tmp_path, monkeypatch):
    cache = cache_module()
    assert cache.write(str(tmp_path), "A", (1,), 1, 1, b"old!")
    def fail(*args, **kwargs):
        raise OSError("synthetic full disk")
    monkeypatch.setattr(cache.os, "replace", fail)
    assert not cache.write(str(tmp_path), "A", (1,), 1, 1, b"new!")
    assert cache.read(str(tmp_path), "A", (1,)) == (1, 1, b"old!")
    root = tmp_path / "user_files" / "A" / "bookshelf_cover_cache"
    assert len(list(root.iterdir())) == 1


def test_pruning_obeys_byte_and_file_limits_and_keeps_recently_read_entries(tmp_path, monkeypatch):
    cache = cache_module()
    monkeypatch.setattr(cache, "MAX_FILES", 2)
    monkeypatch.setattr(cache, "MAX_DISK_BYTES", 2 * cache.HEADER.size + 8)
    assert cache.write(str(tmp_path), "A", (1,), 1, 1, b"one!")
    first = next((tmp_path / "user_files" / "A" / "bookshelf_cover_cache").glob("*.rgba"))
    os.utime(first, ns=(1, 1))
    assert cache.write(str(tmp_path), "A", (2,), 1, 1, b"two!")
    second = next(path for path in first.parent.glob("*.rgba") if path != first)
    os.utime(second, ns=(2, 2))
    assert cache.read(str(tmp_path), "A", (1,)) == (1, 1, b"one!")
    unrelated = first.parent / "unrelated.txt"
    unrelated.write_text("keep")
    assert cache.write(str(tmp_path), "A", (3,), 1, 1, b"tri!")
    assert cache.read(str(tmp_path), "A", (2,)) is None
    assert cache.read(str(tmp_path), "A", (1,)) is not None
    assert unrelated.read_text() == "keep"
    assert sum(p.stat().st_size for p in first.parent.glob("*.rgba")) <= cache.MAX_DISK_BYTES


def test_cache_directory_is_profile_scoped_and_excluded_from_backups(tmp_path):
    import paths
    import export_bundle
    root = paths.get_bookshelf_cover_cache_dir(str(tmp_path), "A")
    assert root == tmp_path / "user_files" / "A" / "bookshelf_cover_cache"
    root.mkdir(parents=True)
    (root / "preview.rgba").write_bytes(b"disposable pixels")
    (root.parent / "book.pdf").write_bytes(b"user document")
    destination = tmp_path / "backup"
    export_bundle.snapshot_tree(str(root.parent), str(destination))
    assert sorted(p.name for p in destination.iterdir()) == ["book.pdf"]


def test_backup_exclusion_does_not_match_a_user_content_subfolder_with_the_same_name():
    import export_bundle
    assert export_bundle.should_skip_user_file("bookshelf_cover_cache/preview.rgba")
    assert not export_bundle.should_skip_user_file("files/bookshelf_cover_cache/keep.txt")
