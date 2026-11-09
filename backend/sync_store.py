"""Storage under the exchange folder: the one thing the sync engine knows about where its files live.

The engine reads and writes only ``/``-separated paths relative to the folder the user chose, through a ``Store``.
A ``LocalStore`` is an ordinary directory (a cloud-synced folder, a network share); other stores can sit on Android's
document provider (a ``content://`` folder has no path) or on a LAN hub reached over HTTPS. Everything above this
layer (validation, conflicts, retention) is the same for all of them.

Contract for every store:

* paths are relative, ``/``-separated, with no ``.``, ``..``, empty, backslash or NUL parts: anything else is a
  ``StoreError`` before any I/O;
* ``write`` and ``upload`` are atomic: a reader sees the old file or the whole new one, never part of it;
* reads are bounded: a file larger than the caller's limit is refused, not truncated;
* ``listdir`` of a missing folder is ``[]``; ``read`` and ``stat`` of a missing file are ``None``; ``delete`` of a
  missing file is not an error;
* a store never follows a symlink, and reports one in ``listdir`` so the caller can refuse it.
"""

from __future__ import annotations

import ntpath
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


class StoreError(OSError):
    """A path or file the store refuses, or a file it cannot read."""


@dataclass(frozen=True)
class Entry:
    name: str
    is_dir: bool
    size: int = 0
    mtime: float = 0.0
    is_symlink: bool = False


@runtime_checkable
class Store(Protocol):
    def listdir(self, rel: str) -> list[Entry]: ...

    def stat(self, rel: str) -> Entry | None: ...

    def read(self, rel: str, limit: int) -> bytes | None: ...

    def write(self, rel: str, data: bytes) -> None: ...

    def upload(self, local: Path, rel: str) -> None: ...

    def download(self, rel: str, local: Path, limit: int) -> None: ...

    def delete(self, rel: str) -> None: ...


def clean(rel: str) -> list[str]:
    """The parts of a relative path, or StoreError. ``""`` is the root and has no parts."""
    if rel == "":
        return []
    parts = rel.split("/")
    if (rel.startswith("/") or "\\" in rel or "\x00" in rel
            or any(part in ("", ".", "..") for part in parts)):
        raise StoreError(f"unsafe path {rel!r}")
    return parts


def as_store(root: object) -> Store:
    """A Store for a folder path, or the store itself."""
    if isinstance(root, (str, os.PathLike)):
        return LocalStore(Path(root))
    return root  # type: ignore[return-value]


# --- A directory ---------------------------------------------------------------------------------

_BACKSLASH = chr(92)
_EXTENDED = _BACKSLASH * 2 + "?" + _BACKSLASH


def extended_windows_path(path: str) -> str:
    """A Windows path in its extended-length form, which is not limited to 260 characters.

    The engine's file names are about 190 characters below the user's folder, and cloud folders are often deep, so
    ordinary paths would fail on a Windows that has not enabled long paths (the default, and Anki's own Python).
    """
    if path.startswith(_EXTENDED):
        return path
    normalized = ntpath.normpath(path)
    if normalized.startswith(_BACKSLASH * 2):  # a network share
        return _EXTENDED + "UNC" + _BACKSLASH + normalized[2:]
    if not ntpath.isabs(normalized):
        normalized = ntpath.abspath(normalized)
    return _EXTENDED + normalized



class LocalStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self._base = Path(extended_windows_path(str(self.root))) if os.name == "nt" else self.root

    def _path(self, rel: str) -> Path:
        current = self._base
        for part in clean(rel):
            current = current / part
            if current.is_symlink():
                raise StoreError(f"symlink not followed: {rel}")
        return current

    def _file_path(self, rel: str) -> Path:
        """A path that names a file inside the folder: the root itself is not one."""
        if not clean(rel):
            raise StoreError(f"unsafe path {rel!r}")
        return self._path(rel)

    @staticmethod
    def _entry(name: str, info: os.stat_result, *, is_dir: bool, is_symlink: bool) -> Entry:
        return Entry(name, is_dir, 0 if is_dir else info.st_size, info.st_mtime, is_symlink)

    def listdir(self, rel: str) -> list[Entry]:
        path = self._path(rel)
        if not path.is_dir():
            return []
        entries = []
        with os.scandir(path) as scan:
            for item in scan:
                info = item.stat(follow_symlinks=False)
                entries.append(self._entry(item.name, info, is_dir=item.is_dir(follow_symlinks=False),
                                           is_symlink=item.is_symlink()))
        return entries

    def stat(self, rel: str) -> Entry | None:
        path = self._path(rel)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return None
        return self._entry(path.name, info, is_dir=path.is_dir(), is_symlink=False)

    def read(self, rel: str, limit: int) -> bytes | None:
        path = self._path(rel)
        if not path.is_file():
            return None
        if path.stat().st_size > limit:
            raise StoreError(f"{rel} is larger than {limit} bytes")
        data = path.read_bytes()
        if len(data) > limit:
            raise StoreError(f"{rel} is larger than {limit} bytes")
        return data

    def _temporary(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        os.close(handle)
        return Path(name)

    def _commit(self, temporary: Path, path: Path) -> None:
        with open(temporary, "r+b") as stream:  # Windows cannot fsync a read-only handle
            os.fsync(stream.fileno())
        if path.is_symlink():
            temporary.unlink(missing_ok=True)
            raise StoreError(f"symlink not followed: {path.name}")
        os.replace(temporary, path)

    def write(self, rel: str, data: bytes) -> None:
        path = self._file_path(rel)
        temporary = self._temporary(path)
        try:
            temporary.write_bytes(data)
            self._commit(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def upload(self, local: Path, rel: str) -> None:
        path = self._file_path(rel)
        temporary = self._temporary(path)
        try:
            shutil.copyfile(local, temporary)
            self._commit(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def download(self, rel: str, local: Path, limit: int) -> None:
        path = self._path(rel)
        if not path.is_file():
            raise StoreError(f"{rel} is missing")
        if path.stat().st_size > limit:
            raise StoreError(f"{rel} is larger than {limit} bytes")
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, local)

    def delete(self, rel: str) -> None:
        path = self._file_path(rel)
        if path.is_file():
            path.unlink(missing_ok=True)


# --- In memory ---------------------------------------------------------------------------------------

class MemoryStore:
    """A store in a dict: for tests, and as the simplest model of the contract."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._files: dict[str, bytes] = {}
        self._mtimes: dict[str, float] = {}
        self._clock = clock

    def touch(self, rel: str, mtime: float) -> None:
        """Set a file's modification time (tests of age-based cleanup)."""
        self._mtimes["/".join(clean(rel))] = mtime

    def listdir(self, rel: str) -> list[Entry]:
        prefix = "/".join(clean(rel))
        prefix = prefix + "/" if prefix else ""
        children: dict[str, Entry] = {}
        for path, data in self._files.items():
            if not path.startswith(prefix):
                continue
            name, _, rest = path[len(prefix):].partition("/")
            if rest:
                children.setdefault(name, Entry(name, True))
            else:
                children[name] = Entry(name, False, len(data), self._mtimes[path])
        return list(children.values())

    def stat(self, rel: str) -> Entry | None:
        key = "/".join(clean(rel))
        if key in self._files:
            return Entry(key.rsplit("/", 1)[-1], False, len(self._files[key]), self._mtimes[key])
        if rel == "" or any(path.startswith(key + "/") for path in self._files):
            return Entry(key.rsplit("/", 1)[-1] if key else "", True, 0, self._clock())
        return None

    def read(self, rel: str, limit: int) -> bytes | None:
        key = "/".join(clean(rel))
        data = self._files.get(key)
        if data is not None and len(data) > limit:
            raise StoreError(f"{rel} is larger than {limit} bytes")
        return data

    def write(self, rel: str, data: bytes) -> None:
        key = "/".join(clean(rel))
        if not key:
            raise StoreError("unsafe path ''")
        self._files[key] = bytes(data)
        self._mtimes[key] = self._clock()

    def upload(self, local: Path, rel: str) -> None:
        self.write(rel, Path(local).read_bytes())

    def download(self, rel: str, local: Path, limit: int) -> None:
        data = self.read(rel, limit)
        if data is None:
            raise StoreError(f"{rel} is missing")
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_bytes(data)

    def delete(self, rel: str) -> None:
        key = "/".join(clean(rel))
        self._files.pop(key, None)
        self._mtimes.pop(key, None)
