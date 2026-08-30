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
import hashlib
import unicodedata
from pathlib import Path

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_MAX_PROFILE_COMPONENT_CHARS = 120

_current_profile: str = "Default"


def sanitize_profile_name(name: str) -> str:
    """Strip filesystem-unsafe characters from an Anki profile name.

    Falls back to 'Default' if the result would be empty.

    Note: distinct Anki profile names can sanitize to the same string
    (e.g. "My Profile" and "My_Profile" both become "My_Profile").
    Anki itself prevents spaces in profile names on most platforms, so
    this is not a practical concern in normal usage.
    """
    raw = unicodedata.normalize("NFC", str(name or "")).strip()
    safe = _UNSAFE_RE.sub("_", raw).rstrip(" .")
    if not safe or safe in {".", ".."}:
        return "Default"
    if safe.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        safe = f"_{safe}"
    if len(safe) > _MAX_PROFILE_COMPONENT_CHARS:
        suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
        safe = f"{safe[: _MAX_PROFILE_COMPONENT_CHARS - len(suffix) - 1]}-{suffix}"
    return safe


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
    safe_profile = sanitize_profile_name(profile)
    if safe_profile in {"", ".", ".."} or Path(safe_profile).name != safe_profile:
        raise ValueError("Invalid profile storage name.")
    return Path(addon_dir) / "user_files" / safe_profile


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
