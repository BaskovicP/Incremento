"""Tests for StatsManager in utils/statistics.py.

Imports the module via importlib to avoid shadowing the stdlib `statistics` module.
No Anki mocking needed — statistics.py has no Anki imports.
"""
import importlib.util
import json
import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest

# Load the module by file path to sidestep stdlib `statistics` name collision
_spec = importlib.util.spec_from_file_location(
    "_incremento_statistics",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "utils", "statistics.py")),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

StatsManager = _mod.StatsManager
_empty = _mod._empty
_today = _mod._today
_effective_date = _mod._effective_date
_is_valid_counts_block = _mod._is_valid_counts_block


def make_result(card="fake_card_id", card_type="topics", tag="health", mode="random"):
    r = MagicMock()
    r.card = card
    r.card_type = card_type
    r.tag = tag
    r.mode = mode
    return r


class TestStatsManagerInit:
    def test_empty_start(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        assert sm.session == _empty()
        assert sm.daily == _empty()
        assert sm.lifetime == _empty()

    def test_loads_valid_lifetime(self, tmp_path):
        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        lifetime = {"type": {"topics": 3}, "tags": {"health": 1}, "mode": {"random": 2}}
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": lifetime,
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path))
        assert sm.lifetime == lifetime

    def test_resets_on_old_schema(self, tmp_path):
        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        old_data = {
            "lifetime": {"topic": 0, "item": 0, "priority": 0, "random": 0},
            "daily": {},
            "last_reset": None,
        }
        stats_file.write_text(json.dumps(old_data), encoding="utf-8")

        sm = StatsManager(str(tmp_path))
        assert sm.lifetime == _empty()
        assert sm.daily == _empty()

    def test_loads_todays_daily(self, tmp_path):
        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        today_counts = {"type": {"items": 2}, "tags": {}, "mode": {"priority": 1}}
        data = {
            "daily": {"date": _today(), "counts": today_counts},
            "lifetime": _empty(),
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path))
        assert sm.daily == today_counts

    def test_resets_daily_on_date_mismatch(self, tmp_path):
        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        yesterday_counts = {"type": {"topics": 5}, "tags": {"psych": 2}, "mode": {"random": 3}}
        data = {
            "daily": {"date": "2000-01-01", "counts": yesterday_counts},
            "lifetime": _empty(),
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path))
        assert sm.daily == _empty()


class TestCountsFor:
    def test_returns_session(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        assert sm.counts_for("session") is sm.session

    def test_returns_daily(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        assert sm.counts_for("daily") is sm.daily

    def test_returns_lifetime(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        assert sm.counts_for("lifetime") is sm.lifetime

    def test_raises_on_unknown_scope(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        with pytest.raises(ValueError, match="scope"):
            sm.counts_for("unknown")

    def test_mutation_via_reference(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        counts = sm.counts_for("session")
        counts["type"]["topics"] = 7
        assert sm.session["type"]["topics"] == 7


class TestRecord:
    def test_does_nothing_when_card_is_none(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        result = make_result(card=None)
        sm.record(result, "session")

        assert sm.session == _empty()
        assert sm.daily == _empty()
        assert sm.lifetime == _empty()
        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        assert not stats_file.exists()

    def test_updates_non_scheduled_scopes(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        result = make_result(card_type="topics", tag="health", mode="random")
        sm.record(result, "session")

        # session (scheduled) must NOT be updated
        assert sm.session == _empty()
        # daily and lifetime must be updated
        assert sm.daily["type"] == {"topics": 1}
        assert sm.daily["tags"] == {"health": 1}
        assert sm.daily["mode"] == {"random": 1}
        assert sm.lifetime["type"] == {"topics": 1}
        assert sm.lifetime["tags"] == {"health": 1}
        assert sm.lifetime["mode"] == {"random": 1}

    def test_does_not_touch_tags_when_tag_is_none(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        result = make_result(card_type="items", tag=None, mode="priority")
        sm.record(result, "session")

        assert sm.daily["tags"] == {}
        assert sm.lifetime["tags"] == {}

    def test_saves_to_disk(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        result = make_result(card_type="topics", tag="health", mode="random")
        sm.record(result, "session")

        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        assert stats_file.exists()
        data = json.loads(stats_file.read_text(encoding="utf-8"))
        assert data["lifetime"]["type"] == {"topics": 1}
        assert data["daily"]["counts"]["type"] == {"topics": 1}

    def test_accumulates_multiple_records(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        sm.record(make_result(card_type="topics", tag="health", mode="random"), "session")
        sm.record(make_result(card_type="topics", tag="psych", mode="priority"), "session")

        assert sm.daily["type"] == {"topics": 2}
        assert sm.daily["tags"] == {"health": 1, "psych": 1}
        assert sm.daily["mode"] == {"random": 1, "priority": 1}


class TestSave:
    def test_written_json_matches_schema(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        sm.lifetime["type"]["topics"] = 5
        sm._save()

        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        data = json.loads(stats_file.read_text(encoding="utf-8"))
        assert "daily" in data
        assert "lifetime" in data
        assert "date" in data["daily"]
        assert "counts" in data["daily"]
        assert data["daily"]["counts"] == _empty()
        assert data["lifetime"]["type"] == {"topics": 5}

    def test_session_not_in_file(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        sm.session["type"]["items"] = 99
        sm._save()

        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        data = json.loads(stats_file.read_text(encoding="utf-8"))
        assert "session" not in data

    def test_atomic_write(self, tmp_path):
        sm = StatsManager(str(tmp_path))
        sm._save()

        user_files = tmp_path / "user_files"
        tmp_files = list(user_files.glob("*.tmp"))
        assert tmp_files == []


class TestEffectiveDate:
    def test_midnight_boundary_returns_today(self):
        """With 00:00 boundary, effective date always equals calendar date."""
        result = _effective_date("00:00")
        assert result == _today()

    def test_boundary_after_current_time_gives_yesterday(self, monkeypatch):
        """If current time is before the boundary, logical date is yesterday."""
        # Freeze 'now' to 03:00
        fixed = datetime(2026, 3, 21, 3, 0)
        monkeypatch.setattr(_mod, "datetime", type("_DT", (), {
            "now": staticmethod(lambda: fixed),
            "date": datetime.date,
        })())
        result = _effective_date("04:00")
        assert result == "2026-03-20"  # yesterday

    def test_boundary_before_current_time_gives_today(self, monkeypatch):
        """If current time is at or after the boundary, logical date is today."""
        fixed = datetime(2026, 3, 21, 5, 0)
        monkeypatch.setattr(_mod, "datetime", type("_DT", (), {
            "now": staticmethod(lambda: fixed),
            "date": datetime.date,
        })())
        result = _effective_date("04:00")
        assert result == "2026-03-21"

    def test_stats_manager_uses_day_end_time(self, tmp_path, monkeypatch):
        """StatsManager with day_end='04:00' at 03:00 loads 'yesterday' as today."""
        fixed = datetime(2026, 3, 21, 3, 0)
        monkeypatch.setattr(_mod, "datetime", type("_DT", (), {
            "now": staticmethod(lambda: fixed),
            "date": datetime.date,
        })())
        stats_file = tmp_path / "user_files" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        yesterday_counts = {"type": {"topics": 3}, "tags": {}, "mode": {"random": 2}}
        data = {
            "daily": {"date": "2026-03-20", "counts": yesterday_counts},
            "lifetime": _empty(),
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path), day_end_time="04:00")
        # At 03:00 with 04:00 boundary, logical date is 2026-03-20 → loads yesterday's counts
        assert sm.daily == yesterday_counts
