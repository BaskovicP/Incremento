"""Bounded reference windows, instance-owned bridges, and pin-to-reader layout."""
import json
from dataclasses import replace
from pathlib import Path

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QApplication, QDockWidget, QSignalBlocker, Qt, QUrl
from aqt.utils import tooltip
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    from ..backend.i18n import get_custom_reader_payload, get_locale, t
    from ..backend.paths import get_active_profile
    from ..backend.pdf_reader_state import PdfReaderState, maximum_reference_page as _maximum_reference_page
    from ..backend.pdf_reference import resolve_pdf_reference
    from ..backend.pdf_manager import get_pdf_daily_limit_status
    from .reader_links import make_reader_anchor_html, set_reader_anchor_clipboard
except ImportError:
    from backend.i18n import get_custom_reader_payload, get_locale, t
    from backend.paths import get_active_profile
    from backend.pdf_reader_state import PdfReaderState, maximum_reference_page as _maximum_reference_page
    from backend.pdf_reference import resolve_pdf_reference
    from backend.pdf_manager import get_pdf_daily_limit_status
    from frontend.reader_links import make_reader_anchor_html, set_reader_anchor_clipboard

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_windows = []
_request = 0
_slot_requests = {False: 0, True: 0}


class _ReferencePage(QWebEnginePage):
    def __init__(self, profile, parent, interceptor, state, handler):
        super().__init__(profile, parent)
        self.interceptor, self.state, self.handler = interceptor, state, handler

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if is_main_frame and not self.interceptor.main_frame_url_is_allowed(url):
            return False
        return super().acceptNavigationRequest(url, navigation_type, is_main_frame)

    def javaScriptConsoleMessage(self, level, message, line, source):
        prefix = "__incremento_reference__:" + self.state.nonce + ":"
        if not isinstance(message, str) or len(message) > 24_000 or not message.startswith(prefix):
            return
        try:
            payload = json.loads(message[len(prefix):])
            if self.state.receive(payload, profile=get_active_profile(), nonce=self.state.nonce):
                self.handler(payload.get("action"), payload)
        except (ValueError, TypeError, RuntimeError):
            return


def create_reference_view(parent, snapshot, state, handler, *, page_y=None, excerpt='', choosing=False):
    """Share the restricted PDF engine between a reader and a destination dialog."""
    from . import pdf_dock
    engine_profile = QWebEngineProfile(parent)
    interceptor = pdf_dock._PdfRequestInterceptor(engine_profile)
    interceptor.set_pdf_path(snapshot['path'])
    engine_profile.setUrlRequestInterceptor(interceptor)
    page = _ReferencePage(engine_profile, parent, interceptor, state, handler)
    settings = page.settings()
    settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
    for name in ('LocalContentCanAccessRemoteUrls', 'DnsPrefetchEnabled', 'JavascriptCanAccessClipboard',
                 'JavascriptCanOpenWindows', 'LocalStorageEnabled', 'PluginsEnabled', 'ScreenCaptureEnabled'):
        attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
        if attribute is not None:
            settings.setAttribute(attribute, False)
    view = QWebEngineView(parent)
    view.setPage(page)
    config = {**snapshot, 'url': QUrl.fromLocalFile(snapshot['path']).toString(),
              'page': state.page, 'scroll_ratio': state.scroll_ratio, 'max_page': state.max_page,
              'worker': pdf_dock._WORKER_URL, 'locale': get_locale(), 'custom_language': get_custom_reader_payload(),
              'excerpt': excerpt, 'page_y': page_y, 'choose_destination': choosing}
    config.pop('path', None)
    nonce = state.nonce
    def loaded(ok):
        if not ok or not state.is_current(get_active_profile(), nonce):
            return
        prefix = '__incremento_reference__:' + nonce + ':'
        page.runJavaScript(
            'window.pycmd = message => console.info(' + json.dumps(prefix) + ' + message);'
            'window._incReferencePending=' + json.dumps(config) + ';'
            'if(window.incrementoReferenceStart){window.incrementoReferenceStart(window._incReferencePending);'
            'window._incReferencePending=null;}')
    view.loadFinished.connect(loaded)
    url = QUrl(pdf_dock._DOCK_HTML)
    url.setQuery('reference=1')
    view.load(url)
    return view, page, engine_profile, interceptor


