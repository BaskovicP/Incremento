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


def copy_blob(source_store: Path, sha: str, target_store: Path) -> bool:
    """Copy one blob between stores, verifying it. False if the source lacks a complete copy."""
    if has_blob(target_store, sha):
        return True
    source = blob_path(source_store, sha)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_BLOB_BYTES:
        return False
    temporary, actual = _copy_hashing(source, Path(target_store) / ".tmp")
    if actual != sha:
        temporary.unlink(missing_ok=True)
        return False
    _place(temporary, Path(target_store), sha)
    return True


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
