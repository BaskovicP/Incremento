"""Content-addressed file storage for sync: ``<store>/<aa>/<sha256>``.

Used for the profile's local blob store and for the exchange folder's
``blobs/``. A blob is written to a temporary name while it is hashed and is
renamed into place only when its bytes match its name, so a blob that exists
under its name is complete and verified.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

try:
    from .sync_store import Store, StoreError
except ImportError:
    from sync_store import Store, StoreError  # type: ignore[no-redef]

MAX_BLOB_BYTES = 512 * 1024 * 1024
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def blob_path(store: Path, sha: str) -> Path:
    if not _HEX64.match(sha):
        raise ValueError(f"not a blob name: {sha!r}")
    return Path(store) / sha[:2] / sha


def has_blob(store: Path | None, sha: str) -> bool:
    if store is None:
        return False
    path = blob_path(store, sha)
    return path.is_file() and not path.is_symlink()


def _copy_hashing(source: Path, directory: Path) -> tuple[Path, str]:
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    handle, name = tempfile.mkstemp(dir=directory, prefix=".incoming-")
    try:
        with os.fdopen(handle, "wb") as target, source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BLOB_BYTES:
                    raise ValueError(f"{source.name} exceeds {MAX_BLOB_BYTES} bytes")
                digest.update(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name), digest.hexdigest()


def _place(temporary: Path, store: Path, sha: str) -> None:
    final = blob_path(store, sha)
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.is_file():
        temporary.unlink(missing_ok=True)
        return
    os.replace(temporary, final)


def store_file(store: Path, source: Path) -> str:
    """Copy ``source`` into the store; returns its sha256."""
    if Path(source).is_symlink():
        raise ValueError(f"{source} is a symlink")
    temporary, sha = _copy_hashing(Path(source), Path(store) / ".tmp")
    _place(temporary, Path(store), sha)
    return sha


def exchange_blob_rel(library_rel: str, sha: str) -> str:
    if not _HEX64.match(sha):
        raise ValueError(f"not a blob name: {sha!r}")
    return f"{library_rel}/blobs/{sha[:2]}/{sha}"


def put_exchange_blob(store: Store, library_rel: str, local_store: Path, sha: str) -> bool:
    """Place one of this device's verified local blobs in the exchange. False if it has no local copy."""
    if not has_blob(local_store, sha):
        return False
    source = blob_path(local_store, sha)
    rel = exchange_blob_rel(library_rel, sha)
    existing = store.stat(rel)
    if existing is not None and not existing.is_dir and existing.size == source.stat().st_size:
        return True  # named by its hash and written atomically: complete
    store.upload(source, rel)
    return True


def fetch_exchange_blob(store: Store, library_rel: str, sha: str, local_store: Path) -> bool:
    """Copy one blob from the exchange into the local store after verifying its bytes against its name."""
    if has_blob(local_store, sha):
        return True
    rel = exchange_blob_rel(library_rel, sha)
    entry = store.stat(rel)
    if entry is None or entry.is_dir or entry.size > MAX_BLOB_BYTES:
        return False
    directory = Path(local_store) / ".tmp"
    directory.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=directory, prefix=".incoming-")
    os.close(handle)
    downloaded = Path(name)
    try:
        try:
            store.download(rel, downloaded, MAX_BLOB_BYTES)
        except StoreError:
            return False
        if _file_sha256(downloaded) != sha:
            return False
        _place(downloaded, Path(local_store), sha)
        return True
    finally:
        downloaded.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def materialize(store: Path, sha: str, destination: Path) -> None:
    """Atomically place a stored blob at ``destination``."""
    source = blob_path(store, sha)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.")
    os.close(handle)
    try:
        shutil.copyfile(source, name)
        with open(name, "r+b") as stream:  # Windows cannot fsync a read-only handle
            os.fsync(stream.fileno())
        os.replace(name, destination)
    finally:
        Path(name).unlink(missing_ok=True)
