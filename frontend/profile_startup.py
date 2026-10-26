"""Explain slow profile upgrades while Qt continues to paint and handle events."""

from concurrent.futures import CancelledError
import time

try:
    from ..backend.i18n import t
    from ..backend.profile_startup import prepare_storage, storage_preparation_needed
except ImportError:
    from backend.i18n import t
    from backend.profile_startup import prepare_storage, storage_preparation_needed


def _create_dialog(parent):
    from aqt.qt import QDialog, QLabel, QProgressBar, QTimer, Qt, QVBoxLayout

    class PreparationDialog(QDialog):
        def __init__(self):
            super().__init__(parent)
            self.setWindowTitle(t("admin_startup_title"))
            # Startup waits for storage to be consistent. Keep its explanation
            # visible and prevent profile/reviewer actions until it is ready.
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
            self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
            self.setMinimumWidth(440)
            layout = QVBoxLayout(self)
            explanation = QLabel(t("admin_startup_explanation"), self)
            explanation.setWordWrap(True)
            layout.addWidget(explanation)
            self._stage = QLabel(t("admin_startup_files"), self)
            self._stage.setWordWrap(True)
            self._stage.setAccessibleName(t("admin_startup_stage"))
            layout.addWidget(self._stage)
            bar = QProgressBar(self)
            bar.setRange(0, 0)
            bar.setTextVisible(False)
            bar.setAccessibleName(t("admin_startup_title"))
            layout.addWidget(bar)
            self._elapsed = QLabel(self)
            layout.addWidget(self._elapsed)
            self._started = time.monotonic()
            self._timer = QTimer(self)
            self._timer.setInterval(1000)
            self._timer.timeout.connect(self._update_elapsed)
            self._timer.start()
            self._update_elapsed()

        def _update_elapsed(self):
            seconds = max(0, int(time.monotonic() - self._started))
            self._elapsed.setText(t("admin_startup_elapsed", seconds=seconds))

        def set_stage(self, stage):
            key = "admin_startup_database" if stage == "database" else "admin_startup_files"
            self._stage.setText(t(key))

        def reject(self):
            # Escape must not dismiss the explanation while startup is waiting.
            pass

        def closeEvent(self, event):
            event.ignore()

        def dispose(self):
            self._timer.stop()
            self.hide()
            self.deleteLater()

    return PreparationDialog()


def _run_preparation(window, work):
    from aqt.qt import QTimer

    dialog = _create_dialog(window)
    outcome = {}
    active = True

    def progress(stage):
        def display():
            if active:
                dialog.set_stage(stage)
        window.taskman.run_on_main(display)

    def completed(future):
        if not active:
            return
        try:
            outcome["result"] = future.result()
        except Exception as error:
            outcome["error"] = error
        dialog.accept()

    def launch():
        if not active:
            return
        try:
            # Supplemental SQLite/files only: never queue behind AnkiWeb sync
            # and never use Anki's collection from this worker.
            window.taskman.run_in_background(lambda: work(progress), completed, uses_collection=False)
        except Exception as error:
            outcome["error"] = error
            dialog.accept()

    # Enter Qt's dialog event loop before starting the potentially slow work.
    # The original profile-open hook resumes only after the worker finishes.
    QTimer.singleShot(0, launch)
    try:
        dialog.exec()
    finally:
        active = False
        dialog.dispose()
    if "error" in outcome:
        raise outcome["error"]
    if "result" not in outcome:
        raise CancelledError()
    return outcome["result"]


def prepare_profile_storage(window, addon_dir: str, profile: str):
    if not storage_preparation_needed(addon_dir, profile):
        return None
    return _run_preparation(window, lambda progress: prepare_storage(addon_dir, profile, progress=progress))
