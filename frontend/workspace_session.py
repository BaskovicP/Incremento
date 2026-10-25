"""Capture live pane settings and reopen canonical content under a captured profile."""
from importlib import import_module
import json
from pathlib import Path
from types import SimpleNamespace

from aqt.operations import QueryOp
from aqt.qt import QTimer

try:
    from ..backend.workspace_layouts import pane_kind, normalize_controls
    from ..backend.pdf_reference import resolve_pdf_reference
    from ..backend.epub_reference import resolve_epub_reference
    from ..backend.paths import get_user_files_dir
    from ..backend.pdf_manager import get_page, get_scroll_ratio, get_pdf_daily_limit_status
    from ..backend.pdf_reader_state import maximum_reference_page
    from ..backend.epub_reference import validate_location, location_allowed
    from ..backend.epub_manager import get_epub_progress, get_epub_daily_limit_status
    from ..backend.writing_manager import writing_file_abspath
    from ..backend.video_manager import get_video_note_media
except ImportError:
    from backend.workspace_layouts import pane_kind, normalize_controls
    from backend.pdf_reference import resolve_pdf_reference
    from backend.epub_reference import resolve_epub_reference
    from backend.paths import get_user_files_dir
    from backend.pdf_manager import get_page, get_scroll_ratio, get_pdf_daily_limit_status
    from backend.pdf_reader_state import maximum_reference_page
    from backend.epub_reference import validate_location, location_allowed
    from backend.epub_manager import get_epub_progress, get_epub_daily_limit_status
    from backend.writing_manager import writing_file_abspath
    from backend.video_manager import get_video_note_media

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_MODELS = {'pdf': 'Incremento PDF', 'epub': 'Incremento EPUB', 'writing': 'Incremento Writing',
           'video': 'Incremento Video', 'web': 'Incremento Web', 'local_file': 'Incremento Local File'}


