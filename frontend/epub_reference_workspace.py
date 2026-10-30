"""Independent EPUB reference panes, destination picking, and passage connections."""
import json
from pathlib import Path

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import (QApplication, QComboBox, QDialog, QDockWidget, QLabel, QLineEdit, QListWidget,
                    QPushButton, QVBoxLayout, QWidget, Qt, QUrl)
from aqt.utils import showInfo, tooltip
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.epub_reference import resolve_epub_reference, validate_location, location_allowed
    from ..backend.epub_connections import normalize_location, add_connection, list_connections, remove_connection
    from ..backend.epub_highlights import (load_highlights, add_highlight, update_highlight,
        remove_highlight, update_highlight_note, update_highlight_color, update_highlight_style)
    from ..backend.epub_manager import (get_epub_daily_limit_status, get_epub_font_scale,
        get_read_anchor, get_read_section_index, set_read_section_index)
    from ..backend.epub_appearance import get_appearance, set_appearance
    from ..backend.reader_bookmarks import add_reader_bookmark
    from . import epub_dock as reader
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.epub_reference import resolve_epub_reference, validate_location, location_allowed
    from backend.epub_connections import normalize_location, add_connection, list_connections, remove_connection
    from backend.epub_highlights import (load_highlights, add_highlight, update_highlight,
        remove_highlight, update_highlight_note, update_highlight_color, update_highlight_style)
    from backend.epub_manager import (get_epub_daily_limit_status, get_epub_font_scale,
        get_read_anchor, get_read_section_index, set_read_section_index)
    from backend.epub_appearance import get_appearance, set_appearance
    from backend.reader_bookmarks import add_reader_bookmark
    import epub_dock as reader

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_windows = []
_dialogs = []
_generation = 0
_requests = {False: 0, True: 0}


def reset_for_profile_switch():
    global _generation
    _generation += 1
    for window in list(_windows):
        window.close()
    for dialog in list(_dialogs):
        dialog.reject()


def _keep(dialog):
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    _dialogs.append(dialog)
    dialog.finished.connect(lambda *_: _dialogs.remove(dialog) if dialog in _dialogs else None)
    dialog.show()


def _load(col, profile, location):
    snapshot = resolve_epub_reference(_ADDON_DIR, profile, col, location['card_id'])
    location = validate_location(snapshot, location)
    status = get_epub_daily_limit_status(_ADDON_DIR, profile, location['card_id'],
        count_current_page=False, persist_usage=False)
    if not location_allowed(location, status):
        raise ValueError('EPUB passage is locked')
    snapshot['appearance'] = get_appearance(_ADDON_DIR, profile, location['card_id'])
    highlights = load_highlights(_ADDON_DIR, profile, location['card_id'])
    scale = get_epub_font_scale(_ADDON_DIR, profile, location['card_id'])
    anchor = get_read_anchor(_ADDON_DIR, profile, location['card_id'])
    return snapshot, status, highlights, scale, anchor


class _ReferencePage(reader._EpubDockPage):
    def __init__(self, profile, parent, interceptor):
        super().__init__(profile, parent, interceptor)
        self.owner = parent

    def javaScriptConsoleMessage(self, level, message, line, source):
        prefix = reader._PYCMD_BRIDGE + self.bridge_nonce() + ':'
        if (self.bridge_nonce() and self.owner.current() and isinstance(message, str)
                and len(message) <= reader._MAX_EPUB_BRIDGE_MESSAGE_CHARS and message.startswith(prefix)):
            self.owner.command(message[len(prefix):])


