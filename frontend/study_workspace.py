"""A supplemental study visit over the still-active Anki review card."""
from pathlib import Path
import secrets
from threading import Event

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (QButtonGroup, QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QSplitter,
                    QTimer, QVBoxLayout, QWidget, Qt)

try:
    from ..backend.anki_compat import pause_reviewer_auto_advance
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.recording_links import list_recording_links, normalize_source, remove_recording_link
    from ..backend.study_resources import (load_card_resources, resolve_document, resolve_recording,
                                          resolve_link_rows)
    from .study_visit import StudyVisit
    from .recording_player import RecordingPlayer, timestamp
    from .study_navigation import reviewer_navigation_script, set_stage_icon, style_stage_bar
except ImportError:
    from backend.anki_compat import pause_reviewer_auto_advance
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.recording_links import list_recording_links, normalize_source, remove_recording_link
    from backend.study_resources import load_card_resources, resolve_document, resolve_recording, resolve_link_rows
    from frontend.study_visit import StudyVisit
    from frontend.recording_player import RecordingPlayer, timestamp
    from frontend.study_navigation import reviewer_navigation_script, set_stage_icon, style_stage_bar

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_window = None
_review_token = ''
_review_context = None


def _context():
    reviewer = getattr(mw, 'reviewer', None)
    card = getattr(reviewer, 'card', None)
    reviewing = getattr(mw, 'state', '') == 'review' and card is not None
    return (get_active_profile(), mw.col, int(card.id) if reviewing else 0,
            reviewer.state if reviewing else '')


def source_label(source):
    if source['kind'] == 'pdf':
        return t('study_pdf_page', page=source['page'])
    if source['kind'] == 'epub':
        return t('study_epub_section', section=source['section'] + 1)
    return t('study_card')


