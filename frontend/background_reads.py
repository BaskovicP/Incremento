"""Profile-scoped read requests shared by maintenance and branch dialogs."""
from concurrent.futures import CancelledError
from aqt import mw

try:
    from .latest_query import LatestQuery
except ImportError:
    from latest_query import LatestQuery

try:
    from ..backend.paths import get_active_profile
except ImportError:
    from paths import get_active_profile


class BackgroundReads:
    def __init__(self, parent, profile, *, current_profile=None, dispatch=None):
        self.parent, self.profile, self.collection = parent, profile, mw.col
        self.current_profile = current_profile or get_active_profile
        self._queries = LatestQuery(
            dispatch=dispatch or self._dispatch,
            accept=lambda _: self.profile == self.current_profile() and self.collection is mw.col,
            success=lambda request, value: request["success"](value),
            failure=lambda request, error: request["failure"](error),
        )
        finished = getattr(parent, "finished", None)
        if finished is not None:
            finished.connect(self.close)

    def submit(self, work, success, failure=None):
        self._queries.submit({"work": work, "success": success, "failure": failure or (lambda error: None)})

    def _dispatch(self, ticket, success, failure, _progress):
        from aqt.operations import QueryOp
        def read(col):
            if ticket.cancel.is_set() or col is not self.collection:
                raise CancelledError()
            return ticket.payload["work"](col, ticket.cancel)
        QueryOp(parent=self.parent, op=read, success=success).failure(failure).run_in_background()

    def close(self, *_args):
        self._queries.close()