class EpubReferenceWindow(QDockWidget):
    def __init__(self, result, location, *, profile, owner=None, beside=False, on_choose=None, embedded=False):
        snapshot, self.limit, self.highlights, self.scale, self.anchor = result
        super().__init__(snapshot['title'], owner if embedded else mw)
        self.embedded = embedded
        self.snapshot, self.location, self.profile = snapshot, dict(location), profile
        self.owner, self.on_choose = owner, on_choose
        self.generation, self.closed, self.loaded = _generation, False, False
        self.history, self.links_enabled, self.request = [], False, 0
        self.annotation_style = 'highlight'
        self.fragment = ""
        self._last_allowed_scroll = None
        self.setObjectName('incremento_epub_reference_' + str(id(self)))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(280)
        host = QWidget(self)
        layout = QVBoxLayout(host)
        self.engine_profile = QWebEngineProfile(self)
        self.interceptor = reader._EpubRequestInterceptor(self.engine_profile)
        self.engine_profile.setUrlRequestInterceptor(self.interceptor)
        self.page = _ReferencePage(self.engine_profile, self, self.interceptor)
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        for name in ('LocalContentCanAccessRemoteUrls', 'DnsPrefetchEnabled', 'JavascriptCanAccessClipboard',
                     'JavascriptCanOpenWindows', 'LocalStorageEnabled', 'PluginsEnabled', 'ScreenCaptureEnabled'):
            attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
            if attribute is not None:
                settings.setAttribute(attribute, False)
        self.view = QWebEngineView(host)
        self.view.setPage(self.page)
        self.view.loadFinished.connect(self.loaded_document)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        layout.addWidget(self.view, 1)
        toolbar = QWidget(host)
        flow = reader._FlowLayout(toolbar, margin=0, h_spacing=5, v_spacing=4)
        def button(label, callback, *, checkable=False):
            widget = QPushButton(label, toolbar)
            widget.setAccessibleName(label)
            widget.setCheckable(checkable)
            widget.clicked.connect(callback)
            flow.addWidget(widget)
            return widget
        button(t('reader_previous_page'), lambda: self.navigate(self.location['section'] - 1))
        self.sections = QComboBox(toolbar)
        self.sections.setMaximumWidth(240)
        self.sections.setAccessibleName(t('reader_contents'))
        for index, section in enumerate(snapshot['sections']):
            self.sections.addItem(t('reader_epub_connection_label',
                title=section.get('title', '')[:120], section=index + 1), index)
        self.sections.setCurrentIndex(location['section'])
        self.sections.activated.connect(lambda index: self.navigate(index))
        flow.addWidget(self.sections)
        button(t('reader_next_page'), lambda: self.navigate(self.location['section'] + 1))
        button('−', lambda: self.zoom(-.1))
        button('+', lambda: self.zoom(.1))
        self.appearance = QComboBox(toolbar)
        self.appearance.setAccessibleName(t('reader_epub_appearance'))
        for mode in ('original', 'dark', 'night'):
            self.appearance.addItem(t('reader_pdf_appearance_' + mode), mode)
        self.appearance.setCurrentIndex(self.appearance.findData(snapshot['appearance']))
        self.appearance.activated.connect(lambda index: self.set_appearance(self.appearance.itemData(index)))
        flow.addWidget(self.appearance)
        self.links_button = button(t('reader_epub_links_accessible'), self.toggle_links, checkable=True)
        self.back_button = button(t('reader_epub_jump_back_accessible'), self.back)
        self.back_button.setEnabled(False)
        button(t('reader_page_links'), lambda: self.capture(lambda loc: show_connections(loc, owner=self,
                                                                        is_current=self.current)))
        self.search = QLineEdit(toolbar)
        self.search.setMaximumWidth(180)
        self.search.setPlaceholderText(t('reader_find'))
        self.search.returnPressed.connect(lambda: self.view.findText(self.search.text()))
        flow.addWidget(self.search)
        button(t('reader_extract'), lambda: self.js('window.incrementoFillEpubField(0);'))
        self.style_combo = QComboBox(toolbar)
        for style in reader.ANNOTATION_STYLES:
            self.style_combo.addItem(t(f'reader_style_{style}'), style)
        self.style_combo.setAccessibleName(t('reader_annotation_style'))
        self.style_combo.setToolTip(t('reader_annotation_style_help'))
        self.style_combo.currentIndexChanged.connect(self.set_annotation_style)
        flow.addWidget(self.style_combo)
        button(t('reader_mark_selection'), lambda: self.js('window.incrementoAddEpubHighlight();'))
        self.default_color_button = button(t('reader_default_annotation_color'), self.choose_default_highlight_color)
        try:
            from .highlight_color_dialog import set_default_color_button
        except ImportError:
            from highlight_color_dialog import set_default_color_button
        set_default_color_button(self.default_color_button,
            reader.configured_reader_default_highlight_color(reader._config(), self.profile))
        button(t('reader_bookmark'), self.bookmark)
        button(t('reader_read_to_here'), self.mark_read)
        if not embedded:
            button(t('reader_reference_pin'), self.pin)
        if on_choose:
            self.choose_button = button(t('reader_epub_use_passage'), lambda: self.capture(self.choose))
            self.choose_button.setEnabled(False)
        layout.addWidget(toolbar)
        self.setWidget(host)
        if embedded:
            self.setTitleBarWidget(QWidget(self))
            self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        else:
            mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
            self.setFloating(not beside)
            if beside:
                self.pin()
            else:
                self.resize(760, 700)
        self.load()

    def current(self):
        return not self.closed and self.profile == get_active_profile() and self.generation == _generation

    def js(self, script, callback=None):
        if self.current():
            reader._run_epub_javascript(self.page, script, callback)

    def load(self):
        self.loaded = False
        self._last_allowed_scroll = None
        self.page.prepare_document_load(self.snapshot['root'], self.snapshot['paths'][self.location['section']])
        self.view.load(QUrl.fromLocalFile(self.snapshot['paths'][self.location['section']]))
        self.sections.blockSignals(True)
        self.sections.setCurrentIndex(self.location['section'])
        self.sections.blockSignals(False)
        if self.on_choose:
            self.choose_button.setEnabled(False)

    def loaded_document(self, ok):
        if not ok or not self.current():
            return
        self.loaded = True
        section = self.location['section']
        script = reader._build_page_script(card_id=self.location['card_id'], section_index=section,
            scroll_ratio=self.location['scroll'], text_scale=self.scale, read_anchor=self.anchor,
            focus_offset=self.location['offset'], search_query='',
            highlights=[h for h in self.highlights if h['sectionIndex'] == section],
            bridge_nonce=self.page.bridge_nonce(), clickable_links=self.links_enabled,
            link_fragment=self.fragment,
            annotation_style=self.annotation_style,
            default_highlight_color=reader.configured_reader_default_highlight_color(reader._config(), self.profile),
            sections=self.snapshot['sections'], appearance=self.snapshot.get('appearance', 'original'))
        self.js(script)
        if self.on_choose:
            self.choose_button.setEnabled(True)

    def set_annotation_style(self, _index):
        self.annotation_style = self.style_combo.currentData()
        self.js('window.incrementoSetEpubAnnotationStyle && window.incrementoSetEpubAnnotationStyle('
                + json.dumps(self.annotation_style) + ');')

    def capture(self, callback):
        context = (self.request, self.page.bridge_nonce())
        def ready(value):
            if (not self.current() or not self.loaded or context != (self.request, self.page.bridge_nonce())
                    or not isinstance(value, dict) or value.get('cardId') != self.location['card_id']):
                return
            try:
                loc = normalize_location(dict(card_id=value['cardId'], section=value['sectionIndex'],
                    offset=value['focusOffset'], scroll=value['scrollRatio']))
            except (ValueError, KeyError):
                return
            callback(loc)
        self.js('window.incrementoEpubCurrentLocation && window.incrementoEpubCurrentLocation();', ready)

    def choose(self, location):
        if self.on_choose and self.current():
            self.on_choose({**location, "filename": self.snapshot["filename"]})
            self.close()

    def navigate(self, section, *, location=None, remember=False, fragment="", returning=False):
        if not self.current() or not 0 <= section < len(self.snapshot['sections']):
            return
        target = location or dict(card_id=self.location['card_id'], section=section, offset=-1, scroll=0)
        self.request += 1
        request = self.request
        previous = dict(self.location)
        def work(col):
            result = _load(col, self.profile, target)
            if result[0]['filename'] != self.snapshot['filename']:
                raise ValueError('EPUB changed')
            return result
        def ready(result):
            if not self.current() or request != self.request:
                return
            if remember:
                self.history = (self.history + [previous])[-32:]
            elif returning and self.history and self.history[-1] == target:
                self.history.pop()
            self.back_button.setEnabled(bool(self.history))
            self.snapshot, self.limit, self.highlights, _saved_scale, self.anchor = result
            self.fragment = fragment
            self.location = dict(target)
            self.load()
        QueryOp(parent=mw, op=work, success=ready).failure(
            lambda error: tooltip(t('reader_epub_reference_unavailable')) if self.current() else None).run_in_background()

    def back(self):
        if self.history:
            location = self.history[-1]
            self.navigate(location['section'], location=location, returning=True)

    def zoom(self, delta):
        self.scale = max(.7, min(2.2, self.scale + delta))
        self.js(f'window.incrementoSetEpubTextScale({json.dumps(self.scale)});')

    def set_appearance(self, mode):
        if self.current():
            set_appearance(_ADDON_DIR, self.profile, self.location['card_id'], mode)
            refresh_appearance(self.profile, self.location['card_id'])

    def toggle_links(self, checked):
        self.links_enabled = bool(checked)
        self.js(f'window.incrementoSetEpubClickableLinks({json.dumps(self.links_enabled)});')

    def pin(self):
        if getattr(self, 'embedded', False):
            return
        for window in list(_windows):
            if window is not self and not getattr(window, 'embedded', False) and not window.isFloating():
                window.close()
        self.setFloating(False)
        if self.owner is not None and self.owner is not self:
            mode = getattr(self.owner, '_epub_focus_mode', None)
            if mode is not None and mode.active:
                mode.request_enabled(False)
            if self.owner.isFloating():
                self.owner.setFloating(False)
            self.owner.show()
            mw.splitDockWidget(self.owner, self, Qt.Orientation.Horizontal)
        self.show()

    def choose_default_highlight_color(self):
        try:
            from .highlight_color_dialog import choose_highlight_color, refresh_reader_default_highlight_color
        except ImportError:
            from highlight_color_dialog import choose_highlight_color, refresh_reader_default_highlight_color
        context = (self.request, self.page.bridge_nonce())
        color = choose_highlight_color(self,
            reader.configured_reader_default_highlight_color(reader._config(), self.profile),
            addon_dir=_ADDON_DIR, profile=self.profile, default_color=True)
        if color is None or not self.current() or context != (self.request, self.page.bridge_nonce()):
            return
        try:
            color = reader.save_reader_default_highlight_color(mw.addonManager, reader._ADDON_PKG, self.profile, color)
        except Exception:
            showInfo(t('settings_save_failed'))
            return
        refresh_reader_default_highlight_color(self.profile, color)

    def bookmark(self):
        def save(location):
            add_reader_bookmark(_ADDON_DIR, self.profile, location['card_id'], 'epub',
                {'section_index': location['section'], 'scroll_ratio': location['scroll']})
            tooltip(t('reader_epub_bookmark_saved'))
        self.capture(save)

    def mark_read(self):
        if self.current():
            set_read_section_index(_ADDON_DIR, self.profile, self.location['card_id'], self.location['section'], None)
            refresh_read_progress(self.profile, self.location['card_id'])

    def context_menu(self, position):
        def copy(value):
            if not self.current() or not isinstance(value, dict) or value.get('cardId') != self.location['card_id']:
                return False
            html = reader.epub_anchor_link_html(card_id=value['cardId'], section_index=value['sectionIndex'],
                focus_offset=value['focusOffset'], scroll_ratio=value['scrollRatio'], label=self.snapshot['title'])
            return reader.set_reader_anchor_clipboard(html, self.snapshot['title'])
        def populate(menu, value):
            if not self.current() or not isinstance(value, dict) or value.get('cardId') != self.location['card_id']:
                return
            try:
                from .recording_link_dialog import add_context_actions
            except ImportError:
                from recording_link_dialog import add_context_actions
            try:
                source = normalize_location(dict(card_id=value['cardId'], section=value['sectionIndex'],
                    offset=value['focusOffset'], scroll=value['scrollRatio']))
            except (KeyError, ValueError):
                return
            add_context_actions(menu, dict(source, kind='epub', quote=str(self.view.selectedText() or '')[:2000]),
                                owner=self, is_current=self.current)
        reader.show_reader_anchor_context_menu(self.view, position,
            resolver_script=f'window.incrementoEpubAnchorAtPoint({position.x()}, {position.y()});',
            on_copy=copy, run_javascript=lambda script, callback: self.js(script, callback),
            action_label=t('reader_copy_link_to_place'), populate_menu=populate)

    def command(self, message):
        if not self.current() or not self.loaded or ':' not in message:
            return
        name, raw = message.split(':', 1)
        try:
            data = json.loads(raw)
            if (not isinstance(data, dict) or type(data.get('cardId')) is not int
                    or data['cardId'] != self.location['card_id']):
                return
            cid, section = self.location['card_id'], self.location['section']
            if name == 'incremento_epub_progress':
                next_location = normalize_location(dict(card_id=cid, section=data['sectionIndex'], offset=-1,
                                                         scroll=data['scrollRatio']))
                if next_location['section'] != section:
                    return
                if not location_allowed(next_location, self.limit, page_index=data.get('pageIndex', section)):
                    if self._last_allowed_scroll is None:
                        # Reflow can place a section/passage beyond the limit
                        # even when its section index passed the load preflight.
                        self.close()
                        tooltip(t('reader_epub_reference_unavailable'))
                        return
                    self.js(f'window.scrollTo(0, {self._last_allowed_scroll} * '
                            '(document.documentElement.scrollHeight-window.innerHeight));')
                    return
                self.location.update(scroll=next_location['scroll'], offset=-1)
                self._last_allowed_scroll = next_location['scroll']
                return  # Reference navigation never writes the main reader's progress.
            if name == 'incremento_epub_section_nav':
                delta = data.get('delta')
                if type(delta) is int and delta in (-1, 1):
                    self.navigate(section + delta)
                return
            if name == 'incremento_epub_open_link' and self.links_enabled:
                link = reader._resolve_epub_reader_link(data.get('href'), content_root=self.snapshot['root'],
                    current_section_path=self.snapshot['paths'][section], section_paths=self.snapshot['paths'])
                if link and link['kind'] == 'external':
                    reader.open_external_reader_link(link['url'])
                elif link:
                    self.navigate(link['section_index'], remember=True, fragment=link['fragment'])
                return
            if name == 'incremento_epub_fill_field':
                text, index = data.get('text'), data.get('idx')
                if (not isinstance(text, str) or not 0 < len(text) <= reader._MAX_EPUB_SELECTION_CHARS
                        or type(index) is not int or not 0 <= index <= 3):
                    return
                if reader._cb_fill_dock_field is not None:
                    if reader._cb_open_add_card_dock:
                        reader._cb_open_add_card_dock()
                    citation = reader.epub_anchor_link_html(card_id=cid, section_index=section,
                        focus_offset=data.get('startOffset', -1), scroll_ratio=self.location['scroll'],
                        label=t('reader_epub_connection_label', title=self.snapshot['title'], section=section+1))
                    reader._cb_fill_dock_field(index, reader.external_plain_text_to_anki_html(text),
                        include_pdf_citation=False, citation_html=citation, source_link_kind='epub',
                        source_card_id=cid, source_position=section)
                return
            if name in ('incremento_epub_hl_add', 'incremento_epub_hl_update'):
                highlight = data.get('highlight')
                if (not isinstance(highlight, dict) or highlight.get('sectionIndex') != section
                        or not isinstance(highlight.get('id'), str) or len(highlight['id']) > 200
                        or type(highlight.get('startOffset')) is not int or type(highlight.get('endOffset')) is not int
                        or not 0 <= highlight['startOffset'] < highlight['endOffset'] <= 50_000_000):
                    return
                (add_highlight if name.endswith('_add') else update_highlight)(
                    _ADDON_DIR, self.profile, cid, highlight)
            elif name == 'incremento_epub_hl_del':
                remove_highlight(_ADDON_DIR, self.profile, cid, str(data.get('id') or ''))
            elif name == 'incremento_epub_hl_style' or (name == 'incremento_epub_hl_color' and 'color' in data):
                hl_id = str(data.get('id') or '')
                if not any(h['id'] == hl_id and h['sectionIndex'] == section
                           for h in load_highlights(_ADDON_DIR, self.profile, cid, section_index=section)):
                    return
                update = update_highlight_style if name.endswith('_style') else update_highlight_color
                update(_ADDON_DIR, self.profile, cid, hl_id, data.get('style' if name.endswith('_style') else 'color'))
            elif name in ('incremento_epub_hl_note', 'incremento_epub_hl_color'):
                self.edit_highlight(str(data.get('id') or ''), color=name.endswith('_color'))
                return
            else:
                return
            appearance_edit = name == 'incremento_epub_hl_style' or (
                name == 'incremento_epub_hl_color' and 'color' in data)
            refresh_readers(self.profile, cid, exclude=self if appearance_edit else None)
        except (ValueError, TypeError, KeyError, OverflowError):
            return

    def edit_highlight(self, hl_id, *, color=False):
        try:
            from .highlight_color_dialog import choose_highlight_color
            from .highlight_note_dialog import HighlightNoteDialog
        except ImportError:
            from highlight_color_dialog import choose_highlight_color
            from highlight_note_dialog import HighlightNoteDialog
        target = next((h for h in load_highlights(_ADDON_DIR, self.profile, self.location['card_id'])
                       if h['id'] == hl_id and h['sectionIndex'] == self.location['section']), None)
        if target is None:
            return
        if color:
            value = choose_highlight_color(self, target['color'], addon_dir=_ADDON_DIR, profile=self.profile)
            if value and self.current():
                update_highlight_color(_ADDON_DIR, self.profile, self.location['card_id'], hl_id, value)
        else:
            dialog = HighlightNoteDialog(self, title=t('reader_epub_highlight_note_title'),
                                         excerpt=target['text'], current_note=target['note'])
            if dialog.exec() and self.current():
                update_highlight_note(_ADDON_DIR, self.profile, self.location['card_id'], hl_id, dialog.note_text())
        refresh_readers(self.profile, self.location['card_id'])

    def closeEvent(self, event):
        self.closed = True
        self.page._bridge_nonce = ''
        self.view.stop()
        if self in _windows:
            _windows.remove(self)
        super().closeEvent(event)


