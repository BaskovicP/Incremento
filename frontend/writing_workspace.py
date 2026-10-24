"""Background, profile-bound selection of a writing card to keep beside a reader."""
from aqt.operations import QueryOp
from aqt.qt import QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, Qt

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile as active_profile
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile as active_profile


_LIMIT = 2000


def load_writing_choices(col):
    entries = []
    for cid in col.find_cards('note:"Incremento Writing"')[:_LIMIT]:
        card = col.get_card(cid)
        note = col.get_note(card.nid)
        entries.append((int(cid), str(note['Title'] or cid)))
    return sorted(entries, key=lambda row: (row[1].casefold(), row[0]))


class WritingPicker(QDialog):
    def __init__(self, main, *, open_card, new_writing=None):
        super().__init__(main)
        self.main = main
        self.profile, self.collection = active_profile(), main.col
        self._closed = False
        self._generation = 0
        self._entries = []
        self._open_card = open_card
        self.setWindowTitle(t('workspace_write_beside'))
        self.resize(460, 420)
        layout = QVBoxLayout(self)
        self.status = QLabel(t('workspace_loading'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(t('workspace_search'))
        self.search.setAccessibleName(t('workspace_search'))
        layout.addWidget(self.search)
        self.choices = QListWidget(self)
        self.choices.setAccessibleName(t('workspace_writing_cards'))
        layout.addWidget(self.choices)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        self.open_button = buttons.addButton(t('workspace_open_beside'), QDialogButtonBox.ButtonRole.AcceptRole)
        self.open_button.setEnabled(False)
        buttons.accepted.connect(self.open_selected)
        buttons.rejected.connect(self.reject)
        if new_writing is not None:
            create = QPushButton(t('workspace_new_writing'), self)
            def new():
                if self._current():
                    new_writing()
                    if self._current():
                        self.reload()
            create.clicked.connect(new)
            buttons.addButton(create, QDialogButtonBox.ButtonRole.ActionRole)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.filter_entries)
        self.choices.itemSelectionChanged.connect(lambda: self.open_button.setEnabled(self.choices.currentItem() is not None))
        self.choices.itemDoubleClicked.connect(lambda item: self.open_selected())
        self.finished.connect(lambda result: self._retire())
        self.reload()

    def _current(self):
        return not self._closed and self.profile == active_profile() and self.collection is self.main.col

    def _retire(self):
        self._closed = True
        self._generation += 1

    def closeEvent(self, event):
        self._retire()
        super().closeEvent(event)

    def reload(self):
        self._generation += 1
        generation = self._generation
        self.open_button.setEnabled(False)
        def success(entries):
            if not self._current() or generation != self._generation:
                return
            self._entries = entries
            self.status.setText(t('workspace_choose_writing') if entries else t('workspace_no_writing'))
            if len(entries) >= _LIMIT:
                self.status.setText(t('workspace_writing_limit', count=_LIMIT))
            self.filter_entries()
        def failed(error):
            if self._current() and generation == self._generation:
                self.status.setText(t('workspace_load_failed'))
        QueryOp(parent=self.main, op=load_writing_choices, success=success).failure(failed).run_in_background()

    def filter_entries(self, *_args):
        self.choices.clear()
        query = self.search.text().strip().casefold()
        for card_id, title in self._entries:
            if query in title.casefold():
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, card_id)
                self.choices.addItem(item)
        if self.choices.count():
            self.choices.setCurrentRow(0)

    def open_selected(self):
        item = self.choices.currentItem()
        if item is None or not self._current():
            return
        card_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        self._open_card(card_id)
