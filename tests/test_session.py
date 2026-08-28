"""Integration tests for the learnFunction picking loop and _on_card_answered logic.

These tests exercise the behaviors of the session machinery without requiring the
full Anki UI by reproducing the key logic using the public API of scheduler.py and
statistics.py with lightweight mocks.
"""

import copy
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import scheduler as sched
from scheduler import NO_TAGS_KEY


_ADDON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_package(name: str, path: str) -> None:
    module = sys.modules.get(name)
    if module is None or not isinstance(module, types.ModuleType):
        module = types.ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [path]


def _load_repo_module(fullname: str, relpath: str):
    _ensure_package("incremento", _ADDON_ROOT)
    _ensure_package("incremento.backend", os.path.join(_ADDON_ROOT, "backend"))
    _ensure_package("incremento.frontend", os.path.join(_ADDON_ROOT, "frontend"))

    aqt_module = sys.modules.setdefault("aqt", types.ModuleType("aqt"))
    if not hasattr(aqt_module, "gui_hooks"):
        aqt_module.gui_hooks = types.SimpleNamespace(
            reviewer_did_show_question=[],
            reviewer_did_show_answer=[],
            reviewer_did_answer_card=[],
            reviewer_will_end=[],
            state_did_change=[],
        )
    qt_module = sys.modules.setdefault("aqt.qt", types.ModuleType("aqt.qt"))
    for name in ("QDialog", "QVBoxLayout", "QTextEdit", "QPushButton"):
        if not hasattr(qt_module, name):
            setattr(qt_module, name, type(name, (), {"__init__": lambda self, *args, **kwargs: None}))
    if not hasattr(qt_module, "QTimer"):
        qt_module.QTimer = types.SimpleNamespace(singleShot=lambda _ms, callback: callback())

    if "incremento.frontend.learn_dialog" not in sys.modules:
        stub = types.ModuleType("incremento.frontend.learn_dialog")
        stub.SchedulerConfigDialog = object
        sys.modules["incremento.frontend.learn_dialog"] = stub

    spec = importlib.util.spec_from_file_location(
        fullname,
        os.path.join(_ADDON_ROOT, relpath),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    return module


_SESSION_MOD = _load_repo_module("incremento.backend.session", "backend/session.py")


def _load_review_time_tracker_module():
    sys.modules.pop("incremento.backend.review_time_tracker", None)

    pdf_manager = types.ModuleType("incremento.backend.pdf_manager")
    pdf_manager.PDF_NOTE_TYPE = "Incremento PDF"
    sys.modules["incremento.backend.pdf_manager"] = pdf_manager

    epub_manager = types.ModuleType("incremento.backend.epub_manager")
    epub_manager.EPUB_NOTE_TYPE = "Incremento EPUB"
    sys.modules["incremento.backend.epub_manager"] = epub_manager

    scheduler_config = types.ModuleType("incremento.backend.scheduler_config")
    scheduler_config.load_scheduler_config = lambda: types.SimpleNamespace(day_end_time="00:00")
    sys.modules["incremento.backend.scheduler_config"] = scheduler_config

    statistics = types.ModuleType("incremento.backend.statistics")

    class _StatsManager:
        def __init__(self, *_args, **_kwargs):
            self.record_time_only = MagicMock()

    statistics.StatsManager = _StatsManager
    sys.modules["incremento.backend.statistics"] = statistics

    return _load_repo_module(
        "incremento.backend.review_time_tracker",
        "backend/review_time_tracker.py",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stats_mock():
    """Return a mock StatsManager with an in-memory counts dict."""
    stats = MagicMock()
    stats.session  = {"type": {}, "tags": {}, "mode": {}}
    stats.counts_for.side_effect = lambda scope: stats.session
    return stats


def _simulate_pick(get_card_fn, selected_ids, added_to_filtered, picked_meta, stats, scope):
    """Replicate one iteration of the _pick() inner function from learnFunction."""
    counts = stats.counts_for(scope)
    result = get_card_fn(exclude_ids=added_to_filtered)
    if result.card is None:
        return False
    counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
    counts["mode"][result.mode]      = counts["mode"].get(result.mode, 0) + 1
    if result.tag:
        counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1
    picked_meta[result.card] = {
        "card_type": result.card_type,
        "tag":       result.tag,
        "mode":      result.mode,
    }
    added_to_filtered.add(result.card)
    selected_ids.append(result.card)
    return True


def _simulate_on_card_answered(cid, picked_meta, reviewed_ids, stats, scope):
    """Replicate _on_card_answered from learnFunction."""
    if cid not in picked_meta or cid in reviewed_ids:
        return
    reviewed_ids.add(cid)
    meta = picked_meta[cid]
    tag = None if meta["tag"] == NO_TAGS_KEY else meta["tag"]
    fake = types.SimpleNamespace(
        card=cid, card_type=meta["card_type"], tag=tag, mode=meta["mode"]
    )
    stats.record(fake, scope)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPickLoopDeduplication:
    """_pick excludes cards already selected via added_to_filtered."""

    def test_second_call_excludes_first_card(self):
        """A card returned twice by the scheduler is only added once."""
        call_count = [0]
        CARD_A = 101

        def fake_get(exclude_ids):
            call_count[0] += 1
            if CARD_A not in exclude_ids:
                return types.SimpleNamespace(card=CARD_A, card_type="items", tag=None, mode="random")
            return types.SimpleNamespace(card=None, card_type=None, tag=None, mode=None)

        stats     = _make_stats_mock()
        selected  = []
        excluded  = set()
        meta      = {}

        _simulate_pick(fake_get, selected, excluded, meta, stats, "session")
        _simulate_pick(fake_get, selected, excluded, meta, stats, "session")

        assert selected == [CARD_A], "Card should appear exactly once in selected_ids"
        assert call_count[0] == 2, "Scheduler was called twice"


class TestOnCardAnsweredDeduplication:
    """_on_card_answered only records a card once even if called repeatedly."""

    def test_second_answer_for_same_card_not_recorded(self):
        picked_meta   = {42: {"card_type": "items", "tag": None, "mode": "random"}}
        reviewed_ids  = set()
        stats         = _make_stats_mock()

        _simulate_on_card_answered(42, picked_meta, reviewed_ids, stats, "session")
        _simulate_on_card_answered(42, picked_meta, reviewed_ids, stats, "session")

        assert stats.record.call_count == 1


class TestOnCardAnsweredIgnoresUnpickedCards:
    """_on_card_answered is a no-op for cards not in picked_meta."""

    def test_card_not_in_picked_meta_not_recorded(self):
        picked_meta  = {}   # card 99 was never scheduled
        reviewed_ids = set()
        stats        = _make_stats_mock()

        _simulate_on_card_answered(99, picked_meta, reviewed_ids, stats, "session")

        stats.record.assert_not_called()


class TestNoTagsKeyNotPersisted:
    """NO_TAGS_KEY is synthetic — it must never reach stats.record as a real tag."""

    def test_no_tags_key_becomes_none(self):
        picked_meta  = {7: {"card_type": "topics", "tag": NO_TAGS_KEY, "mode": "priority"}}
        reviewed_ids = set()
        stats        = _make_stats_mock()

        _simulate_on_card_answered(7, picked_meta, reviewed_ids, stats, "session")

        call_args = stats.record.call_args
        result_ns = call_args[0][0]      # first positional arg is the fake SchedulerResult
        assert result_ns.tag is None, "NO_TAGS_KEY should be converted to None before recording"


class TestSessionCountsSnapshot:
    """Session counts accumulate correctly across multiple picks."""

    def test_type_counts_increment_per_pick(self):
        results_queue = [
            types.SimpleNamespace(card=1, card_type="topics", tag=None, mode="random"),
            types.SimpleNamespace(card=2, card_type="items",  tag=None, mode="random"),
            types.SimpleNamespace(card=3, card_type="topics", tag=None, mode="priority"),
        ]
        queue_iter = iter(results_queue)

        def fake_get(exclude_ids):
            return next(queue_iter)

        stats    = _make_stats_mock()
        selected = []
        excluded = set()
        meta     = {}

        for _ in range(3):
            _simulate_pick(fake_get, selected, excluded, meta, stats, "session")

        session_copy = copy.deepcopy(stats.session)
        assert session_copy["type"]["topics"] == 2
        assert session_copy["type"]["items"]  == 1
        assert session_copy["mode"]["random"]   == 2
        assert session_copy["mode"]["priority"] == 1


class TestRuntimeSessionStats:
    def test_records_only_answered_cards_for_session_dialog(self, monkeypatch):
        monkeypatch.setattr(_SESSION_MOD, "_empty", lambda: {"type": {}, "tags": {}, "mode": {}})
        monkeypatch.setattr(_SESSION_MOD, "_empty_time", lambda: {"type": {}, "tags": {}})
        _SESSION_MOD.reset_session_counts()

        _SESSION_MOD._record_session_count("pdf", None, "random")
        _SESSION_MOD._record_session_count("topics", "math", "priority")

        assert _SESSION_MOD.get_session_counts() == {
            "type": {"pdf": 1, "topics": 1},
            "tags": {"math": 1},
            "mode": {"random": 1, "priority": 1},
        }

    def test_reset_clears_session_counts_and_time(self, monkeypatch):
        monkeypatch.setattr(_SESSION_MOD, "_empty", lambda: {"type": {}, "tags": {}, "mode": {}})
        monkeypatch.setattr(_SESSION_MOD, "_empty_time", lambda: {"type": {}, "tags": {}})
        _SESSION_MOD._record_session_count("items", None, "random")
        _SESSION_MOD.reset_session_counts()

        assert _SESSION_MOD.get_session_counts() == {"type": {}, "tags": {}, "mode": {}}
        assert _SESSION_MOD.get_session_times() == {"type": {}, "tags": {}}


class TestSessionDiagnostics:
    def test_snapshot_contains_only_safe_counts_and_flags(self, monkeypatch):
        state = types.SimpleNamespace(
            session_closed=False,
            selected_ids=[101, 202],
            reviewed_ids={101},
            window_size=40,
            auto_refill_enabled=True,
            refill_retry_pending=True,
            session_deck_name="Private Deck Name",
            picked_meta={101: {"tag": "private-tag", "text": "private content"}},
        )
        monkeypatch.setattr(_SESSION_MOD, "_active_incremento_session_state", state)

        snapshot = _SESSION_MOD.diagnostic_session_snapshot()

        assert snapshot == {
            "active": True,
            "selected_count": 2,
            "reviewed_count": 1,
            "window_size": 40,
            "auto_refill": True,
            "refill_pending": True,
            "closed": False,
        }
        encoded = repr(snapshot)
        assert "101" not in encoded
        assert "202" not in encoded
        assert "private-tag" not in encoded
        assert "Private Deck Name" not in encoded

    def test_diagnostic_sink_failure_never_escapes(self, monkeypatch):
        def _broken_sink(_event, _fields):
            raise RuntimeError("diagnostics unavailable")

        monkeypatch.setattr(_SESSION_MOD, "_diagnostic_event_callback", _broken_sink)
        _SESSION_MOD._emit_diagnostic_event(
            "incremento_session_requested",
            target_count=500,
        )

    def test_registered_sink_receives_separate_event_and_field_mapping(self, monkeypatch):
        received = []
        monkeypatch.setattr(_SESSION_MOD, "_diagnostic_event_callback", None)
        _SESSION_MOD.register_diagnostic_event_callback(
            lambda event, fields: received.append((event, fields))
        )

        _SESSION_MOD._emit_diagnostic_event(
            "incremento_session_requested",
            target_count=500,
            auto_refill=True,
        )

        assert received == [
            (
                "incremento_session_requested",
                {"target_count": 500, "auto_refill": True},
            )
        ]

    def test_media_inspection_failure_records_only_type_and_kind(self, monkeypatch):
        received = []
        monkeypatch.setattr(
            _SESSION_MOD,
            "_diagnostic_event_callback",
            lambda event, fields: received.append((event, fields)),
        )

        _SESSION_MOD.record_media_review_inspection_failed(
            "pdf",
            RuntimeError("private filename and card content"),
        )

        assert received == [
            (
                "media_review_inspection_failed",
                {"content_kind": "pdf", "error_type": "RuntimeError"},
            )
        ]
        assert "private filename" not in repr(received)


class TestIncrementoSessionDeckNaming:
    def test_no_dialog_profile_uses_base_session_deck(self):
        assert _SESSION_MOD.incremento_session_deck_name(None) == "Incremento Session"
        assert _SESSION_MOD.incremento_session_deck_name("") == "Incremento Session"

    def test_named_dialog_profile_scopes_session_deck(self):
        assert _SESSION_MOD.incremento_session_deck_name("Focus") == "Incremento Session (Focus)"


class TestQuickOpenReview:
    def test_starts_one_card_filtered_review_for_quick_open(self, monkeypatch):
        calls = []

        def _fake_start_explicit_review(selected_ids, **kwargs):
            calls.append((list(selected_ids), dict(kwargs)))
            return True

        monkeypatch.setattr(_SESSION_MOD, "start_explicit_review", _fake_start_explicit_review)

        assert _SESSION_MOD.start_quick_open_review(321) is True
        assert calls == [
            (
                [321],
                {
                    "deck_name": _SESSION_MOD.INCREMENTO_QUICK_OPEN_REVIEW_DECK,
                    "preserve_order": True,
                    "empty_message": "No selected card is available to study.",
                    "diagnostic_source": "quick_open",
                },
            )
        ]

    def test_rejects_invalid_card_id_before_starting_review(self, monkeypatch):
        shown = []

        monkeypatch.setattr(
            _SESSION_MOD,
            "start_explicit_review",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not start")),
        )
        monkeypatch.setattr(_SESSION_MOD, "showInfo", shown.append)

        assert _SESSION_MOD.start_quick_open_review("bad-id") is False
        assert shown == ["No selected card is available to study."]


class TestExplicitReviewSelector:
    def test_resolves_and_builds_review_inside_collection_operation(self, monkeypatch):
        operations = []
        selection_calls = []
        prepare_calls = []
        moved = []
        selected_decks = []
        diagnostic_events = []
        hooks = types.SimpleNamespace(reviewer_will_end=[], state_did_change=[])
        fake_col = types.SimpleNamespace(
            get_card=lambda card_id: types.SimpleNamespace(did=77),
            decks=types.SimpleNamespace(
                select=lambda deck_id: selected_decks.append(deck_id)
            ),
        )

        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: operations.append(kwargs),
        )
        monkeypatch.setattr(_SESSION_MOD, "gui_hooks", hooks)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_diagnostic_event_callback",
            lambda event, fields: diagnostic_events.append((event, fields)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_prepare_filtered_review_deck",
            lambda ids, **kwargs: prepare_calls.append((list(ids), dict(kwargs)))
            or _SESSION_MOD._FilteredDeckBuildResult(deck_id=77, changes="changes"),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(moveToState=lambda state: moved.append(state)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_defer_collection_ui_action",
            lambda callback: callback(),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda _ms, callback: callback()),
        )

        def _selector(col):
            selection_calls.append(col)
            return [30, "20", 30, 0, "bad"]

        assert _SESSION_MOD.start_explicit_review_from_selector(
            _selector,
            deck_name="Incremento Video Review",
            diagnostic_source="media_review",
            diagnostic_content_kind="video",
            diagnostic_media_order="created_oldest",
            diagnostic_media_card_kind="both",
            diagnostic_media_tree_scope="nested",
            diagnostic_media_range="all",
            diagnostic_media_state="due",
            diagnostic_limit=25,
        ) is True
        assert selection_calls == []
        assert len(operations) == 1

        result = operations[0]["op"](fake_col)
        assert selection_calls == [fake_col]
        assert result.selected_ids == [30, 20]
        assert prepare_calls == [
            (
                [30, 20],
                {
                    "deck_name": "Incremento Video Review",
                    "preserve_order": True,
                    "select_deck": False,
                    "col": fake_col,
                    "return_result": True,
                },
            )
        ]
        assert selected_decks == [77]

        operations[0]["success"](result)
        assert moved == ["review"]
        assert len(hooks.reviewer_will_end) == 1
        hooks.reviewer_will_end[0]()
        assert [event for event, _fields in diagnostic_events] == [
            "explicit_review_requested",
            "explicit_review_build_started",
            "explicit_review_build_finished",
            "explicit_review_started",
            "explicit_review_ended",
        ]
        assert all(
            fields.get("source") == "media_review"
            and fields.get("content_kind") == "video"
            for _event, fields in diagnostic_events
        )
        assert diagnostic_events[0][1] == {
            "source": "media_review",
            "content_kind": "video",
            "requested_count": 0,
            "preserve_order": True,
            "media_order": "created_oldest",
            "media_card_kind": "both",
            "media_tree_scope": "nested",
            "media_range": "all",
            "media_state": "due",
            "limit": 25,
        }

    def test_selector_failure_is_reported_as_selection_stage(self, monkeypatch):
        operations = []
        diagnostic_events = []
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: operations.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_defer_collection_ui_action",
            lambda callback: callback(),
        )
        monkeypatch.setattr(_SESSION_MOD, "showInfo", lambda _message: None)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_diagnostic_event_callback",
            lambda event, fields: diagnostic_events.append((event, fields)),
        )

        def _broken_selector(_col):
            raise RuntimeError("private selector detail")

        assert _SESSION_MOD.start_explicit_review_from_selector(_broken_selector)
        try:
            operations[0]["op"](object())
        except RuntimeError as exc:
            operations[0]["failure"](exc)

        assert diagnostic_events[-1] == (
            "explicit_review_failed",
            {
                "source": "selected_cards",
                "content_kind": "other",
                "stage": "selection",
                "error_type": "RuntimeError",
            },
        )
        assert "private selector detail" not in repr(diagnostic_events)

    def test_empty_background_selection_shows_message_without_building(self, monkeypatch):
        operations = []
        shown = []
        moved = []
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: operations.append(kwargs),
        )
        monkeypatch.setattr(_SESSION_MOD, "_empty_op_changes", object)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_prepare_filtered_review_deck",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("an empty selection must not build a deck")
            ),
        )
        monkeypatch.setattr(_SESSION_MOD, "showInfo", shown.append)
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(moveToState=lambda state: moved.append(state)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_defer_collection_ui_action",
            lambda callback: callback(),
        )

        assert _SESSION_MOD.start_explicit_review_from_selector(
            lambda _col: [],
            empty_message="No attached cards.",
        ) is True
        result = operations[0]["op"](object())
        operations[0]["success"](result)

        assert shown == ["No attached cards."]
        assert moved == []

    def test_reports_cards_that_anki_cannot_move_from_another_filtered_deck(
        self, monkeypatch
    ):
        operations = []
        shown = []
        moved = []
        fake_col = types.SimpleNamespace(
            get_card=lambda card_id: types.SimpleNamespace(
                did=77 if int(card_id) == 10 else 88
            ),
            decks=types.SimpleNamespace(select=lambda _deck_id: None),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: operations.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_prepare_filtered_review_deck",
            lambda *_args, **_kwargs: _SESSION_MOD._FilteredDeckBuildResult(
                deck_id=77,
                changes="changes",
            ),
        )
        monkeypatch.setattr(_SESSION_MOD, "showInfo", shown.append)
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(moveToState=lambda state: moved.append(state)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda _ms, callback: callback()),
        )

        assert _SESSION_MOD.start_explicit_review_from_selector(
            lambda _col: [10, 20],
        ) is True
        result = operations[0]["op"](fake_col)

        assert result.requested_ids == [10, 20]
        assert result.selected_ids == [10]
        assert result.unavailable_ids == [20]
        operations[0]["success"](result)
        assert "1 requested card was not added" in shown[0]
        assert moved == ["review"]

    def test_all_unavailable_cards_leave_current_deck_selected(self, monkeypatch):
        operations = []
        shown = []
        moved = []
        selected_decks = []
        fake_col = types.SimpleNamespace(
            get_card=lambda _card_id: types.SimpleNamespace(did=88),
            decks=types.SimpleNamespace(
                select=lambda deck_id: selected_decks.append(deck_id)
            ),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: operations.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_prepare_filtered_review_deck",
            lambda *_args, **_kwargs: _SESSION_MOD._FilteredDeckBuildResult(
                deck_id=77,
                changes="changes",
            ),
        )
        monkeypatch.setattr(_SESSION_MOD, "showInfo", shown.append)
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(moveToState=lambda state: moved.append(state)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_defer_collection_ui_action",
            lambda callback: callback(),
        )

        assert _SESSION_MOD.start_explicit_review_from_selector(
            lambda _col: [10, 20],
            empty_message="No attached cards.",
        ) is True
        result = operations[0]["op"](fake_col)
        operations[0]["success"](result)

        assert result.selected_ids == []
        assert result.unavailable_ids == [10, 20]
        assert selected_decks == []
        assert moved == []
        assert shown[0].startswith("No attached cards.")
        assert "2 linked cards were unavailable" in shown[0]


