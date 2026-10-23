"""User-triggered SimpleTex account guidance and explicit credential saving."""

from aqt.qt import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, Qt

try:
    from ..backend.i18n import t
    from ..backend.simpletex_credentials import normalize_credentials
except ImportError:
    from backend.i18n import t
    from backend.simpletex_credentials import normalize_credentials


ACCOUNT_URL = "https://simpletex.net/user/center"
INSTRUCTIONS_URL = "https://doc.simpletex.cn/en/api/"


class SimpleTexSetupDialog(QDialog):
    def __init__(self, parent, *, initial_credentials, is_current, save, on_saved, open_url):
        super().__init__(parent)
        self._is_current = is_current
        self._save_credentials = save
        self._on_saved = on_saved
        self._open_url = open_url
        self._closed = False
        self.setWindowTitle(t("reader_math_setup_title"))
        self.resize(610, 540)
        layout = QVBoxLayout(self)

        def guidance(key):
            label = QLabel(t(key), self)
            label.setWordWrap(True)
            layout.addWidget(label)
            return label

        guidance("reader_math_setup_account")
        self._account_button = QPushButton(t("reader_math_setup_open_account"), self)
        self._account_button.clicked.connect(lambda: self._open(ACCOUNT_URL))
        layout.addWidget(self._account_button)
        self._application_help = guidance("reader_math_setup_application")
        self._docs_button = QPushButton(t("reader_math_setup_open_instructions"), self)
        self._docs_button.clicked.connect(lambda: self._open(INSTRUCTIONS_URL))
        layout.addWidget(self._docs_button)
        self._secret_help = guidance("reader_math_setup_paste")
        form = QFormLayout()
        self._app_id = QLineEdit(self)
        self._app_id.setAccessibleName(t("reader_math_app_id"))
        self._app_id.setMaxLength(512)
        self._secret = QLineEdit(self)
        self._secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._secret.setAccessibleName(t("reader_math_app_secret"))
        self._secret.setMaxLength(512)
        self._app_id.setText(initial_credentials[0])
        self._secret.setText(initial_credentials[1])
        form.addRow(t("reader_math_app_id"), self._app_id)
        form.addRow(t("reader_math_app_secret"), self._secret)
        layout.addLayout(form)
        guidance("reader_math_setup_storage")
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setAccessibleName(t("reader_math_status"))
        self._status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                             | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        layout.addWidget(self._status)
        self._save_button = QPushButton(t("reader_math_setup_save"), self)
        self._save_button.clicked.connect(self._save)
        layout.addWidget(self._save_button)
        cancel = QPushButton(t("reader_cancel"), self)
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)
        for button in (self._account_button, self._docs_button, self._save_button, cancel):
            button.setAutoDefault(False)
        self.finished.connect(self._retire)
        self.destroyed.connect(lambda: setattr(self, "_closed", True))

    def _current(self):
        if self._closed:
            return False
        if not self._is_current():
            self.reject()
            return False
        return True

    def _retire(self, *_args):
        if not self._closed:
            self._closed = True
            self._app_id.clear()
            self._secret.clear()

    def _open(self, url):
        if not self._current():
            return
        try:
            opened = self._open_url(url)
        except Exception:
            opened = False
        if not opened:
            self._status.setText(t("reader_math_setup_browser_failed", url=url))

    def _save(self):
        if not self._current():
            return
        try:
            credentials = normalize_credentials((self._app_id.text(), self._secret.text()))
            if not credentials[0]:
                raise ValueError("Missing credentials")
        except ValueError:
            self._status.setText(t("reader_math_error_credentials"))
            return
        try:
            self._save_credentials(credentials)
        except Exception:
            self._status.setText(t("reader_math_setup_save_failed"))
            return
        if self._current():
            self._on_saved(credentials)
            self.accept()
