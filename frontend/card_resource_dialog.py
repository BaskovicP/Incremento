"""Inline multi-resource linking and row-based management for one captured card."""
from pathlib import Path
from threading import Event

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (QBoxLayout, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QPalette,
                    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QStyle, QTimer,
                    QVBoxLayout, QWidget, Qt)

try:
    from ..backend.card_resource_links import (card_summary, load_resource_library, save_card_resource_links,
        unlink_card_resource, restore_card_resource_link, pdf_page_count, MAX_BATCH)
    from ..backend.anki_compat import pause_reviewer_auto_advance
    from ..backend.i18n import t, tn
    from ..backend.paths import get_active_profile
    from ..backend.recording_links import validate_segment
    from ..backend.study_resources import load_card_resources, resolve_document, resolve_recording, file_signature
    from .recording_link_dialog import parse_timestamp
    from .recording_player import timestamp
    from .study_navigation import NAVIGATION_COLORS
    from .study_resource_widgets import LibraryResourceRow, ElidedLabel, ResourceButton, resource_styles
    from .study_resource_titles import display_resource_title
    from .study_link_preview import LinkPreviewPanel, render_link_page
except ImportError:
    from backend.card_resource_links import (card_summary, load_resource_library, save_card_resource_links,
        unlink_card_resource, restore_card_resource_link, pdf_page_count, MAX_BATCH)
    from backend.anki_compat import pause_reviewer_auto_advance
    from backend.i18n import t, tn
    from backend.paths import get_active_profile
    from backend.recording_links import validate_segment
    from backend.study_resources import load_card_resources, resolve_document, resolve_recording, file_signature
    from frontend.recording_link_dialog import parse_timestamp
    from frontend.recording_player import timestamp
    from frontend.study_navigation import NAVIGATION_COLORS
    from frontend.study_resource_widgets import LibraryResourceRow, ElidedLabel, ResourceButton, resource_styles
    from frontend.study_resource_titles import display_resource_title
    from frontend.study_link_preview import LinkPreviewPanel, render_link_page

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_dialogs = []
_importers = {}


def configure_importers(**importers):
    _importers.update(importers)


def resource_draft(row):
    if 'location' in row:
        loc = row['location']
        return dict(kind='pdf', card_id=loc['card_id'], page=loc['page'], scroll=loc.get('scroll', 0),
            page_y=loc.get('page_y'), label=row.get('label', ''), link_id=row.get('link_id', 0))
    return dict(kind=(row.get('recording') or {}).get('kind', 'video'), card_id=row['recording_card_id'],
                start=row['start'], end=row['end'], label=row['label'], link_id=row['id'])


