"""The exchange over the local network: a hub that serves one folder, and the engine's Store over it.

A hub is a file server over the folder that would otherwise be a cloud folder, so devices without a shared folder (a
phone and a computer on one network) can still sync. It understands no Incremento data: the engine on every device
validates everything it reads, exactly as for a cloud folder, so a hub cannot make a device accept bad data.

The channel is TLS with a pre-shared key, the pairing secret:

* encrypted and forward secret (``ECDHE-PSK-CHACHA20-POLY1305``), and each side proves it holds the key, so a device
  knows it talks to its own hub and the hub knows the device is paired;
* no certificate to create, trust, pin or renew, and no dependency beyond Python's ``ssl`` (3.13 or later);
* one identity and key per paired device, so a lost device is removed by deleting its key.

Wire protocol (all under ``/v1``, the path in the ``path`` query parameter, ``/``-separated and relative)::

    GET    /v1/list?path=<folder>   JSON [{name, dir, size, mtime}]; a missing folder is []
    GET    /v1/stat?path=<rel>      JSON {name, dir, size, mtime}, or 404
    GET    /v1/file?path=<rel>      the bytes, or 404
    PUT    /v1/file?path=<rel>      replace the file atomically; Content-Length required, 204
    DELETE /v1/file?path=<rel>      204, also when there is nothing to delete

The hub refuses unsafe paths, bodies over ``MAX_BODY_BYTES`` and uploads that are cut short, and it never shows a
symbolic link. A paired device can write anywhere in the folder, as it can in a cloud folder; clients check what
they read.
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import http.server
import json
import re
import secrets
import shutil
import socket
import ssl
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

try:
    from .sync_store import Entry, LocalStore, Store, StoreError, as_store, clean
except ImportError:
    from sync_store import Entry, LocalStore, Store, StoreError, as_store, clean  # type: ignore[no-redef]

#: Forward secret, authenticated encryption; the second is for a Python whose OpenSSL lacks ChaCha20.
CIPHERS = "ECDHE-PSK-CHACHA20-POLY1305:PSK-AES256-GCM-SHA384"
MAX_BODY_BYTES = 512 * 1024 * 1024
MAX_LISTING_BYTES = 16 * 1024 * 1024
HANDSHAKE_SECONDS = 10.0
IDLE_SECONDS = 60.0
_IDENTITY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CHUNK = 256 * 1024


def require_psk() -> None:
    """TLS pre-shared keys need Python 3.13's ssl module (Anki 25 and the phone have it)."""
    if not getattr(ssl, "HAS_PSK", False):
        raise StoreError("Syncing over the network needs Python 3.13 or later (TLS pre-shared keys).")


def new_key() -> bytes:
    """A pairing key: 256 random bits."""
    return secrets.token_bytes(32)


@dataclass(frozen=True)
class Pairing:
    """What a device needs to reach a hub, as one string to copy or scan."""

    host: str
    port: int
    identity: str
    key: bytes

    def code(self) -> str:
        payload = json.dumps([1, self.host, self.port, self.identity, self.key.hex()], separators=(",", ":"))
        body = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
        return f"ihub1-{body}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:6]}"

    @classmethod
    def from_code(cls, code: str) -> Pairing:
        try:
            prefix, body, check = code.strip().split("-")
            if prefix != "ihub1":
                raise ValueError
            payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8")
            if hashlib.sha256(payload.encode("utf-8")).hexdigest()[:6] != check:
                raise ValueError
            version, host, port, identity, key = json.loads(payload)
            if (version != 1 or not isinstance(host, str) or not host or not isinstance(port, int)
                    or isinstance(port, bool) or not 0 < port < 65536 or not isinstance(identity, str)
                    or not _IDENTITY.match(identity) or not isinstance(key, str)):
                raise ValueError
            raw = bytes.fromhex(key)
            if len(raw) != 32:
                raise ValueError
        except (ValueError, TypeError, UnicodeError):
            raise ValueError("This is not a valid hub pairing code.") from None
        return cls(host, port, identity, raw)