class WorkspaceSession:
    def __init__(self, main, profile):
        self.main, self.profile = main, profile

    @staticmethod
    def _module(kind):
        name = kind + ('_workspace' if kind.endswith('_reference') else '_dock')
        return import_module('.' + name, __package__)

    def _describe(self, dock):
        kind = pane_kind(dock.objectName())
        entry = {'name': dock.objectName(), 'kind': kind}
        module = self._module(kind)
        if kind == 'pdf_reference':
            state = dock.state
            entry.update(card_id=state.card_id, zoom=state.zoom)
        elif kind == 'epub_reference':
            entry['card_id'] = dock.location['card_id']
            entry['controls'] = {'links': dock.links_enabled, 'scale': dock.scale,
                                 'appearance': dock.snapshot.get('appearance', 'original')}
        elif kind == 'add_card':
            pass
        elif kind == 'local_file':
            entry['card_id'] = module._current_card_id
        else:
            entry['card_id'] = getattr(module, 'current_' + kind + '_card_id')()
            if kind == 'epub':
                entry.update(controls={'collapsed': dock._controls_collapsed,
                                       'groups': dock._epub_control_visibility,
                                       'scale': module._current_epub_font_scale,
                                       'appearance': dock._appearance_combo.currentData(),
                                       'links': dock._links_btn.isChecked()})
            elif kind == 'writing':
                entry['controls'] = {'preview': dock._preview_visible, 'wrap': dock._wrap_enabled,
                                     'focus': dock._focus_mode, 'scale': dock._font_scale,
                                     'keep_open': module._writing_keep_open, 'split': dock._split.sizes()}
            elif kind == 'video':
                entry['position'] = module._last_known_position
        mode = getattr(dock, '_pdf_focus_mode', None) or getattr(dock, '_epub_focus_mode', None)
        if mode is not None:
            entry['focused'] = mode.active
        return entry

    def capture(self, panes, done):
        """Wait for PDF toolbar state; an interrupted capture must never save half a workspace."""
        profile, entries, waiting = self.profile(), [], set()
        timer = QTimer(self.main)
        timer.setSingleShot(True)
        finished = False
        def finish(ok=True):
            nonlocal finished
            if finished:
                return
            finished = True
            timer.stop()
            timer.deleteLater()
            done(entries if ok and profile == self.profile() else [])
        timer.timeout.connect(lambda: finish(False))
        try:
            for index, dock in enumerate(panes):
                entry = self._describe(dock)
                entries.append(entry)
                if entry['kind'] in ('pdf', 'pdf_reference'):
                    waiting.add(index)
            for index in tuple(waiting):
                dock, entry = panes[index], entries[index]
                page = dock.page if entry['kind'] == 'pdf_reference' else dock._view.page()
                def received(value, index=index, dock=dock):
                    if finished:
                        return
                    entry = entries[index]
                    if not isinstance(value, dict) or value.get('card_id') != entry['card_id']:
                        finish(False)
                        return
                    try:
                        if self._describe(dock).get('card_id') != entry['card_id']:
                            finish(False)
                            return
                    except RuntimeError:
                        finish(False)
                        return
                    for key in ('zoom', 'controls'):
                        if key in value:
                            entry[key] = value[key]
                    waiting.discard(index)
                    if not waiting:
                        finish()
                page.runJavaScript('window.incrementoPdfWorkspaceState?.() || null;', received)
        except Exception:
            finish(False)
            return
        if not waiting:
            finish()
        elif not finished:
            timer.start(5000)

    def _resolve(self, col, profile, entry):
        kind = entry['kind']
        if kind == 'add_card':
            return {}
        cid = entry['card_id']
        card = col.get_card(cid)
        note = col.get_note(card.nid)
        base = kind.removesuffix('_reference')
        if (note.note_type() or {}).get('name') != _MODELS[base]:
            raise ValueError('Saved card type changed')
        if base == 'pdf':
            snapshot = resolve_pdf_reference(_ADDON_DIR, profile, col, cid)
            status = get_pdf_daily_limit_status(_ADDON_DIR, profile, cid, count_current_page=False, persist_usage=False)
            return {'snapshot': snapshot, 'maximum': maximum_reference_page(status),
                    'position': {'page': get_page(_ADDON_DIR, profile, cid),
                                 'scroll': get_scroll_ratio(_ADDON_DIR, profile, cid)}}
        if base == 'epub':
            snapshot = resolve_epub_reference(_ADDON_DIR, profile, col, cid)
            section, scroll, _ = get_epub_progress(_ADDON_DIR, profile, cid)
            location = {'card_id': cid, 'section': section, 'offset': -1, 'scroll': scroll}
            location = validate_location(snapshot, location)
            status = get_epub_daily_limit_status(_ADDON_DIR, profile, cid, count_current_page=False, persist_usage=False)
            if not location_allowed(location, status):
                raise ValueError('Saved section is locked')
            result = {'snapshot': snapshot, 'location': location, 'limit': status}
            if kind == 'epub_reference':
                result['reference'] = self._module(kind)._load(col, profile, location)
            return result
        if kind == 'writing':
            relpath = str(note['Markdown_File'] or '').strip()
            root = get_user_files_dir(_ADDON_DIR, profile).resolve()
            path = Path(writing_file_abspath(_ADDON_DIR, relpath, profile=profile))
            if not relpath or not path.is_relative_to(root / 'writing') or not path.is_file():
                raise ValueError('Saved writing unavailable')
            return {'title': str(note['Title']), 'relpath': relpath}
        if kind == 'video':
            return {'url': str(note['YouTube_URL'] or ''), 'media': get_video_note_media(note)}
        return {'card_id': cid, 'note_id': card.nid}

    def restore(self, entries, current, done):
        profile = self.profile()
        # Reference modules own Qt classes: import them on the UI thread before
        # their read-only resolver is used by the collection worker.
        for kind in {entry.get('kind') for entry in entries}:
            if kind in ('pdf_reference', 'epub_reference'):
                self._module(kind)
        def valid():
            return current() and profile == self.profile()
        def resolve(col):
            results = []
            for entry in entries:
                if not valid():
                    return []
                try:
                    result = self._resolve(col, profile, entry)
                except Exception:
                    result = None
                results.append(result)
            return results
        def ready(results):
            if not valid():
                return
            panes, missing = [], 0
            self._restore_current = valid
            for entry, result in zip(entries, results):
                if not valid():
                    return
                if result is None:
                    missing += 1
                    continue
                try:
                    dock = self._open(entry, result)
                    if dock is None:
                        raise ValueError('Pane unavailable')
                    panes.append(dock)
                except Exception:
                    missing += 1
            done(panes, missing)
        def failed(error):
            if valid():
                done([], len(entries))
        try:
            QueryOp(parent=self.main, op=resolve, success=ready).failure(failed).run_in_background()
        except Exception as error:
            failed(error)

    def _pdf_position(self, cid, result, window=None):
        """Keep an open view in place; otherwise resume the document's latest progress."""
        position = result['position']
        if window is not None:
            position = {'page': window.state.page, 'scroll': window.state.scroll_ratio}
        else:
            reader = self._module('pdf')
            live = getattr(reader, '_live_pdf_location', lambda cid: None)(cid)
            if (live is not None and live.get('profile') == self.profile()
                    and live.get('filename') == result['snapshot']['filename']):
                position = {'page': live['page'], 'scroll': live['scroll_ratio']}
        page = max(1, min(position['page'], result['maximum']))
        return {'page': page, 'scroll': position['scroll'] if page == position['page'] else 0}

    def _epub_position(self, cid, result, window=None):
        location = result['location']
        if window is not None:
            live = window.location
        else:
            reader = self._module('epub')
            live = None
            if (reader.current_epub_card_id() == cid
                    and reader._current_epub_filename == result['snapshot']['filename']):
                live = {'card_id': cid, 'section': reader._current_epub_section_index,
                        'offset': -1, 'scroll': reader._current_epub_scroll_ratio}
        if live is not None:
            live = validate_location(result['snapshot'], live)
            if location_allowed(live, result['limit']):
                location = live
        return dict(location)

    def _open(self, entry, result):
        kind, cid = entry['kind'], entry.get('card_id')
        module, controls = self._module(kind), normalize_controls(entry.get('controls'))
        if kind.endswith('_reference'):
            for window in module._windows:
                if window.objectName() == entry['name']:
                    other_id = window.state.card_id if kind == 'pdf_reference' else window.location['card_id']
                    if other_id != cid:
                        window.setObjectName(entry['name'] + '_kept_' + str(id(window)))
        if kind == 'pdf':
            position = self._pdf_position(cid, result)
            module.show_pdf_in_dock(cid, result['snapshot']['filename'],
                position['page'], entry.get('zoom', 1),
                scroll_ratio_override=position['scroll'], preserve_history=True, offer_due_review_prompt=False)
            dock = module._pdf_dock
        elif kind == 'pdf_reference':
            dock = next((window for window in module._windows
                         if entry['name'] in (window.objectName(), getattr(window, '_workspace_saved_name', None))
                         and window.state.card_id == cid and not window.state.closed), None)
            position = self._pdf_position(cid, result, dock)
            if dock is None:
                if len(module._windows) + len(module._pending_windows) >= module._MAX_WINDOWS:
                    return None
                dock = module.ReferenceWindow(result['snapshot'], profile=self.profile(),
                    page=position['page'], scroll_ratio=position['scroll'], zoom=entry.get('zoom', 1),
                    max_page=result['maximum'], beside=False, owner=None, independent=True)
                module._windows.append(dock)
            else:
                dock.state.max_page = result['maximum']
                dock.state.page = position['page']
                dock.state.zoom, dock.state.scroll_ratio = entry.get('zoom', 1), position['scroll']
                dock.reload_reader(dock.reader.service._initial_pdf_annotation_result(
                    self.profile(), cid, result['snapshot']['path']))
        elif kind == 'epub':
            location = self._epub_position(cid, result)
            module.show_epub_in_dock(cid, result['snapshot']['filename'], section_index=location['section'],
                scroll_ratio=location['scroll'], focus_offset=location['offset'], offer_due_review_prompt=False)
            dock = module._epub_dock
            if 'groups' in controls:
                module._apply_epub_control_visibility(controls['groups'])
            if 'collapsed' in controls:
                module._set_epub_controls_collapsed(controls['collapsed'], remember=False)
            if 'scale' in controls:
                module._current_epub_font_scale = controls['scale']
                module._load_current_section()
            if 'links' in controls:
                module._toggle_epub_clickable_links(controls['links'])
            if 'appearance' in controls:
                module._set_epub_appearance(controls['appearance'])
        elif kind == 'epub_reference':
            dock = next((window for window in module._windows
                         if entry['name'] in (window.objectName(), getattr(window, '_workspace_saved_name', None))
                         and window.location['card_id'] == cid and not window.closed), None)
            location = self._epub_position(cid, result, dock)
            if dock is None:
                dock = module.EpubReferenceWindow(result['reference'], location,
                    profile=self.profile(), beside=False)
                module._windows.append(dock)
            else:
                dock.location = location
                dock.load()
            if 'scale' in controls:
                dock.scale = controls['scale']
            if 'links' in controls:
                dock.links_enabled = controls['links']
                dock.links_button.setChecked(controls['links'])
            if 'appearance' in controls:
                dock.snapshot['appearance'] = controls['appearance']
                dock.appearance.setCurrentIndex(dock.appearance.findData(controls['appearance']))
        elif kind == 'writing':
            previous = getattr(module, '_current_writing_card_id', None)
            if previous is not None and previous != cid and not module._flush_editor_state():
                return None
            keep_open = controls.get('keep_open', True)
            module.show_writing_in_dock(cid, result['title'], result['relpath'], keep_open=keep_open)
            module.set_keep_open(keep_open)
            dock = module._writing_dock
            for key, function in (('wrap', '_apply_wrap_mode'), ('focus', '_apply_focus_mode'),
                                  ('preview', '_apply_preview_visibility'), ('scale', '_apply_font_scale')):
                if key in controls:
                    getattr(module, function)(controls[key])
            if 'split' in controls:
                dock._split.setSizes(controls['split'])
        elif kind == 'video':
            media = result['media']
            module.show_video_in_dock(cid, result['url'], entry.get('position', 0), **media)
            dock = module._video_dock
        elif kind == 'add_card':
            module.open_add_card_dock()
            dock = module.get_add_card_dock()
        else:
            getattr(module, 'on_' + kind + '_question_shown')(
                SimpleNamespace(id=cid, nid=result['note_id']))
            if kind == 'web':
                dock = module._runtime.dock if module.current_web_card_id() == cid else None
            else:
                dock = module._local_file_dock if module._current_card_id == cid else None
        if dock is None:
            return None
        dock.setObjectName(entry['name'])
        if kind in ('pdf', 'pdf_reference'):
            self._restore_pdf_controls(dock, cid, controls, reference=kind == 'pdf_reference')
        return dock

    def _restore_pdf_controls(self, dock, cid, controls, *, reference):
        view = dock.view if reference else dock._view
        profile = self.profile()
        current = getattr(self, '_restore_current', lambda: True)
        def apply(*_):
            try:
                active = dock.state.card_id if reference else self._module('pdf').current_pdf_card_id()
                if not current() or profile != self.profile() or active != cid:
                    return
                payload = json.dumps({'card_id': cid, 'controls': controls})
                view.page().runJavaScript('window._incWorkspacePending=' + payload + ';'
                    'window.incrementoPdfRestoreWorkspace?.(window._incWorkspacePending);')
            except RuntimeError:
                pass
        # Startup may still be loading the host page. Replay once after its load,
        # then let the viewer consume pending state when React is ready.
        def loaded(*_):
            try:
                view.loadFinished.disconnect(loaded)
            except RuntimeError:
                return
            apply()
        view.loadFinished.connect(loaded)
        apply()
