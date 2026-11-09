"""The hub and its client: the exchange over the network, in a channel only a paired device can open.

The channel is TLS with a pre-shared key (the pairing secret): encrypted, forward secret, and mutually authenticated,
with no certificate to create, trust or renew. ``sync_http.Hub`` is a file server over one folder; ``HttpStore`` is
the engine's Store over it. The whole Store contract (tests/test_sync_store.py) runs against it too.
"""

import http.client
import json
import socket
import ssl
import time

import pytest

import db
import sync_http
import sync_service
from sync_http import HttpStore, Hub, Pairing
from sync_store import LocalStore, StoreError

KEY = bytes(range(32))
OTHER_KEY = bytes(reversed(range(32)))


@pytest.fixture
def hub(tmp_path):
    root = tmp_path / "HubFolder"
    root.mkdir()
    server = Hub(root, {"phone": KEY, "laptop": OTHER_KEY}, host="127.0.0.1", port=0)
    server.start()
    yield server
    server.stop()


def _store(hub, identity="phone", key=KEY, **options):
    return HttpStore("127.0.0.1", hub.port, identity, key, **options)


def _raw_context():
    """A client that does not use HttpStore, so it checks nothing the hub should check itself."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.set_ciphers(sync_http.CIPHERS)
    context.set_psk_client_callback(lambda hint: ("phone", KEY))
    return context


def _raw_connection(hub):
    return http.client.HTTPSConnection("127.0.0.1", hub.port, context=_raw_context(), timeout=5)


def test_a_paired_device_writes_and_reads_through_the_hub(hub):
    store = _store(hub)

    store.write("a/b.txt", b"hello")

    assert store.read("a/b.txt", 100) == b"hello"
    assert (hub.root / "a" / "b.txt").read_bytes() == b"hello"


def test_the_channel_is_encrypted_with_a_forward_secret_cipher(hub):
    store = _store(hub)
    store.write("x", b"1")

    assert store.cipher().startswith("ECDHE-PSK")
    assert store.tls_version() == "TLSv1.2"


def test_an_unknown_identity_cannot_connect(hub):
    store = _store(hub, identity="stranger")

    with pytest.raises(StoreError):
        store.write("x", b"1")
    assert not (hub.root / "x").exists()


def test_a_wrong_key_cannot_connect(hub):
    store = _store(hub, key=bytes(32))

    with pytest.raises(StoreError):
        store.read("x", 10)


def test_plain_http_is_not_answered(hub):
    connection = http.client.HTTPConnection("127.0.0.1", hub.port, timeout=5)

    with pytest.raises((OSError, http.client.HTTPException)):
        connection.request("GET", "/v1/list?path=")
        connection.getresponse().read()


def test_a_client_that_only_connects_and_stalls_does_not_block_other_devices(hub):
    stalled = socket.create_connection(("127.0.0.1", hub.port))
    try:
        store = _store(hub)
        store.write("ok", b"fine")
        assert store.read("ok", 10) == b"fine"
    finally:
        stalled.close()


def test_a_garbage_connection_does_not_stop_the_hub(hub):
    junk = socket.create_connection(("127.0.0.1", hub.port))
    junk.sendall(b"\x16\x03\x01garbage" * 10)
    junk.close()

    store = _store(hub)
    store.write("still", b"serving")

    assert store.read("still", 10) == b"serving"


@pytest.mark.parametrize("rel", ["../outside", "a/../../outside", "/etc/passwd", "a//b", "a/./b"])
def test_the_hub_refuses_unsafe_paths_even_from_a_client_that_does_not_check(hub, rel):
    connection = _raw_connection(hub)
    connection.request("PUT", "/v1/file?path=" + rel.replace("/", "%2F"), body=b"x",
                       headers={"Content-Length": "1"})

    assert connection.getresponse().status == 400
    assert not (hub.root.parent / "outside").exists()


def test_an_upload_larger_than_the_hubs_limit_is_refused(hub, monkeypatch):
    monkeypatch.setattr(sync_http, "MAX_BODY_BYTES", 10)
    connection = _raw_connection(hub)
    connection.request("PUT", "/v1/file?path=big", body=b"x" * 11, headers={"Content-Length": "11"})

    assert connection.getresponse().status == 413
    assert not (hub.root / "big").exists()


def test_an_upload_without_a_length_is_refused(hub):
    connection = _raw_connection(hub)
    connection.putrequest("PUT", "/v1/file?path=nolength")
    connection.endheaders()

    assert connection.getresponse().status == 411


def test_a_truncated_upload_leaves_no_file(hub):
    connection = _raw_connection(hub)
    connection.putrequest("PUT", "/v1/file?path=cut")
    connection.putheader("Content-Length", "100")
    connection.endheaders()
    connection.send(b"only a little")
    connection.sock.close()
    time.sleep(0.5)

    assert not (hub.root / "cut").exists()


def test_a_large_file_round_trips_through_upload_and_download(hub, tmp_path):
    store = _store(hub)
    source = tmp_path / "big.bin"
    source.write_bytes(bytes(range(256)) * 40_000)  # about 10 MB

    store.upload(source, "blobs/aa/big")
    store.download("blobs/aa/big", tmp_path / "copy.bin", 20_000_000)

    assert (tmp_path / "copy.bin").read_bytes() == source.read_bytes()


def test_a_download_larger_than_the_limit_is_refused_and_leaves_nothing(hub, tmp_path):
    store = _store(hub)
    store.write("big", b"x" * 1000)

    with pytest.raises(StoreError):
        store.download("big", tmp_path / "copy.bin", 100)
    assert not (tmp_path / "copy.bin").exists()


def test_the_client_reconnects_after_the_hub_restarts(hub):
    store = _store(hub)
    store.write("one", b"1")
    port, root = hub.port, hub.root
    hub.stop()
    again = Hub(root, {"phone": KEY}, host="127.0.0.1", port=port)
    again.start()
    try:
        assert store.read("one", 10) == b"1"
    finally:
        again.stop()
        hub.start()  # so the fixture can stop it


def test_the_listing_is_json_with_names_sizes_and_times(hub):
    _store(hub).write("d/f", b"abc")
    connection = _raw_connection(hub)
    connection.request("GET", "/v1/list?path=d")
    response = connection.getresponse()
    [entry] = json.loads(response.read())

    assert response.status == 200
    assert (entry["name"], entry["dir"], entry["size"]) == ("f", False, 3) and entry["mtime"] > 0


def test_a_python_without_tls_psk_says_so_instead_of_failing_obscurely(hub, monkeypatch):
    monkeypatch.setattr(ssl, "HAS_PSK", False)

    with pytest.raises(StoreError, match="Python 3.13"):
        _store(hub).read("x", 10)
    with pytest.raises(StoreError, match="Python 3.13"):
        Hub(hub.root, {"phone": KEY}, host="127.0.0.1", port=0).start()


def test_a_pairing_code_round_trips_and_rejects_damage():
    pairing = Pairing("192.168.1.20", 8765, "phone", KEY)
    code = pairing.code()
    damaged = code[:-2] + ("AA" if not code.endswith("AA") else "BB")

    assert Pairing.from_code(code) == pairing
    with pytest.raises(ValueError):
        Pairing.from_code(damaged)
    with pytest.raises(ValueError):
        Pairing.from_code("not a code")


def test_a_new_pairing_key_is_32_random_bytes():
    assert len({sync_http.new_key() for _ in range(5)}) == 5
    assert len(sync_http.new_key()) == 32


# --- The engine over the network ---------------------------------------------------------------------------------

def _collection(cards, usn=20):
    import sqlite3

    col = sqlite3.connect(":memory:", check_same_thread=False)
    col.execute("CREATE TABLE col (usn INTEGER, scm INTEGER, mod INTEGER DEFAULT 1)")
    col.execute("INSERT INTO col(usn, scm) VALUES (?, 1000)", (usn,))
    col.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY, guid TEXT)")
    col.execute("CREATE TABLE cards (id INTEGER PRIMARY KEY, nid INTEGER, usn INTEGER)")
    for card_id in cards:
        col.execute("INSERT INTO notes VALUES (?, ?)", (card_id * 10, f"g{card_id}"))
        col.execute("INSERT INTO cards VALUES (?, ?, 5)", (card_id, card_id * 10))
    return lambda sql, *args: col.execute(sql, args).fetchall()


def test_two_devices_sync_priorities_through_the_hub(hub, tmp_path):
    cards = _collection(range(1, 30))
    db.close_connection()
    phone_store, laptop_store = _store(hub), _store(hub, "laptop", OTHER_KEY)
    phone, laptop = str(tmp_path / "phone"), str(tmp_path / "laptop")
    sync_service.configure(phone, "P", "hub:phone", query=cards, store=phone_store)
    sync_service.configure(laptop, "P", "hub:laptop", query=cards, store=laptop_store)

    with db.get_connection(laptop, "P") as conn:
        conn.execute("INSERT INTO priorities(card_id, priority) VALUES (7, 31.0)")
    for addon, store in ((laptop, laptop_store), (phone, phone_store)):
        report = sync_service.sync_now(addon, "P", cards, store=store)
        assert report.problems == [], report.problems

    row = db.get_connection(phone, "P").execute("SELECT priority FROM priorities WHERE card_id=7").fetchone()
    assert row == (31.0,)
    assert LocalStore(hub.root).listdir("IncrementoSync")  # it is on the hub's disk
    db.close_connection()


# --- A paired device can only write its own device folder ---------------------------------------------------------

def _device_file(device, name="000001-000000000001-" + "a" * 64 + ".pack"):
    return f"IncrementoSync/v1/{'1' * 32}/devices/{device}/packs/{name}"


def test_the_first_device_to_write_a_device_folder_owns_it(hub):
    phone, laptop = _store(hub), _store(hub, "laptop", OTHER_KEY)
    phone.write(_device_file("p" * 32), b"phone's pack")

    with pytest.raises(StoreError, match="403"):
        laptop.write(_device_file("p" * 32, "other.pack"), b"tampering")
    with pytest.raises(StoreError, match="403"):
        laptop.delete(_device_file("p" * 32))
    assert phone.read(_device_file("p" * 32), 100) == b"phone's pack"
    laptop.write(_device_file("l" * 32), b"laptop's own pack")  # its own folder is fine
    assert phone.read(_device_file("l" * 32), 100) == b"laptop's own pack"  # everyone may read everything


def test_one_device_can_own_several_device_folders(hub):
    phone = _store(hub)

    phone.write(_device_file("a" * 32), b"1")
    phone.write(_device_file("b" * 32), b"2")  # a restored profile adopts a new device id

    assert phone.read(_device_file("b" * 32), 10) == b"2"


def test_blobs_and_the_library_file_are_shared_by_all_devices(hub):
    phone, laptop = _store(hub), _store(hub, "laptop", OTHER_KEY)
    blob = f"IncrementoSync/v1/{'1' * 32}/blobs/aa/{'a' * 64}"
    library = f"IncrementoSync/v1/{'1' * 32}/library.json"

    phone.write(blob, b"shared")
    phone.write(library, b"{}")
    laptop.write(library, b"{ }")
    laptop.delete(blob)  # any device may clear a blob nobody names any more

    assert phone.read(blob, 10) is None and phone.read(library, 10) == b"{ }"


def test_who_owns_a_device_folder_survives_a_hub_restart(tmp_path):
    root, state = tmp_path / "Hub", tmp_path / "owners.json"
    root.mkdir()
    keys = {"phone": KEY, "laptop": OTHER_KEY}
    first = Hub(root, keys, host="127.0.0.1", port=0, state_path=state)
    first.start()
    HttpStore("127.0.0.1", first.port, "phone", KEY).write(_device_file("p" * 32), b"1")
    first.stop()

    second = Hub(root, keys, host="127.0.0.1", port=0, state_path=state)
    second.start()
    try:
        with pytest.raises(StoreError, match="403"):
            HttpStore("127.0.0.1", second.port, "laptop", OTHER_KEY).write(_device_file("p" * 32, "x.pack"), b"2")
    finally:
        second.stop()


def test_a_refused_write_does_not_leave_the_connection_unusable(hub):
    phone, laptop = _store(hub), _store(hub, "laptop", OTHER_KEY)
    phone.write(_device_file("p" * 32), b"1")

    with pytest.raises(StoreError):
        laptop.write(_device_file("p" * 32, "x.pack"), b"x" * 100_000)  # a body the hub did not read
    laptop.write(_device_file("l" * 32), b"fine afterwards")

    assert laptop.read(_device_file("l" * 32), 100) == b"fine afterwards"


# --- Many connections -----------------------------------------------------------------------------------------------

def test_the_hub_serves_at_most_a_fixed_number_of_connections_at_once(tmp_path):
    root = tmp_path / "Hub"
    root.mkdir()
    server = Hub(root, {"phone": KEY}, host="127.0.0.1", port=0, max_connections=2)
    server.start()
    held = []
    try:
        for _ in range(2):
            store = HttpStore("127.0.0.1", server.port, "phone", KEY, timeout=3)
            store.write("x", b"1")  # connects and keeps the connection open
            held.append(store)
        crowded = HttpStore("127.0.0.1", server.port, "phone", KEY, timeout=3)
        with pytest.raises(StoreError):
            crowded.read("x", 10)

        held[0].close()
        time.sleep(0.5)
        assert HttpStore("127.0.0.1", server.port, "phone", KEY, timeout=3).read("x", 10) == b"1"
    finally:
        for store in held:
            store.close()
        server.stop()
