"""
Dependency detection and guided installation for Incremento.

Two kinds of dependency:
  - Python packages (PyMuPDF / fitz): explicitly installed with a compatible
    interpreter into Incremento's local dependency folder.
  - System binaries (Tesseract): must be installed by the user at the OS
    level; we provide platform-specific instructions.
"""

from __future__ import annotations
try:
    from .i18n import t
except ImportError:
    from backend.i18n import t


from collections.abc import Callable
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid

PYMUPDF_REQUIREMENT = "PyMuPDF>=1.26,<2"
_install_lock = threading.Lock()
_PYTHON_NAME = re.compile(r'python(?:3(?:\.\d+)?)?(?:\.exe)?$', re.IGNORECASE)
_PYTHON_PROBE = (
    'import json,platform,sys,pip; print(json.dumps({"version": list(sys.version_info[:2]), '
    '"machine": platform.machine(), "implementation": sys.implementation.name}))'
)
_PACKAGE_PROBE = (
    'import json,sys; sys.path.insert(0,sys.argv[1]); import pymupdf; '
    'doc=pymupdf.open(); doc.new_page(); doc.close(); '
    'print(json.dumps({"version": pymupdf.VersionBind, "file": pymupdf.__file__}))'
)


def _pymupdf_target() -> Path:
    tag = f'{sys.implementation.cache_tag}-{sys.platform}-{platform.machine().lower()}'
    return Path(__file__).resolve().parent.parent / '.dependencies' / 'pymupdf' / tag


def activate_pymupdf() -> None:
    """Activate an already installed package before the readers use it."""
    target = _pymupdf_target()
    if (target / 'pymupdf' / '__init__.py').is_file() and not target.is_symlink():
        path = str(target)
        if path not in sys.path:
            sys.path.insert(0, path)
            importlib.invalidate_caches()


def _python_candidates() -> list[str]:
    version = f'{sys.version_info.major}.{sys.version_info.minor}'
    names = [f'python{version}', 'python3', 'python']
    candidates = [sys.executable, getattr(sys, '_base_executable', '')]
    for prefix in {sys.prefix, sys.base_prefix}:
        candidates.extend(str(Path(prefix) / 'bin' / name) for name in names)
        candidates.append(str(Path(prefix) / 'Scripts' / 'python.exe'))
    if _platform() == 'Darwin':
        root = Path.home() / 'Library' / 'Application Support' / 'AnkiProgramFiles'
    elif _platform() == 'Windows':
        root = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AnkiProgramFiles'
        candidates.append(str(root.parent / 'Programs' / 'Python' /
                              f'Python{sys.version_info.major}{sys.version_info.minor}' / 'python.exe'))
    else:
        root = Path.home() / '.local' / 'share' / 'AnkiProgramFiles'
    candidates.extend(str(root / '.venv' / 'bin' / name) for name in names)
    candidates.append(str(root / '.venv' / 'Scripts' / 'python.exe'))
    candidates.extend(str(path) for path in sorted((root / 'python').glob(f'*/bin/python{version}')))
    candidates.extend(str(path) for path in sorted((root / 'python').glob('*/python.exe')))
    candidates.extend(found for name in names if (found := shutil.which(name)))
    return list(dict.fromkeys(path for path in candidates if path))


def _subprocess_env() -> dict[str, str]:
    # Embedded Anki can set Python's home to its application bundle. A real
    # interpreter must discover its own standard library and site packages.
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    return env


def _cpu(value: str) -> str:
    return {'aarch64': 'arm64', 'amd64': 'x86_64'}.get(value.lower(), value.lower())


def _installer_python() -> str | None:
    for candidate in _python_candidates():
        path = Path(candidate)
        if not _PYTHON_NAME.fullmatch(path.name) or not path.is_file():
            continue
        # A zero exit from an application launcher is not proof of Python.
        if not _PYTHON_NAME.fullmatch(path.resolve().name):
            continue
        try:
            proc = subprocess.run([candidate, '-I', '-c', _PYTHON_PROBE],
                                  capture_output=True, timeout=5, env=_subprocess_env())
            data = json.loads(proc.stdout) if proc.returncode == 0 else {}
            if (isinstance(data, dict) and isinstance(data.get('machine'), str)
                    and data.get('version') == list(sys.version_info[:2])
                    and data.get('implementation') == sys.implementation.name
                    and _cpu(data.get('machine', '')) == _cpu(platform.machine())):
                return candidate
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
            continue
    return None