class TestPrepareFilteredReviewDeck:
    def test_preserve_order_assigns_due_after_rebuild(self, monkeypatch):
        updated_cards = []
        rebuild_calls = []

        class _Terms(list):
            def add(self, **kwargs):
                self.append(kwargs)

        terms = _Terms()
        fdu = types.SimpleNamespace(
            config=types.SimpleNamespace(
                reschedule=False,
                search_terms=terms,
            )
        )
        original_deck_id = 9
        filtered_deck_id = 55
        cards = {
            101: types.SimpleNamespace(id=101, due=999, did=original_deck_id),
            102: types.SimpleNamespace(id=102, due=999, did=original_deck_id),
            103: types.SimpleNamespace(id=103, due=999, did=original_deck_id),
        }

        def _rebuild_filtered_deck(did):
            rebuild_calls.append(
                {
                    "did": did,
                    "dues": {cid: card.due for cid, card in cards.items()},
                    "terms": list(terms),
                }
            )
            cards[101].did = filtered_deck_id
            cards[101].due = -99999
            cards[102].did = original_deck_id
            cards[102].due = -99998
            cards[103].did = filtered_deck_id
            cards[103].due = -99997

        fake_sched = types.SimpleNamespace(
            empty_filtered_deck=lambda did: None,
            get_or_create_filtered_deck=lambda did: fdu,
            add_or_update_filtered_deck=lambda fdu_arg: types.SimpleNamespace(id=filtered_deck_id),
            rebuild_filtered_deck=_rebuild_filtered_deck,
        )
        fake_decks = types.SimpleNamespace(
            by_name=lambda name: None,
            new_filtered=lambda name: 55,
            select=lambda did: None,
        )
        fake_col = types.SimpleNamespace(
            decks=fake_decks,
            sched=fake_sched,
            get_card=lambda cid: cards[cid],
            update_cards=lambda batch, skip_undo_entry=False: updated_cards.append(
                ([(card.id, card.due) for card in batch], skip_undo_entry)
            ),
        )
        monkeypatch.setattr(_SESSION_MOD, "mw", types.SimpleNamespace(col=fake_col))

        did = _SESSION_MOD._prepare_filtered_review_deck(
            [101, 102, 103],
            deck_name="Incremento Session (Test)",
            preserve_order=True,
        )

        assert did == filtered_deck_id
        assert updated_cards == [([(101, 0), (103, 1)], True)]
        assert cards[102].due == -99998
        assert rebuild_calls == [
            {
                "did": filtered_deck_id,
                "dues": {101: 999, 102: 999, 103: 999},
                "terms": [
                    {
                        "search": "cid:101,102,103",
                        "limit": 3,
                        "order": _SESSION_MOD.DYN_DUE,
                    }
                ],
            }
        ]
        assert _SESSION_MOD.incremento_session_deck_name("Writing") == "Incremento Session (Writing)"

    def test_prepare_deduplicates_ids_before_building_search_and_order(self, monkeypatch):
        class _Terms(list):
            def add(self, **kwargs):
                self.append(kwargs)

        terms = _Terms()
        fdu = types.SimpleNamespace(
            config=types.SimpleNamespace(reschedule=False, search_terms=terms)
        )
        cards = {
            cid: types.SimpleNamespace(id=cid, due=99, did=55)
            for cid in (101, 102)
        }
        updated = []
        fake_col = types.SimpleNamespace(
            decks=types.SimpleNamespace(
                by_name=lambda _name: None,
                new_filtered=lambda _name: 55,
                select=lambda _did: None,
            ),
            sched=types.SimpleNamespace(
                get_or_create_filtered_deck=lambda _did: fdu,
                add_or_update_filtered_deck=lambda _fdu: types.SimpleNamespace(id=55),
                rebuild_filtered_deck=lambda _did: None,
            ),
            get_card=lambda cid: cards[cid],
            update_cards=lambda batch, skip_undo_entry=False: updated.extend(
                (card.id, card.due, skip_undo_entry) for card in batch
            ),
        )
        monkeypatch.setattr(_SESSION_MOD, "mw", types.SimpleNamespace(col=fake_col))

        _SESSION_MOD._prepare_filtered_review_deck(
            [101, "bad", 102, 101, -1],
            deck_name="Incremento Session",
            preserve_order=True,
        )

        assert terms[0]["search"] == "cid:101,102"
        assert terms[0]["limit"] == 2
        assert updated == [(101, 0, True), (102, 1, True)]

    def test_session_deck_predicate_matches_only_incremento_session_variants(self):
        assert _SESSION_MOD.is_incremento_session_deck_name("Incremento Session") is True
        assert _SESSION_MOD.is_incremento_session_deck_name("Incremento Session (Focus)") is True
        assert _SESSION_MOD.is_incremento_session_deck_name("Incremento Session (Writing)") is True
        assert _SESSION_MOD.is_incremento_session_deck_name("Incremento Session ()") is False
        assert _SESSION_MOD.is_incremento_session_deck_name("Incremento Session Focus") is False
        assert _SESSION_MOD.is_incremento_session_deck_name("Incremento PDF Review") is False

    def test_empty_filtered_deck_by_name_only_clears_dynamic_decks(self, monkeypatch):
        emptied = []
        fake_sched = types.SimpleNamespace(
            empty_filtered_deck=lambda did: emptied.append(did),
        )
        fake_decks = types.SimpleNamespace(
            by_name=lambda name: (
                {"id": 12, "dyn": True}
                if name == "Incremento Session"
                else {"id": 99, "dyn": False}
                if name == "Regular Deck"
                else None
            ),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(col=types.SimpleNamespace(decks=fake_decks, sched=fake_sched)),
        )

        assert _SESSION_MOD._empty_filtered_deck_by_name("Incremento Session") is True
        assert _SESSION_MOD._empty_filtered_deck_by_name("Regular Deck") is False
        assert _SESSION_MOD._empty_filtered_deck_by_name("Missing Deck") is False
        assert emptied == [12]

    def test_sync_filtered_deck_by_name_rebuilds_unfinished_session_without_selecting(self, monkeypatch):
        calls = []

        def _fake_prepare(selected_ids, *, deck_name, preserve_order, select_deck):
            calls.append(
                {
                    "selected_ids": list(selected_ids),
                    "deck_name": deck_name,
                    "preserve_order": preserve_order,
                    "select_deck": select_deck,
                }
            )
            return 55

        monkeypatch.setattr(_SESSION_MOD, "_prepare_filtered_review_deck", _fake_prepare)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_empty_filtered_deck_by_name",
            lambda _name: (_ for _ in ()).throw(AssertionError("should not empty deck")),
        )

        assert _SESSION_MOD._sync_filtered_deck_by_name(
            "Incremento Session",
            [101, 102, 101],
            preserve_order=True,
        ) is True
        assert calls == [
            {
                "selected_ids": [101, 102],
                "deck_name": "Incremento Session",
                "preserve_order": True,
                "select_deck": False,
            }
        ]

    def test_sync_filtered_deck_by_name_empties_when_no_cards_remain(self, monkeypatch):
        monkeypatch.setattr(
            _SESSION_MOD,
            "_prepare_filtered_review_deck",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not rebuild")),
        )
        monkeypatch.setattr(_SESSION_MOD, "_empty_filtered_deck_by_name", lambda name: name == "Incremento Session")

        assert _SESSION_MOD._sync_filtered_deck_by_name(
            "Incremento Session",
            [],
            preserve_order=True,
        ) is True


