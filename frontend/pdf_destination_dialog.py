"""A read-only PDF preview for choosing a precise link destination."""
import json
from dataclasses import replace
from pathlib import Path

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QDialog, QVBoxLayout, Qt
from aqt.utils import tooltip

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.pdf_reader_state import PdfReaderState, maximum_reference_page
    from ..backend.pdf_reference import resolve_pdf_reference
    from ..backend.pdf_manager import get_pdf_daily_limit_status
    from .pdf_page_links import pdf_page_count
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.pdf_reader_state import PdfReaderState, maximum_reference_page
    from backend.pdf_reference import resolve_pdf_reference
    from backend.pdf_manager import get_pdf_daily_limit_status
    from pdf_page_links import pdf_page_count

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)


class PdfDestinationDialog(QDialog):
    def __init__(self, snapshot, *, profile, max_page, is_current):
        super().__init__(mw)
        from .pdf_reference_workspace import create_reference_view
        self.setWindowTitle(t('reader_destination_title'))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(900, 760)
        self._snapshot, self._source_current = dict(snapshot), is_current
        self._closed, self._saving, self.selected_location = False, False, None
        self.state = PdfReaderState(profile, snapshot['card_id'], snapshot['filename'], max_page=max_page)
        self._nonce = self.state.nonce
        self.view, self.page, self._engine_profile, self._interceptor = create_reference_view(
            self, snapshot, self.state, self.command, choosing=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.finished.connect(lambda *_: self._dispose())

    def current(self):
        return (not self._closed and self.state.is_current(get_active_profile(), self._nonce)
                and self._source_current())

    def _set_pending(self, value):
        self._saving = value
        self.page.runJavaScript('window.incrementoReferencePickPending?.(' + json.dumps(value) + ');')

    def command(self, action, payload=None):
        if not self.current():
            return
        if action == 'close':
            self.reject()
            return
        if action != 'pick' or self._saving or not isinstance(payload, dict):
            return
        point = payload.get('page_y')
        if (type(point) not in (int, float) or not 0 <= point <= 1
                or type(payload.get('page')) is not int or payload['page'] != self.state.page):
            return
        location = replace(self.state)
        self._set_pending(True)
        def validate(col):
            if not self.current():
                return None
            snapshot = resolve_pdf_reference(_ADDON_DIR, location.profile, col, location.card_id)
            if snapshot['filename'] != location.filename or snapshot['path'] != self._snapshot['path']:
                raise ValueError('Destination document changed')
            if location.page > pdf_page_count(snapshot['path']):
                raise ValueError('Destination page unavailable')
            status = get_pdf_daily_limit_status(_ADDON_DIR, location.profile, location.card_id,
                                               count_current_page=False, persist_usage=False)
            if location.page > maximum_reference_page(status):
                raise ValueError('Destination page is locked')
            return {**snapshot, 'page': location.page, 'scroll_ratio': location.scroll_ratio, 'page_y': point}
        def ready(selected):
            if self.current() and selected is not None:
                self.selected_location = selected
                self.accept()
        def failed(error):
            if self.current():
                self._set_pending(False)
                tooltip(t('reader_reference_unavailable'))
        QueryOp(parent=mw, op=validate, success=ready).failure(failed).run_in_background()

    def _dispose(self):
        if self._closed:
            return
        self._closed = True
        self.state.close()
        self.view.stop()
        self.page.deleteLater()
