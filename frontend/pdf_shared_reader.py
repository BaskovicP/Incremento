"""Instance-owned bridge for the main PDF reading UI in supplemental panes.

Uses the original reader's storage and dialogs. Never swaps the main reader's
module globals: navigation, callbacks, and document identity belong to this pane.
"""
import json
import math


# Only reader tools are accepted; review/card/scheduling commands never reach
# the original dock's global dispatcher.
READER_COMMANDS = frozenset({
    'incremento_pdf_nav', 'incremento_pdf_zoom', 'incremento_pdf_scroll',
    'incremento_pdf_hl_add', 'incremento_pdf_hl_update', 'incremento_pdf_hl_del',
    'incremento_pdf_hl_note', 'incremento_pdf_hl_color', 'incremento_pdf_bookmark_add',
    'incremento_pdf_bookmark_delete', 'incremento_pdf_bookmark_list',
    'incremento_pdf_mark_read', 'incremento_pdf_appearance', 'incremento_pdf_link_preview_zoom',
    'incremento_pdf_link_preview_size',
    'incremento_pdf_page_links', 'incremento_pdf_open_link', 'incremento_pdf_contents',
    'incremento_pdf_find', 'incremento_pdf_find_nav', 'incremento_pdf_open_find_dialog',
    'incremento_pdf_limit_override', 'incremento_pdf_annotations',
    'incremento_fill_field', 'incremento_pdf_snapshot',
    'incremento_pdf_controls',
    'incremento_pdf_page_labels',
})


def reader_service():
    try:
        from . import pdf_dock
    except ImportError:
        import pdf_dock
    return pdf_dock


