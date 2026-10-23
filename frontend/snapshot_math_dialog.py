"""Shared, opt-in formula recognition for reader snapshot previews."""

from __future__ import annotations

from html import escape
from pathlib import Path

from aqt import mw
from aqt.qt import (
    QApplication, QBuffer, QDialog, QHBoxLayout, QIODevice,
    QLabel, QLineEdit, QMimeData, QPlainTextEdit, QPushButton, QTimer,
    QVBoxLayout, Qt,
)

try:
    from ..backend.i18n import t
    from ..backend.math_ocr import (
        MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, MathRecognitionError,
        format_math_copy, recognize_snapshot,
    )
    from ..backend.paths import get_active_profile as _active_profile
    from ..backend.simpletex_credentials import load_credentials, normalize_credentials, save_credentials
except ImportError:
    from backend.i18n import t
    from backend.math_ocr import (
        MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, MathRecognitionError,
        format_math_copy, recognize_snapshot,
    )
    from backend.paths import get_active_profile as _active_profile
    from backend.simpletex_credentials import load_credentials, normalize_credentials, save_credentials

try:
    from .simpletex_setup_dialog import SimpleTexSetupDialog
    from .file_shell import open_companion_url
except ImportError:
    from simpletex_setup_dialog import SimpleTexSetupDialog
    from file_shell import open_companion_url


_ADDON_DIR = str(Path(__file__).resolve().parents[1])


def _error_text(code: str) -> str:
    return {
        "credentials": t("reader_math_error_credentials"),
        "image": t("reader_math_error_image"),
        "empty": t("reader_math_error_empty"),
        "response": t("reader_math_error_response"),
        "auth": t("reader_math_error_auth"),
        "quota": t("reader_math_error_quota"),
        "busy": t("reader_math_error_busy"),
        "network": t("reader_math_error_network"),
    }.get(code, t("reader_math_error_network"))


