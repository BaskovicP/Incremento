import hashlib

from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode("utf-8")).hexdigest()


class PinUnlockDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Incremento – Enter PIN")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(QLabel(
            "Enter your PIN to unlock web and video browsing:"
        ))

        self._pin_edit = QLineEdit()
        self._pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin_edit.setPlaceholderText("PIN")
        self._pin_edit.returnPressed.connect(self.accept)
        layout.addWidget(self._pin_edit)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color: red; font-size: 11px;")
        layout.addWidget(self._error_lbl)

        btn_row = QHBoxLayout()
        unlock_btn = QPushButton("Unlock")
        unlock_btn.setDefault(True)
        skip_btn = QPushButton("Skip (stay locked)")
        btn_row.addStretch()
        btn_row.addWidget(unlock_btn)
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

        unlock_btn.clicked.connect(self.accept)
        skip_btn.clicked.connect(self.reject)

    def show_error(self, msg: str) -> None:
        self._error_lbl.setText(msg)

    @property
    def pin(self) -> str:
        return self._pin_edit.text()


class PinSetupDialog(QDialog):
    """Set, change, or remove the addon PIN."""

    def __init__(self, has_pin: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Incremento – Manage PIN")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        if has_pin:
            layout.addWidget(QLabel("Current PIN:"))
            self._current_edit = QLineEdit()
            self._current_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._current_edit.setPlaceholderText("Enter current PIN")
            layout.addWidget(self._current_edit)
        else:
            self._current_edit = None

        layout.addWidget(QLabel("New PIN (leave blank to remove PIN):"))
        self._new_edit = QLineEdit()
        self._new_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_edit.setPlaceholderText("New PIN")
        layout.addWidget(self._new_edit)

        layout.addWidget(QLabel("Confirm new PIN:"))
        self._confirm_edit = QLineEdit()
        self._confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_edit.setPlaceholderText("Confirm new PIN")
        layout.addWidget(self._confirm_edit)

        self._error_lbl = QLabel("")
        self._error_lbl.setStyleSheet("color: red; font-size: 11px;")
        layout.addWidget(self._error_lbl)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.reject)

    def _on_save(self) -> None:
        new_pin = self._new_edit.text()
        confirm = self._confirm_edit.text()
        if new_pin != confirm:
            self._error_lbl.setText("PINs do not match.")
            return
        self.accept()

    @property
    def current_pin(self) -> str:
        return self._current_edit.text() if self._current_edit else ""

    @property
    def new_pin(self) -> str:
        return self._new_edit.text()