# --- The paired devices ----------------------------------------------------------------------------------------

class KeyBook:
    """The hub's list of paired devices and their keys, in a file that is not in the folder the hub serves."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def devices(self) -> dict[str, bytes]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as error:
            raise ValueError(f"The hub's keys file {self.path} cannot be read: {error}") from error
        try:
            devices = {str(name): bytes.fromhex(key) for name, key in raw["devices"].items()}
        except (KeyError, AttributeError, TypeError, ValueError) as error:
            raise ValueError(f"The hub's keys file {self.path} is damaged.") from error
        return devices

    def _save(self, devices: Mapping[str, bytes]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps({"version": 1, "devices": {name: key.hex() for name, key in sorted(devices.items())}},
                          indent=2)
        handle, name = tempfile.mkstemp(dir=self.path.parent, prefix=".keys-", suffix=".tmp")
        try:
            with open(handle, "w", encoding="utf-8") as out:  # mkstemp's file is already private to the owner
                out.write(text)
            Path(name).replace(self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def add(self, name: str) -> bytes:
        """Pair a new device: returns its key, which is shown once and never needs to be shown again."""
        if not _IDENTITY.match(name):
            raise ValueError("A device name is 1 to 64 letters, digits, dashes or underscores.")
        devices = self.devices()
        if name in devices:
            raise ValueError(f"A device called {name!r} is already paired.")
        devices[name] = new_key()
        self._save(devices)
        return devices[name]

    def revoke(self, name: str) -> bool:
        devices = self.devices()
        if name not in devices:
            return False
        del devices[name]
        self._save(devices)
        return True

    def as_mapping(self) -> Mapping[str, bytes]:
        """A live view for a running hub: devices paired or revoked later take effect at once."""
        return _LiveKeys(self)


class _LiveKeys(Mapping[str, bytes]):
    def __init__(self, book: KeyBook):
        self._book = book
        self._seen: tuple[float, int] | None = None
        self._devices: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def _current(self) -> dict[str, bytes]:
        with self._lock:
            try:
                info = self._book.path.stat()
                stamp: tuple[float, int] | None = (info.st_mtime, info.st_size)
            except OSError:
                stamp = None
            if stamp != self._seen:
                try:
                    self._devices = self._book.devices()
                except ValueError:
                    self._devices = {}  # a damaged file admits nobody until it is repaired
                self._seen = stamp
            return self._devices

    def __getitem__(self, name: str) -> bytes:
        return self._current()[name]

    def __iter__(self) -> Any:
        return iter(self._current())

    def __len__(self) -> int:
        return len(self._current())


# --- The hub ---------------------------------------------------------------------------------------------------

class _HandshakeFailed(Exception):
    pass


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: _Server

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base class's name
        pass

    def setup(self) -> None:
        # The handshake happens here, in the connection's own thread, so one stalled client cannot hold up the rest.
        sock: ssl.SSLSocket = self.request
        sock.settimeout(HANDSHAKE_SECONDS)
        try:
            sock.do_handshake()
        except (ssl.SSLError, OSError) as error:
            raise _HandshakeFailed from error
        sock.settimeout(IDLE_SECONDS)
        super().setup()

    # -- helpers --

    def _reply(self, status: int, body: bytes = b"", content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _refuse(self, status: int, message: str) -> None:
        # A body we did not read would be taken for the next request.
        self.close_connection = True
        self._reply(status, json.dumps({"error": message}).encode("utf-8"))

    def _target(self) -> tuple[str, str] | None:
        parts = urlsplit(self.path)
        rel = parse_qs(parts.query, keep_blank_values=True).get("path", [""])[0]
        try:
            clean(rel)
        except StoreError:
            self._refuse(400, "unsafe path")
            return None
        return parts.path, rel

    @staticmethod
    def _entry(entry: Entry) -> dict[str, Any]:
        return {"name": entry.name, "dir": entry.is_dir, "size": entry.size, "mtime": entry.mtime}

    # -- methods --

    def do_GET(self) -> None:  # noqa: N802 - the base class's naming
        target = self._target()
        if target is None:
            return
        route, rel = target
        store = self.server.store
        try:
            if route == "/v1/list":
                entries = [self._entry(e) for e in store.listdir(rel) if not e.is_symlink]
                self._reply(200, json.dumps(entries).encode("utf-8"))
            elif route == "/v1/stat":
                found = store.stat(rel)
                if found is None:
                    self._reply(404, b"{}")
                else:
                    self._reply(200, json.dumps(self._entry(found)).encode("utf-8"))
            elif route == "/v1/file":
                self._send_file(rel)
            else:
                self._refuse(404, "unknown route")
        except StoreError as error:
            self._refuse(400, str(error))
        except OSError as error:
            self._refuse(500, str(error))

    def _send_file(self, rel: str) -> None:
        store = self.server.store
        found = store.stat(rel)
        if found is None or found.is_dir:
            self._reply(404, b"{}")
            return
        if found.size > MAX_BODY_BYTES:
            self._refuse(413, "file too large")
            return
        with tempfile.TemporaryDirectory(prefix="incremento-hub-") as spool:
            copy = Path(spool) / "file"
            store.download(rel, copy, MAX_BODY_BYTES)
            size = copy.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(size))
            self.end_headers()
            with copy.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile, _CHUNK)

    def do_PUT(self) -> None:  # noqa: N802
        target = self._target()
        if target is None:
            return
        route, rel = target
        if route != "/v1/file" or not rel:
            self._refuse(400 if route == "/v1/file" else 404, "a file path is required")
            return
        length = self.headers.get("Content-Length")
        if length is None:
            self._refuse(411, "Content-Length required")
            return
        try:
            expected = int(length)
            if expected < 0:
                raise ValueError
        except ValueError:
            self._refuse(400, "bad Content-Length")
            return
        if expected > MAX_BODY_BYTES:
            self._refuse(413, "body too large")
            return
        with tempfile.TemporaryDirectory(prefix="incremento-hub-") as spool:
            received = Path(spool) / "upload"
            remaining = expected
            with received.open("wb") as out:
                while remaining:
                    chunk = self.rfile.read(min(_CHUNK, remaining))
                    if not chunk:  # the client went away part-way: nothing is written
                        self.close_connection = True
                        return
                    out.write(chunk)
                    remaining -= len(chunk)
            try:
                self.server.store.upload(received, rel)
            except StoreError as error:
                self._refuse(400, str(error))
                return
            except OSError as error:
                self._refuse(500, str(error))
                return
        self._reply(204)

    def do_DELETE(self) -> None:  # noqa: N802
        target = self._target()
        if target is None:
            return
        route, rel = target
        if route != "/v1/file" or not rel:
            self._refuse(400 if route == "/v1/file" else 404, "a file path is required")
            return
        try:
            self.server.store.delete(rel)
        except StoreError as error:
            self._refuse(400, str(error))
            return
        except OSError as error:
            self._refuse(500, str(error))
            return
        self._reply(204)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, address: tuple[str, int], store: Store, context: ssl.SSLContext):
        self.store = store
        self.context = context
        super().__init__(address, _Handler)

    def get_request(self) -> tuple[socket.socket, Any]:
        sock, address = super().get_request()
        return self.context.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), address

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # a failed handshake or a dropped connection is not the hub's problem


class Hub:
    """Serve ``root`` to the paired devices in ``keys`` (identity to key)."""

    def __init__(self, root: Path | str, keys: Mapping[str, bytes], *, host: str = "0.0.0.0", port: int = 0):
        if isinstance(keys, dict):
            for identity, key in keys.items():
                if not _IDENTITY.match(identity) or len(key) < 16:
                    raise ValueError(f"unusable pairing for {identity!r}")
        self.root = Path(root)
        self._store = LocalStore(self.root)
        self._keys = keys  # not copied: a live view of the key book sees devices paired later
        self._host, self._port = host, port
        self._server: _Server | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            return self._port
        return int(self._server.server_address[1])

    def _context(self) -> ssl.SSLContext:
        require_psk()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(CIPHERS)
        keys = self._keys

        def lookup(identity: str | None) -> bytes:
            key = keys.get(identity or "", b"")
            return key if len(key) >= 16 else b""  # empty: unknown identity, the handshake fails

        context.set_psk_server_callback(lookup)  # type: ignore[attr-defined]
        return context

    def start(self) -> None:
        if self._server is not None:
            return
        self._server = _Server((self._host, self._port), self._store, self._context())
        self._thread = threading.Thread(target=self._server.serve_forever, name="incremento-hub", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            self._port = int(server.server_address[1])
            server.shutdown()
            server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


# --- The client ------------------------------------------------------------------------------------------------

class HttpStore:
    """The engine's Store over a hub. Keeps one connection open and reconnects when the hub restarted."""

    def __init__(self, host: str, port: int, identity: str, key: bytes, *, timeout: float = 30.0):
        self._host, self._port, self._timeout = host, port, timeout
        self._identity, self._key = identity, key
        self._connection: http.client.HTTPSConnection | None = None
        self._lock = threading.RLock()

    @classmethod
    def from_pairing(cls, pairing: Pairing, **options: Any) -> HttpStore:
        return cls(pairing.host, pairing.port, pairing.identity, pairing.key, **options)

    def _context(self) -> ssl.SSLContext:
        require_psk()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False  # there is no certificate: the key proves who the hub is
        context.verify_mode = ssl.CERT_NONE
        context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers(CIPHERS)
        identity, key = self._identity, self._key
        context.set_psk_client_callback(lambda hint: (identity, key))  # type: ignore[attr-defined]
        return context

    def _drop(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass

    def _connect(self) -> http.client.HTTPSConnection:
        if self._connection is None:
            self._connection = http.client.HTTPSConnection(self._host, self._port, context=self._context(),
                                                           timeout=self._timeout)
        return self._connection

    def _exchange(self, method: str, target: str, body: Any = None, length: int | None = None) -> http.client.HTTPResponse:
        """Send one request and return its response, retrying once on a connection that went stale."""
        headers = {} if length is None else {"Content-Length": str(length)}
        for attempt in (0, 1):
            reused = self._connection is not None
            try:
                connection = self._connect()
                if hasattr(body, "seek"):
                    body.seek(0)
                connection.request(method, target, body=body, headers=headers)
                return connection.getresponse()
            except (OSError, http.client.HTTPException) as error:
                self._drop()
                if attempt == 0 and reused:
                    continue
                raise StoreError(f"{method} {target.split('?')[0]}: {error}") from error
        raise AssertionError("unreachable")

    @staticmethod
    def _target(route: str, rel: str) -> str:
        return f"/v1/{route}?path={quote(rel, safe='')}"

    def _finish(self, response: http.client.HTTPResponse, what: str) -> None:
        if response.status in (400, 411, 413, 500):
            detail = response.read(2000).decode("utf-8", "replace")
            self._drop()
            raise StoreError(f"{what}: the hub answered {response.status} {detail}")
        if response.status not in (200, 204, 404):
            self._drop()
            raise StoreError(f"{what}: the hub answered {response.status}")

    def _json(self, route: str, rel: str) -> Any | None:
        with self._lock:
            response = self._exchange("GET", self._target(route, rel))
            self._finish(response, f"{route} {rel!r}")
            declared = int(response.getheader("Content-Length") or 0)
            if declared > MAX_LISTING_BYTES:
                self._drop()
                raise StoreError(f"{route} {rel!r}: the answer is too large")
            data = response.read()
            if response.status == 404:
                return None
            try:
                return json.loads(data)
            except ValueError as error:
                self._drop()
                raise StoreError(f"{route} {rel!r}: the hub sent something that is not JSON") from error

    @staticmethod
    def _entry(info: Mapping[str, Any]) -> Entry:
        try:
            return Entry(str(info["name"]), bool(info["dir"]), int(info["size"]), float(info["mtime"]), False)
        except (KeyError, TypeError, ValueError) as error:
            raise StoreError("the hub sent a damaged listing") from error

    # -- Store --

    def listdir(self, rel: str) -> list[Entry]:
        clean(rel)
        data = self._json("list", rel)
        if not isinstance(data, list):
            raise StoreError("the hub sent a damaged listing")
        return [self._entry(info) for info in data]

    def stat(self, rel: str) -> Entry | None:
        clean(rel)
        data = self._json("stat", rel)
        return None if data is None else self._entry(data)

    def read(self, rel: str, limit: int) -> bytes | None:
        clean(rel)
        with self._lock:
            response = self._exchange("GET", self._target("file", rel))
            self._finish(response, f"read {rel!r}")
            if response.status == 404:
                response.read()
                return None
            if int(response.getheader("Content-Length") or 0) > limit:
                self._drop()
                raise StoreError(f"{rel} is larger than {limit} bytes")
            data = response.read(limit + 1)
            if len(data) > limit:
                self._drop()
                raise StoreError(f"{rel} is larger than {limit} bytes")
            return data

    def _put(self, rel: str, body: Any, length: int) -> None:
        if not clean(rel):
            raise StoreError(f"unsafe path {rel!r}")
        with self._lock:
            response = self._exchange("PUT", self._target("file", rel), body=body, length=length)
            self._finish(response, f"write {rel!r}")
            response.read()

    def write(self, rel: str, data: bytes) -> None:
        self._put(rel, bytes(data), len(data))

    def upload(self, local: Path, rel: str) -> None:
        with Path(local).open("rb") as stream:
            self._put(rel, stream, Path(local).stat().st_size)

    def download(self, rel: str, local: Path, limit: int) -> None:
        if not clean(rel):
            raise StoreError(f"unsafe path {rel!r}")
        target = Path(local)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            response = self._exchange("GET", self._target("file", rel))
            self._finish(response, f"download {rel!r}")
            if response.status == 404:
                response.read()
                raise StoreError(f"{rel} is missing")
            if int(response.getheader("Content-Length") or 0) > limit:
                self._drop()
                raise StoreError(f"{rel} is larger than {limit} bytes")
            total = 0
            try:
                with target.open("wb") as out:
                    while chunk := response.read(_CHUNK):
                        total += len(chunk)
                        if total > limit:
                            raise StoreError(f"{rel} is larger than {limit} bytes")
                        out.write(chunk)
            except (OSError, http.client.HTTPException, StoreError) as error:
                self._drop()
                target.unlink(missing_ok=True)
                if isinstance(error, StoreError):
                    raise
                raise StoreError(f"download {rel!r}: {error}") from error

    def delete(self, rel: str) -> None:
        if not clean(rel):
            raise StoreError(f"unsafe path {rel!r}")
        with self._lock:
            response = self._exchange("DELETE", self._target("file", rel))
            self._finish(response, f"delete {rel!r}")
            response.read()

    # -- for tests and diagnostics --

    def _socket(self) -> ssl.SSLSocket:
        with self._lock:
            connection = self._connect()
            if connection.sock is None:
                connection.connect()
            return connection.sock  # type: ignore[return-value]

    def cipher(self) -> str:
        negotiated = self._socket().cipher()
        return "" if negotiated is None else str(negotiated[0])

    def tls_version(self) -> str:
        return str(self._socket().version())

    def close(self) -> None:
        with self._lock:
            self._drop()


__all__ = ["CIPHERS", "HttpStore", "Hub", "KeyBook", "Pairing", "as_store", "new_key", "require_psk"]