class SnapshotMathDialog(QDialog):
    def __init__(self, parent, pixmap, *, is_current):
        super().__init__(parent)
        self._pixmap = pixmap
        self._source_current = is_current
        self._profile = str(_active_profile() or "")
        self._collection = mw.col
        self._closed = False
        self._running = False
        self._recognized = False
        self._setup_dialog = None
        self.setWindowTitle(t("reader_math_title"))
        self.resize(620, 580)
        layout = QVBoxLayout(self)

        preview = QLabel(self)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setPixmap(pixmap.scaled(540, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(preview)
        guidance = QLabel(t("reader_math_privacy"), self)
        guidance.setWordWrap(True)
        layout.addWidget(guidance)
        account = QLabel(t("reader_math_account_help"), self)
        account.setWordWrap(True)
        account.setOpenExternalLinks(True)
        layout.addWidget(account)
        self._app_id = QLineEdit(self)
        self._app_id.setPlaceholderText(t("reader_math_app_id"))
        self._app_id.setAccessibleName(t("reader_math_app_id"))
        layout.addWidget(self._app_id)
        self._secret = QLineEdit(self)
        self._secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._secret.setPlaceholderText(t("reader_math_app_secret"))
        self._secret.setAccessibleName(t("reader_math_app_secret"))
        layout.addWidget(self._secret)
        app_id, secret = load_credentials(_ADDON_DIR, self._profile)
        self._app_id.setText(app_id)
        self._secret.setText(secret)
        self._setup_button = QPushButton(t("reader_math_setup_open"), self)
        self._setup_button.setAutoDefault(False)
        self._setup_button.clicked.connect(self._open_setup)
        layout.addWidget(self._setup_button)
        self._scan = QPushButton(t("reader_math_scan"), self)
        self._scan.setAutoDefault(False)
        self._scan.clicked.connect(self._start_scan)
        layout.addWidget(self._scan)
        self._status = QLabel(t("reader_math_ready"), self)
        self._status.setWordWrap(True)
        self._status.setAccessibleName(t("reader_math_status"))
        layout.addWidget(self._status)
        self._result = QPlainTextEdit(self)
        self._result.setAccessibleName(t("reader_math_latex_result"))
        self._result.textChanged.connect(self._update_copy_buttons)
        layout.addWidget(self._result, 1)
        row = QHBoxLayout()
        self._copy_inline = QPushButton(t("reader_math_copy_inline"), self)
        self._copy_display = QPushButton(t("reader_math_copy_display"), self)
        self._copy_latex = QPushButton(t("reader_math_copy_latex"), self)
        for button, mode in ((self._copy_inline, "inline"), (self._copy_display, "display"),
                             (self._copy_latex, "latex")):
            button.setAutoDefault(False)
            button.clicked.connect(lambda _checked=False, mode=mode: self._copy(mode))
            row.addWidget(button)
        layout.addLayout(row)
        close = QPushButton(t("reader_close"), self)
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.finished.connect(self._retire)
        self.destroyed.connect(lambda: setattr(self, "_closed", True))
        self._guard = QTimer(self)
        self._guard.setInterval(250)
        self._guard.timeout.connect(self._check_source)
        self._guard.start()
        self._update_copy_buttons()

    def _current(self) -> bool:
        if self._closed:
            return False
        try:
            return (str(_active_profile() or "") == self._profile
                    and mw.col is self._collection and bool(self._source_current()))
        except (AttributeError, RuntimeError):
            return False

    def _check_source(self) -> None:
        if not self._current():
            self.reject()

    def _retire(self, *_args) -> None:
        if self._closed:
            return
        self._closed = True
        self._guard.stop()
        if self._setup_dialog is not None:
            self._setup_dialog.reject()
        self._secret.clear()
        self._app_id.clear()
        self._recognized = False
        self._result.clear()
        self._pixmap = None

    def _has_credentials(self) -> bool:
        try:
            return bool(normalize_credentials((self._app_id.text(), self._secret.text()))[0])
        except ValueError:
            return False

    def _open_setup(self) -> None:
        if self._setup_dialog is not None or self._running or not self._current():
            return

        def saved(credentials):
            if self._current():
                self._app_id.setText(credentials[0])
                self._secret.setText(credentials[1])
                self._status.setText(t("reader_math_setup_saved"))

        dialog = SimpleTexSetupDialog(self,
            initial_credentials=(self._app_id.text(), self._secret.text()),
            is_current=self._current,
            save=lambda credentials: save_credentials(_ADDON_DIR, self._profile, credentials),
            on_saved=saved, open_url=lambda url: open_companion_url(url))
        self._setup_dialog = dialog
        dialog.finished.connect(lambda _result: setattr(self, "_setup_dialog", None))
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()

    def _update_copy_buttons(self) -> None:
        valid = self._recognized and not self._running and not self._closed
        if valid:
            try:
                format_math_copy(self._result.toPlainText(), "latex")
            except MathRecognitionError:
                valid = False
        for button in (self._copy_inline, self._copy_display, self._copy_latex):
            button.setEnabled(valid)

    def _start_scan(self) -> None:
        if self._running or self._setup_dialog is not None or not self._current():
            return
        app_id, secret = self._app_id.text().strip(), self._secret.text().strip()
        if not self._has_credentials():
            self._status.setText(_error_text("credentials"))
            self._open_setup()
            return
        if self._pixmap.isNull() or self._pixmap.width() * self._pixmap.height() > MAX_IMAGE_PIXELS:
            self._status.setText(_error_text("image"))
            return
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not self._pixmap.save(buffer, "PNG") or buffer.size() > MAX_IMAGE_BYTES:
            buffer.close()
            self._status.setText(_error_text("image"))
            return
        image = bytes(buffer.data())
        buffer.close()
        self._running = True
        self._recognized = False
        self._result.clear()
        self._scan.setEnabled(False)
        self._setup_button.setEnabled(False)
        self._status.setText(t("reader_math_scanning"))
        self._update_copy_buttons()

        def finished(future):
            if self._closed:
                return
            if not self._current():
                self.reject()
                return
            self._running = False
            self._scan.setEnabled(True)
            self._setup_button.setEnabled(True)
            try:
                latex = future.result()
            except Exception as error:
                self._status.setText(_error_text(
                    error.code if isinstance(error, MathRecognitionError) else "network"))
            else:
                self._recognized = True
                self._result.setPlainText(latex)
                self._status.setText(t("reader_math_found"))
            self._update_copy_buttons()

        try:
            mw.taskman.run_in_background(
                lambda: recognize_snapshot(image, app_id, secret), finished, uses_collection=False,
            )
        except Exception:
            self._running = False
            self._scan.setEnabled(True)
            self._setup_button.setEnabled(True)
            self._status.setText(_error_text("network"))

    def _copy(self, mode: str) -> None:
        if not self._current():
            self.reject()
            return
        if not self._recognized or self._running:
            return
        try:
            text = format_math_copy(self._result.toPlainText(), mode)
        except MathRecognitionError:
            return
        # Never copy provider HTML. A rich fallback protects <, >, and & when
        # pasting into Anki, while plain text works in any other application.
        payload = QMimeData()
        payload.setText(text)
        payload.setHtml(escape(text).replace("\n", "<br>"))
        QApplication.clipboard().setMimeData(payload)
        self._status.setText(t("reader_math_copied"))


def add_snapshot_math_action(picker, layout, pixmap, *, is_current):
    """Attach a local action; neither opening the picker nor this dialog uploads."""
    button = QPushButton(t("reader_math_open"), picker)
    button.setAutoDefault(False)
    button.setAccessibleDescription(t("reader_math_privacy"))

    def show_scanner():
        dialog = SnapshotMathDialog(picker, pixmap, is_current=is_current)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
        if not dialog._has_credentials():
            dialog._open_setup()

    button.clicked.connect(show_scanner)
    layout.addSpacing(8)
    layout.addWidget(button)
    return button
