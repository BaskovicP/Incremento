"""Debounced, cancellable file-index reads with document identity guards."""
from aqt import mw
try:
    from .latest_query import LatestQuery
except ImportError:
    from latest_query import LatestQuery


class DocumentQuery:
    def __init__(self, parent, *, read, publish, current, timer=None, dispatch=None):
        self.read, self.publish = read, publish
        self._pending = None
        self._queries = LatestQuery(dispatch=dispatch or self._dispatch,
            accept=current, success=publish, failure=lambda request, error: publish(request, []))
        if timer is None:
            from aqt.qt import QTimer
            timer = QTimer(parent)
            timer.setSingleShot(True)
            timer.setInterval(180)
            timer.timeout.connect(self.start)
        self.timer = timer

    def submit(self, profile, card_id, query, **options):
        self._queries.invalidate()
        self._pending = {"profile": profile, "card_id": card_id, "query": query, **options}
        self.timer.start()

    def start(self):
        if self._pending is not None:
            request, self._pending = self._pending, None
            self._queries.submit(request)

    def _dispatch(self, ticket, success, failure, _progress):
        request = ticket.payload
        def work():
            return self.read(request["profile"], request["card_id"], request["query"], ticket.cancel)
        def finished(future):
            try:
                result = future.result()
            except Exception as error:
                failure(error)
            else:
                success(result)
        mw.taskman.run_in_background(work, finished, uses_collection=False)

    def close(self, *_args):
        self.timer.stop()
        self._pending = None
        self._queries.close()