class ReferenceWindow(QDockWidget):
    def __init__(self, snapshot, *, profile, page, scroll_ratio, max_page, beside, owner, excerpt='', page_y=None):
        super().__init__(snapshot["title"], mw)
        self.state = PdfReaderState(profile, snapshot["card_id"], snapshot["filename"],
                                    page=min(max(1, page), max_page), scroll_ratio=scroll_ratio,
                                    max_page=max_page)
        self.owner = owner
        self._source_path = snapshot['path']
        self.setObjectName("incremento_pdf_reference_" + self.state.nonce)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(280)
        self.view, self.page, self._engine_profile, self._interceptor = create_reference_view(
            self, snapshot, self.state, self.command, excerpt=excerpt, page_y=page_y)
        self.setWidget(self.view)
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        self.setFloating(not beside)
        if beside:
            self.pin()
        else:
            self.resize(720, 650)
        self.topLevelChanged.connect(lambda floating: self._claim_slot())

    def _claim_slot(self):
        if self.state.closed:
            return
        beside = not self.isFloating()
        _slot_requests[beside] += 1
        for window in list(_windows):
            if window is not self and window.isFloating() == self.isFloating():
                window.close()

    def pin(self):
        if self.state.closed:
            return
        self.setFloating(False)
        self._claim_slot()
        owner = self.owner
        try:
            if owner is not None and not owner.isVisible():
                owner = None
        except RuntimeError:
            owner = None
        if owner is None and hasattr(mw, 'findChildren'):
            owner = next((dock for dock in mw.findChildren(QDockWidget)
                          if dock is not self and dock.isVisible() and dock.objectName() in {
                              'incremento_pdf_dock', 'incremento_epub_dock', 'incremento_web_dock'}), None)
        if owner is not None and owner is not self:
            try:
                if owner.isFloating():
                    # Qt emits a hide/show pair while reparenting a floating
                    # reader. Its document remains open; don't stop its timer.
                    with QSignalBlocker(owner):
                        owner.setFloating(False)
                owner.show()
                mw.splitDockWidget(owner, self, Qt.Orientation.Horizontal)
                self.owner = owner
            except RuntimeError:
                pass
        self.show()

    def trigger_extract(self, index):
        self.page.runJavaScript("window.incrementoHandleExtractShortcut?.(" + json.dumps(index) + ");")

    def command(self, action, payload=None):
        if self.state.closed or self.state.profile != get_active_profile():
            return
        if action == 'page_links':
            try:
                from .pdf_page_links import PdfPageLinksBridge
            except ImportError:
                from pdf_page_links import PdfPageLinksBridge
            bridge = getattr(self, '_page_links', None)
            if bridge is None or not bridge.current():
                nonce = self.state.nonce
                def current():
                    return self.state.is_current(get_active_profile(), nonce)
                def jump(snapshot, link):
                    open_reference(snapshot['card_id'], link['target_page'], scroll_ratio=link['target_scroll'],
                                   page_y=link.get('target_y'), beside=not self.isFloating(),
                                   owner=self.owner, is_current=current)
                bridge = PdfPageLinksBridge(profile=self.state.profile, card_id=self.state.card_id,
                    filename=self.state.filename, source_path=getattr(self, '_source_path', None),
                    owner=self, is_current=current, open_pdf=jump,
                    reply=lambda data: self.page.runJavaScript('window.incrementoReceivePdfPageLinks?.(' + json.dumps(data) + ');'),
                    refresh=lambda: self.page.runJavaScript('window.incrementoRefreshPdfPageLinks?.();'))
                self._page_links = bridge
            bridge.handle(payload)
        elif action == 'position':
            bridge = getattr(self, '_page_links', None)
            if bridge is not None and bridge.location is not None and bridge.location[0] != self.state.page:
                bridge.close()
                self._page_links = None
        elif action == "pin":
            self.pin()
        elif action == "close":
            self.close()
        elif action in ('copy', 'extract', 'open'):
            location = replace(self.state)
            payload = dict(payload or {})
            source_path = getattr(self, '_source_path', None)
            def current():
                return self.state.is_current(get_active_profile(), location.nonce)
            def validate(col):
                if not current():
                    return None
                snapshot = resolve_pdf_reference(_ADDON_DIR, location.profile, col, location.card_id)
                if (snapshot['filename'] != location.filename
                        or (source_path is not None and snapshot['path'] != source_path)):
                    raise ValueError('Reference document changed')
                status = get_pdf_daily_limit_status(_ADDON_DIR, location.profile, location.card_id,
                                                   count_current_page=False, persist_usage=False)
                if location.page > _maximum_reference_page(status):
                    raise ValueError('Reference page is locked')
                return snapshot
            def ready(snapshot):
                if current() and snapshot is not None:
                    self._apply_action(action, location, payload, snapshot)
            def failed(error):
                if current():
                    tooltip(t('reader_reference_unavailable'))
            QueryOp(parent=mw, op=validate, success=ready).failure(failed).run_in_background()

    def _apply_action(self, action, location, payload, snapshot):
        data = {'card_id': location.card_id, 'filename': location.filename,
                'page': location.page, 'scroll_ratio': location.scroll_ratio}
        command = 'incremento_open_pdf_ref:' + json.dumps(data)
        label = t('reader_pdf_copied_label', title=snapshot['title'], page=location.page)
        citation = make_reader_anchor_html(command, label)
        if action == "open":
            from . import pdf_dock
            pdf_dock.show_pdf_in_dock(location.card_id, location.filename, location.page,
                                     location.zoom, via_link=True, offer_due_review_prompt=False,
                                     scroll_ratio_override=location.scroll_ratio)
            self.close()
        elif action == "copy":
            set_reader_anchor_clipboard(citation, label)
        elif action == "extract":
            from . import add_card_dock
            from ..backend.content_safety import external_plain_text_to_anki_html
            index, text = payload.get("index"), payload.get("text")
            if type(index) is not int or not 0 <= index <= 3 or not isinstance(text, str) or not text.strip():
                return
            add_card_dock.fill_dock_field(index, external_plain_text_to_anki_html(text[:6000]),
                citation_html=citation, source_link_kind="pdf", source_card_id=location.card_id)

    def closeEvent(self, event):
        bridge = getattr(self, '_page_links', None)
        if bridge is not None:
            bridge.close()
        self.state.close()
        if self in _windows:
            _windows.remove(self)
        self.view.stop()
        self.page.deleteLater()
        super().closeEvent(event)


