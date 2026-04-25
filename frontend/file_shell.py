import os
import subprocess
import sys

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def reveal_file_command(path: str, platform: str | None = None) -> list[str] | None:
    current_platform = platform or sys.platform
    normalized = os.path.normpath(path)
    if current_platform == "darwin":
        return ["open", "-R", normalized]
    if current_platform.startswith("win"):
        return ["explorer", f"/select,{normalized}"]
    return None


def reveal_local_file(path: str, platform: str | None = None) -> bool:
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
    target = os.path.normpath(str(path or "").strip())
    if not target:
        return False
    return bool(QDesktopServices.openUrl(QUrl.fromLocalFile(target)))
