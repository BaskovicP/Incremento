"""Choose a recording, preview a passage, then save a supplemental association."""
from pathlib import Path
from threading import Event

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                    QPushButton, QStackedWidget, QVBoxLayout, QWidget, Qt)

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.recording_links import (normalize_source, validate_segment,
                                          add_recording_link, replace_recording_link)
    from ..backend.study_resources import list_recordings, resolve_recording, resolve_document, file_signature
    from .recording_player import RecordingPlayer, timestamp
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.recording_links import normalize_source, validate_segment, add_recording_link, replace_recording_link
    from backend.study_resources import list_recordings, resolve_recording, resolve_document, file_signature
    from frontend.recording_player import RecordingPlayer, timestamp

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_dialogs = []
_importers = {}


def configure_importers(*, video, audio):
    _importers.update(video=video, audio=audio)


def parse_timestamp(text):
    """User time entry in seconds, m:ss or h:mm:ss (up to seven days)."""
    if not isinstance(text, str) or len(text) > 30:
        raise ValueError('Invalid timestamp')
    parts = text.strip().split(':')
    if not 1 <= len(parts) <= 3 or any(not p or not p.isascii() for p in parts):
        raise ValueError('Invalid timestamp')
    if len(parts) > 1 and (any(not p.isdigit() for p in parts[:-1]) or
                          any(not 0 <= float(p) < 60 for p in parts[1:])):
        raise ValueError('Invalid timestamp')
    value = 0.
    for part in parts:
        value = value * 60 + float(part)
    return validate_segment(value)[0]