class SharedPdfReader:
    def __init__(self, owner, *, service=None, on_change=None):
        self.owner = owner
        self.state = owner.state
        self.service = service if service is not None else reader_service()
        self.nonce = self.state.nonce
        self.on_change = on_change or self.changed
        self.search = {'query': '', 'hits': [], 'activeIndex': -1}
        self.search_generation = 0
        self._find_queries = None
        self.page_labels = ()

    def current(self):
        return self.state.is_current(self.service._active_profile(), self.nonce)

    def reply(self, function, value):
        if self.current():
            self.owner.page.runJavaScript(f'window.{function}?.({json.dumps(value)});')

    def storage(self, function, *args, **kwargs):
        return getattr(self.service, function)(self.service._ADDON_DIR,
            self.state.profile, self.state.card_id, *args, **kwargs)

    def page_allowed(self, value, *, zero=False):
        return type(value) is int and (0 if zero else 1) <= value <= self.state.max_page

    def refresh(self, kind):
        if not self.current():
            return
        if kind == 'highlights':
            self.reply('incrementoReceivePdfHighlights', self.storage('load_highlights'))
        elif kind == 'bookmarks':
            self.reply('incrementoReceivePdfBookmarks', self.storage('list_reader_bookmarks', 'pdf'))
        elif kind == 'reading':
            self.reply('incrementoReceivePdfReadProgress', {
                'page': self.storage('get_read_page'), 'anchor': self.storage('get_read_anchor')})

    def changed(self, kind):
        try:
            from .pdf_reference_workspace import refresh_reference_readers
        except ImportError:
            from pdf_reference_workspace import refresh_reference_readers
        refresh_reference_readers(self.state.profile, self.state.card_id, kind)
        s = self.service
        if s.current_pdf_card_id() == self.state.card_id:
            if kind == 'highlights':
                s._push_pdf_highlights(self.state.card_id)
            elif kind == 'bookmarks':
                s._push_pdf_bookmarks(self.state.card_id)
            elif kind == 'reading' and s._pdf_dock:
                value = {'page': self.storage('get_read_page'), 'anchor': self.storage('get_read_anchor')}
                s._pdf_dock._view.page().runJavaScript(
                    'window.incrementoReceivePdfReadProgress?.(' + json.dumps(value) + ');')
        if kind == 'highlights':
            self.sync_annotations(dirty=True)

    def sync_annotations(self, source=None, callback=None, *, dirty=False):
        s = self.service
        def done(result, error):
            if not self.current():
                return
            if error:
                s.tooltip(s.sync_error_text(error))
            else:
                self.refresh('highlights')
                if s.current_pdf_card_id() == self.state.card_id:
                    s._push_pdf_highlights(self.state.card_id)
                # Reopen this view with the annotation-free PDF rendering copy,
                # retaining its transient position (not the main pane's page).
                if result.get('reader_changed'):
                    if s.current_pdf_card_id() == self.state.card_id:
                        s._reload_current_pdf_annotations(result)
                    else:
                        s._refresh_reference_pdf_state(self.state.card_id, 'highlights', annotation_result=result)
                elif result.get('reader_path') and (result.get('appearance_changed')
                        or getattr(self.owner, '_reader_path', None) != result['reader_path']):
                    self.owner.reload_reader(result)
                if (not result.get('reader_changed') and result.get('appearance_changed')
                        and s.current_pdf_card_id() == self.state.card_id):
                    s._reload_current_pdf_annotations(result)
            if callback:
                callback(result, error)
        s._annotation_queue.request(s._ADDON_DIR, self.state.profile, self.state.card_id,
            self.state.filename, source_path=source, callback=done,
            dirty=dirty, immediate=source is not None or callback is not None,
            callback_key=callback or ('reference', self.nonce), automatic=source is None and callback is None)

    def handle(self, message):
        if not self.current() or not isinstance(message, str) or len(message) > 24_000_000:
            return False
        name, _, raw = message.partition(':')
        if name not in READER_COMMANDS or (name != 'incremento_pdf_snapshot' and len(message) > 1_000_000):
            return False
        try:
            data = json.loads(raw) if raw.startswith(('{', '[')) else None
            if isinstance(data, dict) and 'cardId' in data and (
                    type(data['cardId']) is not int or data['cardId'] != self.state.card_id):
                return False
            return self._handle(name, raw, data)
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
            return False

    def _handle(self, name, raw, data):
        s, state = self.service, self.state
        if name in ('incremento_pdf_nav', 'incremento_pdf_zoom'):
            cid, value = raw.split(':')
            if int(cid) != state.card_id:
                return False
            if name.endswith('_nav'):
                page = int(value)
                if not self.page_allowed(page):
                    return False
                self.search_generation += 1
                state.page, state.scroll_ratio = page, 0
                self.owner.command('position')
            else:
                zoom = float(value)
                if not math.isfinite(zoom) or not .25 <= zoom <= 4:
                    return False
                state.zoom = zoom
        elif name == 'incremento_pdf_scroll':
            ratio = data.get('scrollRatio')
            if type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
                return False
            state.scroll_ratio = ratio
        elif name in ('incremento_pdf_hl_add', 'incremento_pdf_hl_update'):
            highlight = data['highlight']
            if not isinstance(highlight, dict) or not self.page_allowed(highlight.get('page')):
                return False
            self.storage('add_highlight' if name.endswith('_add') else 'update_highlight', highlight)
            self.on_change('highlights')
        elif name == 'incremento_pdf_hl_del':
            highlight_id = str(data.get('id') or '')
            self.storage('remove_highlight', highlight_id)
            self.storage('delete_pdf_card_source_for_highlight', highlight_id)
            self.on_change('highlights')
        elif name == 'incremento_pdf_hl_note':
            self.edit_note(str(data.get('id') or ''))
        elif name == 'incremento_pdf_hl_color':
            try:
                from .highlight_color_dialog import choose_highlight_color, refresh_reader_default_highlight_color
            except ImportError:
                from highlight_color_dialog import choose_highlight_color, refresh_reader_default_highlight_color
            context = (state.card_id, state.filename, state.page)
            choose_default = data.get('defaultColor') is True
            if choose_default and data.get('cardId') != state.card_id:
                return False
            color = choose_highlight_color(self.owner, data.get('currentColor', 'yellow'),
                addon_dir=s._ADDON_DIR, profile=state.profile, default_color=choose_default)
            if not self.current() or context != (state.card_id, state.filename, state.page):
                return False
            if choose_default and color is not None:
                try:
                    color = s.save_reader_default_highlight_color(s.mw.addonManager, s._ADDON_PKG, state.profile, color)
                except Exception:
                    color = None
                    s.showInfo(s.t('settings_save_failed'))
                else:
                    refresh_reader_default_highlight_color(state.profile, color)
            self.reply('incrementoPickPdfHighlightColor', color)
        elif name == 'incremento_pdf_bookmark_add':
            if not self.page_allowed(data.get('page')):
                return False
            self.storage('add_reader_bookmark', 'pdf', {'page': data['page']})
            self.on_change('bookmarks')
        elif name == 'incremento_pdf_bookmark_delete':
            self.storage('delete_reader_bookmark', 'pdf', str(data.get('id') or ''))
            self.on_change('bookmarks')
        elif name == 'incremento_pdf_bookmark_list':
            if int(raw) != state.card_id:
                return False
            self.refresh('bookmarks')
        elif name == 'incremento_pdf_mark_read':
            page = data.get('readPage')
            if not self.page_allowed(page, zero=True):
                return False
            anchor = data.get('anchor')
            self.storage('set_read_page', page, anchor if isinstance(anchor, dict) else None)
            self.on_change('reading')
        elif name == 'incremento_pdf_appearance':
            if data.get('mode') not in ('original', 'dark', 'night'):
                return False
            self.storage('set_pdf_appearance_mode', data['mode'])
        elif name == 'incremento_pdf_page_labels':
            if data.get('cardId') != state.card_id or data.get('filename') != state.filename:
                return False
            labels = data.get('labels')
            if labels is None:
                self.page_labels = ()
            elif (isinstance(labels, list) and 0 < len(labels) <= 20_000
                  and all(isinstance(label, str) and len(label) <= 128
                          and not any(ord(char) < 32 or ord(char) == 127 for char in label) for label in labels)):
                self.page_labels = tuple(label.strip() for label in labels)
            else:
                return False
        elif name == 'incremento_pdf_controls':
            if data.get('cardId') != state.card_id or type(data.get('collapsed')) is not bool:
                return False
            return s.save_pdf_controls_collapsed(data['collapsed'], profile=state.profile, reading_only=True)
        elif name == 'incremento_pdf_link_preview_size':
            if data.get('cardId') != state.card_id:
                return False
            return s.save_pdf_link_preview_size(data.get('size'), profile=state.profile)
        elif name == 'incremento_pdf_link_preview_zoom':
            zoom = data.get('zoom')
            if type(zoom) not in (int, float) or not 1 <= zoom <= 4:
                return False
            config = dict(s._config())
            values = dict(config.get('pdf_link_preview_zoom_by_profile') or {})
            values[state.profile] = zoom
            config['pdf_link_preview_zoom_by_profile'] = values
            s.save_addon_config(s.mw.addonManager, s._ADDON_PKG, config)
        elif name == 'incremento_pdf_page_links':
            self.owner.command('page_links', data)
        elif name == 'incremento_pdf_open_link':
            s.open_external_reader_link(data.get('url'))
        elif name == 'incremento_pdf_contents':
            self.contents(data)
        elif name == 'incremento_pdf_find':
            self.find(str(data.get('query') or '')[:200])
        elif name == 'incremento_pdf_find_nav':
            hits = self.search['hits']
            if hits:
                index = self.search['activeIndex'] + (1 if data.get('direction', 0) > 0 else -1)
                self.search['activeIndex'] = max(0, min(index, len(hits) - 1))
                self.jump_to_search_hit()
        elif name == 'incremento_pdf_open_find_dialog':
            self.search_dialog()
        elif name == 'incremento_pdf_limit_override':
            if int(raw) != state.card_id:
                return False
            status = self.storage('set_pdf_daily_limit_override', enabled=True, current_page=state.page)
            try:
                from ..backend.pdf_reader_state import maximum_reference_page
            except ImportError:
                from backend.pdf_reader_state import maximum_reference_page
            state.max_page = maximum_reference_page(status)
            self.reply('incrementoReceivePdfLimitStatus', status)
        elif name == 'incremento_pdf_annotations':
            try:
                from .pdf_annotation_dialog import show_pdf_annotation_dialog
            except ImportError:
                from pdf_annotation_dialog import show_pdf_annotation_dialog
            saved = self.storage('pdf_annotation_sync_state') or {}
            show_pdf_annotation_dialog(self.owner, self.owner._source_path, saved.get('source_path', ''),
                lambda source, done: self.sync_annotations(source, done) if self.current() else None)
        elif name == 'incremento_fill_field':
            self.owner.extract_reader_selection(data)
        elif name == 'incremento_pdf_snapshot':
            if not self.page_allowed(data.get('page')):
                return False
            self.owner.extract_reader_snapshot(data)
        else:
            return False
        return True

    def edit_note(self, highlight_id):
        s = self.service
        highlight = next((row for row in self.storage('load_highlights') if row['id'] == highlight_id), None)
        if not highlight:
            return
        profile, card_id, filename = self.state.profile, self.state.card_id, self.state.filename
        collection = getattr(getattr(s, 'mw', None), 'col', None)
        expected = (str(highlight.get('note') or ''), str(highlight.get('note_html') or ''))

        def is_current():
            return (self.current() and self.state.card_id == card_id and self.state.filename == filename
                    and getattr(getattr(s, 'mw', None), 'col', None) is collection)

        def save(dialog):
            updated = s.update_highlight_note(s._ADDON_DIR, profile, card_id, highlight_id,
                dialog.note_text(), note_html=dialog.note_html(), expected_note=expected)
            if updated is None:
                return s.t('reader_note_editor_changed')
            self.on_change('highlights')
            return None

        s.HighlightNoteDialog.show_for_annotation(getattr(s, 'mw', self.owner),
            key=(s._ADDON_DIR, profile, id(collection), 'pdf', card_id, highlight_id),
            title=s.t('reader_pdf_highlight_note_title'), excerpt=str(highlight.get('text') or ''),
            current_note=expected[0], current_note_html=expected[1], is_current=is_current, save=save)

    def citation_page(self, page):
        label = self.page_labels[page - 1] if 0 < page <= len(self.page_labels) else ''
        mode = self.service.configured_pdf_citation_page_numbering()
        if mode == 'pdf' or not label:
            return str(page)
        if mode == 'both' and label != str(page):
            return self.service.t('reader_pdf_citation_page_both', label=label, page=page)
        return label

    def contents(self, data):
        try:
            from .reader_contents_popup import ReaderContentsPopup
            from ..backend.reader_contents import normalize_contents_entries
        except ImportError:
            from reader_contents_popup import ReaderContentsPopup
            from backend.reader_contents import normalize_contents_entries
        location, total, token = data.get('location') or {}, data.get('totalPages'), data.get('token')
        page, ratio = location.get('page'), location.get('scrollRatio')
        if (not self.page_allowed(page) or type(total) is not int or not page <= total <= 1_000_000
                or type(token) is not int or token < 0 or type(ratio) not in (int, float)
                or not math.isfinite(ratio) or not 0 <= ratio <= 1):
            return
        def open_entry(entry):
            if self.current():
                self.owner.page.runJavaScript('window.incrementoPdfContentsJump?.('
                    + json.dumps(entry) + ',' + str(token) + ');')
        def save_place(label):
            if self.current():
                self.storage('add_reader_bookmark', 'pdf', {'page': page, 'scroll_ratio': ratio},
                    label=label, replace_label=True)
                self.on_change('bookmarks')
        previous = getattr(self.owner, '_contents_popup', None)
        if previous:
            previous.close()
            previous.deleteLater()
        popup = ReaderContentsPopup(self.owner,
            entries=normalize_contents_entries(data.get('entries'), 'pdf', min(total, self.state.max_page)),
            bookmarks=self.storage('list_reader_bookmarks', 'pdf'), current_position=page, kind='pdf',
            is_current=self.current, open_entry=open_entry, save_place=save_place)
        self.owner._contents_popup = popup
        popup.show_at(self.owner.view)

    def find(self, query):
        try:
            from .latest_query import LatestQuery
        except ImportError:
            from latest_query import LatestQuery
        from aqt.operations import QueryOp
        self.search_generation += 1
        def current(request):
            return self.current() and request['generation'] == self.search_generation
        def dispatch(ticket, success, failure, progress):
            request = ticket.payload
            def work(col):
                try:
                    from ..backend.db import CompiledSearch
                except ImportError:
                    from db import CompiledSearch
                s, text = self.service, request['query'].strip()
                compiled = CompiledSearch(text, cancel=ticket.cancel)
                rows = s.search_pdf_text_index_for_card(s._ADDON_DIR, request['profile'],
                    request['cid'], compiled, limit=250) if text else []
                return [{'page': page, 'excerpt': s._pdf_search_snippet(body, text, max_len=260),
                         'snippet': s._pdf_search_snippet(body, text)} for page, body in rows
                        if page <= request['maximum']]
            QueryOp(parent=self.owner, op=work, success=success).failure(failure).run_in_background()
        def publish(request, hits):
            self.search = {'query': request['query'], 'hits': hits, 'activeIndex': 0 if hits else -1}
            self.jump_to_search_hit()
        if self._find_queries is None:
            self._find_queries = LatestQuery(dispatch=dispatch, accept=current, success=publish,
                failure=lambda request, error: publish(request, []))
        self._find_queries.submit({'query': query, 'generation': self.search_generation,
            'profile': self.state.profile, 'cid': self.state.card_id, 'maximum': self.state.max_page})

    def jump_to_search_hit(self):
        if not self.current():
            return
        hits, index = self.search['hits'], self.search['activeIndex']
        if hits and 0 <= index < len(hits):
            delta = hits[index]['page'] - self.state.page
            self.owner.page.runJavaScript(f'window.incrementoPdfNav?.({delta});')
        self.reply('incrementoReceivePdfSearchState', self.search)

    def search_dialog(self):
        self.search_generation += 1
        previous = getattr(self.owner, '_search_dialog', None)
        if previous is not None:
            previous.close()
            previous.deleteLater()
        try:
            from .current_document_search_dialog import _CurrentDocumentSearchDialog
        except ImportError:
            from current_document_search_dialog import _CurrentDocumentSearchDialog
        service, profile, cid, maximum = self.service, self.state.profile, self.state.card_id, self.state.max_page
        def jump(hit, index, query):
            results = dialog._hits
            if self.current() and 0 <= index < len(results) and results[index] == hit:
                self.search_generation += 1
                self.search = {'query': query, 'hits': list(results), 'activeIndex': index}
                self.jump_to_search_hit()
                return True
            return False
        def hits(query, *, cancel=None):
            try:
                from ..backend.db import CompiledSearch
            except ImportError:
                from db import CompiledSearch
            compiled = CompiledSearch(query[:200], cancel=cancel)
            rows = service.search_pdf_text_index_for_card(service._ADDON_DIR, profile, cid, compiled, limit=250)
            return [{'page': page, 'snippet': service._pdf_search_snippet(text, query),
                     'excerpt': service._pdf_search_snippet(text, query, max_len=260)}
                    for page, text in rows if page <= maximum]
        dialog = _CurrentDocumentSearchDialog(self.owner, document_kind='pdf',
            document_label=self.owner.windowTitle(), initial_query=self.search['query'],
            search_hits_fn=hits, open_hit_fn=jump, open_search_all_fn=lambda query: None,
            request_is_current=self.current)
        dialog._search_all_btn.hide()
        dialog.show()
        self.owner._search_dialog = dialog
