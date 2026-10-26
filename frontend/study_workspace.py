"""A supplemental study visit over the still-active Anki review card."""
from pathlib import Path
import secrets
from threading import Event

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                    QPushButton, QScrollArea, QSize, QSplitter, QTimer, QVBoxLayout, QWidget, Qt)

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
    from .study_surface import StudySurface
except ImportError:
    from backend.anki_compat import pause_reviewer_auto_advance
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.recording_links import list_recording_links, normalize_source, remove_recording_link
    from backend.study_resources import load_card_resources, resolve_document, resolve_recording, resolve_link_rows
    from frontend.study_visit import StudyVisit
    from frontend.recording_player import RecordingPlayer, timestamp
    from frontend.study_navigation import reviewer_navigation_script, set_stage_icon, style_stage_bar
    from frontend.study_surface import StudySurface

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
        self._recording_summary = None
        self.surface = StudySurface(mw, self)
        # Leave the existing web document intact, including the question/answer side.
        self._suspend_reviewer()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)
        header_panel = QFrame(self)
        header_panel.setObjectName('study-header')
        header = QHBoxLayout(header_panel)
        header.setContentsMargins(16, 12, 16, 12)
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
        self.breadcrumb.setWordWrap(True)
        header.addWidget(self.breadcrumb, 1)
        layout.addWidget(header_panel)
        self.context_panel = QFrame(self)
        self.context_panel.setObjectName('study-context')
        context_row = QHBoxLayout(self.context_panel)
        context_row.setContentsMargins(16, 12, 16, 12)
        context_copy = QVBoxLayout()
        self.context_state = QLabel(t('study_answer_revealed' if self.visit.side == 'answer' else 'study_question_side'), self)
        self.context_state.setObjectName('study-context-state')
        self.context_title = QLabel(t('study_review_card'), self)
        self.context_title.setTextFormat(Qt.TextFormat.PlainText)
        self.context_title.setWordWrap(True)
        self.context_title.setObjectName('study-context-title')
        context_copy.addWidget(self.context_state)
        context_copy.addWidget(self.context_title)
        context_row.addLayout(context_copy, 1)
        back = QPushButton(t('study_return_card') if self.visit.card_id else t('study_close'), self)
        back.clicked.connect(lambda: self.navigate('card') if self.visit.card_id else self.close())
        (context_row if self.visit.card_id else header).addWidget(back)
        layout.addWidget(self.context_panel)
        self.context_panel.setVisible(bool(self.visit.card_id))
        self.status = QLabel(t('study_loading'), self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(14)
        self.book_host = QFrame(self)
        self.book_host.setObjectName('study-book-panel')
        self.book_layout = QVBoxLayout(self.book_host)
        self.book_layout.setContentsMargins(12, 12, 12, 12)
        self.book_layout.setSpacing(10)
        self.book_title = QLabel(t('study_tab_textbook'), self.book_host)
        self.book_title.setObjectName('study-panel-title')
        self.book_title.setTextFormat(Qt.TextFormat.PlainText)
        self.book_title.setWordWrap(True)
        self.book_position = QLabel('', self.book_host)
        self.book_position.setObjectName('study-panel-detail')
        self.book_layout.addWidget(self.book_title)
        self.book_layout.addWidget(self.book_position)
        self.splitter.addWidget(self.book_host)
        self.book_host.hide()
        self.side = QWidget(self)
        side = QVBoxLayout(self.side)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(14)
        self.play_host = QFrame(self)
        self.play_host.setObjectName('study-player-panel')
        player_layout = QVBoxLayout(self.play_host)
        player_layout.setContentsMargins(16, 16, 16, 16)
        self.player_title = QLabel(t('study_tab_video'), self.play_host)
        self.player_title.setObjectName('study-panel-title')
        self.player_title.setTextFormat(Qt.TextFormat.PlainText)
        self.player_title.setWordWrap(True)
        self.player_segment = QLabel('', self.play_host)
        self.player_segment.setObjectName('study-panel-detail')
        self.player_segment.setWordWrap(True)
        player_layout.addWidget(self.player_title)
        player_layout.addWidget(self.player_segment)
        player_body = QWidget(self.play_host)
        self.play_layout = QVBoxLayout(player_body)
        self.play_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.addWidget(player_body, 1)
        self.back_passage = QPushButton(t('study_back_passage'), self.play_host)
        self.back_passage.clicked.connect(self.back_to_passage)
        player_layout.addWidget(self.back_passage)
        side.addWidget(self.play_host, 2)
        self.play_host.hide()
        self.back_passage.hide()
        self.more_resources = QPushButton(t('study_other_resources'), self)
        self.more_resources.setObjectName('study-more-resources')
        self.more_resources.setCheckable(True)
        self.more_resources.clicked.connect(self._sync_panels)
        side.addWidget(self.more_resources)
        self.more_resources.hide()
        self.resource_panel = QFrame(self)
        self.resource_panel.setObjectName('study-resource-panel')
        resources_layout = QVBoxLayout(self.resource_panel)
        resources_layout.setContentsMargins(16, 16, 16, 16)
        resources_layout.setSpacing(10)
        resource_heading = QLabel(t('study_resources'), self.resource_panel)
        resource_heading.setObjectName('study-panel-title')
        resources_layout.addWidget(resource_heading)
        self.resource_intro = QLabel(t('study_card_hint'), self.resource_panel)
        self.resource_intro.setWordWrap(True)
        self.resource_intro.setObjectName('study-panel-detail')
        resources_layout.addWidget(self.resource_intro)
        self.resources = QListWidget(self.resource_panel)
        self.resources.setObjectName('study-resource-list')
        self.resources.setFrameShape(QFrame.Shape.NoFrame)
        self.resources.setSpacing(6)
        self.resources.setIconSize(QSize(20, 20))
        self.resources.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.resources.setAccessibleName(t('study_resources'))
        self.resources.itemDoubleClicked.connect(lambda *_: self.open_selected())
        resources_layout.addWidget(self.resources, 1)
        self.open_resource = QPushButton(t('study_open'), self.resource_panel)
        self.open_resource.setObjectName('study-open-resource')
        self.open_resource.clicked.connect(self.open_selected)
        resources_layout.addWidget(self.open_resource)
        self.add_recording = QPushButton(t('study_link_recording'), self.resource_panel)
        self.add_recording.clicked.connect(self.link_recording)
        resources_layout.addWidget(self.add_recording)
        self.link_book = QPushButton(t('reader_reference_add'), self.resource_panel)
        self.link_book.clicked.connect(self.link_textbook)
        self.link_book.setVisible(self.source['kind'] == 'card')
        resources_layout.addWidget(self.link_book)
        actions = QHBoxLayout()
        for key, fn in (('study_edit', self.edit_selected), ('study_remove', self.remove_selected),
                        ('study_refresh', self.refresh)):
            button = QPushButton(t(key), self)
            button.clicked.connect(fn)
            actions.addWidget(button)
        resources_layout.addLayout(actions)
        side.addWidget(self.resource_panel, 1)
        self.splitter.addWidget(self.side)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.content_scroll = QScrollArea(self)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setWidget(self.splitter)
        layout.addWidget(self.content_scroll, 1)
        layout.addWidget(self.status)
        self._style_workspace()
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

    def _style_workspace(self):
        c = self._stage_colors
        self.setObjectName('study-workspace')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QWidget#study-workspace {{ background: {c['surface']}; color: {c['ink']}; }}
            QFrame#study-header, QFrame#study-book-panel, QFrame#study-resource-panel,
            QFrame#study-player-panel {{ background: {c['paper']}; border: 1px solid {c['border']}; border-radius: 10px; }}
            QFrame#study-context {{ background: {c['selected']}; border: 1px solid {c['border']}; border-radius: 8px; }}
            QLabel#study-panel-title, QLabel#study-context-title {{ color: {c['ink']}; font-weight: 600; }}
            QLabel#study-panel-detail, QLabel#study-context-state {{ color: {c['foreground']}; }}
            QListWidget#study-resource-list {{ background: transparent; color: {c['ink']}; border: 0; }}
            QListWidget#study-resource-list::item {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 10px; }}
            QListWidget#study-resource-list::item:selected {{ background: {c['selected']}; color: {c['accent']}; border-color: {c['accent']}; }}
            QFrame#study-resource-panel QPushButton, QFrame#study-player-panel QPushButton,
            QFrame#study-context QPushButton, QPushButton#study-more-resources {{ padding: 7px 12px; border: 1px solid {c['border']}; border-radius: 6px; background: {c['paper']}; color: {c['ink']}; }}
            QFrame#study-resource-panel QPushButton#study-open-resource {{ background: {c['selected']}; color: {c['accent']}; font-weight: 600; }}
            QFrame#study-resource-panel QPushButton:hover, QFrame#study-player-panel QPushButton:hover,
            QFrame#study-context QPushButton:hover, QPushButton#study-more-resources:hover {{ border-color: {c['accent']}; }}
            QFrame#study-resource-panel QPushButton:disabled {{ color: {c['foreground']}; background: {c['surface']}; }}
        """)

    def present(self):
        self.surface.present()
        self.context_state.setText(t('study_answer_revealed' if self.visit.side == 'answer' else 'study_question_side'))
        context = _context()
        evaluate = getattr(getattr(getattr(mw, 'reviewer', None), 'web', None), 'evalWithCallback', None)
        if self.visit.card_id and callable(evaluate):
            def captured(value):
                if self.current() and _context() == context and isinstance(value, str) and value.strip():
                    self.context_title.setText(' '.join(value.split())[:240])
            evaluate("(() => {const q=document.getElementById('qa');return q ? q.innerText.slice(0,320) : '';})()", captured)
        self._adapt_panels()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'splitter'):
            self._adapt_panels()

    def _adapt_panels(self):
        orientation = Qt.Orientation.Vertical if self.width() < 880 else Qt.Orientation.Horizontal
        if self.splitter.orientation() != orientation:
            self.splitter.setOrientation(orientation)
            self.splitter.setSizes([500, 400])

    def _sync_panels(self, *_):
        video = self.visit.stage == 'video' and self.player is not None
        self.play_host.setVisible(video)
        self.back_passage.setVisible(video and self.reader is not None)
        self.book_host.setVisible(self.reader is not None)
        self.more_resources.setVisible(video)
        self.resource_panel.setVisible(not video or self.more_resources.isChecked())
        chooser = self.reader is None and not video
        self.resource_panel.setMaximumWidth(640 if chooser else 16777215)
        self.side.layout().setAlignment(self.resource_panel,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop if chooser else Qt.AlignmentFlag(0))
        self.resources.setVisible(bool(self._items))
        self.resources.setMaximumHeight(200 if video else 360 if chooser else 16777215)
        self.open_resource.setEnabled(bool(self._items))
        self.resource_intro.setText(t('study_card_hint') if self._items else
            t('study_no_textbooks' if self.source['kind'] == 'card' and self.visit.stage == 'book' else 'study_no_recordings'))

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
        self._sync_panels()

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
            self.surface.leave()
            self._restore_reviewer(resume=True)
            refresh_reviewer_navigation()
            mw.activateWindow()
            mw.reviewer.web.setFocus()
            return
        self._suspend_reviewer()
        self.present()
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
        self._sync_panels()

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
            self._sync_panels()
        self.submit(load, ready)

    def _append_document(self, item):
        self._add_item('document', item, (item['title'] or t('study_tab_textbook')) + '\n' + source_label(item['location']))

    def _append_recording(self, item):
        title = item['label'] or (item['recording'] or {}).get('title', '')
        text = (title or t('study_tab_video')) + '\n' + timestamp(item['start'])
        if item['end'] is not None:
            text += '–' + timestamp(item['end'])
        self._add_item('recording', item, text)

    def _add_item(self, kind, item, text):
        if not item['available']:
            text += ' · ' + t('study_missing')
        row = QListWidgetItem(text)
        row.setToolTip(text)
        row.setIcon(self.stage_buttons['book' if kind == 'document' else 'video'].icon())
        row.setSizeHint(QSize(160, self.resources.fontMetrics().height() * 2 + 32))
        self.resources.addItem(row)
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
            self.book_layout.addWidget(self.reader, 1)
            self.book_title.setText(result.get('title') or t('study_tab_textbook'))
            self.book_position.setText(source_label(source))
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
            self.player_title.setText(recording.get('title') or t('study_tab_video'))
            segment = timestamp(item['start'])
            if item['end'] is not None:
                segment += '–' + timestamp(item['end'])
            self.player_segment.setText(segment + ' · ' + source_label(item['source']))
            self._recording_summary = dict(title=item['label'] or self.player_title.text(),
                                          detail=self.player_segment.text())
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
            self.book_position.setText(source_label(self.source))
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
        self.surface.leave(detach=True)
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
    window.present()


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
        routes = [dict(stage=stage, label=t(key), command=command + ':' + stage, current=stage == 'card')
                  for stage, key in (('card', 'study_tab_card'), ('book', 'study_tab_textbook'), ('video', 'study_tab_video'))]
    book = dict(stage='book', title=t('study_tab_textbook'), detail=t('study_read_hint'),
                action=t('study_read_passage'), command=command + ':book')
    video = dict(stage='video', title=t('study_tab_video'), detail=t('study_recording_hint'),
                 action=t('study_open_recording'), command=command + ':video')
    if _window is not None and _window.current():
        if _window.reader is not None:
            book.update(title=_window.book_title.text(), detail=source_label(_window.source))
        elif _window._documents:
            item = _window._documents[0]
            book.update(title=item['title'] or book['title'], detail=source_label(item['location']))
        if _window._recording_summary:
            video.update(_window._recording_summary)
        elif _window._recordings:
            item = _window._recordings[0]
            video.update(title=item['label'] or (item.get('recording') or {}).get('title') or video['title'],
                         detail=timestamp(item['start']))
    workspace = dict(heading=t('study_review_card'),
        state=t('study_answer_revealed' if _context()[3] == 'answer' else 'study_question_side'),
        resources_label=t('study_resources'), hint=t('study_card_hint'), tiles=[book, video])
    mw.reviewer.web.eval(reviewer_navigation_script(routes, t('study_resources'), workspace=workspace))


def on_js_message(handled, message, context):
    if not isinstance(message, str) or not message.startswith('incremento_study:'):
        return handled
    parts = message.removeprefix('incremento_study:').split(':')
    if (context is getattr(mw, 'reviewer', None) and _review_token and len(parts) in (1, 2)
            and parts[0].isascii() and secrets.compare_digest(parts[0], _review_token)
            and _review_context == _context()):
        if len(parts) == 1:
            show_resources()
        elif parts[1] in ('card', 'book', 'video'):
            if _window is None and parts[1] != 'card':
                show_resources()
            if _window is not None:
                _window.navigate(parts[1])
    return True, None
