"""Disposable, profile-local RGBA previews. All I/O belongs in task workers."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import threading

try:
    from .paths import get_bookshelf_cover_cache_dir
except ImportError:
    from paths import get_bookshelf_cover_cache_dir


HEADER = struct.Struct('>8sII32s')
MAX_ENTRY_BYTES = HEADER.size + 160 * 320 * 4
MAX_DISK_BYTES = 64 * 1024 * 1024
MAX_FILES = 512
_MAGIC = b'ICOVER1\0'
_OWNED = re.compile(r'(?:[0-9a-f]{64}\.rgba|\.cover-cache-[0-9a-f]{32}\.tmp)\Z')
_FD = os.open in os.supports_dir_fd and os.mkdir in os.supports_dir_fd
# ponytail: one lock for bounded cache I/O; shard only if contention is measured.
_LOCK = threading.RLock()


def _reject_link(info):
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise OSError('Unsafe cover cache path')


@contextmanager
def _directory(addon_dir, profile, *, create=False):
    base = Path(addon_dir).resolve(strict=True)
    target = get_bookshelf_cover_cache_dir(str(base), profile)
    parts = target.relative_to(base).parts
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    if not _FD:
        directory = base
        for part in parts:
            directory /= part
            if create:
                directory.mkdir(mode=0o700, exist_ok=True)
            info = directory.lstat()
            _reject_link(info)
            if not stat.S_ISDIR(info.st_mode):
                raise OSError('Invalid cover cache directory')
        yield directory
        return
    descriptor = os.open(base, flags)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def _path(directory, name):
    for parent in (directory, *directory.parents):
        info = parent.lstat()
        _reject_link(info)
        if not stat.S_ISDIR(info.st_mode):
            raise OSError('Invalid cover cache directory')
    target = directory / name
    try:
        _reject_link(target.lstat())
    except FileNotFoundError:
        pass
    return target


def _open(directory, name, flags):
    flags |= getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_BINARY', 0)
    return (os.open(name, flags, 0o600, dir_fd=directory) if isinstance(directory, int)
            else os.open(_path(directory, name), flags, 0o600))


def _unlink(directory, name):
    if isinstance(directory, int):
        os.unlink(name, dir_fd=directory)
    else:
        _path(directory, name).unlink()


def _filename(key):
    # Include the on-disk format version; source/renderer identity is in key.
    return hashlib.sha256(json.dumps([1, key], separators=(',', ':'), allow_nan=False).encode()).hexdigest() + '.rgba'


def _pixels(width, height, pixels):
    return (type(width) is int and type(height) is int and 0 < width <= 160 and 0 < height <= 320
            and isinstance(pixels, bytes) and len(pixels) == width * height * 4)


def _checksum(width, height, pixels):
    return hashlib.sha256(struct.pack('>II', width, height) + pixels).digest()


def read(addon_dir, profile, key):
    """Return validated (width, height, RGBA bytes), or a cache miss."""
    try:
        name = _filename(key)
        with _LOCK, _directory(addon_dir, profile) as directory:
            with os.fdopen(_open(directory, name, os.O_RDONLY), 'rb') as stream:
                info = os.fstat(stream.fileno())
                _reject_link(info)
                if not stat.S_ISREG(info.st_mode) or not HEADER.size <= info.st_size <= MAX_ENTRY_BYTES:
                    return None
                payload = stream.read(MAX_ENTRY_BYTES + 1)
            magic, width, height, checksum = HEADER.unpack(payload[:HEADER.size])
            pixels = payload[HEADER.size:]
            if magic != _MAGIC or not _pixels(width, height, pixels) or _checksum(width, height, pixels) != checksum:
                return None
            try:
                if isinstance(directory, int):
                    os.utime(name, dir_fd=directory, follow_symlinks=False)
                else:
                    os.utime(_path(directory, name), follow_symlinks=False)
            except OSError:
                pass
            return width, height, pixels
    except (OSError, ValueError, TypeError, struct.error):
        return None


def _prune(directory, name, reserved):
    owned = []
    with os.scandir(directory) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_FILES * 2:
                raise OSError('Cover cache directory exceeds inspection budget')
            if not _OWNED.fullmatch(entry.name):
                continue
            info = entry.stat(follow_symlinks=False)
            _reject_link(info)
            if not stat.S_ISREG(info.st_mode):
                raise OSError('Invalid cover cache entry')
            if entry.name != name:
                owned.append((info.st_mtime_ns, entry.name, info.st_size))
    total = sum(item[2] for item in owned)
    owned.sort()
    while owned and (len(owned) >= MAX_FILES or total + reserved > MAX_DISK_BYTES):
        _age, old_name, size = owned.pop(0)
        _unlink(directory, old_name)
        total -= size
    if total + reserved > MAX_DISK_BYTES or len(owned) >= MAX_FILES:
        raise OSError('Cover exceeds disk cache budget')


def write(addon_dir, profile, key, width, height, pixels):
    """Atomically publish private pixels; failure must never prevent reading."""
    if not _pixels(width, height, pixels):
        return False
    payload = HEADER.pack(_MAGIC, width, height, _checksum(width, height, pixels)) + pixels
    temporary = ''
    try:
        name = _filename(key)
        with _LOCK, _directory(addon_dir, profile, create=True) as directory:
            try:
                _prune(directory, name, len(payload))
                temporary = '.cover-cache-' + secrets.token_hex(16) + '.tmp'
                with os.fdopen(_open(directory, temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL), 'wb') as stream:
                    stream.write(payload)
                if isinstance(directory, int):
                    os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
                else:
                    os.replace(_path(directory, temporary), _path(directory, name))
                temporary = ''
            finally:
                if temporary:
                    _unlink(directory, temporary)
        return True
    except (OSError, ValueError, TypeError):
        return False