def reset_for_profile_switch():
    global _request
    _request += 1
    for window in list(_windows):
        window.close()


def focused_reference():
    focus = QApplication.focusWidget()
    if focus is None:
        return None
    for window in _windows:
        if not window.state.closed and (focus is window.view or window.view.isAncestorOf(focus)):
            return window
    return None


def open_reference(card_id, page=1, *, scroll_ratio=0, beside=False, owner=None, is_current=lambda: True,
                   excerpt='', page_y=None):
    """Resolve under serialized read-only collection access, then create Qt UI."""
    beside = bool(beside)
    _slot_requests[beside] += 1
    request, generation, profile = _slot_requests[beside], _request, get_active_profile()
    def request_current():
        return (profile == get_active_profile() and generation == _request
                and request == _slot_requests[beside])
    if type(page) is not int or page < 1:
        page = 1
    if type(scroll_ratio) not in (float, int) or not 0 <= scroll_ratio <= 1:
        scroll_ratio = 0
    if page_y is not None and (type(page_y) not in (float, int) or not 0 <= page_y <= 1):
        page_y = None
    def load(col):
        if not request_current():
            return None
        snapshot = resolve_pdf_reference(_ADDON_DIR, profile, col, card_id)
        status = get_pdf_daily_limit_status(_ADDON_DIR, profile, card_id,
                                           count_current_page=False, persist_usage=False)
        return snapshot, _maximum_reference_page(status)
    def ready(result):
        if not request_current() or not is_current():
            return
        snapshot, maximum = result
        # One floating preview plus one pinned reference keeps WebEngine memory bounded.
        for old in list(_windows):
            if old.isFloating() == (not beside):
                old.close()
        window = ReferenceWindow(snapshot, profile=profile, page=page, scroll_ratio=scroll_ratio,
                                 max_page=maximum, beside=beside, owner=owner,
                                 excerpt=str(excerpt or '')[:320], page_y=page_y)
        _windows.append(window)
        window.show()
    def failed(error):
        if request_current() and is_current():
            tooltip(t("reader_reference_unavailable"))
    QueryOp(parent=mw, op=load, success=ready).failure(failed).run_in_background()