class StudyWorkspace(QDialog):
    def __init__(self, source=None):
        super().__init__(mw)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(t('study_resources'))
        self.resize(1200, 800)
        self.visit = StudyVisit(*_context())
        self.source = normalize_source(source) if source else dict(kind='card', card_id=self.visit.card_id)
        self.reader = None
        self.reader_kind = None
        self.player = None
        self._requests = {}
        self._disabled = []
        self._items = []
        self._documents = []
        self._recordings = []
        self._last_resource_stage = 'book'
        self._review_suspended = False
        self._last_location = None
        self._resume_auto_advance = lambda: None
        # Leave the existing web document intact, including the question/answer side.
        self._suspend_reviewer()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)
        header = QHBoxLayout()
        header.setSpacing(16)
        self.stage_bar = QWidget(self)
        stages = QHBoxLayout(self.stage_bar)
        stages.setContentsMargins(5, 5, 5, 5)
        stages.setSpacing(4)
        self.stage_buttons = {}
        self.stage_group = QButtonGroup(self)
        self.stage_group.setExclusive(True)
        for stage, key in (('card', 'study_tab_card'), ('book', 'study_tab_textbook'), ('video', 'study_tab_video')):
            button = QPushButton(t(key), self.stage_bar)
            button.setObjectName('study-stage-' + stage)
            button.setAccessibleName(t(key))
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _=False, stage=stage: self.navigate(stage))
            self.stage_group.addButton(button)
            self.stage_buttons[stage] = button
            stages.addWidget(button)
        self._stage_colors = style_stage_bar(self.stage_bar, self.stage_buttons)
        self._recording_icon = 'video'
        header.addWidget(self.stage_bar)
        self.stage_buttons['card'].setEnabled(bool(self.visit.card_id))
        if not self.visit.card_id:
            self.stage_buttons['card'].setToolTip(t('study_no_active_card'))
        self.breadcrumb = QLabel('', self)
        header.addWidget(self.breadcrumb, 1)
        back = QPushButton(t('study_return_card') if self.visit.card_id else t('study_close'), self)
        back.clicked.connect(self.close)
        header.addWidget(back)
        layout.addLayout(header)
        self.status = QLabel(t('study_loading'), self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.book_host = QWidget(self)
        self.book_layout = QVBoxLayout(self.book_host)
        self.book_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter.addWidget(self.book_host)
        self.book_host.hide()
        self.side = QWidget(self)
        side = QVBoxLayout(self.side)
        self.resources = QListWidget(self)
        self.resources.setAccessibleName(t('study_resources'))
        self.resources.itemDoubleClicked.connect(lambda *_: self.open_selected())
        side.addWidget(self.resources, 1)
        row = QHBoxLayout()
        for key, fn in (('study_open', self.open_selected), ('study_refresh', self.refresh)):
            button = QPushButton(t(key), self)
            button.clicked.connect(fn)
            row.addWidget(button)
        side.addLayout(row)
        actions = QHBoxLayout()
        for key, fn in (('study_link_recording', self.link_recording), ('study_edit', self.edit_selected),
                        ('study_remove', self.remove_selected)):
            button = QPushButton(t(key), self)
            button.clicked.connect(fn)
            actions.addWidget(button)
            if key == 'study_link_recording':
                self.add_recording = button
        side.addLayout(actions)
        self.link_book = QPushButton(t('reader_reference_add'), self)
        self.link_book.clicked.connect(self.link_textbook)
        self.link_book.setVisible(self.source['kind'] == 'card')
        side.addWidget(self.link_book)
        self.play_host = QWidget(self)
        self.play_layout = QVBoxLayout(self.play_host)
        self.play_layout.setContentsMargins(0, 0, 0, 0)
        side.addWidget(self.play_host, 2)
        self.play_host.hide()
        self.back_passage = QPushButton(t('study_back_passage'), self)
        self.back_passage.clicked.connect(self.back_to_passage)
        self.back_passage.hide()
        side.addWidget(self.back_passage)
        self.splitter.addWidget(self.side)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        layout.addWidget(self.splitter, 1)
        self.finished.connect(self.finish)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_location)
        self.timer.start(400)
        self._set_stage('book')
        if self.source['kind'] == 'card':
            self.refresh()
        else:
            self.open_document(self.source)

    def current(self):
        return self.visit.current(*_context())

    def _suspend_reviewer(self):
        if not self.visit.card_id or self._review_suspended:
            return
        reviewer = mw.reviewer
        self._review_suspended = True
        self._resume_auto_advance = pause_reviewer_auto_advance(reviewer)
        bottom = getattr(reviewer, 'bottom', None)
        self._disabled = []
        for widget in (reviewer.web, getattr(bottom, 'web', bottom)):
            if widget is not None and hasattr(widget, 'isEnabled'):
                self._disabled.append((widget, widget.isEnabled()))
                widget.setEnabled(False)

    def _restore_reviewer(self, *, resume):
        if not self._review_suspended:
            return
        self._review_suspended = False
        for widget, enabled in self._disabled:
            try:
                widget.setEnabled(enabled)
            except RuntimeError:
                pass
        self._disabled = []
        if resume:
            self._resume_auto_advance()
        self._resume_auto_advance = lambda: None

    def _set_stage(self, stage):
        self.visit.navigate(stage)
        self.stage_buttons[stage].setChecked(True)
        if stage != 'card':
            self._last_resource_stage = stage
        self.play_host.setVisible(stage == 'video' and self.player is not None)
        self.back_passage.setVisible(stage == 'video' and self.reader is not None)
        self.book_host.setVisible(self.reader is not None)

    def navigate(self, stage):
        if not self.current() or stage not in self.stage_buttons:
            return
        if stage == 'card' and not self.visit.card_id:
            return
        for channel in ('document', 'recording', 'resources'):
            pending = self._requests.get(channel)
            if pending:
                pending.set()
        if self.player:
            self.player.pause()
        self._set_stage(stage)
        if stage == 'card':
            self.hide()
            self._restore_reviewer(resume=True)
            refresh_reviewer_navigation()
            mw.activateWindow()
            mw.reviewer.web.setFocus()
            return
        self._suspend_reviewer()
        self.show()
        self.raise_()
        self.activateWindow()
        if stage == 'book' and self.reader is not None:
            self.status.setText(t('study_choose_resource'))
            self.reader.view.setFocus()
        elif stage == 'video' and self.player is not None:
            self.status.setText(t('study_player_paused'))
        elif stage == 'book' and self.source['kind'] != 'card':
            self.open_document(self.source)
        else:
            self.status.setText(t('study_loading'))
            self.refresh(navigate_to=stage)

    def _choose_stage_resource(self, stage):
        if self.visit.stage != stage:
            return
        choices = self._documents if stage == 'book' else self._recordings
        available = [item for item in choices if item['available']]
        if len(available) == 1:
            if stage == 'book':
                self.open_document(available[0]['location'])
            else:
                self._open_recording_resource(available[0])
            return
        self.resources.clear()
        self._items = []
        for item in choices:
            if stage == 'book':
                self._append_document(item)
            else:
                self._append_recording(item)
        self.link_book.setVisible(stage == 'book' and not choices and self.source['kind'] == 'card')
        self.status.setText(t('study_choose_resource') if choices else
                            t('study_no_textbooks' if stage == 'book' else 'study_no_recordings'))
        if choices:
            self.resources.setCurrentRow(0)

    def submit(self, work, ready, *, channel='resources'):
        previous = self._requests.get(channel)
        if previous:
            previous.set()
        cancelled = Event()
        self._requests[channel] = cancelled
        collection = self.visit.collection
        def run(col):
            if cancelled.is_set() or col is not collection:
                return None
            return work(col)
        def done(result):
            if not cancelled.is_set() and self.current():
                ready(result)
        def failed(_error):
            if not cancelled.is_set() and self.current():
                self.status.setText(t('study_resource_unavailable'))
        QueryOp(parent=mw, op=run, success=done).failure(failed).run_in_background()

    def refresh(self, *, navigate_to=None):
        if not self.current():
            return
        source, profile = dict(self.source), self.visit.profile
        def load(col):
            if source['kind'] == 'card':
                return load_card_resources(_ADDON_DIR, profile, col, source['card_id'])
            rows = list_recording_links(_ADDON_DIR, profile, source=source)
            return dict(documents=[], recordings=resolve_link_rows(_ADDON_DIR, profile, col, rows))
        def ready(result):
            if source['kind'] == 'card':
                self._documents = result['documents']
            self._recordings = result['recordings']
            self.resources.clear()
            self._items = []
            for item in result['documents']:
                self._append_document(item)
            for item in result['recordings']:
                self._append_recording(item)
            self.status.setText(t('study_choose_resource') if self._items else
                t('study_no_recordings') if source['kind'] != 'card' or self.visit.stage == 'video'
                else t('study_no_textbooks'))
            if self._items:
                self.resources.setCurrentRow(0)
            if navigate_to:
                self._choose_stage_resource(navigate_to)
        self.submit(load, ready)

    def _append_document(self, item):
        self._add_item('document', item, item['title'] + ' · ' + source_label(item['location']))

    def _append_recording(self, item):
        title = item['label'] or (item['recording'] or {}).get('title', '')
        text = title + ' · ' + timestamp(item['start'])
        if item['end'] is not None:
            text += '–' + timestamp(item['end'])
        self._add_item('recording', item, text)

    def _add_item(self, kind, item, text):
        if not item['available']:
            text += ' · ' + t('study_missing')
        self.resources.addItem(text)
        self._items.append((kind, item))

    def selected(self):
        index = self.resources.currentRow()
        return self._items[index] if 0 <= index < len(self._items) else (None, None)

    def open_selected(self):
        kind, item = self.selected()
        if item is None or not self.current():
            return
        if kind == 'document':
            self.open_document(item['location'])
        else:
            self._open_recording_resource(item)

    def _open_recording_resource(self, item):
        source = item['source']
        same_passage = all(source.get(key) == self.source.get(key)
                           for key in ('kind', 'card_id', 'page', 'section'))
        if source['kind'] != 'card' and (self.reader is None or not same_passage):
            self.open_document(source, after=lambda: self.open_recording(item))
        else:
            self.open_recording(item)

    def open_document(self, source, *, after=None):
        source, profile = normalize_source(source), self.visit.profile
        pending = self._requests.get('recording')
        if pending:
            pending.set()
        if self.player:
            self.player.pause()
        def work(col):
            snapshot = resolve_document(_ADDON_DIR, profile, col, source)
            if source['kind'] == 'pdf':
                from .pdf_page_links import pdf_page_count
                count = pdf_page_count(snapshot['path'])
                if source['page'] > count:
                    raise ValueError('Page unavailable')
                snapshot['max_page'] = min(count, snapshot['max_page'])
                return snapshot
            from .epub_reference_workspace import _load
            return _load(col, profile, source)
        def ready(result):
            if self.reader:
                self.reader.close()
            if source['kind'] == 'pdf':
                from . import pdf_reference_workspace as pdf
                self.reader = pdf.ReferenceWindow(result, profile=profile, page=source['page'],
                    scroll_ratio=source['scroll'], max_page=result['max_page'], beside=True, owner=self,
                    excerpt=source['quote'], page_y=source.get('page_y'), embedded=True)
                pdf._windows.append(self.reader)
            else:
                from . import epub_reference_workspace as epub
                self.reader = epub.EpubReferenceWindow(result, source, profile=profile, owner=self, embedded=True)
                epub._windows.append(self.reader)
            self.source = source
            self.reader_kind = source['kind']
            self._last_location = (source['card_id'], source.get('page', source.get('section')))
            self.book_layout.addWidget(self.reader)
            self.reader.show()
            self.book_host.show()
            self.link_book.hide()
            self._set_stage('book')
            self.breadcrumb.setText(source_label(source))
            self.refresh()
            if after:
                after()
        self.submit(work, ready, channel='document')

    def open_recording(self, item):
        profile = self.visit.profile
        def ready(recording):
            if self.player is None:
                self.player = RecordingPlayer(self)
                self.play_layout.addWidget(self.player)
            self.player.load(recording, start=item['start'], end=item['end'])
            self.stage_buttons['video'].setText(t('study_tab_audio' if recording.get('kind') == 'audio' else 'study_tab_video'))
            self.stage_buttons['video'].setAccessibleName(self.stage_buttons['video'].text())
            self._recording_icon = 'audio' if recording.get('kind') == 'audio' else 'video'
            set_stage_icon(self.stage_buttons['video'], self._recording_icon, self._stage_colors)
            self._set_stage('video')
            self.status.setText(t('study_player_paused'))
        self.submit(lambda col: resolve_recording(_ADDON_DIR, profile, col, item['recording_card_id']),
                    ready, channel='recording')

    def back_to_passage(self):
        self.navigate('book')

    def poll_location(self):
        if not self.current():
            self.close()
            return
        if self.reader is None:
            return
        if self.reader_kind == 'pdf':
            state = self.reader.state
            self.source.update(page=state.page, scroll=state.scroll_ratio)
        else:
            self.source.update(self.reader.location)
        key = (self.source['card_id'], self.source.get('page', self.source.get('section')))
        if key != self._last_location:
            self._last_location = key
            self.source.pop('page_y', None)
            self.source['quote'] = ''
            self.breadcrumb.setText(source_label(self.source))
            self.refresh()

    def link_recording(self, *, existing=None):
        from .recording_link_dialog import open_link_dialog
        self.poll_location()
        if not self.current():
            return
        if self.player:
            self.player.pause()
        def create(source):
            open_link_dialog(source, owner=self, is_current=self.current, on_saved=self.refresh, existing=existing)
        if self.reader_kind == 'epub' and existing is None:
            self.reader.capture(lambda location: create(dict(location, kind='epub')))
        else:
            create(existing['source'] if existing else self.source)

    def edit_selected(self):
        kind, row = self.selected()
        if kind == 'recording' and row['id']:
            self.link_recording(existing=row)

    def remove_selected(self):
        kind, row = self.selected()
        if kind != 'recording' or not row['id']:
            return
        profile, source, link_id = self.visit.profile, dict(row['source']), row['id']
        # Removing an association leaves both original resources intact.
        self.submit(lambda col: remove_recording_link(_ADDON_DIR, profile, link_id,
                    owner_card_id=source['card_id']), lambda _: self.refresh(), channel='write')

    def link_textbook(self):
        from .document_link_ui import choose_pdf
        try:
            from ..backend.document_links import add_document_link
        except ImportError:
            from backend.document_links import add_document_link
        source, profile = dict(self.source), self.visit.profile
        def chosen(location):
            target = dict(kind='pdf', card_id=location['card_id'], page=location['page'],
                          scroll=location['scroll_ratio'], page_y=location.get('page_y'))
            def save(col):
                col.get_card(source['card_id'])
                snapshot = resolve_document(_ADDON_DIR, profile, col, target)
                if snapshot['path'] != location['path']:
                    raise ValueError('Document changed')
                return add_document_link(_ADDON_DIR, profile, source_card_id=source['card_id'],
                    source_kind='card', source_page=0, quote='', target_card_id=target['card_id'],
                    target_page=target['page'], target_scroll=target['scroll'], target_y=target.get('page_y'))
            self.submit(save, lambda _: self.refresh(), channel='write')
        choose_pdf(chosen, is_current=self.current)

    def finish(self, *_):
        global _window
        if self.visit.closed:
            return
        valid = self.visit.finish(*_context())
        if _window is self:
            _window = None
        self.timer.stop()
        for cancelled in self._requests.values():
            cancelled.set()
        if self.player:
            self.player.dispose()
        if self.reader:
            try:
                self.reader.close()
            except RuntimeError:
                pass  # A profile-reset hook may already have destroyed this pane.
        self._restore_reviewer(resume=valid)
        if valid and self.visit.card_id:
            refresh_reviewer_navigation()
            mw.reviewer.web.setFocus()

    def closeEvent(self, event):
        # Qt does not always emit QDialog.finished when an already-hidden visit
        # closes after the reviewer advances. Retire it before native teardown.
        self.finish()
        super().closeEvent(event)


