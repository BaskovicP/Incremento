"""Visible, indeterminate progress for automatic full-profile backups."""

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t

from threading import Lock


def _build_dialog():
    from aqt.qt import QDialog, QLabel, QProgressBar, QVBoxLayout, Qt

    class _BackupDialog(QDialog):
        def __init__(self):
            # The close gate disables Anki's main window before starting a backup.
            # Keep this window independent so it remains visible and enabled.
            super().__init__(None)
            self.setWindowTitle(t('admin_backup_progress_incremento_automatic_backup'))
            self.setWindowModality(Qt.WindowModality.ApplicationModal)
            self.setMinimumWidth(430)

            layout = QVBoxLayout(self)
            explanation = QLabel(
                t('admin_backup_progress_automatic_full_backup_in_progress_anki_is_temporarily')
            )
            explanation.setWordWrap(True)
            layout.addWidget(explanation)
            self._stage = QLabel(t('admin_backup_progress_preparing_backup'))
            self._stage.setAccessibleName(t('admin_backup_progress_automatic_backup_stage'))
            layout.addWidget(self._stage)
            bar = QProgressBar()
            bar.setRange(0, 0)
            bar.setTextVisible(False)
            bar.setAccessibleName(t('admin_backup_progress_automatic_backup_in_progress'))
            layout.addWidget(bar)

        def set_stage(self, stage: str) -> None:
            self._stage.setText(stage)

        def reject(self) -> None:
            # Escape must not hide the only explanation for blocked Anki input.
            pass

        def closeEvent(self, event) -> None:
            event.ignore()

        def finish(self) -> None:
            self.hide()
            self.deleteLater()

    dialog = _BackupDialog()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog


class AutomaticBackupProgress:
    def __init__(self, main_window):
        self._window = main_window
        self._dialog = None
        self._lock = Lock()
        self._pending_stage = None
        self._update_queued = False

    def start(self) -> None:
        dialog = _build_dialog()
        with self._lock:
            self._dialog = dialog

    def update(self, stage: str) -> None:
        with self._lock:
            if self._dialog is None:
                return
            self._pending_stage = stage
            if self._update_queued:
                return
            self._update_queued = True
        try:
            self._window.taskman.run_on_main(self._update_on_main)
        except Exception:
            # A UI update must never invalidate an otherwise healthy backup.
            with self._lock:
                self._update_queued = False

    def _update_on_main(self) -> None:
        with self._lock:
            dialog = self._dialog
            stage = self._pending_stage
            self._update_queued = False
        if dialog is not None and stage is not None:
            dialog.set_stage(stage)

    def finish(self) -> None:
        with self._lock:
            dialog = self._dialog
            self._dialog = None
        if dialog is not None:
            dialog.finish()
