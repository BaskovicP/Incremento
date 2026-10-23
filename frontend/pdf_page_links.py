"""Current-view bridge for visible, bidirectional PDF page connections."""
from pathlib import Path
from weakref import WeakSet

from aqt import mw
from aqt.operations import QueryOp
from aqt.utils import tooltip

try:
    from ..backend.document_links import list_pdf_page_links
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.pdf_manager import get_pdf_daily_limit_status
    from ..backend.pdf_reference import resolve_pdf_reference
except ImportError:
    from backend.document_links import list_pdf_page_links
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.pdf_manager import get_pdf_daily_limit_status
    from backend.pdf_reference import resolve_pdf_reference

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_bridges = WeakSet()


def pdf_page_count(path):
    """Read local PDF metadata in the caller's worker, using Anki's bundled Qt."""
    from PyQt6.QtPdf import QPdfDocument
    document = QPdfDocument(None)
    try:
        document.load(path)
        count = document.pageCount()
        if not 1 <= count <= 1_000_000:
            raise ValueError('PDF pages unavailable')
        return count
    finally:
        document.close()


def refresh_page_links():
    """Refresh both open endpoints after a committed association change."""
    for bridge in list(_bridges):
        if bridge.current() and bridge.refresh is not None:
            bridge.refresh()


class PdfPageLinksBridge:
    def __init__(self, *, profile, card_id, filename, is_current, reply, open_pdf,
                 owner, refresh=None, source_path=None):
        self.profile, self.card_id, self.filename = profile, card_id, filename
        self.is_current, self.reply, self.open_pdf = is_current, reply, open_pdf
        self.owner, self.refresh, self.source_path = owner, refresh, source_path
        self.location, self.closed = None, False
        _bridges.add(self)

    def current(self):
        return not self.closed and self.profile == get_active_profile() and self.is_current()

    def close(self):
        self.closed = True
        self.location = None
        _bridges.discard(self)

    def handle(self, payload):
        if (not self.current() or not isinstance(payload, dict)
                or type(payload.get('cardId')) is not int or payload['cardId'] != self.card_id
                or any(type(payload.get(key)) is not int or not 1 <= payload[key] <= 2**53 - 1
                       for key in ('page', 'request', 'generation'))
                or payload['page'] > 1_000_000):
            return False
        operation = payload.get('operation')
        point = payload.get('page_y')
        if point is not None and (type(point) not in (int, float) or not 0 <= point <= 1):
            return False
        if operation not in ('list', 'jump', 'create', 'manage'):
            return False
        location = tuple(payload[key] for key in ('page', 'request', 'generation'))
        if operation == 'list':
            self.location = location
        elif self.location != location:
            return False
        if operation == 'jump' and (
                type(payload.get('id')) is not int or not 1 <= payload['id'] <= 2**63 - 1
                or payload.get('direction') not in ('outgoing', 'incoming')
                or payload.get('mode') not in ('jump', 'beside')):
            return False
        request = {key: payload[key] for key in ('cardId', 'page', 'request', 'generation')}
        def current():
            return self.current() and self.location == location
        def source_current():
            return (self.current() and self.location is not None
                    and self.location[0] == location[0] and self.location[2] == location[2])
        def work(col):
            if not current():
                return None
            source = resolve_pdf_reference(_ADDON_DIR, self.profile, col, self.card_id)
            if (source['filename'] != self.filename
                    or (self.source_path is not None and source['path'] != self.source_path)):
                raise ValueError('Source document changed')
            if operation in ('create', 'manage'):
                return True
            rows = list_pdf_page_links(_ADDON_DIR, self.profile, self.card_id, location[0])
            if operation == 'jump':
                link = next((row for row in rows if row['id'] == payload['id']
                             and row['direction'] == payload['direction']), None)
                if link is None:
                    raise ValueError('Connection unavailable')
                snapshot = resolve_pdf_reference(_ADDON_DIR, self.profile, col, link['target_card_id'])
                if link['target_page'] > pdf_page_count(snapshot['path']):
                    raise ValueError('Destination page unavailable')
                status = get_pdf_daily_limit_status(_ADDON_DIR, self.profile, link['target_card_id'],
                                                   count_current_page=False, persist_usage=False)
                maximum = status.get('allowed_max_page')
                if (status.get('enabled') and status.get('enforcement_mode') in ('soft_lock', 'hard_stop')
                        and not status.get('override_enabled') and maximum is not None
                        and link['target_page'] > maximum):
                    raise ValueError('Destination page is locked')
                return snapshot, link
            visible = []
            for row in rows:
                try:
                    snapshot = resolve_pdf_reference(_ADDON_DIR, self.profile, col, row['target_card_id'])
                    title, available = snapshot['title'], True
                except ValueError:
                    title, available = t('reader_reference_unavailable'), False
                visible.append({key: row[key] for key in ('id', 'direction', 'target_page')}
                               | {'title': title[:240], 'available': available})
            return visible
        def ready(result):
            if not current() or result is None:
                return
            if operation == 'list':
                self.reply({**request, 'links': result})
            elif operation == 'jump':
                snapshot, link = result
                if payload['mode'] == 'beside':
                    try:
                        from .pdf_reference_workspace import open_reference
                    except ImportError:
                        from pdf_reference_workspace import open_reference
                    open_reference(snapshot['card_id'], link['target_page'], scroll_ratio=link['target_scroll'],
                                   page_y=link.get('target_y'), beside=True, owner=self.owner, is_current=current)
                else:
                    self.open_pdf(snapshot, link)
            else:
                try:
                    from . import document_link_ui
                except ImportError:
                    import document_link_ui
                source = {'card_id': self.card_id, 'kind': 'pdf', 'page': location[0], 'filename': self.filename}
                if point is not None:
                    source['page_y'] = point
                if operation == 'create':
                    document_link_ui.link_pdf(source, owner=self.owner, is_current=source_current, show_after=False)
                else:
                    document_link_ui.show_links(source, owner=self.owner, is_current=source_current)
        def failed(error):
            if current():
                if operation == 'list':
                    self.reply({**request, 'links': [], 'error': True})
                else:
                    tooltip(t('reader_reference_unavailable'))
        QueryOp(parent=mw, op=work, success=ready).failure(failed).run_in_background()
        return True
