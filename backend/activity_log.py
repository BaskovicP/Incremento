"""Bounded in-memory state for user-visible Incremento background activity."""

from __future__ import annotations

import math
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass


MAX_ACTIVITIES = 100
_FINAL_STATUSES = {"succeeded", "failed", "cancelled"}


@dataclass
class _Activity:
    activity_id: str
    title: str
    category: str
    status: str
    progress: float | None
    detail: str
    created_at: float
    updated_at: float
    cancel_callback: Callable[[], object] | None = None
    retry_callback: Callable[[], object] | None = None


_lock = threading.RLock()
_activities: "OrderedDict[str, _Activity]" = OrderedDict()


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _timestamp(value: float | None) -> float:
    try:
        result = float(time.time() if value is None else value)
    except Exception:
        result = time.time()
    return result if math.isfinite(result) and result >= 0 else time.time()


def _progress(value) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except Exception:
        return None
    if not math.isfinite(result):
        return None
    return max(0.0, min(1.0, result))


def _prune_locked() -> None:
    while len(_activities) > MAX_ACTIVITIES:
        _activities.popitem(last=False)


def start_activity(
    title: str,
    *,
    category: str = "General",
    detail: str = "",
    progress=None,
    cancel: Callable[[], object] | None = None,
    retry: Callable[[], object] | None = None,
    now: float | None = None,
) -> str:
    timestamp = _timestamp(now)
    activity_id = uuid.uuid4().hex
    activity = _Activity(
        activity_id=activity_id,
        title=_text(title, 240) or "Incremento task",
        category=_text(category, 80) or "General",
        status="running",
        progress=_progress(progress),
        detail=_text(detail, 2000),
        created_at=timestamp,
        updated_at=timestamp,
        cancel_callback=cancel if callable(cancel) else None,
        retry_callback=retry if callable(retry) else None,
    )
    with _lock:
        _activities[activity_id] = activity
        _prune_locked()
    return activity_id


def update_activity(
    activity_id: str,
    *,
    progress=None,
    detail: str | None = None,
    now: float | None = None,
) -> bool:
    with _lock:
        activity = _activities.get(str(activity_id or ""))
        if activity is None or activity.status in _FINAL_STATUSES:
            return False
        if progress is not None:
            activity.progress = _progress(progress)
        if detail is not None:
            activity.detail = _text(detail, 2000)
        activity.updated_at = _timestamp(now)
        return True


def finish_activity(
    activity_id: str,
    *,
    detail: str = "",
    now: float | None = None,
) -> bool:
    with _lock:
        activity = _activities.get(str(activity_id or ""))
        if activity is None or activity.status in _FINAL_STATUSES:
            return False
        activity.status = "succeeded"
        activity.progress = 1.0
        if detail:
            activity.detail = _text(detail, 2000)
        activity.updated_at = _timestamp(now)
        activity.cancel_callback = None
        return True


def fail_activity(
    activity_id: str,
    error: object,
    *,
    retry: Callable[[], object] | None = None,
    now: float | None = None,
) -> bool:
    with _lock:
        activity = _activities.get(str(activity_id or ""))
        if activity is None or activity.status in _FINAL_STATUSES:
            return False
        activity.status = "failed"
        activity.detail = _text(error, 2000) or "The operation failed."
        activity.updated_at = _timestamp(now)
        if callable(retry):
            activity.retry_callback = retry
        return True


def cancel_activity(activity_id: str, *, now: float | None = None) -> bool:
    with _lock:
        activity = _activities.get(str(activity_id or ""))
        if (
            activity is None
            or activity.status != "running"
            or not callable(activity.cancel_callback)
        ):
            return False
        callback = activity.cancel_callback
        activity.status = "cancelled"
        activity.detail = "Cancellation requested."
        activity.updated_at = _timestamp(now)
    try:
        callback()
    except Exception as exc:
        with _lock:
            activity.status = "failed"
            activity.detail = _text(exc, 2000) or "Could not cancel the operation."
        return False
    return True


def retry_activity(activity_id: str, *, now: float | None = None) -> bool:
    with _lock:
        activity = _activities.get(str(activity_id or ""))
        if (
            activity is None
            or activity.status not in {"failed", "cancelled"}
            or not callable(activity.retry_callback)
        ):
            return False
        callback = activity.retry_callback
        activity.status = "running"
        activity.progress = None
        activity.detail = "Retry started."
        activity.updated_at = _timestamp(now)
    try:
        callback()
    except Exception as exc:
        fail_activity(activity_id, exc, now=now)
        return False
    return True


def _snapshot(activity: _Activity) -> dict:
    return {
        "activity_id": activity.activity_id,
        "title": activity.title,
        "category": activity.category,
        "status": activity.status,
        "progress": activity.progress,
        "detail": activity.detail,
        "created_at": activity.created_at,
        "updated_at": activity.updated_at,
        "can_cancel": activity.status == "running" and callable(activity.cancel_callback),
        "can_retry": activity.status in {"failed", "cancelled"}
        and callable(activity.retry_callback),
    }


def snapshot_activities(*, include_finished: bool = True) -> list[dict]:
    with _lock:
        activities = reversed(list(_activities.values()))
        return [
            _snapshot(activity)
            for activity in activities
            if include_finished or activity.status not in _FINAL_STATUSES
        ]


def dismiss_activity(activity_id: str) -> bool:
    with _lock:
        activity = _activities.get(str(activity_id or ""))
        if activity is None or activity.status not in _FINAL_STATUSES:
            return False
        del _activities[activity.activity_id]
        return True


def clear_finished_activities() -> int:
    with _lock:
        finished_ids = [
            activity_id
            for activity_id, activity in _activities.items()
            if activity.status in _FINAL_STATUSES
        ]
        for activity_id in finished_ids:
            del _activities[activity_id]
        return len(finished_ids)


def reset_activity_log_for_tests() -> None:
    with _lock:
        _activities.clear()