def focused_reference():
    focus = QApplication.focusWidget()
    if focus is None or QApplication.activeModalWidget() is not None:
        return None
    return next((window for window in _windows if window.current() and window.isVisible()
                 and (focus is window.view or window.view.isAncestorOf(focus))), None)


def refresh_default_highlight_color(profile, color):
    try:
        from .highlight_color_dialog import set_default_color_button
    except ImportError:
        from highlight_color_dialog import set_default_color_button
    for window in list(_windows):
        if window.profile == profile and window.current():
            window.js(f'window.incrementoSetDefaultHighlightColor?.({json.dumps(color)});')
            set_default_color_button(window.default_color_button, color)


def refresh_readers(profile, card_id, *, include_main=True, exclude=None):
    if profile != get_active_profile():
        return
    highlights = load_highlights(_ADDON_DIR, profile, card_id)
    for window in list(_windows):
        if window.current() and window.location['card_id'] == card_id:
            window.highlights = highlights
            if window is exclude:
                continue
            window.js('window.incrementoReplaceEpubHighlights(' + json.dumps(
                [h for h in highlights if h['sectionIndex'] == window.location['section']]) + ');')
    if include_main and reader._current_epub_card_id == card_id and reader._epub_dock is not None:
        reader._run_epub_javascript(reader._epub_dock._view.page(),
            'window.incrementoReplaceEpubHighlights && window.incrementoReplaceEpubHighlights(' + json.dumps(
                [h for h in highlights if h['sectionIndex'] == reader._current_epub_section_index]) + ');')
        reader._update_sources_panel()


