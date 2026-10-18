"""Capture inspection uses the serialized background collection path."""

import sys
from types import SimpleNamespace

import browser_bridge as bridge
import browser_capture_source as ui
import paths
import pytest


@pytest.fixture
def dispatch_env(monkeypatch):
    operations = []
    col = object()
    mw = SimpleNamespace(col=col)
    profile = ["ProfileA"]
    monkeypatch.setattr(paths, "get_active_profile", lambda: profile[0])
    monkeypatch.setitem(sys.modules, "aqt", SimpleNamespace(mw=mw))

    class QueryOp:
        def __init__(self, *, parent, op, success):
            self.op, self.success = op, success

        def failure(self, callback):
            self.fail = callback
            return self

        def run_in_background(self):
            operations.append(self)

    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=QueryOp))
    return mw, profile, operations


def test_capture_waits_for_background_inspection_before_creating(dispatch_env, monkeypatch):
    mw, _, operations = dispatch_env
    inspected, created, replies, failures = [], [], [], []
    monkeypatch.setattr(bridge, "_find_browser_capture_duplicate", lambda col, profile, raw:
        inspected.append((col, profile, raw)) or None)
    monkeypatch.setattr(bridge, "_create_browser_capture_note_on_main", lambda raw, **kwargs:
        created.append((raw, kwargs)) or {"ok": True, "preview": True})
    raw = {"profile_token": ""}
    ui.dispatch_browser_capture(raw, replies.append, failures.append)
    assert created == [] and inspected == [] and replies == []
    operation = operations[0]
    result = operation.op(mw.col)
    assert inspected == [(mw.col, "ProfileA", raw)]
    operation.success(result)
    assert len(created) == 1
    assert created[0][1]["legacy_checked"] is True
    assert replies == [{"ok": True, "preview": True}]
    assert failures == []


def test_profile_switch_discards_inspection_before_any_creation(dispatch_env, monkeypatch):
    mw, profile, operations = dispatch_env
    created, replies, failures = [], [], []
    monkeypatch.setattr(bridge, "_find_browser_capture_duplicate", lambda *args: None)
    monkeypatch.setattr(bridge, "_create_browser_capture_note_on_main", lambda *args, **kwargs: created.append(1))
    ui.dispatch_browser_capture({"profile_token": ""}, replies.append, failures.append)
    result = operations[0].op(mw.col)
    profile[0] = "ProfileB"
    operations[0].success(result)
    assert created == [] and replies == []
    assert len(failures) == 1 and "profile changed" in str(failures[0])


def test_timed_out_capture_discards_late_inspection_without_creating(dispatch_env, monkeypatch):
    mw, _, operations = dispatch_env
    created, replies, failures = [], [], []
    cancelled = [False]
    monkeypatch.setattr(bridge, "_find_browser_capture_duplicate", lambda *args: None)
    monkeypatch.setattr(bridge, "_create_browser_capture_note_on_main", lambda *args, **kwargs: created.append(1))
    ui.dispatch_browser_capture({"profile_token": ""}, replies.append, failures.append,
                                is_cancelled=lambda: cancelled[0])
    result = operations[0].op(mw.col)
    cancelled[0] = True
    operations[0].success(result)
    assert created == [] and replies == [] and len(failures) == 1


def test_bridge_timeout_prevents_a_queued_request_from_starting(dispatch_env, monkeypatch):
    mw, _, _ = dispatch_env
    launches, dispatched = [], []
    mw.taskman = SimpleNamespace(run_on_main=launches.append)
    monkeypatch.setattr(bridge, "_browser_capture_dispatch", lambda *args, **kwargs: dispatched.append(1))
    with pytest.raises(TimeoutError):
        bridge._run_browser_capture_and_wait({}, timeout_sec=0)
    launches[0]()
    assert dispatched == []
