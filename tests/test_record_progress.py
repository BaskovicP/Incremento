"""Tests for bump, bump_tag, record_done in backend/record_progress.py."""
import importlib.util
import os
from datetime import date

_spec = importlib.util.spec_from_file_location(
    "_incremento_record_progress",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "record_progress.py")),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

bump = _mod.bump
bump_tag = _mod.bump_tag
record_done = _mod.record_done


class TestBump:
    def test_increments_existing_key(self):
        d = {"x": 3}
        bump(d, "x")
        assert d["x"] == 4

    def test_initialises_missing_key(self):
        d = {}
        bump(d, "new_key")
        assert d["new_key"] == 1

    def test_custom_increment(self):
        d = {"y": 10}
        bump(d, "y", 5)
        assert d["y"] == 15

    def test_coerces_string_to_int(self):
        d = {"z": "2"}
        bump(d, "z")
        assert d["z"] == 3


class TestBumpTag:
    def test_increments_tag(self):
        d = {"health": 4}
        bump_tag(d, "health")
        assert d["health"] == 5

    def test_initialises_new_tag(self):
        d = {}
        bump_tag(d, "psych")
        assert d["psych"] == 1

    def test_custom_n(self):
        d = {"sci": 0}
        bump_tag(d, "sci", 3)
        assert d["sci"] == 3


class TestRecordDone:
    def _today(self):
        return date.today().isoformat()

    def test_creates_daily_and_lifetime_keys(self):
        stats = {}
        record_done(stats, card_type="topic", pick_kind="random", subject_tags=[])
        assert "daily" in stats
        assert "lifetime" in stats

    def test_daily_keyed_by_today(self):
        stats = {}
        record_done(stats, card_type="topic", pick_kind="random", subject_tags=[])
        assert self._today() in stats["daily"]

    def test_increments_card_type_in_lifetime(self):
        stats = {}
        record_done(stats, card_type="topic", pick_kind="random", subject_tags=[])
        assert stats["lifetime"]["topic"] == 1

    def test_increments_pick_kind_in_lifetime(self):
        stats = {}
        record_done(stats, card_type="item", pick_kind="priority", subject_tags=[])
        assert stats["lifetime"]["priority"] == 1

    def test_increments_card_type_in_daily(self):
        stats = {}
        record_done(stats, card_type="topic", pick_kind="random", subject_tags=[])
        assert stats["daily"][self._today()]["topic"] == 1

    def test_increments_pick_kind_in_daily(self):
        stats = {}
        record_done(stats, card_type="topic", pick_kind="random", subject_tags=[])
        assert stats["daily"][self._today()]["random"] == 1

    def test_tags_tracked_in_lifetime(self):
        stats = {}
        record_done(stats, card_type="topic", pick_kind="random", subject_tags=["health", "psych"])
        assert stats["lifetime"]["by_tag"]["topic"]["health"] == 1
        assert stats["lifetime"]["by_tag"]["topic"]["psych"] == 1

    def test_tags_tracked_in_daily(self):
        stats = {}
        record_done(stats, card_type="item", pick_kind="random", subject_tags=["math"])
        assert stats["daily"][self._today()]["by_tag"]["item"]["math"] == 1

    def test_no_tags_leaves_by_tag_empty(self):
        stats = {}
        record_done(stats, card_type="topic", pick_kind="random", subject_tags=[])
        assert stats["lifetime"]["by_tag"]["topic"] == {}

    def test_accumulates_multiple_calls(self):
        stats = {}
        for _ in range(3):
            record_done(stats, card_type="topic", pick_kind="random", subject_tags=[])
        assert stats["lifetime"]["topic"] == 3
        assert stats["daily"][self._today()]["topic"] == 3

    def test_preserves_existing_stats(self):
        stats = {"lifetime": {"item": 10}}
        record_done(stats, card_type="topic", pick_kind="priority", subject_tags=[])
        assert stats["lifetime"]["item"] == 10
        assert stats["lifetime"]["topic"] == 1
