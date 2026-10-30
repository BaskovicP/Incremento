"""A supplemental study visit over the still-active Anki review card."""
from pathlib import Path
from copy import deepcopy
import secrets
from threading import Event

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (QBoxLayout, QButtonGroup, QDialog, QFrame, QHBoxLayout, QKeySequence, QLabel, QListWidget, QListWidgetItem, QMenu,
                    QPushButton, QScrollArea, QShortcut, QSize, QSizePolicy, QSplitter, QStackedWidget, QTimer, QVBoxLayout, QWidget, Qt)
from PyQt6 import sip

try:
    from ..backend.config_service import load_addon_config, save_addon_config, configured_study_workspace_enabled
    from ..backend.anki_compat import pause_reviewer_auto_advance
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.recording_links import list_recording_links, normalize_source, remove_recording_link
    from ..backend.study_resources import (load_card_resources, resolve_document, resolve_recording,
                                          resolve_link_rows)
    from .study_visit import StudyVisit
    from .recording_player import RecordingPlayer, timestamp
    from .study_navigation import reviewer_navigation_script, reviewer_navigation_clear_script, set_stage_icon, style_stage_bar
    from .study_surface import StudySurface
    from .study_availability import card_availability, resource_availability
    from .study_focus import StudyFocus
    from .study_resource_widgets import ResourcePicker, StageButton, ElidedLabel, resource_styles
    from .study_resource_titles import display_resource_title
