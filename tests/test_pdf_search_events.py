"""Deletion cache cleanup is deferred, coalesced and tied to its collection."""

from types import SimpleNamespace


def test_delete_events_wait_for_operation_and_ignore_closed_profile(monkeypatch):
    col = object()
    main, jobs, checks = [], [], []

    class QueryOp:
        def __init__(self, *, parent, op, success):
            self.op, self.success = op, success

        def failure(self, callback):
            self.failed = callback
            return self

        def run_in_background(self):
            jobs.append(self)

    import sys

    with monkeypatch.context() as imports:
        imports.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=QueryOp))
        from frontend import pdf_search_lifecycle as events
    monkeypatch.setattr(events, "QueryOp", QueryOp)
    monkeypatch.setattr(events, "pdf_cards_for_notes", lambda collection, ids: {11, 12})
    monkeypatch.setattr(
        events,
        "reconcile_pdf_search_indexes",
        lambda addon, profile, collection, **kw: checks.append((profile, collection, kw["card_ids"])),
    )
    retired = []
    monkeypatch.setattr(events, "invalidate_pdf_index_jobs", lambda *args: retired.append(args))
    current = [True]
    lifecycle = events.PdfSearchLifecycle(
        "/temporary/addon",
        "A",
        col,
        parent=None,
        taskman=SimpleNamespace(run_on_main=main.append),
        valid=lambda: current[0],
    )
    assert jobs == checks == [], "Profile open must not scan indexes"
    lifecycle.notes_will_be_deleted(object(), [1])
    assert main == []
    lifecycle.notes_will_be_deleted(col, [1])
    assert jobs == checks == [], "The before-delete hook cannot purge anything"
    main.pop()()
    assert len(jobs) == 1
    lifecycle.collection_changed(SimpleNamespace(note=True))
    lifecycle.collection_changed(SimpleNamespace(card=True))
    assert len(jobs) == 1, "Events must coalesce behind the active operation"
    # Cancelled queued operation cannot touch the collection or cache.
    from concurrent.futures import CancelledError

    try:
        jobs[0].op(col)
        raise AssertionError("Cancelled cleanup ran")
    except CancelledError:
        jobs[0].failed(CancelledError())
    assert len(jobs) == 2 and checks == []
    jobs[1].success(jobs[1].op(col))
    assert checks == [("A", col, (11, 12))]
    lifecycle.collection_changed(SimpleNamespace(card=True))  # Ordinary review
    assert len(jobs) == 2
    lifecycle.collection_changed(SimpleNamespace(note=True))  # Undo/Redo
    pending = jobs[-1]
    lifecycle.close()
    assert retired == [("/temporary/addon", "A")]
    try:
        pending.op(col)
        raise AssertionError("Closed profile cleanup ran")
    except CancelledError:
        pending.failed(CancelledError())
    current[0] = False
    lifecycle.notes_will_be_deleted(col, [1])
    lifecycle.collection_changed(SimpleNamespace(note=True))
    assert len(jobs) == 3 and len(checks) == 1
