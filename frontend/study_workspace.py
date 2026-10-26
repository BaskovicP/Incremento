"""A supplemental study visit over the still-active Anki review card."""
from pathlib import Path
import json
import secrets
from threading import Event

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (QDialog, QHBoxLayout, QLabel, QListWidget, QPushButton, QSplitter,
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
except ImportError:
    from backend.anki_compat import pause_reviewer_auto_advance
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.recording_links import list_recording_links, normalize_source, remove_recording_link
    from backend.study_resources import load_card_resources, resolve_document, resolve_recording, resolve_link_rows
    from frontend.study_visit import StudyVisit
    from frontend.recording_player import RecordingPlayer, timestamp

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
        self._last_location = None
        self._resume_auto_advance = lambda: None
        # Leave the existing web document intact, including the question/answer side.
        if self.visit.card_id:
            reviewer = mw.reviewer
            self._resume_auto_advance = pause_reviewer_auto_advance(reviewer)
            bottom = getattr(reviewer, 'bottom', None)
            for widget in (reviewer.web, getattr(bottom, 'web', bottom)):
                if widget is not None and hasattr(widget, 'isEnabled'):
                    self._disabled.append((widget, widget.isEnabled()))
                    widget.setEnabled(False)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.breadcrumb = QLabel(t('study_journey'), self)
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
        if self.source['kind'] == 'card':
            self.refresh()
        else:
            self.open_document(self.source)

    def current(self):
        return self.visit.current(*_context())

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

    def refresh(self):
        if not self.current():
            return
        source, profile = dict(self.source), self.visit.profile
        def load(col):
            if source['kind'] == 'card':
                return load_card_resources(_ADDON_DIR, profile, col, source['card_id'])
            rows = list_recording_links(_ADDON_DIR, profile, source=source)
            return dict(documents=[], recordings=resolve_link_rows(_ADDON_DIR, profile, col, rows))
        def ready(result):
            self.resources.clear()
            self._items = []
            for item in result['documents']:
                text = item['title'] + ' · ' + source_label(item['location'])
                self._add_item('document', item, text)
            for item in result['recordings']:
                title = item['label'] or (item['recording'] or {}).get('title', '')
                text = title + ' · ' + timestamp(item['start'])
                if item['end'] is not None:
                    text += '–' + timestamp(item['end'])
                self._add_item('recording', item, text)
            self.status.setText(t('study_choose_resource') if self._items else t('study_no_resources'))
            if self._items:
                self.resources.setCurrentRow(0)
        self.submit(load, ready)

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
            self.visit.navigate('book')
            self.breadcrumb.setText(t('study_journey') + ' · ' + source_label(source))
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
            self.play_host.show()
            self.back_passage.setVisible(self.reader is not None)
            self.visit.navigate('video')
            self.status.setText(t('study_player_paused'))
        self.submit(lambda col: resolve_recording(_ADDON_DIR, profile, col, item['recording_card_id']),
                    ready, channel='recording')

    def back_to_passage(self):
        if self.player:
            self.player.pause()
        self.play_host.hide()
        self.back_passage.hide()
        self.visit.navigate('book')
        if self.reader:
            self.reader.view.setFocus()

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
            self.breadcrumb.setText(t('study_journey') + ' · ' + source_label(self.source))
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
        if self.visit.closed:
            return
        valid = self.visit.finish(*_context())
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
        for widget, enabled in self._disabled:
            try:
                widget.setEnabled(enabled)
            except RuntimeError:
                pass
        if valid and self.visit.card_id:
            self._resume_auto_advance()
            mw.reviewer.web.setFocus()


def show_resources(source=None):
    global _window
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
    reset()
    context = _context()
    if not context[2]:
        return
    _review_context = context
    _review_token = secrets.token_urlsafe(24)
    # App-created DOM only. No user title/HTML is inserted into this control.
    payload = json.dumps(dict(label=t('study_resources'), command='incremento_study:' + _review_token))
    mw.reviewer.web.eval("(() => {document.getElementById('incremento-study-resources')?.remove();"
        "const d=" + payload + "; const b=document.createElement('button');b.id='incremento-study-resources';"
        "b.type='button';b.textContent=d.label;b.style.cssText='display:block;margin:18px auto;padding:7px 14px';"
        "b.onclick=()=>pycmd(d.command);document.body.appendChild(b);})();")


def on_js_message(handled, message, context):
    if not isinstance(message, str) or not message.startswith('incremento_study:'):
        return handled
    if (context is getattr(mw, 'reviewer', None) and _review_token
            and secrets.compare_digest(message, 'incremento_study:' + _review_token)
            and _review_context == _context()):
        show_resources()
    return True, None
