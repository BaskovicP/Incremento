"""Local extension setup without a terminal, installation, or store submission."""
from pathlib import Path

from aqt.qt import (
    QDialog, QDialogButtonBox, QFileDialog, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout, Qt,
)

try:
    from ..backend.companion_install import export_firefox
    from ..backend.i18n import t
except ImportError:
    from backend.companion_install import export_firefox
    from backend.i18n import t

try:
    from .file_shell import reveal_local_file
except ImportError:
    from file_shell import reveal_local_file

ROOT = Path(__file__).resolve().parents[1]


class CompanionSetupDialog(QDialog):
    def __init__(self, browser, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("companion_setup_title"))
        self.resize(680, 520)
        self._source = ROOT / "chrome_extensions/incremento_companion"
        layout = QVBoxLayout(self)
        instructions = QPlainTextEdit()
        instructions.setReadOnly(True)
        instructions.setPlainText(t("companion_setup_firefox_steps") if browser == "firefox"
                                  else t("companion_setup_chrome_steps"))
        layout.addWidget(instructions)
        self._path = QLineEdit(str(self._source) if browser != "firefox" else "")
        self._path.setReadOnly(True)
        self._path.setAccessibleName(t("companion_setup_file"))
        layout.addWidget(self._path)
        action = QPushButton(t("companion_setup_export") if browser == "firefox"
                             else t("companion_setup_folder"))
        action.clicked.connect(self._export if browser == "firefox" else self._show_folder)
        layout.addWidget(action)
        self._status = QLabel()
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _show_folder(self):
        if not reveal_local_file(str(self._source / "manifest.json")):
            self._status.setText(t("companion_setup_failed"))

    def _export(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, t("companion_setup_export"), "incremento-firefox.xpi", t("companion_setup_filter"))
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() != ".xpi":
            destination = destination.with_name(destination.name + ".xpi")
        try:
            export_firefox(self._source, destination)
        except (OSError, ValueError):
            self._status.setText(t("companion_setup_failed"))
            return
        self._path.setText(str(destination))
        self._status.setText(t("companion_setup_saved"))


def show_companion_setup(browser, parent=None):
    CompanionSetupDialog(browser, parent).exec()
