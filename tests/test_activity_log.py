import activity_log


def setup_function():
    activity_log.reset_activity_log_for_tests()


def test_activity_lifecycle_exposes_bounded_progress_and_safe_snapshot():
    activity_id = activity_log.start_activity(
        "Index PDF text",
        category="Search",
        detail="Preparing",
        now=10,
    )
    activity_log.update_activity(
        activity_id,
        progress=1.8,
        detail="Page 12 of 12",
        now=11,
    )
    activity_log.finish_activity(activity_id, detail="12 PDFs indexed", now=12)

    rows = activity_log.snapshot_activities()
    assert rows == [
        {
            "activity_id": activity_id,
            "title": "Index PDF text",
            "category": "Search",
            "status": "succeeded",
            "progress": 1.0,
            "detail": "12 PDFs indexed",
            "created_at": 10.0,
            "updated_at": 12.0,
            "can_cancel": False,
            "can_retry": False,
        }
    ]


def test_cancel_and_retry_invoke_only_supported_callbacks_once():
    calls = []
    running_id = activity_log.start_activity(
        "Download video",
        cancel=lambda: calls.append("cancel"),
        now=10,
    )
    failed_id = activity_log.start_activity(
        "Build index",
        retry=lambda: calls.append("retry"),
        now=11,
    )
    activity_log.fail_activity(failed_id, "network failed", now=12)

    assert activity_log.cancel_activity(running_id, now=13) is True
    assert activity_log.cancel_activity(running_id, now=14) is False
    assert activity_log.retry_activity(failed_id, now=15) is True
    assert activity_log.retry_activity(failed_id, now=16) is False
    assert calls == ["cancel", "retry"]
    by_id = {
        row["activity_id"]: row for row in activity_log.snapshot_activities()
    }
    assert by_id[running_id]["status"] == "cancelled"
    assert by_id[failed_id]["status"] == "running"


def test_log_is_bounded_and_finished_rows_can_be_dismissed():
    for index in range(130):
        activity_id = activity_log.start_activity(f"Task {index}", now=index)
        activity_log.finish_activity(activity_id, now=index + 0.5)

    rows = activity_log.snapshot_activities()
    assert len(rows) == activity_log.MAX_ACTIVITIES
    assert rows[0]["title"] == "Task 129"
    assert activity_log.dismiss_activity(rows[0]["activity_id"]) is True
    assert len(activity_log.snapshot_activities()) == activity_log.MAX_ACTIVITIES - 1


def test_user_facing_text_is_clipped_and_invalid_updates_fail_closed():
    activity_id = activity_log.start_activity("x" * 600, detail="y" * 5000)
    row = activity_log.snapshot_activities()[0]
    assert len(row["title"]) == 240
    assert len(row["detail"]) == 2000
    assert activity_log.update_activity("missing", progress=0.5) is False
    assert activity_log.finish_activity("missing") is False


def test_retry_restores_cancel_capability_for_failed_and_cancelled_activity():
    calls = []

    failed_id = activity_log.start_activity(
        "Index documents",
        cancel=lambda: calls.append("cancel failed retry"),
        retry=lambda: calls.append("retry failed"),
    )
    activity_log.fail_activity(failed_id, "index failed")
    assert activity_log.retry_activity(failed_id) is True

    cancelled_id = activity_log.start_activity(
        "Download media",
        cancel=lambda: calls.append("cancel initial"),
        retry=lambda: calls.append("retry cancelled"),
    )
    assert activity_log.cancel_activity(cancelled_id) is True
    assert activity_log.retry_activity(cancelled_id) is True

    rows = {
        row["activity_id"]: row for row in activity_log.snapshot_activities()
    }
    assert rows[failed_id]["can_cancel"] is True
    assert rows[cancelled_id]["can_cancel"] is True
    assert activity_log.cancel_activity(failed_id) is True
    assert activity_log.cancel_activity(cancelled_id) is True
    assert calls == [
        "retry failed",
        "cancel initial",
        "retry cancelled",
        "cancel failed retry",
        "cancel initial",
    ]