class RecordingLinkDialog(QDialog):
    def __init__(self, source, *, owner=None, is_current=lambda: True, on_saved=lambda: None, existing=None):
        super().__init__(owner or mw)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(t('study_link_recording'))
        self.resize(780, 740)
        self.source = normalize_source(source)
        self.profile, self.collection = get_active_profile(), mw.col
        self.is_current, self.on_saved, self.existing = is_current, on_saved, existing
        self.cancelled = Event()
        self.request = 0
        self.recording = None
        self.source_snapshot = None
        self.rows = []
        self.visible_rows = []
        layout = QVBoxLayout(self)
        try:
            from .study_workspace import source_label
        except ImportError:
            from study_workspace import source_label
        self.summary = QLabel(source_label(self.source), self)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.status = QLabel(t('study_loading'), self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.steps = QStackedWidget(self)
        library = QWidget(self)
        picker = QVBoxLayout(library)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(t('study_search_recordings'))
        self.search.textChanged.connect(self.filter_rows)
        picker.addWidget(self.search)
        self.list = QListWidget(self)
        self.list.setAccessibleName(t('study_choose_recording'))
        self.list.itemDoubleClicked.connect(lambda *_: self.choose())
        picker.addWidget(self.list)
        imports = QHBoxLayout()
        for kind in ('video', 'audio'):
            button = QPushButton(t('study_import_' + kind), self)
            button.setEnabled(kind in _importers)
            button.clicked.connect(lambda _=False, kind=kind: self.import_recording(kind))
            imports.addWidget(button)
        refresh = QPushButton(t('study_refresh'), self)
        refresh.clicked.connect(self.reload)
        imports.addWidget(refresh)
        picker.addLayout(imports)
        self.next = QPushButton(t('study_choose_recording'), self)
        self.next.clicked.connect(self.choose)
        picker.addWidget(self.next)
        self.steps.addWidget(library)
        preview = QWidget(self)
        form = QVBoxLayout(preview)
        form.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.player = RecordingPlayer(self)
        form.addWidget(self.player, 1)
        fields = QFormLayout()
        self.label = QLineEdit(existing['label'] if existing else '', self)
        self.label.setMaxLength(240)
        fields.addRow(t('study_label'), self.label)
        self.start = QLineEdit(timestamp(existing['start']) if existing else '0:00', self)
        self.end = QLineEdit(timestamp(existing['end']) if existing and existing['end'] is not None else '', self)
        for label, edit in (('study_start', self.start), ('study_end', self.end)):
            edit.setPlaceholderText(t('study_time_hint'))
            host = QWidget(self)
            row = QHBoxLayout(host)
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(edit)
            current = QPushButton(t('study_use_position'), self)
            current.clicked.connect(lambda _=False, field=edit: field.setText(timestamp(self.player.position())))
            row.addWidget(current)
            fields.addRow(t(label), host)
        form.addLayout(fields)
        controls = QHBoxLayout()
        back = QPushButton(t('study_choose_another'), self)
        back.clicked.connect(self.back)
        controls.addWidget(back)
        self.save_button = QPushButton(t('study_save_link'), self)
        self.save_button.clicked.connect(self.save)
        controls.addWidget(self.save_button)
        form.addLayout(controls)
        self.steps.addWidget(preview)
        layout.addWidget(self.steps, 1)
        close = QPushButton(t('study_cancel'), self)
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.finished.connect(self.finish)
        if isinstance(owner, QDialog):
            owner.finished.connect(self.reject)
        self.reload()

    def current(self):
        return (not self.cancelled.is_set() and self.profile == get_active_profile()
                and self.collection is mw.col and self.is_current())

    def submit(self, work, ready):
        self.request += 1
        request, collection = self.request, self.collection
        def run(col):
            if self.cancelled.is_set() or col is not collection or request != self.request:
                return None
            return work(col)
        def done(result):
            if self.current() and request == self.request:
                ready(result)
        def failed(_error):
            if self.current() and request == self.request:
                self.save_button.setEnabled(True)
                self.status.setText(t('study_resource_unavailable'))
        QueryOp(parent=mw, op=run, success=done).failure(failed).run_in_background()

    def reload(self):
        source, profile = dict(self.source), self.profile
        def work(col):
            col.get_card(source['card_id'])
            snapshot = resolve_document(_ADDON_DIR, profile, col, source) if source['kind'] != 'card' else None
            if snapshot:
                snapshot['signature'] = file_signature(snapshot['path'])
            return snapshot, list_recordings(_ADDON_DIR, profile, col)
        def ready(result):
            self.source_snapshot, (self.rows, truncated) = result
            try:
                from .study_workspace import source_label
            except ImportError:
                from study_workspace import source_label
            title = (self.source_snapshot or {}).get('title', '')
            self.summary.setText(' · '.join(filter(None, (title, source_label(self.source), self.source['quote']))))
            self.status.setText(t('study_library_limited' if truncated else 'study_choose_recording'))
            self.filter_rows()
        self.submit(work, ready)

    def filter_rows(self, *_):
        query = self.search.text().strip().casefold()
        self.visible_rows = [row for row in self.rows if query in row['title'].casefold()]
        self.list.clear()
        for row in self.visible_rows:
            self.list.addItem(row['title'] + ('' if row['available'] else ' · ' + t('study_missing')))
        if self.visible_rows:
            selected = next((i for i, row in enumerate(self.visible_rows)
                if self.existing and row['card_id'] == self.existing['recording_card_id']), 0)
            self.list.setCurrentRow(selected)
        else:
            self.status.setText(t('study_import_help'))

    def choose(self):
        index = self.list.currentRow()
        if not 0 <= index < len(self.visible_rows) or not self.current():
            return
        card_id, profile = self.visible_rows[index]['card_id'], self.profile
        def ready(recording):
            self.recording = recording
            if not self.label.text():
                self.label.setText(recording['title'])
            # The picker previews the whole file. Saved segment fields may refer
            # to a longer, missing recording that the user is repairing.
            self.player.load(recording)
            self.steps.setCurrentIndex(1)
            self.status.setText(t('study_preview_help'))
        self.submit(lambda col: resolve_recording(_ADDON_DIR, profile, col, card_id), ready)

    def back(self):
        self.player.pause()
        self.steps.setCurrentIndex(0)

    def import_recording(self, kind):
        if self.current() and kind in _importers:
            _importers[kind]()
            if self.current():
                self.status.setText(t('study_import_refresh'))

    def save(self):
        if not self.current() or self.recording is None:
            return
        try:
            if not self.player.ready:
                raise ValueError('Recording not loaded')
            start = parse_timestamp(self.start.text())
            end = parse_timestamp(self.end.text()) if self.end.text().strip() else None
            start, end = validate_segment(start, end, duration=self.player.duration())
            label = self.label.text().strip()
            if not label:
                raise ValueError('A label is required')
        except ValueError:
            self.status.setText(t('study_invalid_segment'))
            return
        self.player.pause()
        self.save_button.setEnabled(False)
        source, profile, expected = dict(self.source), self.profile, dict(self.recording)
        expected_source, existing = self.source_snapshot, self.existing
        def work(col):
            col.get_card(source['card_id'])
            if expected_source:
                current_source = resolve_document(_ADDON_DIR, profile, col, source)
                if (current_source['path'] != expected_source['path'] or
                        file_signature(current_source['path']) != expected_source['signature']):
                    raise ValueError('Source changed')
            fresh = resolve_recording(_ADDON_DIR, profile, col, expected['card_id'])
            if fresh['path'] != expected['path'] or fresh['signature'] != expected['signature']:
                raise ValueError('Recording changed')
            if self.cancelled.is_set():
                return False
            values = dict(recording_card_id=expected['card_id'], start=start, end=end, label=label)
            if existing:
                return replace_recording_link(_ADDON_DIR, profile, existing['id'],
                                              owner_card_id=source['card_id'], **values)
            return add_recording_link(_ADDON_DIR, profile, source, **values)
        def saved(result):
            if result:
                self.on_saved()
                self.accept()
            else:
                self.save_button.setEnabled(True)
                self.status.setText(t('study_resource_unavailable'))
        self.submit(work, saved)

    def finish(self, *_):
        self.cancelled.set()
        self.player.dispose()


def open_link_dialog(source, *, owner=None, is_current=lambda: True, on_saved=lambda: None, existing=None):
    dialog = RecordingLinkDialog(source, owner=owner, is_current=is_current, on_saved=on_saved, existing=existing)
    _dialogs.append(dialog)
    dialog.finished.connect(lambda *_: _dialogs.remove(dialog) if dialog in _dialogs else None)
    dialog.show()


def reset(*_):
    for dialog in list(_dialogs):
        dialog.reject()


def add_context_actions(menu, source, *, owner=None, is_current=lambda: True):
    try:
        from .study_workspace import show_resources
    except ImportError:
        from study_workspace import show_resources
    for key, callback in (
            ('study_link_recording', lambda: open_link_dialog(source, owner=owner, is_current=is_current)),
            ('study_resources', lambda: show_resources(source))):
        action = menu.addAction(t(key))
        action.triggered.connect(lambda _=False, fn=callback: fn() if is_current() else None)
