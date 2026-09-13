"""Configuration for full-profile backups to a user-selected local/synced folder."""

from aqt.qt import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)
from aqt.utils import showInfo

try:
    from ..backend.backup_schedule import normalize_policy, validate_destination
except ImportError:
    from backup_schedule import normalize_policy, validate_destination


class AutomaticBackupDialog(QDialog):
    def __init__(self, profile: str, profile_root, policy: dict, parent=None):
        super().__init__(parent)
        self._profile_root = profile_root
        current = normalize_policy(policy)
        self.setWindowTitle(f"Automatic Full Backups — {profile}")
        self.setMinimumWidth(530)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Choose any local folder, including one synced by Google Drive, Dropbox, or "
            "another service. The sync app handles uploading; Incremento creates ZIPs locally."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        folder_row = QHBoxLayout()
        self._folder = QLineEdit(current["directory"])
        self._folder.setAccessibleName("Full backup destination folder")
        folder_row.addWidget(self._folder)
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(browse)
        form.addRow("Backup folder", folder_row)

        self._enabled = QCheckBox("Enable automatic full backups for this Anki profile")
        self._enabled.setChecked(current["enabled"])
        form.addRow(self._enabled)
        self._on_open = QCheckBox("Back up when this profile opens")
        self._on_open.setChecked(current["on_open"])
        form.addRow(self._on_open)
        self._on_close = QCheckBox("Back up when this profile closes")
        self._on_close.setChecked(current["on_close"])
        form.addRow(self._on_close)
        self._hours = QSpinBox()
        self._hours.setRange(0, 720)
        self._hours.setValue(current["interval_hours"])
        self._hours.setSuffix(" hours (0 = off)")
        form.addRow("While Anki is open, every", self._hours)
        self._versions = QSpinBox()
        self._versions.setRange(1, 20)
        self._versions.setValue(current["versions"])
        form.addRow("Keep latest automatic versions", self._versions)
        layout.addLayout(form)

        notice = QLabel(
            "Full backups contain private cards, media, and settings. Old automatic ZIPs "
            "for this profile are removed only after a new ZIP is verified. Backups run "
            "in the background with a visible progress window. Anki may be temporarily "
            "unavailable until the backup finishes. A close-triggered backup finishes "
            "before Anki closes the collection, so closing may take longer."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._last_success = current["last_success"]
        self._last_close_failed = current["last_close_failed"]

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Choose Backup Folder", self._folder.text()
        )
        if directory:
            self._folder.setText(directory)

    @property
    def policy(self) -> dict:
        return normalize_policy({
            "enabled": self._enabled.isChecked(),
            "directory": self._folder.text(),
            "on_open": self._on_open.isChecked(),
            "on_close": self._on_close.isChecked(),
            "interval_hours": self._hours.value(),
            "versions": self._versions.value(),
            "last_success": self._last_success,
            "last_close_failed": self._last_close_failed,
        })

    def accept(self):
        if self._enabled.isChecked():
            if not self._on_open.isChecked() and not self._on_close.isChecked() and self._hours.value() == 0:
                showInfo("Choose an on-open, on-close, or timed trigger, or disable automatic backups.")
                return
            try:
                validate_destination(self._folder.text(), self._profile_root)
            except (OSError, ValueError) as exc:
                showInfo(f"Backup folder unavailable: {exc}")
                return
        super().accept()