except ImportError:
    from backend.config_service import load_addon_config, save_addon_config, configured_study_workspace_enabled
    from backend.anki_compat import pause_reviewer_auto_advance
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.recording_links import list_recording_links, normalize_source, remove_recording_link
    from backend.study_resources import load_card_resources, resolve_document, resolve_recording, resolve_link_rows
    from frontend.study_visit import StudyVisit
    from frontend.recording_player import RecordingPlayer, timestamp
    from frontend.study_navigation import reviewer_navigation_script, reviewer_navigation_clear_script, set_stage_icon, style_stage_bar
    from frontend.study_surface import StudySurface
    from frontend.study_availability import card_availability, resource_availability
    from frontend.study_focus import StudyFocus
    from frontend.study_resource_widgets import ResourcePicker, StageButton, ElidedLabel, resource_styles
    from frontend.study_resource_titles import display_resource_title

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_ADDON_PKG = __name__.split('.')[0]
_window = None
_review_token = ''
_review_context = None
_resource_context = None
_resource_request = None
_review_resources = None
_resource_failed = False


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
    def __init__(self, source=None, *, initial_stage='book'):
        super().__init__(mw)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(t('study_resources'))
        self.resize(1200, 800)
        self.visit = StudyVisit(*_context())
        self._compact_resources = source is None
        self.active_sheet = None
        self._card_title = ''
        try:
            cfg = load_addon_config(mw.addonManager, _ADDON_PKG)
            self._layout_preferences = deepcopy(cfg['study_layout_by_profile'].get(self.visit.profile, {}))
        except Exception:
            self._layout_preferences = {}
        self._layout_changes = {}
        self._layout_save_warned = False
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(250)
        self._layout_save_timer.timeout.connect(self._flush_layout_preferences)
        self._layout_restore_timer = QTimer(self)
        self._layout_restore_timer.setSingleShot(True)
        self._layout_restore_timer.timeout.connect(self._restore_preferred_focus)
        self.source = normalize_source(source) if source else dict(kind='card', card_id=self.visit.card_id)
        self.reader = None
        self.reader_kind = None
        self.player = None
        self._requests = {}
        self._disabled = []
        self._items = []
        self._documents = []
        self._recordings = []
        self._picker_items = []
        self._selected_document = None
        self._selected_recording = None
        self._document_positions = {}
        self._document_zooms = {}
        self._recording_positions = {}
        self._resources_known = False
        self._resources_failed = False
        self._resources_source = None
        self._last_resource_stage = 'book'
        self._review_suspended = False
        self._last_location = None
        self._resume_auto_advance = lambda: None
        self._recording_summary = None
        self.surface = StudySurface(mw, self)
        self.focus_stage = None
        self.focus_screen = StudyFocus(self, mw)
        self._pane_mode = None
        self._pane_sizes = {
            (orientation, stage): [round(ratio * 10000), round((1 - ratio) * 10000)]
            for stage, view in self._layout_preferences.items()
            for key, orientation in (('horizontal', Qt.Orientation.Horizontal), ('vertical', Qt.Orientation.Vertical))
            if (ratio := view.get(key)) is not None
        }
        # Leave the existing web document intact, including the question/answer side.
        self._suspend_reviewer()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header_panel = self.header_panel = QFrame(self)
        header_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header_panel.setObjectName('study-header')
        header = QHBoxLayout(header_panel)
        header.setContentsMargins(16, 12, 16, 12)
        header.setSpacing(16)
        self.stage_bar = QWidget(self)
        stages = QHBoxLayout(self.stage_bar)
        stages.setContentsMargins(5, 5, 5, 5)
        stages.setSpacing(4)
        self.stage_buttons = {}
        self.stage_status = {}
        self.stage_group = QButtonGroup(self)
        self.stage_group.setExclusive(True)
        for stage, key in (('card', 'study_tab_card'), ('book', 'study_tab_textbook'), ('video', 'study_tab_video')):
            button = StageButton(t(key), self.stage_bar)
            button.setObjectName('study-stage-' + stage)
            button.setAccessibleName(t(key))
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.clicked.connect(lambda _=False, stage=stage: self.navigate(stage))
            self.stage_group.addButton(button)
            self.stage_buttons[stage] = button
            status = QLabel('', self.stage_bar)
            status.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = status.font()
            font.setPointSizeF(max(10, font.pointSizeF() * .85))
            status.setFont(font)
            self.stage_status[stage] = status
            status.hide()
            stages.addWidget(button)
        stages.addStretch(1)
        self._stage_colors = style_stage_bar(self.stage_bar, self.stage_buttons)
        self._recording_icon = 'video'
        header.addWidget(self.stage_bar)
        self.stage_buttons['card'].setEnabled(bool(self.visit.card_id))
        if not self.visit.card_id:
            self.stage_buttons['card'].setToolTip(t('study_no_active_card'))
        self.breadcrumb = QLabel('', self)
        self.breadcrumb.setWordWrap(True)
        header.addWidget(self.breadcrumb, 1)
        header.addStretch(1)
        self.link_resources_button = QPushButton(t('study_link_resources'), self)
        self.link_resources_button.setAutoDefault(False)
        self.link_resources_button.clicked.connect(self.link_resources)
        self.link_resources_button.setVisible(bool(self.visit.card_id))
        header.addWidget(self.link_resources_button)
        self.exit_focus = QPushButton(t('study_exit_focus'), self)
        self.exit_focus.setAutoDefault(False)
        self.exit_focus.clicked.connect(self.leave_focus)
        header.addWidget(self.exit_focus)
        self.exit_focus.hide()
        self.focus_escape = QShortcut(QKeySequence('Esc'), self)
        self.focus_escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.focus_escape.activated.connect(self.leave_focus)
        self.focus_escape.setEnabled(False)
        layout.addWidget(header_panel)
        self.body_stack = QStackedWidget(self)
        layout.addWidget(self.body_stack, 1)
        self.study_body = QWidget(self.body_stack)
        self.body_stack.addWidget(self.study_body)
        layout = QVBoxLayout(self.study_body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        self.context_panel = QFrame(self)
        self.context_panel.setObjectName('study-context')
        context_row = QHBoxLayout(self.context_panel)
        context_row.setContentsMargins(0, 0, 0, 0)
        context_copy = QVBoxLayout()
        self.context_state = QLabel(t('study_answer_revealed' if self.visit.side == 'answer' else 'study_question_side'), self)
        self.context_state.setObjectName('study-context-state')
        self.context_title = ElidedLabel(t('study_review_card'), self)
        self.context_title.setTextFormat(Qt.TextFormat.PlainText)
        self.context_title.setObjectName('study-context-title')
        context_copy.addWidget(self.context_state)
        context_copy.addWidget(self.context_title)
        context_row.addLayout(context_copy, 1)
        back = QPushButton(t('study_return_card') if self.visit.card_id else t('study_close'), self)
        self.return_card_button = back
        back.clicked.connect(lambda: self.navigate('card') if self.visit.card_id else self.close())
        (context_row if self.visit.card_id else header).addWidget(back)
        layout.addWidget(self.context_panel)
        self.context_panel.setVisible(bool(self.visit.card_id))
        self.status = QLabel(t('study_loading'), self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.splitterMoved.connect(self._remember_pane_sizes)
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
        book_heading = QHBoxLayout()
        book_copy = QVBoxLayout()
        book_copy.setSpacing(3)
        book_copy.addWidget(self.book_title)
        book_copy.addWidget(self.book_position)
        book_heading.addLayout(book_copy, 1)
        self.focus_book = QPushButton(t('study_focus_textbook'), self.book_host)
        self.focus_book.setObjectName('study-focus-textbook')
        self.focus_book.setAutoDefault(False)
        self.focus_book.setToolTip(t('study_focus_hint'))
        self.focus_book.clicked.connect(lambda: self.enter_focus('book'))
        book_heading.addWidget(self.focus_book)
        self.book_layout.addLayout(book_heading)
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
        player_heading = QHBoxLayout()
        player_copy = QVBoxLayout()
        player_copy.setSpacing(3)
        player_copy.addWidget(self.player_title)
        player_copy.addWidget(self.player_segment)
        player_heading.addLayout(player_copy, 1)
        self.focus_video = QPushButton(t('study_focus_video'), self.play_host)
        self.focus_video.setAutoDefault(False)
        self.focus_video.setToolTip(t('study_focus_hint'))
        self.focus_video.clicked.connect(lambda: self.enter_focus('video'))
        player_heading.addWidget(self.focus_video)
        player_layout.addLayout(player_heading)
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
        self.resource_scroll = QScrollArea(self.side)
        self.resource_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.resource_scroll.setWidgetResizable(True)
        self.resource_scroll.setWidget(self.resource_panel)
        side.addWidget(self.resource_scroll, 1)
        self.empty_state = QFrame(self.side)
        self.empty_state.setObjectName('study-resource-panel')
        self.empty_state.setMaximumSize(640, 300)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(20, 20, 20, 20)
        self.empty_title = QLabel('', self.empty_state)
        self.empty_title.setWordWrap(True)
        self.empty_title.setTextFormat(Qt.TextFormat.PlainText)
        empty_layout.addWidget(self.empty_title)
        self.empty_link_button = QPushButton(t('study_link_resources'), self.empty_state)
        self.empty_link_button.clicked.connect(self.link_resources)
        empty_layout.addWidget(self.empty_link_button, 0, Qt.AlignmentFlag.AlignLeft)
        empty_layout.addStretch(1)
        side.addWidget(self.empty_state, 0, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.empty_state.hide()
        self.splitter.addWidget(self.side)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        picker_row = self.picker_row = QWidget(self)
        picker_layout = QHBoxLayout(picker_row)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        self.resource_picker = ResourcePicker(self)
        self.resource_picker.setAccessibleName(t('study_choose_resources'))
        self.resource_picker.activated.connect(self.pick_resource)
        self.resource_picker.linkRequested.connect(self.link_resources)
        self.resource_picker.manageRequested.connect(self.manage_links)
        self.resource_picker.toggle_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.resource_picker.toggle_button.customContextMenuRequested.connect(self._picker_context_menu)
        picker_layout.addWidget(self.resource_picker, 1)
        self.manage_links_button = QPushButton(t('study_manage_links'), self)
        self.manage_links_button.clicked.connect(self.manage_links)
        self.manage_links_button.setVisible(bool(self.visit.card_id))
        layout.addWidget(picker_row)
        self.content_scroll = QScrollArea(self)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setWidget(self.splitter)
        layout.addWidget(self.content_scroll, 1)
        footer = QHBoxLayout()
        footer.addWidget(self.status, 1)
        footer.addWidget(self.manage_links_button)
        layout.addLayout(footer)
        self._style_workspace()
        self.finished.connect(self.finish)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_location)
        self.timer.start(400)
        self._set_stage(initial_stage)
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
        self.setStyleSheet(resource_styles(c) + f"""
            QWidget#study-workspace {{ background: {c['surface']}; color: {c['ink']}; }}
            QFrame#study-header {{ background:{c['surface']}; border:0; border-bottom:1px solid {c['border']}; }}
            QFrame#study-book-panel, QFrame#study-resource-panel,
            QFrame#study-player-panel {{ background: {c['paper']}; border: 1px solid {c['border']}; border-radius: 10px; }}
            QFrame#study-context {{ background:transparent; border:0; }}
            QLabel#study-panel-title, QLabel#study-context-title {{ color: {c['ink']}; font-weight: 600; }}
            QLabel#study-panel-detail, QLabel#study-context-state {{ color: {c['foreground']}; }}
            QListWidget#study-resource-list {{ background: transparent; color: {c['ink']}; border: 0; }}
            QListWidget#study-resource-list::item {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 10px; }}
            QListWidget#study-resource-list::item:selected {{ background: {c['selected']}; color: {c['accent']}; border-color: {c['accent']}; }}
            QFrame#study-resource-panel QPushButton, QFrame#study-player-panel QPushButton,
            QFrame#study-context QPushButton, QPushButton#study-more-resources,
            QPushButton#study-focus-textbook, QFrame#study-header > QPushButton {{ padding: 5px 10px; border: 1px solid {c['border']}; border-radius: 6px; background: {c['paper']}; color: {c['ink']}; }}
            QFrame#study-resource-panel QPushButton#study-open-resource {{ background: {c['selected']}; color: {c['accent']}; font-weight: 600; }}
            QFrame#study-resource-panel QPushButton:hover, QFrame#study-player-panel QPushButton:hover,
            QFrame#study-context QPushButton:hover, QPushButton#study-more-resources:hover {{ border-color: {c['accent']}; }}
            QFrame#study-resource-panel QPushButton:disabled {{ color: {c['foreground']}; background: {c['surface']}; }}
        """)

    def present(self):
        self.surface.present()
        self.context_state.setText(t('study_current_card_state', state=t('study_answer_revealed' if self.visit.side == 'answer' else 'study_question_side')))
        context = _context()
        evaluate = getattr(getattr(getattr(mw, 'reviewer', None), 'web', None), 'evalWithCallback', None)
        if self.visit.card_id and callable(evaluate) and not self._card_title:
            def captured(value):
                if not self._card_title and self.current() and _context() == context and isinstance(value, str) and value.strip():
                    self.context_title.setText(' '.join(value.split())[:240])
            evaluate("(() => {const q=document.getElementById('qa');return q ? q.innerText.slice(0,320) : '';})()", captured)
        self._adapt_panels()
        self._schedule_focus_restore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'splitter'):
            self._adapt_panels()

    def _adapt_panels(self):
        if self.focus_stage is not None:
            return
        orientation = Qt.Orientation.Vertical if self.width() < 880 else Qt.Orientation.Horizontal
        header_minimum = self.stage_bar.minimumSizeHint().width() + self.link_resources_button.sizeHint().width() + 64
        self.header_panel.layout().setDirection(QBoxLayout.Direction.TopToBottom if self.width() < max(520, header_minimum)
                                               else QBoxLayout.Direction.LeftToRight)
        self.stage_bar.setMinimumHeight(self.stage_bar.minimumSizeHint().height())
        self.header_panel.setMinimumHeight(self.header_panel.minimumSizeHint().height())
        mode = (orientation, self.visit.stage)
        if mode != self._pane_mode:
            if self._pane_mode is not None and all(self.splitter.sizes()):
                self._pane_sizes[self._pane_mode] = self.splitter.sizes()
            self.splitter.setOrientation(orientation)
            self.splitter.setSizes(self._pane_sizes.get(mode, [380, 620] if self.visit.stage == 'video' else [740, 260]))
            self._pane_mode = mode

    def _remember_pane_sizes(self, *_):
        # splitterMoved records a drag, not resize/layout events or focus's hidden pane.
        if (not self.current() or self.focus_stage is not None or self.visit.stage not in ('book', 'video')
                or not self.book_host.isVisible() or not self.side.isVisible()):
            return
        sizes = self.splitter.sizes()
        if not all(sizes):
            return
        self._pane_sizes[self._pane_mode] = sizes
        key = 'horizontal' if self.splitter.orientation() == Qt.Orientation.Horizontal else 'vertical'
        self._remember_layout(**{key: max(.05, min(.95, sizes[0] / sum(sizes)))})

    def _remember_layout(self, **changes):
        stage = self.visit.stage
        self._layout_preferences.setdefault(stage, {}).update(changes)
        self._layout_changes.setdefault(stage, {}).update(changes)
        self._layout_save_timer.start()

    def _flush_layout_preferences(self):
        self._layout_save_timer.stop()
        if not self._layout_changes:
            return
        if self.visit.profile != get_active_profile() or self.visit.collection is not mw.col:
            self._layout_changes.clear()
            return
        try:
            cfg = deepcopy(load_addon_config(mw.addonManager, _ADDON_PKG))
            profile = cfg['study_layout_by_profile'].setdefault(self.visit.profile, {})
            for stage, changes in self._layout_changes.items():
                profile.setdefault(stage, {}).update(changes)
            save_addon_config(mw.addonManager, _ADDON_PKG, cfg)
        except Exception:
            if not self._layout_save_warned:
                from aqt.utils import tooltip
                tooltip(t('study_layout_save_failed'))
                self._layout_save_warned = True
            return
        self._layout_changes.clear()
        self._layout_save_warned = False

    def _schedule_focus_restore(self):
        if self.active_sheet is not None:
            return
        # Wait for the visible surface to settle. A video may load its textbook
        # first, so a queued restore must still match the requested stage.
        self._focus_restore_stage = self.visit.stage
        self._layout_restore_timer.start(0)

    def _restore_preferred_focus(self):
        if (self.current() and self.isVisible() and self.visit.stage == self._focus_restore_stage
                and self._layout_preferences.get(self.visit.stage, {}).get('focus', False)):
            self.enter_focus(self.visit.stage, remember=False)

    def enter_focus(self, stage, *, remember=True):
        if (not self.current() or self.focus_stage is not None
                or stage not in ('book', 'video')
                or (self._live_reader() if stage == 'book' else self.player) is None):
            return
        if stage != self.visit.stage:
            self.navigate(stage)
        if remember:
            self._remember_layout(focus=True)
            self._flush_layout_preferences()
        self._focus_sizes = self.splitter.sizes()
        self._focus_scroll = self.content_scroll.verticalScrollBar().value()
        self.focus_stage = stage
        self._sync_panels()
        self.focus_screen.enter()
        self.focus_escape.setEnabled(True)
        (self.reader.view if stage == 'book' else self.player).setFocus()

    def leave_focus(self, *, remember=True):
        if self.focus_stage is None:
            return
        if remember:
            self._remember_layout(focus=False)
            self._flush_layout_preferences()
        self.focus_escape.setEnabled(False)
        self.focus_screen.leave()
        self.focus_stage = None
        self._sync_panels()
        self.splitter.setSizes(self._focus_sizes)
        self.content_scroll.verticalScrollBar().setValue(self._focus_scroll)

    def reject(self):
        if self.focus_stage is not None:
            self.leave_focus()
        else:
            super().reject()

    def _sync_panels(self, *_):
        states = self.availability()
        for stage, state in states.items():
            button = self.stage_buttons[stage]
            button.setEnabled(not state['disabled'] or (bool(self.visit.card_id) and state['availability'] in ('empty', 'unavailable')))
            button.setAccessibleDescription(state['status'])
            button.setToolTip(t('study_no_active_card') if stage == 'card' and state['disabled'] else state['status'])
            self.stage_status[stage].setText(state['status'])
            if stage == 'card':
                button.set_title_count(t('study_tab_card'))
            else:
                key = 'study_tab_textbook' if stage == 'book' else 'study_tab_audio' if self._recording_icon == 'audio' else 'study_tab_video'
                if stage == 'book' and not any(item['location']['kind'] == 'epub' for item in self._documents):
                    key = 'study_tab_pdfs'
                button.set_title_count(t(key), state.get('count', 0))
        video = self.visit.stage == 'video' and self.player is not None
        compact_book = self._compact_resources and self.reader is not None and self.visit.stage == 'book'
        focused = self.focus_stage is not None
        self.exit_focus.setVisible(focused)
        self.context_panel.setVisible(bool(self.visit.card_id) and not focused)
        self.status.setVisible(not focused)
        self.breadcrumb.setVisible(not focused and not self._compact_resources)
        self.picker_row.setVisible(not focused)
        self._refresh_picker()
        for label in self.stage_status.values():
            label.hide()
        self.return_card_button.setVisible(not self._compact_resources and not focused)
        self.context_state.setText(t('study_current_card_state', state=t('study_answer_revealed' if self.visit.side == 'answer' else 'study_question_side')))
        self.book_title.setVisible(not self._compact_resources)
        self.book_position.setVisible(not self._compact_resources)
        self.player_title.setVisible(not self._compact_resources)
        self.player_segment.setVisible(not self._compact_resources)
        self.focus_book.setVisible(not focused and not self._compact_resources)
        self.focus_video.setVisible(not focused and not self._compact_resources)
        self.book_layout.setContentsMargins(*((0, 0, 0, 0) if self._compact_resources else (12, 12, 12, 12)))
        self.study_body.layout().setContentsMargins(*((8, 6, 8, 6) if focused else (16, 16, 16, 16)))
        self.header_panel.layout().setContentsMargins(*((8, 4, 8, 4) if focused else (16, 12, 16, 12)))
        self.play_host.setVisible(video)
        self.back_passage.setVisible(video and self.reader is not None and not focused and not self._compact_resources)
        self.book_host.setVisible(self.reader is not None and self.focus_stage != 'video'
            and (self.visit.stage == 'book' or (video and not self._compact_resources)))
        self.side.setVisible(self.focus_stage != 'book' and (not compact_book or self.more_resources.isChecked()))
        self.more_resources.setVisible((video or self.reader is not None) and not focused and not self._compact_resources)
        self.resource_scroll.setVisible(not focused and ((not self._compact_resources and not video) or self.more_resources.isChecked()))
        self.empty_state.setVisible(self._compact_resources and not focused and (
            (self.visit.stage == 'book' and self.reader is None) or (self.visit.stage == 'video' and self.player is None)))
        self.empty_title.setText(t('study_no_textbooks' if self.visit.stage == 'book' else 'study_no_recordings'))
        self.resource_scroll.setMaximumHeight(240 if video else 16777215)
        chooser = self.reader is None and not video
        self.resource_scroll.setMaximumWidth(640 if chooser else 16777215)
        self.side.layout().setAlignment(self.resource_scroll,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop if chooser else Qt.AlignmentFlag(0))
        self.resources.setVisible(bool(self._items))
        self.resources.setMaximumHeight(200 if video else 360 if chooser else 16777215)
        self.open_resource.setEnabled(bool(self._items))
        self.resource_intro.setText(t('study_card_hint') if self._items else
            t('study_no_textbooks' if self.source['kind'] == 'card' and self.visit.stage == 'book' else 'study_no_recordings'))
        self._adapt_panels()

    def _picker_context_menu(self, point):
        menu = QMenu(self)
        stage = self.visit.stage
        if (stage == 'book' and self.reader is not None) or (stage == 'video' and self.player is not None):
            action = menu.addAction(t('study_focus_textbook' if stage == 'book' else 'study_focus_video'))
            action.triggered.connect(lambda: self.enter_focus(stage))
        if self._compact_resources:
            action = menu.addAction(t('study_other_resources'))
            action.setCheckable(True)
            action.setChecked(self.more_resources.isChecked())
            action.triggered.connect(lambda checked: (self.more_resources.setChecked(checked), self._sync_panels()))
        menu.exec(self.resource_picker.toggle_button.mapToGlobal(point))

    def availability(self):
        return dict(card=card_availability(bool(self.visit.card_id)),
            book=resource_availability(self._documents if self._resources_known else None,
                                       present=self._live_reader() is not None and not self._compact_resources, failed=self._resources_failed),
            video=resource_availability(self._recordings if self._resources_known else None,
                                        present=self.player is not None, failed=self._resources_failed))

    def _live_reader(self):
        reader = self.reader
        if reader is not None and (sip.isdeleted(reader) or sip.isdeleted(reader.view)
                or getattr(getattr(reader, 'state', None), 'closed', False)
                or getattr(reader, 'closed', False)):
            self._retire_reader(reader)
        return self.reader

    def _retire_reader(self, reader):
        if sip.isdeleted(self) or self.reader is not reader:
            return
        # These positions are Python-owned and survive the native pane. Keep
        # them so Back to passage can use the normal validated document loader.
        if self.reader_kind == 'pdf':
            self.source.update(page=reader.state.page, scroll=reader.state.scroll_ratio)
        else:
            self.source.update(reader.location)
        key = (self.source['card_id'], self.source.get('page', self.source.get('section')))
        if key != self._last_location:
            self.source.pop('page_y', None)
            self.source['quote'] = ''
        self.reader = self.reader_kind = None
        if self.current():
            if self.focus_stage == 'book':
                self.leave_focus(remember=False)
            self._sync_panels()

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
        if self.focus_stage is not None and stage != self.focus_stage:
            self.leave_focus(remember=False)
        self.visit.navigate(stage)
        self.stage_buttons[stage].setChecked(True)
        if stage != 'card':
            self._last_resource_stage = stage
        self._sync_panels()

    def navigate(self, stage):
        if not self.current() or stage not in self.stage_buttons:
            return
        if self.active_sheet is not None:
            self.active_sheet.reject()
        if stage == 'card' and not self.visit.card_id:
            return
        if self.availability()[stage]['availability'] == 'error':
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
            check_reviewer_resources(force=True)
            mw.activateWindow()
            mw.reviewer.web.setFocus()
            return
        self._suspend_reviewer()
        self.present()
        self.raise_()
        self.activateWindow()
        if stage == 'book' and self.reader is not None:
            self.status.setText(t('study_own_position' if self._compact_resources else 'study_choose_resource'))
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
        if available:
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
        self.link_book.setVisible(stage == 'book' and bool(self.visit.card_id))
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
                if channel == 'resources':
                    self._resources_failed = True
                    self._sync_panels()
                self.status.show()
        QueryOp(parent=mw, op=run, success=done).failure(failed).run_in_background()

    def refresh(self, *, navigate_to=None):
        if not self.current():
            return
        source, profile = dict(self.source), self.visit.profile
        key = (source['kind'], source['card_id'], source.get('page'), source.get('section'))
        if key != self._resources_source:
            self._resources_source = key
            self._resources_known = self._resources_failed = False
            self._recordings = []
            self._sync_panels()
        def load(col):
            if self.visit.card_id:
                result = load_card_resources(_ADDON_DIR, profile, col, self.visit.card_id)
                if source['kind'] != 'card':
                    rows = resolve_link_rows(_ADDON_DIR, profile, col,
                        list_recording_links(_ADDON_DIR, profile, source=source))
                    seen = {self._recording_key(r) for r in result['recordings']}
                    result['recordings'] += [r for r in rows if self._recording_key(r) not in seen]
                return result
            if source['kind'] == 'card':
                return load_card_resources(_ADDON_DIR, profile, col, source['card_id'])
            rows = list_recording_links(_ADDON_DIR, profile, source=source)
            return dict(documents=[], recordings=resolve_link_rows(_ADDON_DIR, profile, col, rows))
        def ready(result):
            self._resources_known = True
            self._resources_failed = False
            if result.get('card_title'):
                self._card_title = result['card_title']
                self.context_title.setText(display_resource_title(self._card_title))
                self.context_title.setToolTip(self._card_title)
            if self.visit.card_id or source['kind'] == 'card':
                self._documents = result['documents']
            self._recordings = result['recordings']
            self.resources.clear()
            self._items = []
            for item in result['documents']:
                self._append_document(item)
            for item in result['recordings']:
                self._append_recording(item)
            self.status.setText(t('study_own_position' if self._compact_resources else 'study_choose_resource') if self._items else
                t('study_no_recordings') if source['kind'] != 'card' or self.visit.stage == 'video'
                else t('study_no_textbooks'))
            if self._items:
                preferred = next((i for i, (kind, _) in enumerate(self._items) if kind == 'recording'), 0) if source['kind'] != 'card' else 0
                self.resources.setCurrentRow(preferred)
            if navigate_to:
                self._choose_stage_resource(navigate_to)
            self._sync_panels()
        self.submit(load, ready)

    def _append_document(self, item):
        self._add_item('document', item, (item['title'] or t('study_tab_textbook')) + '\n' + source_label(item['location']) +
                       (' · ' + item['label'] if item.get('label') else ''))

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
        if source['kind'] != 'card' and (self._live_reader() is None or not same_passage):
            self.open_document(source, after=lambda: self.open_recording(item))
        else:
            self.open_recording(item)

    def open_document(self, source, *, after=None):
        source, profile = normalize_source(source), self.visit.profile
        anchor = self._document_key(source)
        if self.reader is not None:
            self.poll_location()
            if self._selected_document:
                self._document_positions[self._selected_document] = dict(self.source)
                if self.reader_kind == 'pdf':
                    self._document_zooms[self._selected_document] = getattr(self.reader.state, 'zoom', 1)
        if self._selected_recording and self.player and hasattr(self.player, 'position'):
            self._recording_positions[self._selected_recording] = self.player.position()
        source = dict(self._document_positions.get(anchor, source))
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
            reader = self._live_reader()
            if reader is not None:
                reader.close()
            if source['kind'] == 'pdf':
                from . import pdf_reference_workspace as pdf
                self.reader = pdf.ReferenceWindow(result, profile=profile, page=source['page'],
                    scroll_ratio=source['scroll'], max_page=result['max_page'], beside=True, owner=self,
                    excerpt=source['quote'], page_y=source.get('page_y'), embedded=True,
                    zoom=self._document_zooms.get(anchor, 1))
                pdf._windows.append(self.reader)
            else:
                from . import epub_reference_workspace as epub
                self.reader = epub.EpubReferenceWindow(result, source, profile=profile, owner=self, embedded=True)
                epub._windows.append(self.reader)
            self.source = source
            self._selected_document = anchor
            self.reader_kind = source['kind']
            reader = self.reader
            reader.destroyed.connect(lambda: self._retire_reader(reader))
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
            else:
                self._schedule_focus_restore()
        self.submit(work, ready, channel='document')

    def open_recording(self, item):
        profile = self.visit.profile
        key = self._recording_key(item)
        if self._selected_recording and self.player and hasattr(self.player, 'position'):
            self._recording_positions[self._selected_recording] = self.player.position()
        def ready(recording):
            if self.player is None:
                self.player = RecordingPlayer(self, compact=True)
                self.play_layout.addWidget(self.player)
            position = self._recording_positions.get(key, item['start'])
            if item['end'] is not None and position >= item['end']:
                position = item['start']
            self.player.load(recording, start=position, end=item['end'])
            self._selected_recording = key
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
            self._schedule_focus_restore()
        self.submit(lambda col: resolve_recording(_ADDON_DIR, profile, col, item['recording_card_id']),
                    ready, channel='recording')

    def back_to_passage(self):
        self.navigate('book')

    def poll_location(self):
        if not self.current():
            self.close()
            return
        if self._live_reader() is None:
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
        source = dict(kind='card', card_id=self.visit.card_id) if self.visit.card_id else dict(self.source)
        profile = self.visit.profile
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

    @staticmethod
    def _document_key(source):
        return (source['kind'], source['card_id'], source.get('page', source.get('section')),
                source.get('scroll', 0), source.get('page_y'))

    @staticmethod
    def _recording_key(row):
        return row['recording_card_id'], row['start'], row['end']

    def _refresh_picker(self):
        stage = self.visit.stage
        self._picker_items = list(self._documents if stage == 'book' else self._recordings)
        if stage == 'book' and self.reader is not None and not any(
                self._document_key(row['location']) == self._selected_document for row in self._picker_items):
            self._picker_items.append(dict(title=self.book_title.text(), location=dict(self.source), available=True))
        groups = {}
        for row in self._picker_items:
            identity = (row['location']['kind'], row['location']['card_id']) if stage == 'book' else row['recording_card_id']
            groups.setdefault(identity, []).append(row)
        self._picker_items = [row for group in groups.values() for row in group]
        entries, selected = [], -1
        for index, row in enumerate(self._picker_items):
            if stage == 'book':
                title = row['title'] or t('study_unavailable')
                location = row['location']
                detail = t('study_picker_page', page=location['page']) if location['kind'] == 'pdf' else source_label(location)
                active = self._document_key(location) == self._selected_document
            else:
                title = (row.get('recording') or {}).get('title') or row.get('label') or t('study_unavailable')
                detail = timestamp(row['start']) + ('–' + timestamp(row['end']) if row['end'] is not None else '')
                active = self._recording_key(row) == self._selected_recording
            if row.get('label'):
                detail += ' · ' + row['label']
            if not row['available']:
                detail += ' · ' + t('study_missing')
            entries.append(dict(title=display_resource_title(title), full_title=title, detail=detail, available=row['available'],
                                icon=self.stage_buttons['book' if stage == 'book' else 'video'].icon()))
            if active:
                selected = index
        if selected < 0 and entries:
            selected = next((i for i, row in enumerate(entries) if row['available']), 0)
        caption = None
        if stage == 'book' and self.reader is not None:
            caption = t('study_picker_page', page=self.source['page']) if self.source['kind'] == 'pdf' else source_label(self.source)
        self.resource_picker.set_entries(entries, selected,
            placeholder=t('study_not_linked'), caption_detail=caption)
        self.resource_picker.link_button.setVisible(bool(self.visit.card_id))
        self.resource_picker.manage_button.setVisible(bool(self.visit.card_id))

    def pick_resource(self, index):
        if not self.current() or not 0 <= index < len(self._picker_items):
            return
        row = self._picker_items[index]
        if row['available']:
            if self.visit.stage == 'book':
                self.open_document(row['location'])
            else:
                self._open_recording_resource(row)

    def _card_links_changed(self):
        if not self.current():
            return
        profile, card_id = self.visit.profile, self.visit.card_id
        def ready(result):
            self._documents = result['documents']
            self._recordings = result['recordings']
            self._resources_known = True
            self.status.setText(t('study_links_saved'))
            self._sync_panels()
            check_reviewer_resources(force=True)
        self.submit(lambda col: load_card_resources(_ADDON_DIR, profile, col, card_id), ready)

    def link_resources(self, *, manage=False):
        if not self.current() or not self.visit.card_id:
            return
        from .card_resource_dialog import open_resource_dialog
        if self.active_sheet is not None:
            if manage:
                self.active_sheet.show_manage()
            elif self.active_sheet.steps.currentIndex() == 1:
                self.active_sheet.add_more()
            return self.active_sheet
        if self.player:
            self.player.pause()
        open_resource_dialog(self.visit.card_id, owner=self, is_current=self.current,
            on_saved=self._card_links_changed, manage=manage,
            current_location=dict(self.source) if self.source['kind'] == 'pdf' else None)

    def present_resource_dialog(self, dialog):
        if not self.current():
            dialog.reject()
            return
        if self.active_sheet is not None:
            self.active_sheet.reject()
        if self.focus_stage is not None:
            self.leave_focus(remember=False)
        self.resource_picker.setExpanded(False)
        self._layout_restore_timer.stop()
        self.active_sheet = dialog
        dialog.setParent(self.body_stack)
        dialog.setWindowFlags(Qt.WindowType.Widget)
        self.body_stack.addWidget(dialog)
        self.body_stack.setCurrentWidget(dialog)
        def restored(*_):
            if self.active_sheet is not dialog:
                return
            self.active_sheet = None
            self.body_stack.removeWidget(dialog)
            self.body_stack.setCurrentWidget(self.study_body)
            if not self.current():
                return
            if self.visit.stage == 'card':
                self.navigate('card')
            else:
                self._sync_panels()
                self._schedule_focus_restore()
        dialog.finished.connect(restored)
        self._suspend_reviewer()
        self.present()
        dialog.show()

    def manage_links(self):
        self.link_resources(manage=True)

    def finish(self, *_):
        global _window
        if self.visit.closed:
            return
        self._layout_restore_timer.stop()
        self._flush_layout_preferences()
        valid = self.visit.finish(*_context())
        if _window is self:
            _window = None
        self.timer.stop()
        for cancelled in self._requests.values():
            cancelled.set()
        self.leave_focus(remember=False)
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
        stage = _window._last_resource_stage
        if _window.availability()[stage]['disabled']:
            # Explicit management/linking remains available even when a tab has
            # no usable destination. Navigation itself stays disabled.
            _window._suspend_reviewer()
            _window._set_stage(stage)
            _window.present()
            _window.refresh()
        else:
            _window.navigate(stage)
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


def workspace_enabled(config=None):
    if config is None:
        try:
            config = load_addon_config(getattr(mw, 'addonManager', None), _ADDON_PKG)
        except Exception:
            config = {}
    return configured_study_workspace_enabled(config)


def _disable_reviewer_workspace():
    # Explicit Study resources visits remain available in normal-card mode.
    reset(close_visit=bool(_review_token))
    if _context()[2]:
        mw.reviewer.web.eval(reviewer_navigation_clear_script())


def apply_settings(config):
    """Apply an accepted preference without rendering or answering the card."""
    if not workspace_enabled(config):
        _disable_reviewer_workspace()
    elif _context()[2]:
        if not _review_token or _review_context != _context():
            reviewer_shown()
        else:
            refresh_reviewer_navigation()


def reset(*_, close_visit=True):
    global _review_token, _review_context, _resource_context, _review_resources, _resource_failed
    _review_token, _review_context = '', None
    if _resource_request is not None:
        _resource_request.set()
    _resource_context, _review_resources, _resource_failed = None, None, False
    if close_visit and _window is not None:
        _window.close()


def reviewer_shown(*_):
    global _review_token, _review_context
    context = _context()
    if (_window is not None and not _window.visit.closed and _window.visit.stage == 'card'
            and context[0] == _window.visit.profile and context[1] is _window.visit.collection
            and context[2] == _window.visit.card_id):
        _window.visit.side = context[3]
    elif _window is not None:
        _window.close()
    if not context[2]:
        reset()
        return
    if not workspace_enabled():
        _disable_reviewer_workspace()
        return
    _review_context = context
    _review_token = secrets.token_urlsafe(24)
    refresh_reviewer_navigation()
    check_reviewer_resources()


def check_reviewer_resources(*, force=False):
    """Inspect only this card's bounded references off the UI thread."""
    global _resource_context, _resource_request, _review_resources, _resource_failed
    context = _context()[:3]
    if not workspace_enabled() or not context[2] or _review_context != _context():
        return
    if not force and _resource_context == context:
        return
    if _resource_request is not None:
        _resource_request.set()
    previous = _review_resources if _resource_context == context else None
    cancelled = _resource_request = Event()
    _resource_context, _review_resources, _resource_failed = context, previous, False
    profile, collection, card_id = context
    refresh_reviewer_navigation()
    def work(col):
        if not cancelled.is_set() and col is collection:
            return load_card_resources(_ADDON_DIR, profile, col, card_id)
        return None
    def current():
        now = _context()
        return (not cancelled.is_set() and workspace_enabled() and now[0] == profile
                and now[1] is collection and now[2] == card_id)
    def ready(result):
        global _review_resources, _resource_failed
        if current():
            _review_resources, _resource_failed = result, False
            refresh_reviewer_navigation()
    def failed(_error):
        global _resource_failed, _review_resources
        if current():
            _review_resources = None
            _resource_failed = True
            refresh_reviewer_navigation()
    QueryOp(parent=mw, op=work, success=ready).failure(failed).run_in_background()


def refresh_reviewer_navigation():
    if not workspace_enabled() or not _review_token or _review_context != _context():
        return
    command = 'incremento_study:' + _review_token
    result = _review_resources if _resource_context == _context()[:3] else None
    documents = result['documents'] if result is not None else None
    recordings = result['recordings'] if result is not None else None
    states = dict(card=card_availability(True),
                  book=resource_availability(documents, failed=_resource_failed),
                  video=resource_availability(recordings, failed=_resource_failed))
    available_recordings = [item for item in (recordings or []) if item['available']]
    audio = bool(available_recordings) and all((item.get('recording') or {}).get('kind') == 'audio' for item in available_recordings)
    document_key = 'study_tab_textbook' if any(item['location']['kind'] == 'epub' for item in (documents or [])) else 'study_tab_pdfs'
    routes = [dict(stage=stage, label=t(key), command=command + ':' + stage, current=stage == 'card', **states[stage],
                   icon='audio' if stage == 'video' and audio else stage)
              for stage, key in (('card', 'study_tab_card'), ('book', document_key), ('video', 'study_tab_audio' if audio else 'study_tab_video'))]
    for route in routes:
        if route['availability'] in ('empty', 'unavailable'):
            route['disabled'] = False
    book = dict(stage='book', title=t('study_tab_textbook'), detail=t('study_read_hint'),
                action=t('study_read_passage'), command=command + ':book')
    video = dict(stage='video', title=t('study_tab_audio' if audio else 'study_tab_video'), detail=t('study_recording_hint'),
                 action=t('study_open_recording'), command=command + ':video')
    available_documents = [item for item in (documents or []) if item['available']]
    if available_documents:
        item = available_documents[0]
        book.update(title=item['title'] or book['title'], detail=source_label(item['location']))
    if available_recordings:
        item = available_recordings[0]
        video.update(title=item['label'] or (item.get('recording') or {}).get('title') or video['title'],
                     detail=timestamp(item['start']))
    if _window is not None and _window.current():
        if available_documents and _window.reader is not None:
            book.update(title=_window.book_title.text(), detail=source_label(_window.source))
        if available_recordings and _window.player is not None and _window._recording_summary:
            video.update(_window._recording_summary)
    for tile in (book, video):
        state = states[tile['stage']]
        tile.update(status=state['status'], availability=state['availability'], disabled=False)
        if state['availability'] == 'empty':
            tile.update(detail=t('study_no_textbooks' if tile['stage'] == 'book' else 'study_no_recordings'),
                        action=t('reader_reference_add' if tile['stage'] == 'book' else 'study_link_recording'),
                        command=command + (':link_book' if tile['stage'] == 'book' else ':link_video'))
        elif state['availability'] == 'unavailable':
            tile.update(detail=t('study_resource_unavailable'), action=t('study_manage_links'), command=command + ':manage')
        elif state['availability'] == 'error':
            tile.update(detail=state['status'], action=t('study_retry'), command=command + ':retry')
        elif state['availability'] == 'loading':
            tile.update(detail=state['status'], action=state['status'], disabled=True)
    workspace = dict(heading=t('study_review_card'),
        state=t('study_answer_revealed' if _context()[3] == 'answer' else 'study_question_side'),
        resources_label=t('study_resources'), hint=t('study_card_hint'), tiles=[book, video],
        summary=t('study_linked_summary', documents=states['book'].get('count', 0), recordings=states['video'].get('count', 0)),
        link_action=dict(label=t('study_link_resources'), command=command + ':link'),
        manage_action=dict(label=t('study_manage_links'), command=command + ':manage'))
    mw.reviewer.web.eval(reviewer_navigation_script(routes, t('study_resources'), workspace=workspace))


def on_js_message(handled, message, context):
    global _window
    if not isinstance(message, str) or not message.startswith('incremento_study:'):
        return handled
    parts = message.removeprefix('incremento_study:').split(':')
    if (context is getattr(mw, 'reviewer', None) and workspace_enabled() and _review_token and len(parts) in (1, 2)
            and parts[0].isascii() and secrets.compare_digest(parts[0], _review_token)
            and _review_context == _context()):
        if len(parts) == 1:
            show_resources()
        elif parts[1] == 'retry':
            check_reviewer_resources(force=True)
        elif parts[1] in ('link', 'manage'):
            if _window is None:
                _window = StudyWorkspace(initial_stage='card')
            _window.link_resources(manage=parts[1] == 'manage')
        elif parts[1] in ('link_book', 'link_video'):
            show_resources()
            if parts[1] == 'link_book':
                _window.link_textbook()
            elif parts[1] == 'link_video':
                _window.link_recording()
        elif parts[1] in ('card', 'book', 'video'):
            if parts[1] != 'card':
                items = (_review_resources or {}).get('documents' if parts[1] == 'book' else 'recordings')
                if resource_availability(items, failed=_resource_failed)['availability'] in ('loading', 'error'):
                    return True, None
            if _window is None and parts[1] != 'card':
                show_resources()
            if _window is not None:
                _window.navigate(parts[1])
    return True, None
