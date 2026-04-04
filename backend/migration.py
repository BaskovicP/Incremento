"""
One-time migration: move legacy flat user_files/ contents into
user_files/<profile>/ so each Anki profile has its own data store.

The migration is idempotent: if the target directory already exists it does
nothing, so it is safe to call on every profile_did_open.
"""

import shutil
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


def migrate_to_profile_dir(addon_dir: str, profile: str) -> None:
    """Move legacy flat user_files/ items into user_files/<profile>/.

    Safe to call repeatedly; exits immediately if the profile directory
    already exists (idempotency guard).
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

    if target_root.exists():
        return

    has_legacy = any((legacy_root / item).exists() for item in _LEGACY_ITEMS)

    close_connection()  # must close before moving .db files
    target_root.mkdir(parents=True, exist_ok=True)

    if not has_legacy:
        return

    for name in _LEGACY_ITEMS:
        src = legacy_root / name
        dst = target_root / name
        if src.exists() and not dst.exists():
            shutil.move(str(src), str(dst))
