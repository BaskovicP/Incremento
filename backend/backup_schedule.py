"""Profile-scoped policy and safe rotation for opt-in full-backup ZIPs."""

from __future__ import annotations

import datetime as dt
import math
import re
import tempfile
from pathlib import Path
from typing import Mapping

try:
    from .paths import sanitize_profile_name
except ImportError:
    from paths import sanitize_profile_name


MAX_AUTOMATIC_BACKUP_VERSIONS = 20
DEFAULT_AUTOMATIC_BACKUP_VERSIONS = 5


def normalize_policy(raw: object) -> dict:
    source = raw if isinstance(raw, Mapping) else {}
    directory = source.get("directory", "")
    directory = directory.strip() if isinstance(directory, str) else ""
    if "\x00" in directory or len(directory) > 4096:
        directory = ""
    try:
        hours = int(source.get("interval_hours", 0))
    except (ValueError, TypeError, OverflowError):
        hours = 0
    try:
        versions = int(source.get("versions", DEFAULT_AUTOMATIC_BACKUP_VERSIONS))
    except (ValueError, TypeError, OverflowError):
        versions = DEFAULT_AUTOMATIC_BACKUP_VERSIONS
    try:
        last_success = float(source.get("last_success", 0))
    except (ValueError, TypeError, OverflowError):
        last_success = 0.0
    return {
        "enabled": source.get("enabled") is True and bool(directory),
        "directory": directory,
        "on_open": source.get("on_open", False) is True,
        "on_close": source.get("on_close", False) is True,
        "interval_hours": max(0, min(720, hours)),
        "versions": max(1, min(MAX_AUTOMATIC_BACKUP_VERSIONS, versions)),
        "last_success": last_success if math.isfinite(last_success) and last_success > 0 else 0.0,
        "last_close_failed": source.get("last_close_failed") is True,
    }


def is_due(policy: Mapping, trigger: str, now: float) -> bool:
    if not policy.get("enabled") or not policy.get("directory"):
        return False
    if trigger == "open":
        return policy.get("on_open") is True
    if trigger == "close":
        return policy.get("on_close") is True
    if trigger == "interval":
        hours = policy.get("interval_hours", 0)
        return bool(hours) and now - float(policy.get("last_success", 0)) >= hours * 3600
    return False


def validate_destination(directory: str, profile_root: Path) -> Path:
    """Keep archives outside the snapshotted profile, including aliased paths."""
    if not directory or "\x00" in directory:
        raise ValueError("Choose a backup folder.")
    destination = Path(directory).expanduser().resolve(strict=True)
    if not destination.is_dir():
        raise ValueError("The backup destination must be an existing folder.")
    if destination.is_relative_to(profile_root.parent.resolve()):
        raise ValueError("The backup folder cannot be inside Incremento profile storage.")
    return destination


def backup_filename(profile: str, now: float) -> str:
    """Name of a legacy timestamped automatic archive."""
    stamp = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"incremento_{sanitize_profile_name(profile)}_auto_backup_{stamp}.zip"


def _slot_path(directory: Path, profile: str, slot: int) -> Path:
    return directory / (
        f"incremento_{sanitize_profile_name(profile)}_auto_backup_slot_{slot:02d}.zip"
    )


def _owned_backup_paths(directory: Path, profile: str) -> list[Path]:
    prefix = f"incremento_{sanitize_profile_name(profile)}_auto_backup_"
    timestamp_pattern = re.compile(rf"{re.escape(prefix)}\d{{8}}T\d{{12}}Z\.zip\Z")
    slot_pattern = re.compile(rf"{re.escape(prefix)}slot_(?:0[1-9]|1\d|20)\.zip\Z")
    return [
        path
        for path in directory.iterdir()
        if (timestamp_pattern.fullmatch(path.name) or slot_pattern.fullmatch(path.name))
        and path.is_file()
        and not path.is_symlink()
    ]


def next_backup_path(directory: Path, profile: str, keep: int) -> Path:
    """Fill to the selected count, then reuse the oldest file at the same path."""
    limit = max(1, min(MAX_AUTOMATIC_BACKUP_VERSIONS, int(keep)))
    owned = _owned_backup_paths(directory, profile)
    if len(owned) >= limit:
        return min(owned, key=lambda path: (path.stat().st_mtime_ns, path.name))
    for slot in range(1, limit + 1):
        path = _slot_path(directory, profile, slot)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("An automatic backup slot is not a regular file.")
        if not path.exists():
            return path
    raise RuntimeError("No automatic backup slot is available.")


def backup_staging_directory(
    destination: Path,
    *,
    automatic: bool,
    system_temp: Path | None = None,
) -> Path:
    """Keep automatic work files outside a synced folder when atomically possible."""
    if not automatic:
        return destination
    try:
        candidate = Path(system_temp or tempfile.gettempdir()).resolve(strict=True)
        if candidate.is_dir() and candidate.stat().st_dev == destination.stat().st_dev:
            return candidate
    except OSError:
        pass
    return destination


def _backup_recency(path: Path, timestamp_pattern: re.Pattern[str]) -> tuple[int, int]:
    match = timestamp_pattern.fullmatch(path.name)
    if match:
        try:
            stamp = dt.datetime.strptime(match.group(1), "%Y%m%dT%H%M%S%fZ")
            instant = int(stamp.replace(tzinfo=dt.timezone.utc).timestamp() * 1_000_000_000)
            return (0, instant)
        except ValueError:
            return (0, path.stat().st_mtime_ns)
    # Every slot archive was written by the new rotation scheme after the
    # timestamped archives. Migrate them out even if an old clock was wrong.
    return (1, path.stat().st_mtime_ns)


def prune_backups(
    directory: Path, profile: str, keep: int, *, protected: Path | None = None
) -> list[Path]:
    """Rotate only this profile's own automatic ZIPs, never manual exports."""
    prefix = f"incremento_{sanitize_profile_name(profile)}_auto_backup_"
    timestamp_pattern = re.compile(rf"{re.escape(prefix)}(\d{{8}}T\d{{12}}Z)\.zip\Z")
    slot_pattern = re.compile(rf"{re.escape(prefix)}slot_(?:0[1-9]|1\d|20)\.zip\Z")
    candidates = sorted(
        (path for path in directory.iterdir()
         if (timestamp_pattern.fullmatch(path.name) or slot_pattern.fullmatch(path.name))
         and path.is_file() and not path.is_symlink()),
        key=lambda path: (_backup_recency(path, timestamp_pattern), path.name),
        reverse=True,
    )
    limit = max(1, min(MAX_AUTOMATIC_BACKUP_VERSIONS, int(keep)))
    if protected in candidates:
        retained = {protected, *[path for path in candidates if path != protected][:limit - 1]}
    else:
        retained = set(candidates[:limit])
    removed = []
    for path in candidates:
        if path in retained:
            continue
        path.unlink()
        removed.append(path)
    return removed