class TestIncrementoSessionAutoRefill:
    def _make_state(self, **overrides):
        picker = types.SimpleNamespace(
            selected_ids=[1, 2, 3],
            picked_meta={1: {"card_type": "topics", "tag": None, "mode": "random"}},
            pick_until=lambda _target: [],
        )
        stats = MagicMock()
        cfg = types.SimpleNamespace(
            scheduler_scope="session",
            preserve_order=True,
            auto_refill_session=True,
        )
        state = _SESSION_MOD._ActiveIncrementoSessionState(
            cfg=cfg,
            stats=stats,
            picker=picker,
            session_deck_name="Incremento Session",
            window_size=50,
            preserve_order=True,
            picked_meta={1: {"card_type": "topics", "tag": None, "mode": "random"}},
            selected_ids=[1, 2, 3],
            auto_refill_enabled=True,
        )
        for key, value in overrides.items():
            setattr(state, key, value)
        return state

    def test_refills_when_live_queue_drops_below_window(self, monkeypatch):
        rebuilt = []
        picker = types.SimpleNamespace(selected_ids=list(range(1, 51)), picked_meta={55: {"card_type": "items", "tag": None, "mode": "random"}})

        def _pick_until(_target):
            picker.selected_ids.append(55)
            return [55]

        picker.pick_until = _pick_until
        state = self._make_state(picker=picker, selected_ids=list(range(1, 51)), window_size=50)
        live_queue = list(range(100, 149))

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: live_queue,
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda deck_name, ordered_ids, preserve_order: rebuilt.append((deck_name, list(ordered_ids), preserve_order)) or True,
        )

        result = _SESSION_MOD._maybe_auto_refill_active_session(state)

        assert result == {"live_queue_ids": live_queue, "new_ids": [55]}
        assert rebuilt == [("Incremento Session", live_queue + [55], True)]
        assert state.selected_ids == list(range(1, 51)) + [55]
        assert state.picked_meta == picker.picked_meta

    def test_live_queue_reader_keeps_active_relearners_even_if_entry_reports_home_deck(self, monkeypatch):
        queued = [
            types.SimpleNamespace(card=types.SimpleNamespace(id=301, did=5), did=5),
            types.SimpleNamespace(card=types.SimpleNamespace(id=302, did=77), did=77),
        ]
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(
                col=types.SimpleNamespace(
                    sched=types.SimpleNamespace(get_queued_cards=lambda fetch_limit=None: queued)
                )
            ),
        )

        assert _SESSION_MOD._live_filtered_queue_ids(
            77,
            fetch_limit=10,
            scheduled_ids={301, 302},
        ) == [301, 302]

    def test_live_queue_reader_ignores_foreign_deck_entries(self, monkeypatch):
        queued = [
            types.SimpleNamespace(card=types.SimpleNamespace(id=401, did=88), did=88),
            types.SimpleNamespace(card=types.SimpleNamespace(id=402, did=77), did=77),
            types.SimpleNamespace(card=types.SimpleNamespace(id=403, did=99), did=99),
            types.SimpleNamespace(card=types.SimpleNamespace(id=404, did=77), did=77),
        ]
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(
                col=types.SimpleNamespace(
                    sched=types.SimpleNamespace(get_queued_cards=lambda fetch_limit=None: queued)
                )
            ),
        )

        assert _SESSION_MOD._live_filtered_queue_ids(77, fetch_limit=10) == [402, 404]

    def test_live_queue_reader_prefers_scheduled_ids_over_deck_metadata(self, monkeypatch):
        queued = [
            types.SimpleNamespace(card=types.SimpleNamespace(id=451, did=88), did=88),
            types.SimpleNamespace(card=types.SimpleNamespace(id=452, did=77), did=77),
            types.SimpleNamespace(card=types.SimpleNamespace(id=453, did=99), did=99),
        ]
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(
                col=types.SimpleNamespace(
                    sched=types.SimpleNamespace(get_queued_cards=lambda fetch_limit=None: queued)
                )
            ),
        )

        assert _SESSION_MOD._live_filtered_queue_ids(
            77,
            fetch_limit=10,
            scheduled_ids={451, 453},
        ) == [451, 453]

    def test_live_queue_reader_keeps_entries_without_deck_metadata(self, monkeypatch):
        queued = [
            types.SimpleNamespace(card=types.SimpleNamespace(id=501)),
            types.SimpleNamespace(card=types.SimpleNamespace(id=502, did=77), did=77),
        ]
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(
                col=types.SimpleNamespace(
                    sched=types.SimpleNamespace(get_queued_cards=lambda fetch_limit=None: queued)
                )
            ),
        )

        assert _SESSION_MOD._live_filtered_queue_ids(77, fetch_limit=10) == [501, 502]

    def test_live_queue_reader_handles_anki_queued_cards_objects(self, monkeypatch):
        queued = types.SimpleNamespace(
            cards=[
                types.SimpleNamespace(card=types.SimpleNamespace(id=601, deck_id=77)),
                types.SimpleNamespace(card=types.SimpleNamespace(id=602, deck_id=88)),
            ]
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(
                col=types.SimpleNamespace(
                    sched=types.SimpleNamespace(get_queued_cards=lambda fetch_limit=None: queued)
                )
            ),
        )

        assert _SESSION_MOD._live_filtered_queue_ids(77, fetch_limit=10) == [601]

    def test_no_refill_when_learning_card_keeps_live_queue_full(self, monkeypatch):
        rebuilt = []
        picker = types.SimpleNamespace(
            selected_ids=list(range(1, 51)),
            picked_meta={},
            pick_until=lambda _target: (_ for _ in ()).throw(AssertionError("should not pick")),
        )
        state = self._make_state(picker=picker, selected_ids=list(range(1, 51)), window_size=50)

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: list(range(200, 250)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda *args, **kwargs: rebuilt.append(args),
        )

        result = _SESSION_MOD._maybe_auto_refill_active_session(state)

        assert result == {"live_queue_ids": list(range(200, 250)), "new_ids": []}
        assert rebuilt == []

    def test_reviewed_learning_card_does_not_block_refill_window(self, monkeypatch):
        rebuilt = []
        live_queue = [1] + list(range(200, 229))
        picker = types.SimpleNamespace(
            selected_ids=list(range(1, 31)),
            picked_meta={31: {"card_type": "items", "tag": None, "mode": "random"}},
        )

        def _pick_until(_target):
            picker.selected_ids.append(31)
            return [31]

        picker.pick_until = _pick_until
        state = self._make_state(picker=picker, selected_ids=list(range(1, 31)), window_size=30)
        state.reviewed_ids = {1}

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: live_queue,
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda deck_name, ordered_ids, preserve_order: rebuilt.append((deck_name, list(ordered_ids), preserve_order)) or True,
        )

        result = _SESSION_MOD._maybe_auto_refill_active_session(state)

        assert result == {"live_queue_ids": live_queue, "new_ids": [31]}
        assert rebuilt == [("Incremento Session", live_queue + [31], True)]

    def test_duplicate_live_queue_defers_refill_without_picking_or_rebuilding(self, monkeypatch):
        rebuilt = []
        picker = types.SimpleNamespace(
            selected_ids=list(range(1, 51)),
            picked_meta={},
            pick_until=lambda _target: (_ for _ in ()).throw(AssertionError("should not pick")),
        )
        state = self._make_state(picker=picker, selected_ids=list(range(1, 51)), window_size=50)

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: [201, 201, 202],
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda *args, **kwargs: rebuilt.append(args),
        )

        result = _SESSION_MOD._maybe_auto_refill_active_session(state)

        assert result == {"live_queue_ids": [201, 201, 202], "new_ids": []}
        assert rebuilt == []

    def test_foreign_live_queue_cards_do_not_block_refill(self, monkeypatch):
        rebuilt = []
        picker = types.SimpleNamespace(selected_ids=list(range(1, 31)), picked_meta={35: {"card_type": "items", "tag": None, "mode": "random"}})

        def _pick_until(_target):
            picker.selected_ids.append(35)
            return [35]

        picker.pick_until = _pick_until
        state = self._make_state(picker=picker, selected_ids=list(range(1, 31)), window_size=30)
        live_queue = [701, 702]

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: live_queue,
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda deck_name, ordered_ids, preserve_order: rebuilt.append((deck_name, list(ordered_ids), preserve_order)) or True,
        )

        result = _SESSION_MOD._maybe_auto_refill_active_session(state)

        assert result == {"live_queue_ids": live_queue, "new_ids": [35]}
        assert rebuilt == [("Incremento Session", [701, 702, 35], True)]

    def test_huge_requested_window_does_not_request_a_huge_live_queue(self):
        state = self._make_state(selected_ids=list(range(1, 41)), window_size=9999)

        assert _SESSION_MOD._live_queue_fetch_limit(state) == 120

    def test_long_running_refill_history_does_not_grow_queue_reads(self):
        state = self._make_state(selected_ids=list(range(1, 1001)), window_size=50)

        assert _SESSION_MOD._live_queue_fetch_limit(state) == 150

    def test_deferred_refill_runs_after_answer_transition(self, monkeypatch):
        callbacks = []
        calls = []
        operations = []
        diagnostic_events = []
        state = self._make_state(window_size=30)

        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda ms, callback: callbacks.append((ms, callback))),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_maybe_auto_refill_active_session",
            lambda _state, **kwargs: calls.append((_state, kwargs))
            or types.SimpleNamespace(
                changes=object(),
                live_queue_ids=[1, 2],
                new_ids=[3],
                outcome="added",
            ),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: operations.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_diagnostic_event_callback",
            lambda event, fields: diagnostic_events.append((event, fields)),
        )

        _SESSION_MOD._schedule_deferred_auto_refill(state, reason="test")

        assert state.refill_retry_pending is True
        assert len(callbacks) == 1
        callbacks[0][1]()
        assert state.refill_retry_pending is True
        assert len(operations) == 1
        fake_col = object()
        result = operations[0]["op"](fake_col)
        assert calls == [(state, {"col": fake_col, "return_result": True})]
        operations[0]["success"](result)
        assert state.refill_retry_pending is False
        assert diagnostic_events == [
            ("incremento_session_refill_requested", {"reason": "other"}),
            (
                "incremento_session_refill_finished",
                {"live_count": 2, "added_count": 1, "outcome": "added"},
            ),
        ]

    def test_deferred_refill_is_not_queued_twice(self, monkeypatch):
        callbacks = []
        diagnostic_events = []
        state = self._make_state(window_size=30)

        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda ms, callback: callbacks.append((ms, callback))),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_diagnostic_event_callback",
            lambda event, fields: diagnostic_events.append((event, fields)),
        )

        _SESSION_MOD._schedule_deferred_auto_refill(state, reason="first")
        _SESSION_MOD._schedule_deferred_auto_refill(state, reason="second")

        assert len(callbacks) == 1
        assert diagnostic_events == [
            ("incremento_session_refill_requested", {"reason": "other"}),
            ("incremento_session_refill_skipped", {"reason": "already_pending"}),
        ]

    def test_deferred_refill_failure_releases_pending_guard(self, monkeypatch):
        callbacks = []
        operations = []
        state = self._make_state(window_size=30)
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda _ms, callback: callbacks.append(callback)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: operations.append(kwargs),
        )

        _SESSION_MOD._schedule_deferred_auto_refill(state, reason="test-failure")
        callbacks[0]()
        assert state.refill_retry_pending is True

        operations[0]["failure"](RuntimeError("boom"))

        assert state.refill_retry_pending is False

    def test_reviewer_advance_waits_until_refill_finishes(
        self, monkeypatch
    ):
        callbacks = []
        next_calls = []

        class _Reviewer:
            def nextCard(self):
                next_calls.append("next")

        reviewer = _Reviewer()
        state = self._make_state(selected_ids=[1], window_size=1)
        state.reviewed_ids = {1}
        state.refill_retry_pending = True
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(
                singleShot=lambda ms, callback: callbacks.append((ms, callback))
            ),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(state="review"),
        )

        assert _SESSION_MOD._defer_next_card_until_refill_finishes(state, reviewer)

        reviewer.nextCard()
        assert next_calls == []
        delay, wait_callback = callbacks.pop(0)
        assert delay == 0
        wait_callback()
        assert callbacks[-1][0] == 25
        assert next_calls == []

        state.refill_retry_pending = False
        callbacks[-1][1]()
        assert next_calls == ["next"]

    def test_reviewer_advance_is_cancelled_when_session_closes_during_refill(
        self, monkeypatch
    ):
        callbacks = []
        next_calls = []

        class _Reviewer:
            def nextCard(self):
                next_calls.append("next")

        reviewer = _Reviewer()
        state = self._make_state(selected_ids=[1], window_size=1)
        state.refill_retry_pending = True
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(
                singleShot=lambda ms, callback: callbacks.append((ms, callback))
            ),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(state="review"),
        )

        assert _SESSION_MOD._defer_next_card_until_refill_finishes(state, reviewer)

        reviewer.nextCard()
        callbacks.pop(0)[1]()
        assert callbacks[-1][0] == 25

        state.session_closed = True
        callbacks[-1][1]()

        assert next_calls == []

    def test_answer_recording_does_not_read_live_queue_on_ui_thread(self, monkeypatch):
        calls = []
        stats = MagicMock()
        stats.session_time = {"type": {}, "tags": {}}
        picker = types.SimpleNamespace(selected_ids=[1], picked_meta={1: {"card_type": "topics", "tag": None, "mode": "random"}})
        state = self._make_state(stats=stats, picker=picker)
        state.picked_meta = {1: {"card_type": "topics", "tag": None, "mode": "random"}}

        monkeypatch.setattr(_SESSION_MOD, "_record_session_count", lambda *args, **kwargs: calls.append("session_count"))
        monkeypatch.setattr(_SESSION_MOD, "_review_seconds", lambda *args, **kwargs: 3.0)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_maybe_auto_refill_active_session",
            lambda _state: calls.append("live_queue"),
        )

        def _record(fake, scope):
            calls.append("record")

        stats.record.side_effect = _record

        _SESSION_MOD._record_incremento_answer(
            state,
            reviewer=types.SimpleNamespace(),
            card=types.SimpleNamespace(id=1),
        )

        assert calls == ["record", "session_count"]

    def test_repeated_refill_cycles_never_schedule_same_new_card_twice(self, monkeypatch):
        cycle = {"count": 0}

        class _Picker:
            def __init__(self):
                self.selected_ids = [1, 2, 3]
                self.picked_meta = {
                    4: {"card_type": "items", "tag": None, "mode": "random"},
                    5: {"card_type": "items", "tag": None, "mode": "random"},
                }

            def pick_until(self, _target):
                cycle["count"] += 1
                if cycle["count"] == 1:
                    self.selected_ids.append(4)
                    return [4]
                if cycle["count"] == 2:
                    self.selected_ids.append(5)
                    return [5]
                return []

        picker = _Picker()
        state = self._make_state(picker=picker, selected_ids=[1, 2, 3], window_size=3)
        rebuilt = []

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: [10, 11] if cycle["count"] == 0 else [11, 12],
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda deck_name, ordered_ids, preserve_order: rebuilt.append(list(ordered_ids)) or True,
        )

        _SESSION_MOD._maybe_auto_refill_active_session(state)
        _SESSION_MOD._maybe_auto_refill_active_session(state)

        assert rebuilt == [[10, 11, 4], [11, 12, 5]]

    def test_refill_rolls_back_picker_if_rebuild_fails(self, monkeypatch):
        class _Picker:
            def __init__(self):
                self.selected_ids = [1, 2, 3]
                self.picked_meta = {1: {"card_type": "topics", "tag": None, "mode": "random"}}
                self.picked_ids = {1, 2, 3}

            def snapshot(self):
                return {
                    "selected_ids": list(self.selected_ids),
                    "picked_meta": copy.deepcopy(self.picked_meta),
                }

            def _restore_snapshot(self, snapshot):
                self.selected_ids = list(snapshot.get("selected_ids", []))
                self.picked_meta = copy.deepcopy(snapshot.get("picked_meta", {}))
                self.picked_ids = set(self.selected_ids)

            def pick_until(self, _target):
                self.selected_ids.append(55)
                self.picked_ids.add(55)
                self.picked_meta[55] = {"card_type": "items", "tag": None, "mode": "random"}
                return [55]

        picker = _Picker()
        state = self._make_state(
            picker=picker,
            selected_ids=[1, 2, 3],
            picked_meta=copy.deepcopy(picker.picked_meta),
            window_size=4,
        )

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: [10, 11, 12],
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        try:
            _SESSION_MOD._maybe_auto_refill_active_session(state)
            assert False, "Expected refill rebuild failure to be raised"
        except RuntimeError as exc:
            assert str(exc) == "boom"

        assert picker.selected_ids == [1, 2, 3]
        assert picker.picked_ids == {1, 2, 3}
        assert 55 not in picker.picked_meta
        assert state.selected_ids == [1, 2, 3]
        assert state.picked_meta == {1: {"card_type": "topics", "tag": None, "mode": "random"}}

    def test_answer_recording_is_isolated_from_refill_failures(self, monkeypatch):
        stats = MagicMock()
        stats.session_time = {"type": {}, "tags": {}}
        picker = types.SimpleNamespace(selected_ids=[1], picked_meta={1: {"card_type": "topics", "tag": None, "mode": "random"}})
        state = self._make_state(stats=stats, picker=picker)
        state.picked_meta = {1: {"card_type": "topics", "tag": None, "mode": "random"}}

        monkeypatch.setattr(_SESSION_MOD, "_record_session_count", lambda *args, **kwargs: None)
        monkeypatch.setattr(_SESSION_MOD, "_review_seconds", lambda *args, **kwargs: 3.0)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_maybe_auto_refill_active_session",
            lambda _state: (_ for _ in ()).throw(RuntimeError("refill failed")),
        )

        _SESSION_MOD._record_incremento_answer(
            state,
            reviewer=types.SimpleNamespace(),
            card=types.SimpleNamespace(id=1),
        )

        assert stats.record.call_count == 1
        assert 1 in state.reviewed_ids