def refresh_read_progress(profile, card_id, *, include_main=True):
    if profile != get_active_profile():
        return
    anchor = get_read_anchor(_ADDON_DIR, profile, card_id)
    section = get_read_section_index(_ADDON_DIR, profile, card_id)
    for window in list(_windows):
        if window.current() and window.location['card_id'] == card_id:
            window.anchor = anchor
            window.js(f'window.incrementoSetEpubReadAnchor({json.dumps(anchor)});')
    if include_main and reader._current_epub_card_id == card_id and reader._epub_dock is not None:
        reader._current_epub_read_anchor = anchor
        reader._current_epub_read_section_index = section
        reader._push_epub_read_anchor()
        reader._update_title_and_buttons()


def refresh_appearance(profile, card_id, *, include_main=True):
    if profile != get_active_profile():
        return
    mode = get_appearance(_ADDON_DIR, profile, card_id)
    for window in list(_windows):
        if window.current() and window.location['card_id'] == card_id:
            window.snapshot['appearance'] = mode
            window.appearance.setCurrentIndex(window.appearance.findData(mode))
            window.js(f'window.incrementoSetEpubAppearance({json.dumps(mode)});')
    if include_main and reader._current_epub_card_id == card_id and reader._epub_dock is not None:
        reader._apply_epub_appearance(mode)