def show_resources(source=None):
    global _window
    if source is None and _window is not None and _window.current():
        _window.navigate(_window._last_resource_stage)
        return
    if _window is not None:
        _window.close()
    _window = StudyWorkspace(source)
    window = _window
    def finished(*_):
        global _window
        if _window is window:
            _window = None
    window.finished.connect(finished)
    window.show()


def reset(*_):
    global _review_token, _review_context
    _review_token, _review_context = '', None
    if _window is not None:
        _window.close()


def reviewer_shown(*_):
    global _review_token, _review_context
    context = _context()
    if (_window is not None and not _window.visit.closed and _window.visit.stage == 'card'
            and context[0] == _window.visit.profile and context[1] is _window.visit.collection
            and context[2] == _window.visit.card_id):
        _window.visit.side = context[3]
    else:
        reset()
    if not context[2]:
        return
    _review_context = context
    _review_token = secrets.token_urlsafe(24)
    refresh_reviewer_navigation()


def refresh_reviewer_navigation():
    if not _review_token or _review_context != _context():
        return
    command = 'incremento_study:' + _review_token
    if _window is not None and _window.current():
        routes = [dict(stage=stage, label=button.text(), command=command + ':' + stage, current=stage == 'card',
                       icon=_window._recording_icon if stage == 'video' else stage)
                  for stage, button in _window.stage_buttons.items()]
    else:
        routes = [dict(stage='resources', label=t('study_resources'), command=command, current=False)]
    mw.reviewer.web.eval(reviewer_navigation_script(routes, t('study_resources')))


def on_js_message(handled, message, context):
    if not isinstance(message, str) or not message.startswith('incremento_study:'):
        return handled
    parts = message.removeprefix('incremento_study:').split(':')
    if (context is getattr(mw, 'reviewer', None) and _review_token and len(parts) in (1, 2)
            and parts[0].isascii() and secrets.compare_digest(parts[0], _review_token)
            and _review_context == _context()):
        if len(parts) == 1:
            show_resources()
        elif parts[1] in ('card', 'book', 'video') and _window is not None:
            _window.navigate(parts[1])
    return True, None