class TestBackgroundSessionStartup:
    def test_read_only_session_query_never_requests_modal_progress(self, monkeypatch):
        events = []

        class _QueryOp:
            def __init__(self, *, parent, op, success):
                events.append(("init", parent, op, success))

            def failure(self, callback):
                events.append(("failure", callback))
                return self

            def with_progress(self, *_args, **_kwargs):
                raise AssertionError("session selection must remain non-modal")

            def run_in_background(self):
                events.append(("run",))

        operations_module = types.ModuleType("aqt.operations")
        operations_module.QueryOp = _QueryOp
        monkeypatch.setitem(sys.modules, "aqt.operations", operations_module)
        parent = object()
        op = lambda _col: None
        success = lambda _result: None
        failure = lambda _exc: None

        _SESSION_MOD._run_collection_query(
            parent=parent,
            op=op,
            success=success,
            failure=failure,
        )

        assert events == [
            ("init", parent, op, success),
            ("failure", failure),
            ("run",),
        ]

    def test_short_session_deck_mutation_never_creates_modal_progress(
        self, monkeypatch
    ):
        events = []

        class _QueryOp:
            def __init__(self, *, parent, op, success):
                self._op = op
                self._success = success
                events.append(("init", parent))

            def failure(self, callback):
                events.append(("failure", callback))
                return self

            def with_progress(self, *_args, **_kwargs):
                raise AssertionError("session deck build must remain non-modal")

            def run_in_background(self):
                events.append(("run",))
                self._success(self._op("collection"))

        def _on_op_finished(mw, result, initiator):
            events.append(("finished", mw, result, initiator))

        operations_module = types.ModuleType("aqt.operations")
        operations_module.QueryOp = _QueryOp
        operations_module.on_op_finished = _on_op_finished
        monkeypatch.setitem(sys.modules, "aqt.operations", operations_module)
        fake_mw = object()
        parent = object()
        initiator = object()
        failure = lambda _exc: None
        success_results = []
        monkeypatch.setattr(_SESSION_MOD, "mw", fake_mw)

        _SESSION_MOD._run_collection_mutation_without_progress(
            parent=parent,
            op=lambda col: ("result", col),
            success=success_results.append,
            failure=failure,
            initiator=initiator,
        )

        assert success_results == [("result", "collection")]
        assert events == [
            ("init", parent),
            ("failure", failure),
            ("run",),
            ("finished", fake_mw, ("result", "collection"), initiator),
        ]

    def test_ui_action_waits_for_native_modal_teardown_without_progress_manager(
        self, monkeypatch
    ):
        deferred = []
        called = []
        fake_progress = types.SimpleNamespace(
            single_shot=lambda *_args: (_ for _ in ()).throw(
                AssertionError("activation must not depend on global progress state")
            ),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(progress=fake_progress),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(
                singleShot=lambda ms, callback: deferred.append((ms, callback))
            ),
        )

        _SESSION_MOD._defer_collection_ui_action(lambda: called.append(True))

        assert called == []
        assert len(deferred) == 1
        assert deferred[0][0] == _SESSION_MOD._COLLECTION_UI_SETTLE_MS
        assert deferred[0][0] >= 100
        deferred[0][1]()
        assert called == [True]

    def test_deferred_ui_action_is_dropped_after_profile_switch(self, monkeypatch):
        called = []
        active_profile = {"name": "Old Profile"}
        monkeypatch.setattr(
            _SESSION_MOD,
            "_active_profile",
            lambda: active_profile["name"],
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_defer_collection_ui_action",
            lambda callback: callback(),
        )

        active_profile["name"] = "New Profile"
        _SESSION_MOD._defer_profile_ui_action(
            "Old Profile",
            lambda: called.append(True),
        )

        assert called == []

    def test_selection_and_deck_build_are_non_modal_serialized_operations(
        self, monkeypatch
    ):
        queries = []
        mutations = []
        picker_events = []
        activation = []
        diagnostic_events = []
        cfg = types.SimpleNamespace(session_card_count=500, preserve_order=True)

        class _Dialog:
            def __init__(self, *_args, **_kwargs):
                pass

            def exec(self):
                return True

            def save_config(self):
                pass

            def to_config(self):
                return cfg

            def get_preview_override(self):
                return None

            def selected_dialog_profile_name(self):
                return None

        class _Picker:
            def __init__(self, *_args, **kwargs):
                picker_events.append(("init", kwargs))
                self.selected_ids = []
                self.picked_meta = {}
                self.stats = types.SimpleNamespace(session_time={"type": {}, "tags": {}})

            def pick_until(self, target):
                picker_events.append(("pick", target))
                self.selected_ids = [101, 102]
                self.picked_meta = {
                    101: {"card_type": "topics", "tag": None, "mode": "random"},
                    102: {"card_type": "items", "tag": None, "mode": "priority"},
                }

        fake_mw = types.SimpleNamespace(
            addonManager=types.SimpleNamespace(getConfig=lambda _pkg: {}),
        )
        classifier = object()
        monkeypatch.setattr(_SESSION_MOD, "mw", fake_mw)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_diagnostic_event_callback",
            lambda event, fields: diagnostic_events.append((event, fields)),
        )
        monkeypatch.setattr(_SESSION_MOD, "SchedulerConfigDialog", _Dialog)
        monkeypatch.setattr(_SESSION_MOD, "SessionPicker", _Picker)
        monkeypatch.setattr(_SESSION_MOD, "release_expired_timed_postpones", lambda: None)
        monkeypatch.setattr(_SESSION_MOD, "_active_profile", lambda: "Profile")
        monkeypatch.setattr(
            _SESSION_MOD,
            "resolve_topic_card_classifier",
            lambda *_args, **_kwargs: classifier,
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_query",
            lambda **kwargs: queries.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_mutation_without_progress",
            lambda **kwargs: mutations.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_prepare_filtered_review_deck",
            lambda ids, **kwargs: _SESSION_MOD._FilteredDeckBuildResult(
                deck_id=77,
                changes=(ids, kwargs),
            ),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_activate_incremento_session",
            lambda result, **kwargs: activation.append((result, kwargs)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda _ms, callback: callback()),
        )

        _SESSION_MOD.learnFunction()

        assert len(queries) == 1
        assert mutations == []
        assert picker_events == []
        fake_col = object()
        selection = queries[0]["op"](fake_col)
        assert picker_events[0][0] == "init"
        assert picker_events[0][1]["col"] is fake_col
        assert picker_events[0][1]["topic_classifier"] is classifier
        assert picker_events[1] == ("pick", 500)
        assert selection.selected_ids == [101, 102]

        queries[0]["success"](selection)
        assert len(mutations) == 1
        assert mutations[0]["initiator"] is mutations[0]["op"]
        result = mutations[0]["op"](fake_col)
        assert result.selected_ids == [101, 102]
        assert result.changes[1]["col"] is fake_col
        assert result.changes[1]["return_result"] is True

        mutations[0]["success"](result)
        assert activation[0][0] is result
        assert [
            fields.get("phase")
            for event, fields in diagnostic_events
            if event == "incremento_session_phase"
        ] == [
            "selection_started",
            "selection_finished",
            "deck_build_started",
            "deck_build_finished",
            "activation_scheduled",
        ]

    def test_superseded_selection_does_not_build_or_activate(self, monkeypatch):
        queries = []
        mutations = []
        activation = []
        cfg = types.SimpleNamespace(session_card_count=1, preserve_order=True)

        class _Dialog:
            def __init__(self, *_args, **_kwargs):
                pass

            def exec(self):
                return True

            def save_config(self):
                pass

            def to_config(self):
                return cfg

            def get_preview_override(self):
                return None

            def selected_dialog_profile_name(self):
                return None

        class _Picker:
            def __init__(self, *_args, **_kwargs):
                self.selected_ids = []
                self.picked_meta = {}
                self.stats = types.SimpleNamespace(
                    session_time={"type": {}, "tags": {}}
                )

            def pick_until(self, _target):
                self.selected_ids = [101]

        monkeypatch.setattr(
            _SESSION_MOD,
            "mw",
            types.SimpleNamespace(
                addonManager=types.SimpleNamespace(getConfig=lambda _pkg: {}),
            ),
        )
        monkeypatch.setattr(_SESSION_MOD, "SchedulerConfigDialog", _Dialog)
        monkeypatch.setattr(_SESSION_MOD, "SessionPicker", _Picker)
        monkeypatch.setattr(
            _SESSION_MOD, "release_expired_timed_postpones", lambda: None
        )
        monkeypatch.setattr(_SESSION_MOD, "_active_profile", lambda: "Profile")
        monkeypatch.setattr(
            _SESSION_MOD,
            "resolve_topic_card_classifier",
            lambda *_args, **_kwargs: object(),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_query",
            lambda **kwargs: queries.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_run_collection_operation",
            lambda **kwargs: mutations.append(kwargs),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_activate_incremento_session",
            lambda *_args, **_kwargs: activation.append(True),
        )

        _SESSION_MOD.learnFunction()
        first_selection = queries[0]["op"](object())

        # A newer accepted session invalidates callbacks from the older one.
        _SESSION_MOD.learnFunction()
        queries[0]["success"](first_selection)

        assert len(queries) == 2
        assert mutations == []
        assert activation == []