def open_reference(location, *, owner=None, beside=False, is_current=lambda: True, on_choose=None):
    location = normalize_location(location)
    profile, generation = get_active_profile(), _generation
    _requests[beside] += 1
    request = _requests[beside]
    def current():
        return (profile == get_active_profile() and generation == _generation
                and request == _requests[beside] and is_current())
    def ready(result):
        if not current():
            return
        host = owner.owner if owner in _windows else owner
        for window in list(_windows):
            if not getattr(window, 'embedded', False) and window.isFloating() != beside:
                window.close()
        window = EpubReferenceWindow(result, location, profile=profile, owner=host,
                                     beside=beside, on_choose=on_choose)
        _windows.append(window)
        window.show()
    QueryOp(parent=mw, op=lambda col: _load(col, profile, location), success=ready).failure(
        lambda error: tooltip(t('reader_epub_reference_unavailable')) if current() else None).run_in_background()


def choose_reference(*, owner=None, callback=None, is_current=lambda: True):
    try:
        from .pdf_bookshelf import _DocumentBookshelfDialog, _load_bookshelf_entries
    except ImportError:
        from pdf_bookshelf import _DocumentBookshelfDialog, _load_bookshelf_entries
    profile, generation = get_active_profile(), _generation
    def current():
        return profile == get_active_profile() and generation == _generation and is_current()
    def ready(entries):
        if not current():
            return
        picker = _DocumentBookshelfDialog(mw, addon_dir=_ADDON_DIR, entries=entries,
                                          attachment_counts={}, selection_only=True)
        picker.setWindowTitle(t('reader_epub_reference'))
        def accepted():
            if current() and picker.selected_card_id:
                location = dict(card_id=picker.selected_card_id, section=0, offset=-1, scroll=0)
                open_reference(location, owner=owner, beside=callback is None,
                               is_current=current, on_choose=callback)
        picker.accepted.connect(accepted)
        _keep(picker)
    QueryOp(parent=mw, op=lambda col: [entry for entry in _load_bookshelf_entries(
        _ADDON_DIR, collection=col, profile=profile) if entry.kind == 'EPUB'], success=ready).failure(
        lambda error: tooltip(t('reader_epub_reference_unavailable')) if current() else None).run_in_background()