def _install_pymupdf_package() -> bool:
    with _install_lock:
        python = _installer_python()
        if not python:
            return False
        target = _pymupdf_target()
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.pymupdf-', dir=target.parent) as directory:
            stage = Path(directory)
            proc = subprocess.run([
                python, '-I', '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
                '--no-input', '--only-binary=:all:', '--no-deps', '--target', str(stage),
                PYMUPDF_REQUIREMENT,
            ], capture_output=True, timeout=180, env=_subprocess_env())
            if proc.returncode != 0:
                return False
            checked = subprocess.run([python, '-I', '-c', _PACKAGE_PROBE, str(stage)],
                                     capture_output=True, timeout=30, env=_subprocess_env())
            if checked.returncode != 0:
                return False
            try:
                data = json.loads(checked.stdout)
                if not isinstance(data, dict) or not isinstance(data.get('version'), str) or not isinstance(data.get('file'), str):
                    return False
                version = tuple(int(part) for part in data['version'].split('.')[:2])
                imported = Path(data['file']).resolve()
                if not (1, 26) <= version < (2, 0) or not imported.is_relative_to(stage.resolve()):
                    return False
            except (KeyError, TypeError, ValueError):
                return False
            backup = target.with_name('.pymupdf-old-' + uuid.uuid4().hex)
            if target.exists():
                target.rename(backup)
            try:
                os.replace(stage, target)
            except OSError:
                if backup.exists():
                    backup.rename(target)
                raise
            finally:
                # Windows can retain loaded native libraries until Anki exits.
                if target.exists() and backup.exists():
                    shutil.rmtree(backup, ignore_errors=True)
        return True


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def has_pymupdf() -> bool:
    try:
        import fitz
        return tuple(int(part) for part in fitz.VersionBind.split('.')[:2]) >= (1, 26)
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def tesseract_path() -> str | None:
    """Return the path to the Tesseract binary, or None if not found."""
    candidates = [
        shutil.which("tesseract"),
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def has_tesseract() -> bool:
    return tesseract_path() is not None


def status() -> dict[str, bool]:
    """Return a snapshot of all dependency states."""
    return {
        "pymupdf":   has_pymupdf(),
        "tesseract": has_tesseract(),
    }


# ---------------------------------------------------------------------------
# Install instructions (platform-aware)
# ---------------------------------------------------------------------------


def _platform() -> str:
    return platform.system()  # "Darwin" | "Windows" | "Linux"


def tesseract_instructions() -> str:
    p = _platform()
    if p == "Darwin":
        return (
            t('backend_deps_tesseract_mac')
        )
    if p == "Windows":
        return (
            t('backend_deps_tesseract_windows')
        )
    # Linux
    return (
        t('backend_deps_tesseract_linux')
    )


def pymupdf_instructions() -> str:
    executable = sys.executable if _PYTHON_NAME.fullmatch(Path(sys.executable).name) else f'python{sys.version_info.major}.{sys.version_info.minor}'
    command = [executable, '-I', '-m', 'pip', 'install', '--only-binary=:all:', '--no-deps',
               '--upgrade', '--target', str(_pymupdf_target()), PYMUPDF_REQUIREMENT]
    if _platform() == 'Windows' and not _PYTHON_NAME.fullmatch(Path(sys.executable).name):
        command[:1] = ['py', f'-{sys.version_info.major}.{sys.version_info.minor}']
    formatted = subprocess.list2cmdline(command) if _platform() == 'Windows' else shlex.join(command)
    return (
        t('backend_deps_pymupdf_instructions', command=formatted,
          version=f'{sys.version_info.major}.{sys.version_info.minor}')
    )


def ankiconnect_instructions() -> str:
    return (
        t('backend_deps_ankiconnect_instructions')
    )


# ---------------------------------------------------------------------------
# PyMuPDF auto-install (background, requires mw.taskman)
# ---------------------------------------------------------------------------


def install_pymupdf(mw, on_done: "Callable[[bool], None] | None" = None) -> None:
    """
    Install and verify PyMuPDF in Incremento's folder in a background thread.
    on_done(success) is called on the main thread when the install completes.
    """
    def _task() -> bool:
        return _install_pymupdf_package()

    def _on_done(fut) -> None:
        try:
            ok = fut.result()
        except Exception:
            ok = False
        if on_done:
            on_done(ok)

    mw.taskman.run_in_background(_task, _on_done)


# ---------------------------------------------------------------------------
# First-run setup dialog
# ---------------------------------------------------------------------------


def show_setup_dialog(mw, force: bool = False) -> None:
    """
    Show the dependency setup dialog.
    On first run (or when force=True) this is called automatically;
    afterwards only when the user opens it from the Utils menu.
    """
    from aqt.qt import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QDialogButtonBox, QFrame, Qt, QTextBrowser,
    )
    from aqt.utils import tooltip

    pymupdf_ok  = has_pymupdf()
    tess_ok     = has_tesseract()

    dlg = QDialog(mw)
    dlg.setWindowTitle(t('backend_deps_title'))
    dlg.setMinimumWidth(500)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(12)

    def _row(label: str, ok: bool) -> QHBoxLayout:
        row = QHBoxLayout()
        icon = QLabel("✓" if ok else "✗")
        icon.setFixedWidth(20)
        icon.setStyleSheet(f"color: {'#4caf50' if ok else '#e05050'}; font-weight: bold;")
        row.addWidget(icon)
        lbl = QLabel(label)
        row.addWidget(lbl, stretch=1)
        return row

    intro = QLabel(
        t('backend_deps_intro')
    )
    intro.setWordWrap(True)
    intro.setStyleSheet("color: gray;")
    layout.addWidget(intro)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.3); }")
    layout.addWidget(sep)

    # PyMuPDF row
    layout.addLayout(_row(t('backend_deps_pymupdf'), pymupdf_ok))

    _pymupdf_status = QLabel()
    _pymupdf_status.setWordWrap(True)
    _pymupdf_install_btn = QPushButton(t('backend_deps_install_pymupdf'))

    if pymupdf_ok:
        _pymupdf_status.setText(
            t('backend_deps_installed')
        )
        _pymupdf_install_btn.setVisible(False)
    else:
        _pymupdf_status.setText(
            t('backend_deps_not_installed')
        )
        _pymupdf_install_btn.setStyleSheet("font-weight: bold;")

    layout.addWidget(_pymupdf_status)
    layout.addWidget(_pymupdf_install_btn)

    # Tesseract row
    layout.addLayout(_row(t('backend_deps_tesseract'), tess_ok))

    _tess_browser = QTextBrowser()
    _tess_browser.setOpenExternalLinks(True)
    _tess_browser.setMaximumHeight(120)
    _tess_browser.setStyleSheet("font-size: 12px;")

    if tess_ok:
        _tess_browser.setPlainText(t("backend_deps_found", path=tesseract_path()))
    else:
        _tess_browser.setPlainText(tesseract_instructions())

    layout.addWidget(_tess_browser)

    _ankiconnect_label = QLabel(t('backend_deps_ankiconnect'))
    _ankiconnect_label.setStyleSheet("font-weight: bold;")
    _ankiconnect_label.setWordWrap(True)
    layout.addWidget(_ankiconnect_label)

    _ankiconnect_browser = QTextBrowser()
    _ankiconnect_browser.setOpenExternalLinks(True)
    _ankiconnect_browser.setMaximumHeight(90)
    _ankiconnect_browser.setStyleSheet("font-size: 12px;")
    _ankiconnect_browser.setPlainText(ankiconnect_instructions())
    layout.addWidget(_ankiconnect_browser)

    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet("QFrame { color: rgba(128,128,128,0.3); }")
    layout.addWidget(sep2)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.button(QDialogButtonBox.StandardButton.Close).setText(t("backend_close"))
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    # Wire install button
    def _do_install() -> None:
        _pymupdf_install_btn.setEnabled(False)
        _pymupdf_install_btn.setText(t('backend_deps_installing'))
        _pymupdf_status.setText(
            t('backend_deps_installing_pymupdf')
        )

        def _done(ok: bool) -> None:
            if ok:
                _pymupdf_install_btn.setText(t('backend_deps_installed_check'))
                _pymupdf_status.setText(
                    t('backend_deps_installed_restart')
                )
                tooltip(t('backend_deps_restart_notice'))
            else:
                _pymupdf_install_btn.setEnabled(True)
                _pymupdf_install_btn.setText(t('backend_deps_install_pymupdf'))
                _pymupdf_status.setText(
                    t('backend_deps_install_failed')
                )
                from aqt.qt import QLabel as _QL
                _fallback = _QL(
                    pymupdf_instructions()
                )
                _fallback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                _fallback.setWordWrap(True)
                layout.insertWidget(layout.indexOf(buttons), _fallback)

        install_pymupdf(mw, on_done=_done)

    _pymupdf_install_btn.clicked.connect(_do_install)

    dlg.exec()