class TestIncrementoSessionExit:
    def test_exit_leaves_anki_managed_filtered_deck_untouched(self, monkeypatch):
        hooks = types.SimpleNamespace(
            reviewer_will_end=[],
            state_did_change=[],
            reviewer_did_show_question=[],
            reviewer_did_show_answer=[],
            reviewer_did_answer_card=[],
        )
        moves = []
        fake_mw = types.SimpleNamespace(
            state="overview",
            reviewer=types.SimpleNamespace(card=None),
        )

        def _move_to_state(new_state):
            moves.append(new_state)
            fake_mw.state = new_state

        fake_mw.moveToState = _move_to_state
        stats = MagicMock()
        stats.session_time = {"type": {}, "tags": {}}
        picker = types.SimpleNamespace(selected_ids=[101], picked_meta={})
        result = _SESSION_MOD._SessionBuildOperationResult(
            changes=object(),
            picker=picker,
            stats=stats,
            selected_ids=[101],
            picked_meta={},
            session_time_snapshot={"type": {}, "tags": {}},
            deck_id=77,
        )
        cfg = types.SimpleNamespace(
            show_debug=False,
            session_card_count=1,
            preserve_order=True,
            auto_refill_session=True,
        )
        collection_calls = []
        diagnostic_events = []

        monkeypatch.setattr(_SESSION_MOD, "gui_hooks", hooks)
        monkeypatch.setattr(_SESSION_MOD, "mw", fake_mw)
        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda _ms, callback: callback()),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_diagnostic_event_callback",
            lambda event, fields: diagnostic_events.append((event, fields)),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_session_deck_id_by_name",
            lambda *_args, **_kwargs: collection_calls.append("read-deck"),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda *_args, **_kwargs: collection_calls.append("rebuild"),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_sync_filtered_deck_by_name",
            lambda *_args, **_kwargs: collection_calls.append("sync"),
        )

        _SESSION_MOD._activate_incremento_session(
            result,
            cfg=cfg,
            branch_scope=None,
            session_deck_name="Incremento Session",
        )
        state = _SESSION_MOD._active_incremento_session_state
        assert state is not None
        state.refill_retry_pending = True
        assert moves == ["review"]
        assert len(hooks.reviewer_will_end) == 1
        assert [event for event, _fields in diagnostic_events[:3]] == [
            "incremento_session_phase",
            "incremento_session_phase",
            "incremento_session_started",
        ]
        assert [fields["phase"] for event, fields in diagnostic_events[:2]] == [
            "activation_started",
            "entered_review",
        ]

        hooks.reviewer_will_end[0]()

        assert state.session_closed is True
        assert _SESSION_MOD._active_incremento_session_state is None
        assert collection_calls == []
        assert hooks.reviewer_will_end == []
        assert hooks.state_did_change == []


