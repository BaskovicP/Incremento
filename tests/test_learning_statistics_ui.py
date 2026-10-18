"""Background delivery and deck-browser refresh lifecycle for daily grades."""

import sys
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from frontend import learning_stats


def test_learning_trend_uses_weighted_recall_and_leaves_unanswered_days_as_gaps():
    history = [{
        "date": (date(2026, 9, 30) + timedelta(days=index)).isoformat(),
        "stages": {"review": {"again": 1, "good": 1}} if index < 7 else {},
    } for index in range(14)]
    history[7]["stages"] = {"learning": {"again": 1, "good": 9}}
    history[-1]["stages"] = {"review": {"again": 1, "hard": 1}}

    display = learning_stats.learning_history_display(history, 7)

    assert display["metrics"] == [
        ("Answer attempts", "12"), ("Again / Fail", "2"),
        ("Recalled", "10"), ("Recall rate", "83.3%"),
    ]
    assert display["series"] == [
        ("Recalled", [9, 0, 0, 0, 0, 0, 1]),
        ("Again / Fail", [1, 0, 0, 0, 0, 0, 1]),
    ]
    assert display["rates"] == [90, None, None, None, None, None, 50]
    assert "33.3" in display["comparison"] and "50%" in display["comparison"]
    assert "83.3%" in display["comparison"]
    assert len(display["labels"]) == len(display["daily_details"]) == 7


def test_learning_trend_never_invents_improvement_without_answers_to_compare():
    assert learning_stats.learning_history_display(None, 30) is None
    display = learning_stats.learning_history_display([{"date": "2026-10-13", "stages": {}}], 30)
    assert dict(display["metrics"])["Recall rate"] == "—"
    assert display["rates"] == [None]
    assert "No answers" in display["comparison"]


@pytest.mark.parametrize("kind", ["documents", "states"])
@pytest.mark.parametrize("stale", [False, True])
def test_library_queries_capture_profile_and_use_operation_collection(monkeypatch, kind, stale):
    active = ["Synthetic"]
    window = SimpleNamespace(col=object())
    pending, reads, received = [], [], []
    class Query:
        def __init__(self, **kwargs):
            pending.append(kwargs)
        def failure(self, _callback):
            return self
        def run_in_background(self):
            pass
    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=Query))
    monkeypatch.setattr(learning_stats, "mw", window)
    monkeypatch.setattr(learning_stats, "_active_profile", lambda: active[0])
    monkeypatch.setattr(learning_stats, "resolve_topic_card_classifier", lambda: "classification")
    cancelled = lambda: False
    if kind == "documents":
        def load(col, addon_dir, profile, **kwargs):
            reads.append((col, addon_dir, profile, kwargs["should_cancel"]))
            return ["snapshot"]
        monkeypatch.setattr(learning_stats, "document_progress_from_collection", load)
        learning_stats.request_document_progress(window, "/synthetic", active[0], "04:00", received.append,
                                                 is_current=lambda: True, cancelled=cancelled)
    else:
        def load(col, **kwargs):
            reads.append((col, kwargs["classifier"], kwargs["should_cancel"]))
            return {"new": 1}
        monkeypatch.setattr(learning_stats, "learning_card_states_from_collection", load)
        learning_stats.request_learning_card_states(window, active[0], "04:00", received.append,
                                                   is_current=lambda: True, cancelled=cancelled)
    assert reads == []
    operation_collection = object()
    result = pending[0]["op"](operation_collection)
    assert reads == ([(operation_collection, "/synthetic", "Synthetic", cancelled)] if kind == "documents"
                     else [(operation_collection, "classification", cancelled)])
    if stale:
        active[0] = "Other"
    pending[0]["success"](result)
    assert received == ([] if stale else [result])


@pytest.mark.parametrize("stale_reason", [None, "profile", "collection", "date", "closed"])
@pytest.mark.parametrize("history", [False, True], ids=["today", "history"])
def test_background_learning_results_use_operation_collection_and_drop_stale_callbacks(monkeypatch, stale_reason, history):
    active = {"profile": "Synthetic", "date": "2026-10-13", "open": True}
    window = SimpleNamespace(col=object())
    requests, delivered, reads = [], [], []

    class Query:
        def __init__(self, **kwargs):
            self.request = kwargs
            requests.append(self)

        def failure(self, callback):
            self.failed = callback
            return self

        def run_in_background(self):
            pass

    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=Query))
    monkeypatch.setattr(learning_stats, "mw", window)
    monkeypatch.setattr(learning_stats, "_active_profile", lambda: active["profile"])
    monkeypatch.setattr(learning_stats, "_effective_date", lambda _cutoff: active["date"])
    classifier = object()
    monkeypatch.setattr(learning_stats, "resolve_topic_card_classifier", lambda: classifier)

    def load(col, cutoff, **kwargs):
        reads.append((col, cutoff, kwargs["classifier"]))
        if history:
            assert kwargs["days"] == 60
            return [{"date": "2026-10-13", "stages": {"learning": {"again": 2}}}]
        return {"stages": {"learning": {"again": 2}}}

    monkeypatch.setattr(learning_stats, "learning_outcome_history_from_collection" if history else "daily_learning_outcomes_from_collection", load)
    request = learning_stats.request_learning_outcome_history if history else learning_stats.request_daily_learning_outcomes
    request(
        window, "Synthetic", "05:30", delivered.append,
        is_current=lambda: active["open"],
    )
    assert reads == [] and delivered == []
    operation_collection = object()
    result = requests[0].request["op"](operation_collection)
    assert reads == [(operation_collection, "05:30", classifier)]
    if stale_reason == "profile":
        active["profile"] = "Other"
    elif stale_reason == "collection":
        window.col = object()
    elif stale_reason == "date":
        active["date"] = "2026-10-14"
    elif stale_reason == "closed":
        active["open"] = False
    requests[0].request["success"](result)
    assert delivered == ([result] if stale_reason is None else [])


def test_deck_browser_updates_once_then_reloads_on_the_next_external_render(monkeypatch):
    pending, refreshes = [], []
    monkeypatch.setattr(learning_stats, "_effective_date", lambda _cutoff: "2026-10-13")
    monkeypatch.setattr(learning_stats, "request_daily_learning_outcomes", lambda *args, **kwargs: pending.append((args[3], kwargs["is_current"])))
    cache = learning_stats.DeckBrowserLearningStats()
    window = SimpleNamespace(col=object(), state="deckBrowser")
    window.deckBrowser = SimpleNamespace(refresh=lambda: refreshes.append(cache.get(window, "Synthetic", "04:00")))

    assert cache.get(window, "Synthetic", "04:00") is None
    assert cache.loading
    cache.get(window, "Synthetic", "04:00")
    assert len(pending) == 1  # Repeated renders while loading share the request.
    result = {"stages": {"review": {"good": 1}}}
    pending[0][0](result)
    assert refreshes == [result] and not cache.loading
    assert len(pending) == 1  # The completion refresh must not start a loop.
    assert cache.get(window, "Synthetic", "04:00") == result
    assert len(pending) == 2
    cache.get(window, "Other", "04:00")
    assert not pending[1][1]()  # A profile change invalidates pending delivery.
    assert cache.loading
