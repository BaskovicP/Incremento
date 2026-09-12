"""Profile-scoped policy and safe rotation for opt-in full-backup ZIPs."""

from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import Mapping

try:
    from .paths import sanitize_profile_name
except ImportError:
    from paths import sanitize_profile_name


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
        versions = int(source.get("versions", 5))
    except (ValueError, TypeError, OverflowError):
        versions = 5
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
        "versions": max(1, min(20, versions)),
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
    stamp = dt.datetime.fromtimestamp(now, dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"incremento_{sanitize_profile_name(profile)}_auto_backup_{stamp}.zip"


def prune_backups(
    directory: Path, profile: str, keep: int, *, protected: Path | None = None
) -> list[Path]:
    """Rotate only this profile's own automatic ZIPs, never manual exports."""
    prefix = f"incremento_{sanitize_profile_name(profile)}_auto_backup_"
    pattern = re.compile(rf"{re.escape(prefix)}\d{{8}}T\d{{12}}Z\.zip\Z")
    candidates = sorted(
        (path for path in directory.iterdir()
         if pattern.fullmatch(path.name) and path.is_file() and not path.is_symlink()),
        key=lambda path: path.name,
        reverse=True,
    )
    limit = max(1, min(20, int(keep)))
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
