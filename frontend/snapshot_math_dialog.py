"""Shared, opt-in formula recognition for reader snapshot previews."""

from __future__ import annotations

from html import escape
import threading
import queue
import time

from aqt import mw
from aqt.qt import (
    QApplication, QBuffer, QDialog, QHBoxLayout, QIODevice,
    QLabel, QMimeData, QPlainTextEdit, QProgressBar, QPushButton, QTimer,
    QVBoxLayout, Qt,
)

try:
    from ..backend.i18n import t
    from ..backend.math_ocr import (
        MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, MathRecognitionError,
        format_math_copy, recognize_snapshot, is_ready, setup_local_ocr,
    )
    from ..backend.paths import get_active_profile as _active_profile
except ImportError:
    from backend.i18n import t
    from backend.math_ocr import (
        MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, MathRecognitionError,
        format_math_copy, recognize_snapshot, is_ready, setup_local_ocr,
    )
    from backend.paths import get_active_profile as _active_profile


def _error_text(code: str) -> str:
    return t("reader_math_local_error_" + code) if code in {
        "setup", "python", "process", "timeout", "cancelled", "busy"
    } else t("reader_math_error_" + code) if code in {
        "image", "empty", "response"
    } else t("reader_math_local_error_process")


def _encode_math_image(image) -> bytes:
    """Encode a detached QImage in the worker, never a GUI-owned QPixmap."""
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    try:
        if not image.save(buffer, "PNG") or buffer.size() > MAX_IMAGE_BYTES:
            raise MathRecognitionError("image")
        return bytes(buffer.data())
    finally:
        buffer.close()


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
        self._cancel = threading.Event()
        self._progress_events = queue.Queue(maxsize=1)
        self._progress_event = {"stage": "loading"}
        self._progress_started = 0.0
        self._operation = "scan"
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
        self._setup_button = QPushButton(t("reader_math_local_install"), self)
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
        self._progress = QProgressBar(self)
        # Neither pip nor model loading reports a reliable overall percentage.
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setAccessibleName(t("reader_math_status"))
        self._progress.hide()
        layout.addWidget(self._progress)
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
        elif self._running:
            self._refresh_progress()

    def _begin_progress(self, operation):
        self._operation = operation
        self._progress_started = time.monotonic()
        self._progress_events = queue.Queue(maxsize=1)
        self._progress_event = {"stage": "environment" if operation == "setup" else "loading"}
        self._refresh_progress()
        events = self._progress_events

        def receive(event):
            # Worker threads only update this bounded mailbox, never Qt widgets.
            try:
                events.get_nowait()
            except queue.Empty:
                pass
            try:
                events.put_nowait(event)
            except queue.Full:
                pass
        return receive

    def _refresh_progress(self):
        try:
            self._progress_event = self._progress_events.get_nowait()
        except queue.Empty:
            pass
        event = self._progress_event
        stage = event["stage"]
        keys = {
            "environment": "reader_math_progress_environment",
            "dependencies": "reader_math_progress_dependencies",
            "installing": "reader_math_progress_installing",
            "starting": "reader_math_progress_starting",
            "loading": "reader_math_progress_loading",
            "download_model": "reader_math_progress_model",
            "download_resizer": "reader_math_progress_resizer",
            "recognizing": "reader_math_scanning",
        }
        if stage not in keys:
            return
        status = t(keys[stage])
        if self._operation == "setup":
            step = {"environment": 1, "dependencies": 2, "installing": 2,
                    "starting": 3, "download_model": 3, "download_resizer": 3, "loading": 4}.get(stage, 4)
            status = t("reader_math_progress_step", step=step, status=status)
        total, current = event.get("total", 0), event.get("current", 0)
        if stage.startswith("download_") and total > 0:
            percent = min(100, current * 100 // total)
            self._progress.setRange(0, 100)
            self._progress.setValue(percent)
            self._progress.setTextVisible(True)
            status = t("reader_math_progress_download", status=status, percent=percent,
                       current=f"{current / (1024**2):.1f}", total=f"{total / (1024**2):.1f}")
        else:
            self._progress.setRange(0, 0)
            self._progress.setTextVisible(False)
            if stage == "dependencies" and current:
                status = t("reader_math_progress_packages", status=status, count=current)
        seconds = max(0, int(time.monotonic() - self._progress_started))
        self._status.setText(t("reader_math_progress_elapsed", status=status,
                               elapsed=f"{seconds // 60}:{seconds % 60:02}"))

    def _retire(self, *_args) -> None:
        if self._closed:
            return
        self._closed = True
        self._guard.stop()
        self._progress.hide()
        self._cancel.set()
        self._recognized = False
        self._result.clear()
        self._pixmap = None

    def _open_setup(self) -> None:
        if self._running or not self._current():
            return
        self._running = True
        self._scan.setEnabled(False)
        self._setup_button.setEnabled(False)
        progress = self._begin_progress("setup")
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
                future.result()
            except Exception as error:
                self._status.setText(_error_text(
                    error.code if isinstance(error, MathRecognitionError) else "process"))
            else:
                self._status.setText(t("reader_math_local_installed"))
            self._update_copy_buttons()

        try:
            mw.taskman.run_in_background(
                lambda: setup_local_ocr(self._cancel, progress=progress), finished, uses_collection=False)
        except Exception:
            self._running = False
            self._scan.setEnabled(True)
            self._setup_button.setEnabled(True)
            self._status.setText(_error_text("process"))
            self._update_copy_buttons()

    def _update_copy_buttons(self) -> None:
        self._progress.setVisible(self._running and not self._closed)
        valid = self._recognized and not self._running and not self._closed
        if valid:
            try:
                format_math_copy(self._result.toPlainText(), "latex")
            except MathRecognitionError:
                valid = False
        for button in (self._copy_inline, self._copy_display, self._copy_latex):
            button.setEnabled(valid)

    def _start_scan(self) -> None:
        if self._running or not self._current():
            return
        if not is_ready():
            self._status.setText(_error_text("setup"))
            return
        if self._pixmap.isNull() or self._pixmap.width() * self._pixmap.height() > MAX_IMAGE_PIXELS:
            self._status.setText(_error_text("image"))
            return
        image = self._pixmap.toImage()
        cancel = self._cancel
        self._running = True
        self._recognized = False
        self._result.clear()
        self._scan.setEnabled(False)
        self._setup_button.setEnabled(False)
        progress = self._begin_progress("scan")
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
                    error.code if isinstance(error, MathRecognitionError) else "process"))
            else:
                self._recognized = True
                self._result.setPlainText(latex)
                self._status.setText(t("reader_math_found"))
            self._update_copy_buttons()

        try:
            mw.taskman.run_in_background(
                lambda: recognize_snapshot(_encode_math_image(image), cancel=cancel, progress=progress),
                finished, uses_collection=False,
            )
        except Exception:
            self._running = False
            self._scan.setEnabled(True)
            self._setup_button.setEnabled(True)
            self._status.setText(_error_text("process"))
            self._update_copy_buttons()

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
        if not is_ready():
            dialog._status.setText(_error_text("setup"))

    button.clicked.connect(show_scanner)
    layout.addSpacing(8)
    layout.addWidget(button)
    return button