class TestReviewTimeTrackerIncrementoSessions:
    def test_profile_scoped_incremento_session_decks_skip_duplicate_pdf_time(self):
        review_time_tracker = _load_review_time_tracker_module()
        get_card = MagicMock(side_effect=AssertionError("should not fetch cards"))
        review_time_tracker.mw = types.SimpleNamespace(
            state="review",
            col=types.SimpleNamespace(
                decks=types.SimpleNamespace(
                    current=lambda: {"name": "Incremento Session (Focus)"}
                ),
                get_card=get_card,
            ),
        )

        review_time_tracker._record_pdf_time(123, 15.0)

        get_card.assert_not_called()

    def test_reader_time_uses_concrete_pdf_and_epub_types(self):
        review_time_tracker = _load_review_time_tracker_module()
        calls = []

        class CapturingStatsManager:
            def __init__(self, *_args, **_kwargs):
                pass

            def record_time_only(self, fake, seconds):
                calls.append((fake.card_type, fake.tag, seconds))

        def make_mw(model_name):
            note = types.SimpleNamespace(mid=99, tags=["reading"])
            card = types.SimpleNamespace(nid=10)
            return types.SimpleNamespace(
                state="overview",
                col=types.SimpleNamespace(
                    decks=types.SimpleNamespace(current=lambda: {"name": "Default"}),
                    get_card=lambda _cid: card,
                    get_note=lambda _nid: note,
                    models=types.SimpleNamespace(get=lambda _mid: {"name": model_name}),
                ),
            )

        review_time_tracker.StatsManager = CapturingStatsManager
        review_time_tracker._runtime_session_time = {"type": {}, "tags": {}}

        review_time_tracker.mw = make_mw("Incremento PDF")
        review_time_tracker._record_pdf_time(101, 5.0)
        review_time_tracker.mw = make_mw("Incremento EPUB")
        review_time_tracker._record_pdf_time(202, 7.0)

        assert calls == [("pdf", "reading", 5.0), ("epub", "reading", 7.0)]
        assert review_time_tracker.get_runtime_session_time()["type"] == {
            "pdf": 5.0,
            "epub": 7.0,
        }
