"""Configuration for full-profile backups to a user-selected local/synced folder."""

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t

from aqt.qt import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
)
from aqt.utils import showInfo

try:
    from ..backend.backup_schedule import (
        MAX_AUTOMATIC_BACKUP_VERSIONS, normalize_policy, validate_destination,
    )
except ImportError:
    from backup_schedule import (
        MAX_AUTOMATIC_BACKUP_VERSIONS, normalize_policy, validate_destination,
    )


class AutomaticBackupDialog(QDialog):
    def __init__(self, profile: str, profile_root, policy: dict, parent=None):
        super().__init__(parent)
        self._profile_root = profile_root
        current = normalize_policy(policy)
        self.setWindowTitle(t('admin_automatic_backup_automatic_full_backups_profile', profile=profile))
        self.setMinimumWidth(530)
        layout = QVBoxLayout(self)
        hint = QLabel(
            t('admin_automatic_backup_choose_any_local_folder_including_one_synced_by')
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        folder_row = QHBoxLayout()
        self._folder = QLineEdit(current["directory"])
        self._folder.setAccessibleName(t('admin_automatic_backup_full_backup_destination_folder'))
        folder_row.addWidget(self._folder)
        browse = QPushButton(t('admin_automatic_backup_choose'))
        browse.clicked.connect(self._browse)
        folder_row.addWidget(browse)
        form.addRow(t('admin_automatic_backup_backup_folder'), folder_row)

        self._enabled = QCheckBox(t('admin_automatic_backup_enable_automatic_full_backups_for_this_anki_profile'))
        self._enabled.setChecked(current["enabled"])
        form.addRow(self._enabled)
        self._on_open = QCheckBox(t('admin_automatic_backup_back_up_when_this_profile_opens'))
        self._on_open.setChecked(current["on_open"])
        form.addRow(self._on_open)
        self._on_close = QCheckBox(t('admin_automatic_backup_back_up_when_this_profile_closes'))
        self._on_close.setChecked(current["on_close"])
        form.addRow(self._on_close)
        self._hours = QSpinBox()
        self._hours.setRange(0, 720)
        self._hours.setValue(current["interval_hours"])
        self._hours.setSuffix(t('admin_automatic_backup_hours_0_off'))
        form.addRow(t('admin_automatic_backup_while_anki_is_open_every'), self._hours)
        self._versions = QSpinBox()
        self._versions.setRange(1, MAX_AUTOMATIC_BACKUP_VERSIONS)
        self._versions.setValue(current["versions"])
        form.addRow(t('admin_automatic_backup_keep_latest_automatic_versions'), self._versions)
        layout.addLayout(form)

        notice = QLabel(
            t('admin_automatic_backup_full_backups_contain_private_cards_media_and_settings')
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("common_ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("common_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._last_success = current["last_success"]
        self._last_close_failed = current["last_close_failed"]

    def _browse(self):
        directory = QFileDialog.getExistingDirectory(
            self, t('admin_automatic_backup_choose_backup_folder'), self._folder.text()
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
                showInfo(t('admin_automatic_backup_choose_an_on_open_on_close_or_timed'))
                return
            try:
                validate_destination(self._folder.text(), self._profile_root)
            except (OSError, ValueError) as exc:
                showInfo(t('admin_automatic_backup_backup_folder_unavailable_error', error=exc))
                return
        super().accept()
