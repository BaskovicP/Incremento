"""
Central path construction for all Incremento user data.

All paths are rooted at user_files/<profile>/ inside the addon directory,
giving each Anki profile its own isolated data store.

Usage
-----
On profile open (profile_did_open hook):
    from .paths import set_active_profile
    set_active_profile(mw.pm.name)

Everywhere else:
    from . import paths
    db_path = paths.get_db_path(addon_dir, paths.get_active_profile())

Zero-argument helpers (pdf_manager, writing_manager, etc.) call
get_active_profile() internally so their public signatures stay stable.
"""

import re
from pathlib import Path

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_current_profile: str = "Default"


def sanitize_profile_name(name: str) -> str:
    """Strip filesystem-unsafe characters from an Anki profile name.

    Falls back to 'Default' if the result would be empty.

    Note: distinct Anki profile names can sanitize to the same string
    (e.g. "My Profile" and "My_Profile" both become "My_Profile").
    Anki itself prevents spaces in profile names on most platforms, so
    this is not a practical concern in normal usage.
    """
    safe = _UNSAFE_RE.sub("_", (name or "").strip())
    return safe or "Default"


def set_active_profile(profile: str) -> None:
    """Set the module-level active profile (called once on profile_did_open)."""
    global _current_profile
    _current_profile = sanitize_profile_name(profile)


def get_active_profile() -> str:
    """Return the currently active sanitized profile name."""
    return _current_profile


# ── Directory helpers ─────────────────────────────────────────────────────────


def get_user_files_dir(addon_dir: str, profile: str) -> Path:
    """Root of per-profile user data: <addon_dir>/user_files/<profile>/"""
    return Path(addon_dir) / "user_files" / sanitize_profile_name(profile)


def get_db_path(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "incremento.db"


def get_db_checkpoint_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "db_checkpoints"


def get_stats_path(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "custom_learn_stats.json"


def get_diagnostics_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "diagnostics"


def get_diagnostic_events_path(addon_dir: str, profile: str) -> Path:
    return get_diagnostics_dir(addon_dir, profile) / "events.jsonl"


def get_pdf_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "pdfs"


def get_epub_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "epubs"


def get_epub_extract_root(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "epub_extracted"


def get_videos_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "videos"


def get_writing_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "writing"


def get_writing_backup_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "writing_backups"


def get_local_files_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "files"


def get_video_profile_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "video_profile"


def get_web_profile_dir(addon_dir: str, profile: str) -> Path:
    return get_user_files_dir(addon_dir, profile) / "web_profile"
