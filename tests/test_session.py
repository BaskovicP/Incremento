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
            update_card=lambda card: updated_cards.append((card.id, card.due)),
        )
        monkeypatch.setattr(_SESSION_MOD, "mw", types.SimpleNamespace(col=fake_col))

        did = _SESSION_MOD._prepare_filtered_review_deck(
            [101, 102, 103],
            deck_name="Incremento Session (Test)",
            preserve_order=True,
        )

        assert did == filtered_deck_id
        assert updated_cards == [(101, 0), (103, 1)]
        assert cards[102].due == -99998
        assert rebuild_calls == [
            {
                "did": filtered_deck_id,
                "dues": {101: 999, 102: 999, 103: 999},
                "terms": [
                    {
                        "search": "cid:101 OR cid:102 OR cid:103",
                        "limit": 3,
                        "order": _SESSION_MOD.DYN_DUE,
                    }
                ],
            }
        ]
        assert _SESSION_MOD.incremento_session_deck_name("Writing") == "Incremento Session (Writing)"

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

    def test_deferred_refill_runs_after_answer_transition(self, monkeypatch):
        callbacks = []
        calls = []
        state = self._make_state(window_size=30)

        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda ms, callback: callbacks.append((ms, callback))),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_maybe_auto_refill_active_session",
            lambda _state: calls.append(_state) or {"live_queue_ids": [1, 2], "new_ids": [3]},
        )

        _SESSION_MOD._schedule_deferred_auto_refill(state, reason="test")

        assert state.refill_retry_pending is True
        assert len(callbacks) == 1
        callbacks[0][1]()
        assert state.refill_retry_pending is False
        assert calls == [state]

    def test_deferred_refill_is_not_queued_twice(self, monkeypatch):
        callbacks = []
        state = self._make_state(window_size=30)

        monkeypatch.setattr(
            _SESSION_MOD,
            "QTimer",
            types.SimpleNamespace(singleShot=lambda ms, callback: callbacks.append((ms, callback))),
        )

        _SESSION_MOD._schedule_deferred_auto_refill(state, reason="first")
        _SESSION_MOD._schedule_deferred_auto_refill(state, reason="second")

        assert len(callbacks) == 1

    def test_answer_recording_runs_before_live_queue_read(self, monkeypatch):
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

        assert calls == ["record", "session_count", "live_queue"]

    def test_cleanup_prefers_live_queue_order(self, monkeypatch):
        rebuilt = []
        state = self._make_state(selected_ids=[1, 2, 3], window_size=3)

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: [3, 1],
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_rebuild_filtered_deck_with_exact_ids",
            lambda deck_name, ordered_ids, preserve_order: rebuilt.append((deck_name, list(ordered_ids), preserve_order)) or True,
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_sync_filtered_deck_by_name",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not use fallback")),
        )

        _SESSION_MOD._sync_session_cleanup_deck(state)

        assert rebuilt == [("Incremento Session", [3, 1], True)]

    def test_cleanup_falls_back_when_live_queue_read_fails(self, monkeypatch):
        fallback = []
        state = self._make_state(selected_ids=[1, 2, 3], window_size=3)
        state.reviewed_ids = {2}

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_sync_filtered_deck_by_name",
            lambda deck_name, selected_ids, preserve_order: fallback.append((deck_name, list(selected_ids), preserve_order)) or True,
        )

        _SESSION_MOD._sync_session_cleanup_deck(state)

        assert fallback == [("Incremento Session", [1, 3], True)]

    def test_cleanup_falls_back_when_live_queue_contains_duplicate_entries(self, monkeypatch):
        fallback = []
        state = self._make_state(selected_ids=[1, 2, 3], window_size=3)
        state.reviewed_ids = {2}

        monkeypatch.setattr(_SESSION_MOD, "_session_deck_id_by_name", lambda _name: 77)
        monkeypatch.setattr(
            _SESSION_MOD,
            "_live_filtered_queue_ids",
            lambda deck_id, fetch_limit, scheduled_ids=None: [3, 3, 1],
        )
        monkeypatch.setattr(
            _SESSION_MOD,
            "_sync_filtered_deck_by_name",
            lambda deck_name, selected_ids, preserve_order: fallback.append((deck_name, list(selected_ids), preserve_order)) or True,
        )

        _SESSION_MOD._sync_session_cleanup_deck(state)

        assert fallback == [("Incremento Session", [1, 3], True)]

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

    def test_answer_recording_does_not_swallow_refill_errors(self, monkeypatch):
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

        try:
            _SESSION_MOD._record_incremento_answer(
                state,
                reviewer=types.SimpleNamespace(),
                card=types.SimpleNamespace(id=1),
            )
            assert False, "Expected refill failure to propagate"
        except RuntimeError as exc:
            assert str(exc) == "refill failed"

        assert stats.record.call_count == 1
        assert 1 in state.reviewed_ids


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
