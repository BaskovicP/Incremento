"""Pairing devices and running a hub: the key book, and scripts/sync_hub.py as a person would use it."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import sync_http
from sync_http import HttpStore, KeyBook, Pairing

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_hub.py"


def test_adding_a_device_gives_it_a_key_that_survives_a_reload(tmp_path):
    book = KeyBook(tmp_path / "keys.json")

    key = book.add("phone")

    assert len(key) == 32
    assert KeyBook(tmp_path / "keys.json").devices() == {"phone": key}


def test_two_devices_get_different_keys_and_a_name_cannot_be_reused(tmp_path):
    book = KeyBook(tmp_path / "keys.json")
    first, second = book.add("phone"), book.add("laptop")

    assert first != second
    with pytest.raises(ValueError, match="already"):
        book.add("phone")


@pytest.mark.parametrize("name", ["", "has space", "slash/name", "x" * 65, "über"])
def test_a_device_name_must_be_simple(tmp_path, name):
    with pytest.raises(ValueError):
        KeyBook(tmp_path / "keys.json").add(name)


def test_revoking_removes_the_key_and_unknown_names_are_reported(tmp_path):
    book = KeyBook(tmp_path / "keys.json")
    book.add("phone")
    book.add("laptop")

    assert book.revoke("phone") is True
    assert book.revoke("phone") is False
    assert list(KeyBook(tmp_path / "keys.json").devices()) == ["laptop"]


def test_a_damaged_key_file_is_an_error_not_an_empty_book(tmp_path):
    path = tmp_path / "keys.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="keys"):
        KeyBook(path).devices()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_the_key_file_is_private_to_its_owner(tmp_path):
    book = KeyBook(tmp_path / "keys.json")
    book.add("phone")

    assert (tmp_path / "keys.json").stat().st_mode & 0o077 == 0


def test_a_running_hub_follows_the_key_book(tmp_path):
    book = KeyBook(tmp_path / "keys.json")
    root = tmp_path / "Hub"
    root.mkdir()
    hub = sync_http.Hub(root, book.as_mapping(), host="127.0.0.1", port=0)
    hub.start()
    try:
        key = book.add("late-device")  # paired while the hub is already serving

        store = HttpStore("127.0.0.1", hub.port, "late-device", key)
        store.write("hello", b"1")
        book.revoke("late-device")
        with pytest.raises(sync_http.StoreError):
            HttpStore("127.0.0.1", hub.port, "late-device", key).read("hello", 10)
    finally:
        hub.stop()


def _run(*args, **options):
    # -S: no site packages, so none of a developer environment's global patches reach the child's ssl module.
    return subprocess.run([sys.executable, "-S", str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          timeout=60, **options)


def test_the_command_pairs_a_device_and_the_code_opens_a_running_hub(tmp_path):
    keys, folder = tmp_path / "keys.json", tmp_path / "Hub"
    folder.mkdir()
    paired = _run("--keys", keys, "pair", "phone", "--host", "127.0.0.1", "--port", "48765")
    assert paired.returncode == 0, paired.stderr
    code = next(line for line in paired.stdout.splitlines() if line.startswith("ihub1-"))
    pairing = Pairing.from_code(code)
    assert (pairing.host, pairing.port, pairing.identity) == ("127.0.0.1", 48765, "phone")

    server = subprocess.Popen([sys.executable, "-S", str(SCRIPT), "--keys", str(keys), "serve", str(folder),
                               "--host", "127.0.0.1", "--port", "48765"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        store = HttpStore.from_pairing(pairing, timeout=5)
        for _ in range(50):  # the hub needs a moment to start listening
            try:
                store.write("proof", b"it works")
                break
            except sync_http.StoreError:
                time.sleep(0.2)
        assert store.read("proof", 100) == b"it works"
        assert (folder / "proof").read_bytes() == b"it works"
        mine = "IncrementoSync/v1/" + "1" * 32 + "/devices/" + "d" * 32 + "/device.json"
        store.write(mine, b"{}")
        assert json.loads((tmp_path / "keys-owners.json").read_text(encoding="utf-8"))["owners"] == {"d" * 32: "phone"}
    finally:
        server.terminate()
        server.communicate(timeout=10)


def test_the_command_lists_and_revokes_devices(tmp_path):
    keys = tmp_path / "keys.json"
    _run("--keys", keys, "pair", "phone", "--host", "10.0.0.2")
    _run("--keys", keys, "pair", "laptop", "--host", "10.0.0.2")

    listed = _run("--keys", keys, "devices")
    revoked = _run("--keys", keys, "revoke", "phone")
    after = _run("--keys", keys, "devices")

    assert sorted(listed.stdout.split()) == ["laptop", "phone"]
    assert revoked.returncode == 0
    assert after.stdout.split() == ["laptop"]
    assert json.loads(keys.read_text(encoding="utf-8"))["devices"].keys() == {"laptop"}


def test_pairing_the_same_name_twice_fails_clearly(tmp_path):
    keys = tmp_path / "keys.json"
    _run("--keys", keys, "pair", "phone", "--host", "10.0.0.2")

    again = _run("--keys", keys, "pair", "phone", "--host", "10.0.0.2")

    assert again.returncode != 0 and "already" in again.stderr
