"""Profile-scoped browser storage and ordered Qt shutdown on the UI thread."""

import hashlib

from PyQt6 import sip
from PyQt6.QtWebEngineCore import QWebEngineProfile

try:
    from ..backend import paths
except ImportError:
    from backend import paths


def create_browser_profile(addon_dir: str, anki_profile: str, *, search: bool = False):
    directory = (paths.get_search_profile_dir if search else paths.get_web_profile_dir)(
        addon_dir, anki_profile
    )
    directory.mkdir(parents=True, exist_ok=True)
    # Qt requires unique storage names even when explicit paths are supplied.
    identity = hashlib.sha256(str(directory).encode("utf-8")).hexdigest()[:24]
    profile = QWebEngineProfile("incremento_" + identity)
    profile.setPersistentStoragePath(str(directory))
    profile.setCachePath(str(directory / "Cache"))
    profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
    return profile


def destroy_browser(owner, profile) -> None:
    """Destroy the widget and its owned pages before flushing its profile.

    Do not defer profile destruction until after the application event loop exits:
    Qt cannot then guarantee that cookies/local storage reach disk.
    """
    if owner is not None and not sip.isdeleted(owner):
        sip.delete(owner)
    if profile is not None and not sip.isdeleted(profile):
        sip.delete(profile)
