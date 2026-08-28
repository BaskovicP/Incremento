"""Crash-resumable migration from flat user_files/ to per-profile storage."""

import json
import os
import shutil
import time
from pathlib import Path

_LEGACY_ITEMS = [
    "incremento.db",
    "incremento.db-shm",
    "incremento.db-wal",
    "custom_learn_stats.json",
    "pdfs",
    "epubs",
    "epub_extracted",
    "videos",
    "writing",
    "video_profile",
    "web_profile",
]

_MIGRATION_MARKER = ".incremento_profile_migration.json"


def _merge_legacy_directory(
    source: Path,
    destination: Path,
    *,
    moved: list[str],
    conflicts: list[str],
    relative_root: str,
) -> None:
    """Move missing descendants while preserving every existing destination."""
    destination.mkdir(parents=True, exist_ok=True)
    for child in list(source.iterdir()):
        relative = f"{relative_root}/{child.name}" if relative_root else child.name
        target = destination / child.name
        if not target.exists():
            shutil.move(str(child), str(target))
            moved.append(relative)
            continue
        if child.is_dir() and not child.is_symlink() and target.is_dir():
            _merge_legacy_directory(
                child,
                target,
                moved=moved,
                conflicts=conflicts,
                relative_root=relative,
            )
            continue
        conflicts.append(relative)
    try:
        source.rmdir()
    except OSError:
        pass


def _write_marker(target_root: Path, report: dict) -> None:
    marker = target_root / _MIGRATION_MARKER
    temp_marker = marker.with_suffix(marker.suffix + ".tmp")
    temp_marker.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temp_marker, marker)


def migrate_to_profile_dir(addon_dir: str, profile: str) -> dict:
    """Move legacy flat user_files/ items into user_files/<profile>/.

    Safe to call repeatedly. Existing destination files are never overwritten;
    missing descendants are merged so a process interruption can resume on the
    next profile open.
    """
    try:
        from .paths import sanitize_profile_name
        from .db import close_connection
    except ImportError:
        from paths import sanitize_profile_name  # test environment
        from db import close_connection

    safe = sanitize_profile_name(profile)
    legacy_root = Path(addon_dir) / "user_files"
    target_root = legacy_root / safe

    has_legacy = any((legacy_root / item).exists() for item in _LEGACY_ITEMS)
    target_root.mkdir(parents=True, exist_ok=True)

    moved: list[str] = []
    conflicts: list[str] = []
    if has_legacy:
        close_connection()  # must close before moving DB/WAL files

    for name in _LEGACY_ITEMS:
        src = legacy_root / name
        dst = target_root / name
        if not src.exists():
            continue
        if not dst.exists():
            shutil.move(str(src), str(dst))
            moved.append(name)
            continue
        if src.is_dir() and not src.is_symlink() and dst.is_dir():
            _merge_legacy_directory(
                src,
                dst,
                moved=moved,
                conflicts=conflicts,
                relative_root=name,
            )
            continue
        conflicts.append(name)

    remaining = [name for name in _LEGACY_ITEMS if (legacy_root / name).exists()]
    report = {
        "version": 1,
        "completed": not remaining,
        "moved": sorted(moved),
        "conflicts": sorted(set(conflicts)),
        "remaining": sorted(remaining),
        "updated_at": int(time.time()),
    }
    _write_marker(target_root, report)
    return report
