"""
Dependency detection and guided installation for Incremento.

Two kinds of dependency:
  - Python packages (PyMuPDF / fitz): can be pip-installed automatically
    inside Anki's own Python environment.
  - System binaries (Tesseract): must be installed by the user at the OS
    level; we provide platform-specific instructions.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys


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
            "Install Tesseract via Homebrew:\n\n"
            "    brew install tesseract\n\n"
            "Don't have Homebrew?  Visit https://brew.sh to install it first.\n\n"
            "After installation, restart Anki."
        )
    if p == "Windows":
        return (
            "Download and run the Tesseract installer for Windows:\n\n"
            "    https://github.com/UB-Mannheim/tesseract/wiki\n\n"
            "During setup, choose 'Add Tesseract to PATH'.\n"
            "If you skip that option, install to the default location:\n"
            "    C:\\Program Files\\Tesseract-OCR\\\n\n"
            "After installation, restart Anki."
        )
    # Linux
    return (
        "Install Tesseract with your package manager:\n\n"
        "    Ubuntu / Debian:  sudo apt install tesseract-ocr\n"
        "    Fedora:           sudo dnf install tesseract\n"
        "    Arch:             sudo pacman -S tesseract\n"
        "    openSUSE:         sudo zypper install tesseract-ocr\n\n"
        "After installation, restart Anki."
    )


def pymupdf_instructions() -> str:
    return (
        "PyMuPDF can be installed automatically by Incremento.\n\n"
        "If automatic installation fails, run this command in a terminal:\n\n"
        f"    {sys.executable} -m pip install PyMuPDF\n\n"
        "Then restart Anki."
    )


def ankiconnect_instructions() -> str:
    return (
        "Install the AnkiConnect add-on as well if you want to use the "
        "Incremento browser companion for page import and video time sync.\n\n"
        "AnkiConnect is an Anki add-on, so install it from the Anki add-on "
        "ecosystem and restart Anki afterwards."
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
            [sys.executable, "-m", "pip", "install", "--quiet", "PyMuPDF"],
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
    dlg.setWindowTitle("Incremento — Dependency Setup")
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
        "Incremento uses optional setup components for PDF OCR and browser "
        "companion sync. Core features work without them."
    )
    intro.setWordWrap(True)
    intro.setStyleSheet("color: gray;")
    layout.addWidget(intro)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("QFrame { color: rgba(128,128,128,0.3); }")
    layout.addWidget(sep)

    # PyMuPDF row
    layout.addLayout(_row("PyMuPDF  (PDF rendering & text extraction)", pymupdf_ok))

    _pymupdf_status = QLabel()
    _pymupdf_status.setWordWrap(True)
    _pymupdf_install_btn = QPushButton("Install PyMuPDF automatically")

    if pymupdf_ok:
        _pymupdf_status.setText(
            '<span style="color: gray; font-size: small;">Installed — no action needed.</span>'
        )
        _pymupdf_install_btn.setVisible(False)
    else:
        _pymupdf_status.setText(
            '<span style="color: gray; font-size: small;">'
            "Not installed. Click the button below to install it automatically "
            "into Anki's Python environment. You will need to restart Anki afterwards."
            "</span>"
        )
        _pymupdf_install_btn.setStyleSheet("font-weight: bold;")

    layout.addWidget(_pymupdf_status)
    layout.addWidget(_pymupdf_install_btn)

    # Tesseract row
    layout.addLayout(_row("Tesseract OCR  (converts scanned pages to searchable text)", tess_ok))

    _tess_browser = QTextBrowser()
    _tess_browser.setOpenExternalLinks(True)
    _tess_browser.setMaximumHeight(120)
    _tess_browser.setStyleSheet("font-size: 12px;")

    if tess_ok:
        _tess_browser.setPlainText(f"Found at: {tesseract_path()}")
    else:
        _tess_browser.setPlainText(tesseract_instructions())

    layout.addWidget(_tess_browser)

    _ankiconnect_label = QLabel("AnkiConnect  (needed for browser companion sync/import)")
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
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)

    # Wire install button
    def _do_install() -> None:
        _pymupdf_install_btn.setEnabled(False)
        _pymupdf_install_btn.setText("Installing…")
        _pymupdf_status.setText(
            '<span style="color: gray; font-size: small;">Installing PyMuPDF — please wait…</span>'
        )

        def _done(ok: bool) -> None:
            if ok:
                _pymupdf_install_btn.setText("Installed ✓")
                _pymupdf_status.setText(
                    '<span style="color: #4caf50;">Installed successfully. '
                    "<b>Please restart Anki</b> to activate it.</span>"
                )
                tooltip("PyMuPDF installed — restart Anki to use it.")
            else:
                _pymupdf_install_btn.setEnabled(True)
                _pymupdf_install_btn.setText("Install PyMuPDF automatically")
                _pymupdf_status.setText(
                    '<span style="color: #e05050;">Automatic install failed. '
                    "See instructions below.</span>"
                )
                from aqt.qt import QLabel as _QL
                _fallback = _QL(f"Manual install:\n    {sys.executable} -m pip install PyMuPDF")
                _fallback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                _fallback.setWordWrap(True)
                layout.insertWidget(layout.indexOf(buttons), _fallback)

        install_pymupdf(mw, on_done=_done)

    _pymupdf_install_btn.clicked.connect(_do_install)

    dlg.exec()
