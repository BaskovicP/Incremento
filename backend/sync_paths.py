"""Where the sync engine keeps its own files in a profile.

Defined here, not in ``paths.py``, so the engine needs nothing added to files a host (Ankrimento's vendored
Incremento) ships without it. Only ``paths.get_user_files_dir`` is used, which every Incremento version has.
"""

from __future__ import annotations

from pathlib import Path

try:
    from . import paths
except ImportError:
    import paths  # type: ignore[no-redef]


def get_sync_dir(addon_dir: str, profile: str) -> Path:
    """Local state of shared-folder sync that is not in SQLite."""
    return paths.get_user_files_dir(addon_dir, profile) / "sync"


def get_sync_blob_dir(addon_dir: str, profile: str) -> Path:
    """Content-addressed copies of document versions captured or received by sync."""
    return get_sync_dir(addon_dir, profile) / "blobs"