class CardResourceDialog(QDialog):
    def __init__(self, card_id, *, owner=None, is_current=lambda: True, on_saved=lambda: None,
                 manage=False, current_location=None):
        super().__init__(owner or mw)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setObjectName('study-resource-sheet')
        self.setWindowTitle(t('study_link_to_card'))
        self.resize(1040, 820)
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        self.setStyleSheet(resource_styles(NAVIGATION_COLORS['dark' if dark else 'light']))
        self.card_id, self.profile, self.collection = card_id, get_active_profile(), mw.col
        self.is_current, self.on_saved = is_current, on_saved
        self.cancelled = Event()
        self.request = 0
        self.rows, self.managed, self.managed_rows = [], [], []
        self.resource_rows = {}
        self._drafts = {}
        self._editing = None
        self._busy = False
        self._undo = None
        self._previews = []
        self.player = None
        self._player_key = None
        self._preview_key = None
        self._preview_generation = 0
        self._preview_fingerprint = None
        self._pdf_maximum = {}
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(180)
        self._preview_timer.timeout.connect(lambda: self.preview(self._preview_key))
        self.current_location = current_location
        self.manage_mode = manage
        reviewer = getattr(mw, 'reviewer', None)
        reviewing = getattr(mw, 'state', '') == 'review' and getattr(getattr(reviewer, 'card', None), 'id', 0) == card_id
        self._resume_advance = pause_reviewer_auto_advance(reviewer) if reviewing else lambda: None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)
        heading = QHBoxLayout()
        self.heading = QLabel(self)
        font = self.heading.font()
        font.setWeight(font.Weight.Medium)
        self.heading.setFont(font)
        heading.addWidget(self.heading, 1)
        self.close_button = QPushButton(self)
        self.close_button.setObjectName('study-quiet-action')
        self.close_button.setAutoDefault(False)
        self.close_button.clicked.connect(self.reject)
        heading.addWidget(self.close_button)
        layout.addLayout(heading)
        hint = QLabel(t('study_preview_instructions'), self)
        hint.setObjectName('study-picker-detail')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.instructions = hint
        self.steps = QStackedWidget(self)
        layout.addWidget(self.steps, 1)
        library_page = QWidget(self.steps)
        self.link_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, library_page)
        self.link_layout.setContentsMargins(0, 0, 0, 0)
        self.link_layout.setSpacing(20)
        self.library_container = QWidget(library_page)
        self.library_container.setMinimumWidth(0)
        self.library_container.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        library_layout = QVBoxLayout(self.library_container)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.setSpacing(10)
        tools = QHBoxLayout()
        tools.addWidget(QLabel(t('study_choose_library'), self), 1)
        self.import_button = QPushButton(t('study_import_files'), self)
        self.import_button.setAutoDefault(False)
        menu = QMenu(self.import_button)
        for kind in ('pdf', 'video', 'audio'):
            action = menu.addAction(t('study_import_' + kind))
            action.setEnabled(kind in _importers)
            action.triggered.connect(lambda _=False, kind=kind: self.import_resource(kind))
        menu.addSeparator()
        refresh = menu.addAction(t('study_refresh'))
        refresh.triggered.connect(self.reload)
        self.import_button.setMenu(menu)
        tools.addWidget(self.import_button)
        library_layout.addLayout(tools)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(t('study_search_resources'))
        self.search.setAccessibleName(t('study_search_resources'))
        self.search.textChanged.connect(self.filter_rows)
        self.search.hide()
        library_layout.addWidget(self.search)
        self.library_scroll = self._scroll(self.library_container)
        self.library_host = self.library_scroll.widget()
        self.library_layout = self.library_host.layout()
        self.library_layout.addStretch(1)
        library_layout.addWidget(self.library_scroll, 1)
        self.link_layout.addWidget(self.library_container, 5)
        self.preview_scroll = QScrollArea(library_page)
        self.preview_scroll.setObjectName('study-sheet-scroll')
        self.preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.preview_scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.preview_panel = LinkPreviewPanel(self.preview_scroll)
        self.preview_scroll.setWidget(self.preview_panel)
        self.preview_panel.activated.connect(self.preview)
        self.preview_panel.removed.connect(lambda key: self.resource_rows[key].check_box.setChecked(False))
        self.preview_panel.chooseRequested.connect(self.choose_pdf_destination)
        self.summary = self.preview_panel.card_title
        self.target_frame = self.preview_panel
        self.link_layout.addWidget(self.preview_scroll, 4)
        self.steps.addWidget(library_page)
        manage_page = QWidget(self.steps)
        manager = QVBoxLayout(manage_page)
        manager.setContentsMargins(0, 0, 0, 0)
        self.manager_scroll = self._scroll(manage_page)
        self.manager_host = self.manager_scroll.widget()
        self.manager_layout = self.manager_host.layout()
        self.manager_layout.addStretch(1)
        manager.addWidget(self.manager_scroll)
        self.steps.addWidget(manage_page)
        footer = QHBoxLayout()
        self.status = QLabel('', self)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        self.status.setObjectName('study-picker-detail')
        self.status.setAccessibleName(t('study_resources'))
        footer.addWidget(self.status, 1)
        self.cancel_button = QPushButton(t('study_cancel'), self)
        self.cancel_button.setObjectName('study-quiet-action')
        self.cancel_button.clicked.connect(self.cancel_action)
        footer.insertWidget(0, self.cancel_button)
        self.undo_button = QPushButton(t('study_undo_unlink'), self)
        self.undo_button.setObjectName('study-quiet-action')
        self.undo_button.clicked.connect(self.undo)
        footer.addWidget(self.undo_button)
        self.add_button = QPushButton(t('study_link_resources'), self)
        self.add_button.setObjectName('study-primary-action')
        self.add_button.clicked.connect(self.add_more)
        footer.addWidget(self.add_button)
        self.save_button = QPushButton(t('study_link_action'), self)
        self.save_button.setObjectName('study-primary-action')
        self.save_button.clicked.connect(self.save)
        footer.addWidget(self.save_button)
        layout.addLayout(footer)
        self.finished.connect(self.finish)
        if isinstance(owner, QDialog):
            owner.finished.connect(self.reject)
        self.steps.setCurrentIndex(1 if manage else 0)
        self._update_controls()
        self.reload()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'link_layout'):
            narrow = self.width() < 860
            self.link_layout.setDirection(QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight)
            self.preview_scroll.setMaximumHeight(360 if narrow else 16777215)

    def _scroll(self, parent):
        scroll = QScrollArea(parent)
        scroll.setObjectName('study-sheet-scroll')
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = QWidget(scroll)
        host.setObjectName('study-sheet-list')
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        scroll.setWidget(host)
        return scroll

    @staticmethod
    def _key(row):
        return row['kind'], row['card_id']

    def current(self):
        return (not self.cancelled.is_set() and self.profile == get_active_profile()
                and self.collection is mw.col and self.is_current())

    def submit(self, work, ready):
        self.request += 1
        request = self.request
        def run(col):
            if request == self.request and self.current() and col is self.collection:
                return work(col)
            return None
        def done(result):
            if request == self.request and self.current():
                self._busy = False
                ready(result)
                if self.current():
                    self._update_controls()
        def failed(_error):
            if request == self.request and self.current():
                self._busy = False
                self.status.setText(t('study_batch_failed'))
                self._update_controls()
        QueryOp(parent=mw, op=run, success=done).failure(failed).run_in_background()

    def reload(self):
        if not self.current() or self._busy:
            return
        profile, card_id = self.profile, self.card_id
        def work(col):
            return (card_summary(col, card_id), load_resource_library(_ADDON_DIR, profile, col),
                    load_card_resources(_ADDON_DIR, profile, col, card_id) if self.manage_mode else None)
        def ready(result):
            summary, (self.rows, limited), resources = result
            self.summary.setText(display_resource_title(summary))
            self.summary.setToolTip(summary)
            self.status.setText(t('study_resource_library_limited') if limited else '')
            self._render_library()
            if resources is not None:
                self.managed = resources['documents'] + resources['recordings']
                self._render_manager()
        self.submit(work, ready)

    def _render_library(self):
        keys = {self._key(row) for row in self.rows}
        for key in list(self.resource_rows):
            if key not in keys and key not in self._drafts:
                widget = self.resource_rows.pop(key)
                self.library_layout.removeWidget(widget)
                widget.deleteLater()
        for index, row in enumerate(self.rows):
            key = self._key(row)
            widget = self.resource_rows.get(key)
            if widget is None:
                widget = LibraryResourceRow(row, self.library_host)
                self.resource_rows[key] = widget
                widget.checked.connect(lambda checked, key=key: self.check_resource(key, checked))
                widget.edited.connect(lambda key=key: self.capture_fields(key))
                widget.previewRequested.connect(lambda key=key: self.preview(key))
                widget.positionRequested.connect(lambda key=key: self.use_current_position(key))
            else:
                widget.row = dict(row)
                widget.title.setText(display_resource_title(row['title']))
                widget.title.setToolTip(row['title'])
                widget.check_box.setAccessibleName(row['title'])
            widget.check_box.setEnabled(row['available'] or key in self._drafts)
            self.library_layout.removeWidget(widget)
            self.library_layout.insertWidget(index, widget)
        self.search.setVisible(len(self.rows) > 8)
        if not self.rows:
            self.status.setText(t('study_library_empty'))
        self.filter_rows()

    def filter_rows(self, *_):
        query = self.search.text().strip().casefold()
        for key, widget in self.resource_rows.items():
            family = not self._editing or (widget.row['kind'] == 'pdf') == (self._editing['kind'] == 'pdf')
            widget.setVisible(family and (query in widget.row['title'].casefold() or key in self._drafts))

    def check_resource(self, key, checked):
        widget = self.resource_rows[key]
        if checked:
            if len(self._drafts) >= MAX_BATCH and key not in self._drafts and not self._editing:
                widget.check_box.setChecked(False)
                self.status.setText(t('study_batch_limit', count=MAX_BATCH))
                return
            if self._editing:
                previous = next(iter(self._drafts.values()), self._editing)
                seed = dict(previous, kind=key[0], card_id=key[1])
                if (previous['kind'], previous['card_id']) != key:
                    seed.pop('snapshot', None)
                    seed.pop('duration', None)
                for other_key in list(self._drafts):
                    if other_key != key:
                        other = self.resource_rows.get(other_key)
                        if other:
                            other.check_box.blockSignals(True)
                            other.check_box.setChecked(False)
                            other.check_box.blockSignals(False)
                            other.fields.hide()
                self._drafts.clear()
                widget.set_values(seed)
            self._drafts[key] = widget.values()
        else:
            self._drafts.pop(key, None)
            if key == self._player_key:
                self._dispose_player()
        self._preview_key = key if checked else next(iter(self._drafts), None)
        self.filter_rows()
        self._update_controls()
        self._refresh_link_preview()

    def capture_fields(self, key=None):
        keys = [key] if key is not None else list(self._drafts)
        for current_key in keys:
            if current_key not in self._drafts or current_key not in self.resource_rows:
                continue
            widget = self.resource_rows[current_key]
            value = widget.values()
            if 'duration' in self._drafts[current_key]:
                value['duration'] = self._drafts[current_key]['duration']
            if self.player and self._player_key == current_key and self.player.duration() > 0:
                value['duration'] = self.player.duration()
            self._drafts[current_key] = value
        if key in self._drafts:
            self._preview_key = key
        self._refresh_link_preview()
        self._update_controls()

    def _location_error(self, key, draft):
        if draft['kind'] == 'pdf':
            maximum = self._pdf_maximum.get(key)
            return t('study_preview_page_error', maximum=maximum) if maximum is not None and draft['page'] > maximum else ''
        try:
            start = parse_timestamp(draft.get('start_text', '0:00'))
            end = parse_timestamp(draft['end_text']) if draft.get('end_text', '').strip() else None
            validate_segment(start, end, duration=draft.get('duration'))
            return ''
        except (ValueError, OverflowError):
            return t('study_preview_time_error')

    def _draft_detail(self, draft):
        if draft['kind'] == 'pdf':
            detail = t('study_preview_pdf_location', page=draft['page'])
        else:
            try:
                start = parse_timestamp(draft.get('start_text', '0:00'))
                end = parse_timestamp(draft['end_text']) if draft.get('end_text', '').strip() else None
                validate_segment(start, end)
                detail = t('study_preview_segment', start=timestamp(start), end=timestamp(end)) if end is not None else t('study_preview_start', start=timestamp(start))
            except (ValueError, OverflowError):
                detail = t('study_preview_time_error')
        return detail + (' · ' + draft['label'].strip() if draft.get('label', '').strip() else '')

    def _refresh_link_preview(self):
        entries = []
        for key, draft in self._drafts.items():
            widget = self.resource_rows[key]
            error = self._location_error(key, draft)
            if widget._editors_built:
                widget.error.setText(error)
                widget.error.setVisible(bool(error))
            entries.append(dict(key=key, title=display_resource_title(widget.row['title']),
                detail=self._draft_detail(draft), error=error))
        self.preview_panel.set_links(entries, self._preview_key)
        active = self._drafts.get(self._preview_key)
        self.preview_panel.media_title.setText(display_resource_title(self.resource_rows[self._preview_key].row['title']) if active else '')
        self.preview_panel.media_detail.setText(self._draft_detail(active) if active else '')
        fingerprint = (self._preview_key, active.get('page'), active.get('start_text'), active.get('end_text')) if active else None
        if fingerprint != self._preview_fingerprint:
            self._preview_fingerprint = fingerprint
            self._preview_generation += 1
            self._preview_timer.stop()
            self._dispose_player()
            self.preview_panel.show_message(t('study_loading') if active else '')
            if active and not self._location_error(self._preview_key, active) and not self._busy:
                self._preview_timer.start()

    def selection(self):
        self.capture_fields()
        result = []
        for value in self._drafts.values():
            draft = dict(value)
            if draft['kind'] != 'pdf':
                draft['start'] = parse_timestamp(draft.get('start_text', '0:00'))
                draft['end'] = parse_timestamp(draft['end_text']) if draft.get('end_text', '').strip() else None
            result.append(draft)
        return result

    def _update_controls(self):
        managing = self.steps.currentIndex() == 1
        self.heading.setText(t('study_managed_title' if managing else 'study_link_to_card'))
        self.instructions.setVisible(not managing)
        self.close_button.setText(t('study_manage_done') if managing else '')
        self.close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_TitleBarCloseButton) if not managing else type(self.close_button.icon())())
        self.close_button.setAccessibleName(t('study_manage_done' if managing else 'study_close'))
        self.cancel_button.setVisible(not managing)
        self.undo_button.setVisible(managing and self._undo is not None)
        self.undo_button.setEnabled(self._undo is not None and not self._busy)
        self.add_button.setVisible(managing)
        self.add_button.setEnabled(not self._busy)
        self.save_button.setVisible(not managing)
        self.save_button.setEnabled(bool(self._drafts) and not self._busy and
            not any(self._location_error(key, draft) for key, draft in self._drafts.items()))
        if self._busy:
            self._preview_timer.stop()
            self._preview_generation += 1
        self.save_button.setText(t('study_save_link') if self._editing else
            tn('study_link_selection', len(self._drafts)) if self._drafts else t('study_link_action'))
        self.import_button.setEnabled(not self._busy)
        self.search.setEnabled(not self._busy)
        self.preview_panel.setEnabled(not self._busy)
        for key, widget in self.resource_rows.items():
            widget.check_box.setEnabled(not self._busy and (widget.row['available'] or key in self._drafts))
            widget.fields.setEnabled(not self._busy)
            if widget._editors_built:
                widget.preview_button.setEnabled(not self._busy and widget.row['available'])
                widget.position_button.setEnabled(not self._busy and (
                    bool(self.current_location and self.current_location.get('card_id') == key[1])
                    or (self.player is not None and self._player_key == key)))
        for widget in self.managed_rows:
            widget.title_button.setEnabled(widget.editable and not self._busy)
            widget.unlink_button.setEnabled(widget.editable and not self._busy)

    def save(self):
        if not self.current() or self._busy:
            return
        try:
            selection = self.selection()
            if not selection:
                return
        except ValueError:
            self.status.setText(t('study_batch_invalid'))
            return
        self._busy = True
        self._update_controls()
        profile, card_id = self.profile, self.card_id
        def saved(result):
            if result:
                self.on_saved()
                if self.manage_mode:
                    self.show_manage()
                else:
                    self.accept()
        self.submit(lambda col: save_card_resource_links(_ADDON_DIR, profile, col, card_id, selection,
                    is_cancelled=lambda: not self.current()), saved)

    def import_resource(self, kind):
        if self.current() and not self._busy and kind in _importers:
            _importers[kind]()
            if self.current():
                self.reload()

    def _dispose_player(self):
        player = self.player
        self.player = None
        self._player_key = None
        if player:
            player.dispose()
            player.hide()
            player.deleteLater()

    def preview(self, key):
        if key not in self._drafts or not self.current() or self._busy:
            return
        self.capture_fields(key)
        self._preview_timer.stop()
        self._preview_generation += 1
        generation = self._preview_generation
        draft = dict(self._drafts[key])
        error = self._location_error(key, draft)
        self._dispose_player()
        self.preview_panel.show_message(error or t('study_loading'))
        if error:
            return
        profile = self.profile
        def valid():
            return (self.current() and generation == self._preview_generation and
                    self._preview_key == key and key in self._drafts and not self._busy)
        def work(col):
            if not valid() or col is not self.collection:
                return None
            if draft['kind'] == 'pdf':
                source = dict(kind='pdf', card_id=draft['card_id'], page=draft['page'])
                snapshot = resolve_document(_ADDON_DIR, profile, col, source)
                snapshot['signature'] = file_signature(snapshot['path'])
                rendered = render_link_page(snapshot, draft['page'])
                return snapshot, rendered
            return resolve_recording(_ADDON_DIR, profile, col, draft['card_id']), None
        def ready(result):
            if not valid() or result is None:
                return
            snapshot, rendered = result
            if draft['kind'] == 'pdf':
                self._pdf_maximum[key] = rendered['maximum']
                error = self._location_error(key, self._drafts[key])
                if error:
                    self.preview_panel.show_message(error)
                else:
                    self.preview_panel.show_page(rendered['image'])
                    self.preview_panel.page_image.setAccessibleName(t('study_preview_pdf_named',
                        title=self.resource_rows[key].row['title'], page=draft['page']))
            else:
                from .recording_player import RecordingPlayer
                self.preview_panel.media_message.hide()
                self.player = RecordingPlayer(self.preview_panel, compact=True)
                self.preview_panel.media_host.addWidget(self.player)
                start = parse_timestamp(draft.get('start_text', '0:00'))
                end = parse_timestamp(draft['end_text']) if draft.get('end_text', '').strip() else None
                self._player_key = key
                media = getattr(self.player, 'media', None)
                if media is not None:
                    media.durationChanged.connect(lambda *_: self.capture_fields(key)
                        if self.current() and self._player_key == key else None)
                self.player.load(snapshot, start=start, end=end)
            value = self.resource_rows[key].values()
            value['snapshot'] = dict(path=snapshot['path'], signature=snapshot['signature'])
            self.resource_rows[key].set_values(value)
            self.capture_fields(key)
            self._update_controls()
        def failed(_error):
            if valid():
                self.preview_panel.show_message(t('study_preview_unavailable'))
        QueryOp(parent=mw, op=work, success=ready).failure(failed).run_in_background()

    def choose_pdf_destination(self):
        key = self._preview_key
        if key is None or key[0] != 'pdf':
            return
        if key not in self._drafts or not self.current() or self._busy:
            return
        self.capture_fields(key)
        draft = dict(self._drafts[key])
        self._dispose_player()
        for dialog in self._previews:
            try:
                dialog.reject()
            except RuntimeError:
                pass
        self._previews.clear()
        profile = self.profile
        def work(col):
            if draft['kind'] == 'pdf':
                source = dict(kind='pdf', card_id=draft['card_id'], page=draft.get('page', 1))
                snapshot = resolve_document(_ADDON_DIR, profile, col, source)
                snapshot['signature'] = file_signature(snapshot['path'])
                return snapshot, min(snapshot['max_page'], pdf_page_count(snapshot['path']))
            return resolve_recording(_ADDON_DIR, profile, col, draft['card_id']), None
        def ready(result):
            if key not in self._drafts:
                return
            snapshot, maximum = result
            if draft['kind'] == 'pdf':
                from .pdf_destination_dialog import PdfDestinationDialog
                dialog = PdfDestinationDialog(snapshot, profile=profile, max_page=maximum,
                    is_current=lambda: self.current() and key in self._drafts,
                    initial_location=dict(draft, page=min(draft.get('page', 1), maximum)))
                self._previews.append(dialog)
                def chosen():
                    if self.current() and key in self._drafts and dialog.selected_location:
                        point = dialog.selected_location
                        value = self.resource_rows[key].values()
                        value.update(page=point['page'], scroll=point['scroll_ratio'], page_y=point.get('page_y'),
                            snapshot=dict(path=snapshot['path'], signature=snapshot['signature']))
                        self.resource_rows[key].set_values(value)
                        self.capture_fields(key)
                dialog.accepted.connect(chosen)
                dialog.show()
            self._update_controls()
        self.submit(work, ready)

    def use_current_position(self, key):
        if key not in self._drafts or not self.current() or self._busy:
            return
        widget = self.resource_rows[key]
        if key[0] == 'pdf' and self.current_location and self.current_location.get('card_id') == key[1]:
            point = self.current_location
            value = widget.values()
            value.update(page=point['page'], scroll=point.get('scroll', 0), page_y=point.get('page_y'))
            widget.set_values(value)
        elif self.player and self._player_key == key and self.player.ready:
            widget.start.setText(timestamp(self.player.position()))
        self.capture_fields(key)

    def _detail(self, draft):
        if draft['kind'] == 'pdf':
            return t('study_picker_page', page=draft['page'])
        return timestamp(draft.get('start', 0)) + (' – ' + timestamp(draft['end']) if draft.get('end') is not None else '')

    def _editable(self, row):
        return bool((row.get('link_id') and row.get('owner_card_id') == self.card_id)
            or (row.get('id') and row.get('source', {}).get('kind') == 'card' and row['source']['card_id'] == self.card_id))

    def _render_manager(self):
        for widget in self.managed_rows:
            self.manager_layout.removeWidget(widget)
            widget.deleteLater()
        self.managed_rows = []
        for row in self.managed:
            frame = QFrame(self.manager_host)
            frame.setObjectName('study-library-row')
            frame.editable = self._editable(row)
            body = QHBoxLayout(frame)
            body.setContentsMargins(0, 10, 0, 10)
            title = row.get('title') or (row.get('recording') or {}).get('title') or t('study_unavailable')
            frame.title_button = ResourceButton(frame)
            frame.title_button.setObjectName('study-quiet-action')
            frame.title_button.setAutoDefault(False)
            frame.title_button.setAccessibleName(t('study_edit') + ' · ' + title)
            frame.title_button.setToolTip(t('study_edit') + '\n' + title)
            copy = QVBoxLayout(frame.title_button)
            copy.setContentsMargins(10, 7, 10, 7)
            copy.setSpacing(4)
            name = ElidedLabel(display_resource_title(title), frame.title_button)
            name.setObjectName('study-picker-title')
            draft = resource_draft(row) if 'location' not in row or row['location']['kind'] == 'pdf' else None
            detail = self._detail(draft) if draft else t('study_tab_textbook')
            if draft and draft.get('label'):
                detail += ' · ' + draft['label']
            if not row['available']:
                detail += ' · ' + t('study_missing')
            metadata = ElidedLabel(detail, frame.title_button)
            metadata.setObjectName('study-picker-detail')
            for label in (name, metadata):
                label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                copy.addWidget(label)
            frame.title_button.clicked.connect(lambda _=False, row=row: self.edit_link(row))
            body.addWidget(frame.title_button, 1)
            frame.unlink_button = QPushButton(t('study_unlink'), frame)
            frame.unlink_button.setObjectName('study-quiet-action')
            frame.unlink_button.setAutoDefault(False)
            frame.unlink_button.clicked.connect(lambda _=False, row=row: self.unlink(row))
            body.addWidget(frame.unlink_button)
            if not frame.editable:
                frame.title_button.setToolTip(t('study_inherited_resource'))
                frame.unlink_button.setToolTip(t('study_inherited_resource'))
            self.manager_layout.insertWidget(self.manager_layout.count()-1, frame)
            self.managed_rows.append(frame)
        if self.steps.currentIndex() == 1 and not self.status.text():
            self.status.setText(t('study_files_kept'))
        self._update_controls()

    def edit_link(self, row):
        if not self.current() or self._busy or not self._editable(row):
            return
        self._dispose_player()
        self._reset_checks()
        self._editing = resource_draft(row)
        key = self._key(self._editing)
        if key not in self.resource_rows:
            value = dict(kind=key[0], card_id=key[1], title=row.get('title') or
                (row.get('recording') or {}).get('title') or t('study_unavailable'), available=row['available'])
            self.rows.append(value)
            self._render_library()
        widget = self.resource_rows[key]
        widget.set_values(self._editing)
        widget.check_box.setChecked(True)
        self.steps.setCurrentIndex(0)
        self.search.clear()
        self.status.clear()
        self.filter_rows()
        self._update_controls()
        self.library_scroll.ensureWidgetVisible(widget)

    def _reset_checks(self):
        self._preview_timer.stop()
        self._preview_generation += 1
        for widget in self.resource_rows.values():
            widget.check_box.blockSignals(True)
            widget.check_box.setChecked(False)
            widget.check_box.blockSignals(False)
            widget.fields.hide()
            if widget._editors_built:
                widget.set_values({})
        self._drafts.clear()
        self._editing = None
        self._preview_key = None
        self._refresh_link_preview()

    def add_more(self):
        self._dispose_player()
        self._reset_checks()
        self.steps.setCurrentIndex(0)
        self.status.clear()
        self.filter_rows()
        self._update_controls()

    def show_manage(self):
        self.manage_mode = True
        self._dispose_player()
        self._reset_checks()
        self.steps.setCurrentIndex(1)
        self.status.setText(t('study_files_kept'))
        self._update_controls()
        self.reload()

    def cancel_action(self):
        if self.manage_mode and self.steps.currentIndex() == 0:
            self.show_manage()
        else:
            self.reject()

    def unlink(self, row):
        if not self.current() or self._busy or not self._editable(row):
            return
        self._busy = True
        self._update_controls()
        profile, card_id = self.profile, self.card_id
        def done(removed):
            if removed:
                self._undo = removed
                self.on_saved()
                self.reload()
        self.submit(lambda col: unlink_card_resource(_ADDON_DIR, profile, card_id, row), done)

    def undo(self):
        if not self._undo or self._busy or not self.current():
            return
        token = dict(self._undo)
        self._busy = True
        self._update_controls()
        profile, card_id = self.profile, self.card_id
        def done(result):
            if result:
                self._undo = None
                self.on_saved()
                self.reload()
        self.submit(lambda col: restore_card_resource_link(_ADDON_DIR, profile, col, card_id, token), done)

    def finish(self, *_):
        if self.cancelled.is_set():
            return
        resume = self.current()
        self.cancelled.set()
        self._preview_timer.stop()
        self._preview_generation += 1
        if resume:
            self._resume_advance()
        self._dispose_player()
        for dialog in self._previews:
            try:
                dialog.reject()
            except RuntimeError:
                pass


def open_resource_dialog(card_id, **kwargs):
    dialog = CardResourceDialog(card_id, **kwargs)
    _dialogs.append(dialog)
    dialog.finished.connect(lambda *_: _dialogs.remove(dialog) if dialog in _dialogs else None)
    owner = kwargs.get('owner')
    if owner is not None and hasattr(owner, 'present_resource_dialog'):
        owner.present_resource_dialog(dialog)
    else:
        dialog.show()
    return dialog


def reset(*_):
    for dialog in list(_dialogs):
        dialog.reject()
