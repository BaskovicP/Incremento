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


class TestPrepareFilteredReviewDeck:
    def test_preserve_order_uses_due_sort_and_assigns_due_before_rebuild(self, monkeypatch):
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
        cards = {
            101: types.SimpleNamespace(id=101, due=999),
            102: types.SimpleNamespace(id=102, due=999),
            103: types.SimpleNamespace(id=103, due=999),
        }

        fake_sched = types.SimpleNamespace(
            empty_filtered_deck=lambda did: None,
            get_or_create_filtered_deck=lambda did: fdu,
            add_or_update_filtered_deck=lambda fdu_arg: types.SimpleNamespace(id=55),
            rebuild_filtered_deck=lambda did: rebuild_calls.append(
                {
                    "did": did,
                    "dues": {cid: card.due for cid, card in cards.items()},
                    "terms": list(terms),
                }
            ),
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

        assert did == 55
        assert updated_cards == [(101, 0), (102, 1), (103, 2)]
        assert rebuild_calls == [
            {
                "did": 55,
                "dues": {101: 0, 102: 1, 103: 2},
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
