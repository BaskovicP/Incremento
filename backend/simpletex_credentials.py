"""Local per-profile SimpleTex credentials, excluded from exports and sync.

This private file is separate from shipped/shared add-on configuration. POSIX
operations pin the profile directory and reject symbolic links and hard links.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import stat

try:
    from .paths import get_simpletex_credentials_path
except ImportError:
    from paths import get_simpletex_credentials_path


def normalize_credentials(values) -> tuple[str, str]:
    if not isinstance(values, (tuple, list)) or len(values) != 2:
        raise ValueError("Invalid SimpleTex credentials.")
    if any(not isinstance(value, str) for value in values):
        raise ValueError("Invalid SimpleTex credentials.")
    app_id, secret = (value.strip() for value in values)
    if (bool(app_id) != bool(secret) or any(
        len(value) > 512 or any(not 33 <= ord(char) <= 126 for char in value)
        for value in (app_id, secret)
    )):
        raise ValueError("Invalid SimpleTex credentials.")
    return app_id, secret


def _reject_link(info):
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError("Unsafe credential storage.")


@contextmanager
def _directory(addon_dir, profile, *, create=False):
    base = Path(addon_dir).resolve()
    path = get_simpletex_credentials_path(str(base), profile)
    parts = path.parent.relative_to(base).parts
    if os.name == 'nt' or os.open not in os.supports_dir_fd:
        directory = base
        for part in parts:
            directory /= part
            if create:
                directory.mkdir(mode=0o700, exist_ok=True)
            info = directory.lstat()
            _reject_link(info)
            if not stat.S_ISDIR(info.st_mode):
                raise ValueError("Unsafe credential storage.")
        yield directory
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(base, flags)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd
    finally:
        os.close(fd)


def _relative(directory, name):
    return (directory / name, {}) if isinstance(directory, Path) else (name, {'dir_fd': directory})


def _regular(directory, name):
    target, options = _relative(directory, name)
    info = os.stat(target, follow_symlinks=False, **options)
    _reject_link(info)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Unsafe credential storage.")
    return info


def load_credentials(addon_dir: str, profile: str) -> tuple[str, str]:
    name = get_simpletex_credentials_path(addon_dir, profile).name
    try:
        with _directory(addon_dir, profile) as directory:
            if _regular(directory, name).st_size > 4096:
                return "", ""
            target, options = _relative(directory, name)
            opened = os.open(target, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
                             | getattr(os, 'O_NONBLOCK', 0), **options)
            with os.fdopen(opened, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    return "", ""
                data = stream.read(4097)
            if len(data) > 4096:
                return "", ""
            payload = json.loads(data)
            if not isinstance(payload, dict) or payload.get('version') != 1:
                return "", ""
            return normalize_credentials((payload.get('app_id'), payload.get('app_secret')))
    except (OSError, ValueError, UnicodeError, RecursionError):
        return "", ""


def save_credentials(addon_dir: str, profile: str, values: tuple[str, str]) -> None:
    app_id, secret = normalize_credentials(values)
    name = get_simpletex_credentials_path(addon_dir, profile).name
    temporary = '.simpletex_credentials-' + secrets.token_hex(12) + '.tmp'
    try:
        with _directory(addon_dir, profile, create=bool(app_id)) as directory:
            try:
                _regular(directory, name)
            except FileNotFoundError:
                pass
            target, options = _relative(directory, name)
            if not app_id:
                try:
                    os.unlink(target, **options)
                except FileNotFoundError:
                    pass
                return
            staged, staged_options = _relative(directory, temporary)
            opened = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                             | getattr(os, 'O_NOFOLLOW', 0), 0o600, **staged_options)
            try:
                with os.fdopen(opened, 'wb') as stream:
                    stream.write(json.dumps({'version': 1, 'app_id': app_id, 'app_secret': secret}).encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                if isinstance(directory, Path):
                    os.replace(staged, target)
                else:
                    os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            finally:
                try:
                    os.unlink(staged, **staged_options)
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        if app_id:
            raise ValueError("Could not save SimpleTex credentials.") from None
    except (OSError, ValueError):
        raise ValueError("Could not save SimpleTex credentials.") from None
