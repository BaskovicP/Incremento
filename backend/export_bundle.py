"""Helpers for building a full Incremento migration/export bundle."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


TRANSIENT_USER_FILE_NAMES = {
    ".ds_store",
    "lock",
    "lockfile",
    "singletoncookie",
    "singletonlock",
    "singletonsocket",
}


def _normalize_relpath(rel_path: str) -> str:
    rel = str(rel_path or "").replace("\\", "/").lstrip("/")
    return "" if rel == "." else rel


def should_skip_user_file(rel_path: str) -> bool:
    """Return True for transient runtime files that should not be exported."""
    rel = _normalize_relpath(rel_path)
    if not rel:
        return False

    parts = [part for part in Path(rel).parts if part not in ("", ".")]
    if "__pycache__" in parts:
        return True

    name = parts[-1] if parts else ""
    return name.casefold() in TRANSIENT_USER_FILE_NAMES


def snapshot_tree(
    source_dir: str,
    dest_dir: str,
    *,
    skip_relpaths: set[str] | None = None,
) -> dict[str, int]:
    """
    Recursively copy source_dir into dest_dir.

    Returns counters describing what was copied/skipped.
    """
    src = Path(source_dir)
    dst = Path(dest_dir)
    skip_relpaths = {_normalize_relpath(p) for p in (skip_relpaths or set())}
    stats = {
        "files_copied": 0,
        "files_skipped": 0,
        "dirs_created": 0,
        "bytes_copied": 0,
    }

    if not src.exists():
        return stats

    for root, dirnames, filenames in os.walk(src):
        root_path = Path(root)
        rel_dir = _normalize_relpath(os.path.relpath(root_path, src))

        kept_dirs: list[str] = []
        for dirname in dirnames:
            rel_path = _normalize_relpath(
                f"{rel_dir}/{dirname}" if rel_dir else dirname
            )
            if should_skip_user_file(rel_path):
                continue
            kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        dest_root = dst / rel_dir if rel_dir else dst
        if not dest_root.exists():
            dest_root.mkdir(parents=True, exist_ok=True)
            stats["dirs_created"] += 1

        for filename in filenames:
            rel_path = _normalize_relpath(
                f"{rel_dir}/{filename}" if rel_dir else filename
            )
            if rel_path in skip_relpaths or should_skip_user_file(rel_path):
                stats["files_skipped"] += 1
                continue

            src_path = root_path / filename
            dest_path = dest_root / filename
            shutil.copy2(src_path, dest_path)
            stats["files_copied"] += 1
            try:
                stats["bytes_copied"] += int(src_path.stat().st_size)
            except OSError:
                pass

    return stats
