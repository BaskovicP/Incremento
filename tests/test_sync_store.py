"""The storage interface under the exchange folder (design note section 8): one contract, several backends."""

import os

import pytest

import sync_store
from sync_store import LocalStore, MemoryStore, StoreError


@pytest.fixture(params=["local", "memory"])
def store(request, tmp_path):
    if request.param == "local":
        root = tmp_path / "Cloud"
        root.mkdir()
        return LocalStore(root)
    return MemoryStore()


def test_a_written_file_reads_back_and_its_parent_folders_appear(store):
    store.write("a/b/c.txt", b"hello")

    assert store.read("a/b/c.txt", limit=100) == b"hello"
    assert [(e.name, e.is_dir) for e in store.listdir("a")] == [("b", True)]
    assert [(e.name, e.is_dir, e.size) for e in store.listdir("a/b")] == [("c.txt", False, 5)]


def test_overwriting_replaces_the_content_and_leaves_no_temporary_file(store):
    store.write("x/f", b"one")
    store.write("x/f", b"two!")

    assert store.read("x/f", limit=100) == b"two!"
    assert [e.name for e in store.listdir("x")] == ["f"]


def test_a_missing_file_reads_as_none_and_a_missing_folder_lists_as_empty(store):
    assert store.read("nothing/here", limit=10) is None
    assert store.listdir("nothing") == []
    assert store.stat("nothing/here") is None


def test_a_file_larger_than_the_limit_is_refused_not_truncated(store):
    store.write("big", b"x" * 50)

    with pytest.raises(StoreError, match="larger"):
        store.read("big", limit=10)


def test_stat_describes_files_and_folders(store):
    store.write("d/f", b"abc")

    assert store.stat("d/f").size == 3 and not store.stat("d/f").is_dir
    assert store.stat("d").is_dir
    assert store.stat("d/f").mtime > 0


def test_deleting_removes_a_file_and_deleting_a_missing_one_is_fine(store):
    store.write("d/f", b"abc")

    store.delete("d/f")
    store.delete("d/f")

    assert store.read("d/f", limit=10) is None


def test_upload_and_download_round_trip_a_large_file(store, tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(os.urandom(3 * 1024 * 1024 + 17))

    store.upload(source, "blobs/ab/blob")
    target = tmp_path / "downloaded.bin"
    store.download("blobs/ab/blob", target, limit=10 * 1024 * 1024)

    assert target.read_bytes() == source.read_bytes()
    assert store.stat("blobs/ab/blob").size == source.stat().st_size


def test_a_download_over_the_limit_is_refused_and_leaves_nothing_behind(store, tmp_path):
    store.write("f", b"x" * 100)
    target = tmp_path / "out.bin"

    with pytest.raises(StoreError, match="larger"):
        store.download("f", target, limit=10)

    assert not target.exists()


def test_downloading_a_missing_file_fails_without_creating_the_target(store, tmp_path):
    target = tmp_path / "out.bin"

    with pytest.raises(StoreError, match="missing"):
        store.download("not/there", target, limit=10)

    assert not target.exists()


@pytest.mark.parametrize("bad", ["../escape", "a/../../b", "/absolute", "a\\b", "a//b", "a/./b", "x\x00y", ""])
def test_paths_that_could_leave_the_folder_are_refused(store, bad):
    with pytest.raises(StoreError, match="path"):
        store.write(bad, b"x")


def test_the_root_itself_can_be_listed_with_an_empty_path(store):
    store.write("one", b"1")

    assert [e.name for e in store.listdir("")] == ["one"]


# --- LocalStore specifics ----------------------------------------------------------------

def test_a_symlinked_entry_is_reported_and_never_traversed(tmp_path):
    root = tmp_path / "Cloud"
    (root / "devices").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_bytes(b"secret")
    try:
        os.symlink(outside, root / "devices" / "linked", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available to this user")
    store = LocalStore(root)

    [entry] = store.listdir("devices")

    assert entry.name == "linked" and entry.is_symlink
    with pytest.raises(StoreError, match="symlink"):
        store.listdir("devices/linked")
    with pytest.raises(StoreError, match="symlink"):
        store.read("devices/linked/secret", limit=100)
    with pytest.raises(StoreError, match="symlink"):
        store.write("devices/linked/new", b"x")
    assert not (outside / "new").exists()


def test_the_local_store_names_its_temporary_files_so_the_engine_never_mistakes_them_for_packs(tmp_path):
    store = LocalStore(tmp_path)
    store.write("packs/000001-000000000001-" + "a" * 64 + ".pack", b"{}")

    assert all(not name.startswith(".") or name.endswith(".tmp") for name in os.listdir(tmp_path / "packs"))


def test_as_store_accepts_a_folder_or_a_store(tmp_path):
    memory = MemoryStore()

    assert isinstance(sync_store.as_store(tmp_path), LocalStore)
    assert isinstance(sync_store.as_store(str(tmp_path)), LocalStore)
    assert sync_store.as_store(memory) is memory


# --- Windows long paths ---------------------------------------------------------------------------------------------
# The engine's file names are about 190 characters below the user's folder, and a cloud folder is often 70 or more:
# past Windows' 260-character limit unless the path is written in its extended form.

BS = chr(92)
PREFIX = BS * 2 + "?" + BS


def _win(*parts):
    return BS.join(parts)


@pytest.mark.parametrize("given, expected", [
    (_win("C:", "Users", "me", "Cloud"), PREFIX + _win("C:", "Users", "me", "Cloud")),
    ("C:/Users/me/Cloud", PREFIX + _win("C:", "Users", "me", "Cloud")),
    (_win("C:", "Users", "other", "..", "me", "Cloud"), PREFIX + _win("C:", "Users", "me", "Cloud")),
    (BS * 2 + _win("server", "share", "Cloud"), PREFIX + _win("UNC", "server", "share", "Cloud")),
    (PREFIX + _win("C:", "Already", "Extended"), PREFIX + _win("C:", "Already", "Extended")),
    (PREFIX + _win("UNC", "server", "share"), PREFIX + _win("UNC", "server", "share")),
])
def test_a_windows_path_is_written_in_its_extended_form(given, expected):
    from sync_store import extended_windows_path

    assert extended_windows_path(given) == expected


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_a_local_store_on_windows_reaches_files_below_the_260_character_limit(tmp_path):
    root = tmp_path / ("cloud" * 20)
    root.mkdir()
    store = LocalStore(root)
    name = "c" * 12 + "-part0000-" + "d" * 64 + ".snap"
    folder = "IncrementoSync/v1/" + "a" * 32 + "/devices/" + "b" * 32 + "/snapshots"
    rel = folder + "/" + name

    store.write(rel, b"data")

    assert len(str(root)) + len(rel) > 260
    assert store.read(rel, 100) == b"data"
    assert [entry.name for entry in store.listdir(folder)] == [name]
    assert str(store._path(rel)).startswith(PREFIX)
    store.delete(rel)
    assert store.read(rel, 100) is None