def show_connections(location, *, owner=None, is_current=lambda: True):
    source = normalize_location(location)
    profile, generation = get_active_profile(), _generation
    def current():
        return profile == get_active_profile() and generation == _generation and is_current()
    def load(col):
        snapshot = resolve_epub_reference(_ADDON_DIR, profile, col, source['card_id'])
        validate_location(snapshot, source)
        rows = list_connections(_ADDON_DIR, profile, source['card_id'], source['section'])
        for row in rows:
            try:
                target = resolve_epub_reference(_ADDON_DIR, profile, col, row['target']['card_id'])
                validate_location(target, row['target'])
                row['title'], row['available'] = target['title'], True
            except ValueError:
                row['title'], row['available'] = t('reader_epub_reference_unavailable'), False
        return snapshot, rows
    def ready(result):
        if not current():
            return
        snapshot, rows = result
        dialog = QDialog(mw)
        alive = [True]
        dialog.finished.connect(lambda *_: alive.__setitem__(0, False))
        def valid():
            return alive[0] and current()
        dialog.setWindowTitle(t('reader_page_links'))
        dialog.resize(700, 380)
        layout = QVBoxLayout(dialog)
        hint = QLabel(t('reader_epub_connections_hint'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        listing = QListWidget(dialog)
        listing.setAccessibleName(t('reader_page_links'))
        layout.addWidget(listing)
        for row in rows:
            listing.addItem(t('reader_epub_connection_label', title=row['title'], section=row['target']['section'] + 1))
        if rows:
            listing.setCurrentRow(0)
        def selected():
            index = listing.currentRow()
            return rows[index] if 0 <= index < len(rows) else None
        def preview(beside):
            row = selected()
            if valid() and row and row['available']:
                open_reference(row['target'], owner=owner, beside=beside, is_current=valid)
        def open_main():
            row = selected()
            if not valid() or row is None or not row['available']:
                return
            def opened(result):
                if not valid():
                    return
                snapshot = result[0]
                point = row['target']
                reader.show_epub_in_dock(point['card_id'], snapshot['filename'], section_index=point['section'],
                    focus_offset=point['offset'], scroll_ratio=point['scroll'], offer_due_review_prompt=False)
                dialog.accept()
            QueryOp(parent=mw, op=lambda col: _load(col, profile, row['target']), success=opened).failure(
                lambda error: tooltip(t('reader_epub_reference_unavailable')) if valid() else None).run_in_background()
        def remove():
            row = selected()
            if not valid() or row is None:
                return
            def removed(result):
                if valid() and result:
                    index = rows.index(row)
                    rows.pop(index)
                    listing.takeItem(index)
            QueryOp(parent=mw, op=lambda col: remove_connection(_ADDON_DIR, profile,
                source['card_id'], source['section'], row['id']) if valid() else False,
                success=removed).failure(lambda error: tooltip(t('reader_epub_reference_unavailable')) if valid() else None).run_in_background()
        def add():
            def chosen(target):
                def work(col):
                    if not valid():
                        return None
                    live_source = resolve_epub_reference(_ADDON_DIR, profile, col, source['card_id'])
                    if live_source['filename'] != snapshot['filename']:
                        raise ValueError('Source EPUB changed')
                    live_target = _load(col, profile, target)[0]
                    if live_target['filename'] != target.get('filename'):
                        raise ValueError('Target EPUB changed')
                    return add_connection(_ADDON_DIR, profile, source, target)
                def saved(result):
                    if valid() and result:
                        dialog.accept()
                        show_connections(source, owner=owner, is_current=current)
                QueryOp(parent=mw, op=work, success=saved).failure(
                    lambda error: tooltip(t('reader_epub_reference_unavailable')) if valid() else None).run_in_background()
            choose_reference(owner=owner, callback=chosen, is_current=valid)
        actions = QWidget(dialog)
        flow = reader._FlowLayout(actions, margin=0, h_spacing=6, v_spacing=5)
        def recording_action(create):
            try:
                from .recording_link_dialog import open_link_dialog
                from .study_workspace import show_resources
            except ImportError:
                from recording_link_dialog import open_link_dialog
                from study_workspace import show_resources
            if valid():
                recording_source = dict(source, kind='epub')
                if create:
                    open_link_dialog(recording_source, owner=dialog, is_current=valid)
                else:
                    show_resources(recording_source)
        for label, callback in ((t('reader_reference_open'), open_main),
                                (t('reader_epub_reference_preview'), lambda: preview(False)),
                                (t('reader_reference_pin'), lambda: preview(True)),
                                (t('reader_epub_link_passage'), add), (t('reader_reference_remove'), remove),
                                (t('study_link_recording'), lambda: recording_action(True)),
                                (t('study_resources'), lambda: recording_action(False)),
                                (t('reader_close'), dialog.close)):
            button = QPushButton(label, actions)
            button.clicked.connect(lambda checked=False, action=callback: action())
            flow.addWidget(button)
        listing.itemActivated.connect(lambda *_: preview(False))
        layout.addWidget(actions)
        _keep(dialog)
    QueryOp(parent=mw, op=load, success=ready).failure(
        lambda error: tooltip(t('reader_epub_reference_unavailable')) if current() else None).run_in_background()
