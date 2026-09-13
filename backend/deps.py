"""
Dependency detection and guided installation for Incremento.

Two kinds of dependency:
  - Python packages (PyMuPDF / fitz): can be pip-installed automatically
    inside Anki's own Python environment.
  - System binaries (Tesseract): must be installed by the user at the OS
    level; we provide platform-specific instructions.
"""

from __future__ import annotations
try:
    from .i18n import t
except ImportError:
    from backend.i18n import t


from collections.abc import Callable
import os
import platform
import shutil
import sys

PYMUPDF_REQUIREMENT = "PyMuPDF>=1.24,<2"


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def has_pymupdf() -> bool:
    try:
        import fitz  # noqa: F401
        return True
    except ImportError:
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
    return (
        t("backend_deps_pymupdf_instructions", executable=sys.executable, requirement=PYMUPDF_REQUIREMENT)
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
    Install PyMuPDF into Anki's Python environment in a background thread.
    on_done(success) is called on the main thread when the install completes.
    """
    import subprocess

    def _task() -> bool:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "--no-input",
                PYMUPDF_REQUIREMENT,
            ],
            capture_output=True,
            timeout=180,
        )
        return proc.returncode == 0

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
                    t("backend_deps_manual_install", executable=sys.executable, requirement=PYMUPDF_REQUIREMENT)
                )
                _fallback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                _fallback.setWordWrap(True)
                layout.insertWidget(layout.indexOf(buttons), _fallback)

        install_pymupdf(mw, on_done=_done)

    _pymupdf_install_btn.clicked.connect(_do_install)

    dlg.exec()
