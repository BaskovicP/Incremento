"""Latest-request scheduling must never publish obsolete UI data."""

from frontend.latest_query import LatestQuery


def test_pending_queries_coalesce_and_stale_success_and_progress_are_discarded():
    dispatched, shown, failures = [], [], []
    runner = LatestQuery(
        dispatch=lambda ticket, success, failure, progress: dispatched.append(
            (ticket, success, failure, progress)
        ),
        success=lambda payload, value: shown.append((payload, value)),
        failure=lambda payload, error: failures.append(error),
        progress=lambda payload, value: shown.append((payload, value)),
    )
    runner.submit("first")
    first, done, failed, progress = dispatched[0]
    runner.submit("second")
    runner.submit("latest")
    assert first.cancel.is_set()
    assert len(dispatched) == 1
    progress("obsolete partial")
    done("obsolete final")
    assert shown == []
    assert len(dispatched) == 2
    assert dispatched[1][0].payload == "latest"
    dispatched[1][3]("partial")
    dispatched[1][1]("final")
    assert shown == [("latest", "partial"), ("latest", "final")]
    assert failures == []


def test_invalidation_close_and_changed_context_reject_callbacks():
    dispatched, shown = [], []
    context = ["profile-a"]
    runner = LatestQuery(
        dispatch=lambda *callbacks: dispatched.append(callbacks),
        accept=lambda payload: payload == context[0],
        success=lambda *result: shown.append(result),
        failure=lambda *result: shown.append(result),
    )
    runner.submit("profile-a")
    context[0] = "profile-b"
    dispatched[0][1]("old profile")
    runner.submit("profile-b")
    runner.invalidate()  # Text changed before the next debounced dispatch.
    dispatched[1][2](RuntimeError("obsolete failure"))
    runner.submit("profile-b")
    runner.submit("queued")
    runner.close()
    dispatched[2][1]("closed")
    runner.submit("after close")
    assert len(dispatched) == 3
    assert shown == []


def test_current_failure_is_reported_and_a_later_request_can_run():
    dispatched, failures = [], []
    runner = LatestQuery(
        dispatch=lambda *callbacks: dispatched.append(callbacks),
        success=lambda *result: None,
        failure=lambda payload, error: failures.append((payload, str(error))),
    )
    runner.submit("bad")
    dispatched[0][2](ValueError("unavailable"))
    assert failures == [("bad", "unavailable")]
    runner.submit("retry")
    assert len(dispatched) == 2
