import os
import shutil
import subprocess
import sys

_companion_browser = "chrome"


def configure_companion_browser(browser: str) -> None:
    global _companion_browser
    try:
        from ..backend.config_service import configured_companion_browser
    except ImportError:
        from config_service import configured_companion_browser
    _companion_browser = configured_companion_browser({"companion_browser": browser})


def _browser_executable(browser: str, platform: str) -> str | None:
    names = ("firefox",) if browser == "firefox" else ("google-chrome", "google-chrome-stable", "chrome")
    for name in names:
        executable = shutil.which(name)
        if executable:
            return executable
    if platform.startswith("win"):
        suffix = ("Mozilla Firefox", "firefox.exe") if browser == "firefox" else ("Google", "Chrome", "Application", "chrome.exe")
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if base:
                executable = os.path.join(base, *suffix)
                if os.path.isfile(executable):
                    return executable
    return None


def open_companion_url(url: str, *, browser: str | None = None, platform: str | None = None) -> bool:
    """Open a validated HTTP(S) URL in the selected browser, without fallback."""
    try:
        from ..backend.content_safety import normalize_external_http_url
        from ..backend.config_service import configured_companion_browser
    except ImportError:
        from content_safety import normalize_external_http_url
        from config_service import configured_companion_browser
    try:
        target = normalize_external_http_url(url)
    except (TypeError, ValueError):
        return False
    selected = configured_companion_browser({"companion_browser": browser or _companion_browser})
    current_platform = platform or sys.platform
    try:
        if current_platform == "darwin":
            app = "org.mozilla.firefox" if selected == "firefox" else "com.google.Chrome"
            result = subprocess.run(["/usr/bin/open", "-b", app, target],
                                    timeout=3, capture_output=True, check=False)
            return result.returncode == 0
        executable = _browser_executable(selected, current_platform)
        if not executable:
            return False
        subprocess.Popen([executable, "--new-tab", target],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def activate_anki_window(window, platform: str | None = None) -> None:
    window.showNormal()
    window.raise_()
    window.activateWindow()
    if (platform or sys.platform) == "darwin":
        # Launch Services activates the already-running Anki app without an
        # Apple Events/Accessibility permission or an interpolated shell script.
        try:
            subprocess.Popen(["open", "-a", "Anki"])
        except OSError:
            pass


def reveal_file_command(path: str, platform: str | None = None) -> list[str] | None:
    current_platform = platform or sys.platform
    normalized = os.path.normpath(path)
    if current_platform == "darwin":
        return ["open", "-R", normalized]
    if current_platform.startswith("win"):
        return ["explorer", f"/select,{normalized}"]
    return None


def reveal_local_file(path: str, platform: str | None = None) -> bool:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    target = os.path.normpath(str(path or "").strip())
    if not target:
        return False
    command = reveal_file_command(target, platform=platform)
    if command is not None:
        try:
            subprocess.Popen(command)
            return True
        except Exception:
            pass
    directory = target if os.path.isdir(target) else os.path.dirname(target)
    if not directory:
        return False
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(directory)))


def open_local_file(path: str) -> bool:
    from PyQt6.QtCore import QUrl
    from PyQt6.QtGui import QDesktopServices

    target = os.path.normpath(str(path or "").strip())
    if not target:
        return False
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(target)))
