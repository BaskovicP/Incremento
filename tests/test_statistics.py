"""Tests for StatsManager in backend/statistics.py.

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
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend", "statistics.py")),
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
        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.session == _empty()
        assert sm.daily == _empty()
        assert sm.lifetime == _empty()

    def test_loads_valid_lifetime(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        lifetime = {"type": {"topics": 3}, "tags": {"health": 1}, "mode": {"random": 2}}
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": lifetime,
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.lifetime == lifetime

    def test_resets_on_old_schema(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        old_data = {
            "lifetime": {"topic": 0, "item": 0, "priority": 0, "random": 0},
            "daily": {},
            "last_reset": None,
        }
        stats_file.write_text(json.dumps(old_data), encoding="utf-8")

        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.lifetime == _empty()
        assert sm.daily == _empty()

    def test_loads_todays_daily(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        today_counts = {"type": {"items": 2}, "tags": {}, "mode": {"priority": 1}}
        data = {
            "daily": {"date": _today(), "counts": today_counts},
            "lifetime": _empty(),
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.daily == today_counts

    def test_resets_daily_on_date_mismatch(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        yesterday_counts = {"type": {"topics": 5}, "tags": {"psych": 2}, "mode": {"random": 3}}
        data = {
            "daily": {"date": "2000-01-01", "counts": yesterday_counts},
            "lifetime": _empty(),
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.daily == _empty()


class TestCountsFor:
    def test_returns_session(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.counts_for("session") is sm.session

    def test_returns_daily(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.counts_for("daily") is sm.daily

    def test_returns_lifetime(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.counts_for("lifetime") is sm.lifetime

    def test_raises_on_unknown_scope(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        with pytest.raises(ValueError, match="scope"):
            sm.counts_for("unknown")

    def test_mutation_via_reference(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        counts = sm.counts_for("session")
        counts["type"]["topics"] = 7
        assert sm.session["type"]["topics"] == 7


class TestRecord:
    def test_does_nothing_when_card_is_none(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card=None)
        sm.record(result, "session")

        assert sm.session == _empty()
        assert sm.daily == _empty()
        assert sm.lifetime == _empty()
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        assert not stats_file.exists()

    def test_updates_non_scheduled_scopes(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
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
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card_type="items", tag=None, mode="priority")
        sm.record(result, "session")

        assert sm.daily["tags"] == {}
        assert sm.lifetime["tags"] == {}

    def test_saves_to_disk(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card_type="topics", tag="health", mode="random")
        sm.record(result, "session")

        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        assert stats_file.exists()
        data = json.loads(stats_file.read_text(encoding="utf-8"))
        assert data["lifetime"]["type"] == {"topics": 1}
        assert data["daily"]["counts"]["type"] == {"topics": 1}

    def test_accumulates_multiple_records(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        sm.record(make_result(card_type="topics", tag="health", mode="random"), "session")
        sm.record(make_result(card_type="topics", tag="psych", mode="priority"), "session")

        assert sm.daily["type"] == {"topics": 2}
        assert sm.daily["tags"] == {"health": 1, "psych": 1}
        assert sm.daily["mode"] == {"random": 1, "priority": 1}


class TestSave:
    def test_written_json_matches_schema(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        sm.lifetime["type"]["topics"] = 5
        sm._save()

        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        data = json.loads(stats_file.read_text(encoding="utf-8"))
        assert "daily" in data
        assert "lifetime" in data
        assert "date" in data["daily"]
        assert "counts" in data["daily"]
        assert data["daily"]["counts"] == _empty()
        assert data["lifetime"]["type"] == {"topics": 5}

    def test_session_not_in_file(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        sm.session["type"]["items"] = 99
        sm._save()

        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        data = json.loads(stats_file.read_text(encoding="utf-8"))
        assert "session" not in data

    def test_atomic_write(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        sm._save()

        user_files = tmp_path / "user_files" / "TestProfile"
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
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        yesterday_counts = {"type": {"topics": 3}, "tags": {}, "mode": {"random": 2}}
        data = {
            "daily": {"date": "2026-03-20", "counts": yesterday_counts},
            "lifetime": _empty(),
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")

        sm = StatsManager(str(tmp_path), "TestProfile", day_end_time="04:00")
        # At 03:00 with 04:00 boundary, logical date is 2026-03-20 → loads yesterday's counts
        assert sm.daily == yesterday_counts


# ── load_stats / save_stats ───────────────────────────────────────────────────

load_stats = _mod.load_stats
save_stats = _mod.save_stats
delete_daily_stats = _mod.delete_daily_stats
delete_lifetime_stats = _mod.delete_lifetime_stats
delete_all_stats = _mod.delete_all_stats


class TestLoadStats:
    def test_returns_empty_dict_when_no_file_or_db(self, tmp_path, monkeypatch):
        """When no JSON file and DB query fails, return {}."""
        def failing_conn(addon_dir):
            raise Exception("no db")
        monkeypatch.setattr(_mod, "get_connection", failing_conn)
        result = load_stats(str(tmp_path), "TestProfile")
        assert result == {}

    def test_loads_from_db_when_no_json_file(self, tmp_path):
        """When no JSON file exists, fall back to reading the SQLite DB."""
        import json as _json
        # Seed the DB directly via the real get_connection
        conn = _mod.get_connection(str(tmp_path), "TestProfile")
        conn.execute(
            "INSERT OR REPLACE INTO stats (scope, date, data) VALUES (?, ?, ?)",
            ("daily", "2026-01-01", _json.dumps({"type": {}, "tags": {}, "mode": {}})),
        )
        conn.execute(
            "INSERT OR REPLACE INTO stats (scope, date, data) VALUES (?, ?, ?)",
            ("lifetime", None, _json.dumps({"type": {}, "tags": {}, "mode": {}})),
        )
        conn.commit()
        # No JSON file exists — load_stats should fall back to DB
        result = load_stats(str(tmp_path), "TestProfile")
        assert "daily" in result or "lifetime" in result  # something was read

    def test_returns_data_from_file(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        data = {"lifetime": _empty(), "daily": {"date": _today(), "counts": _empty()}}
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        result = load_stats(str(tmp_path), "TestProfile")
        assert "lifetime" in result

    def test_returns_empty_on_corrupt_json(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        stats_file.write_text("not valid json{{{{", encoding="utf-8")
        result = load_stats(str(tmp_path), "TestProfile")
        assert result == {}

    def test_returns_empty_when_file_is_not_dict(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        stats_file.write_text("[1, 2, 3]", encoding="utf-8")
        result = load_stats(str(tmp_path), "TestProfile")
        assert result == {}


class TestDeleteStats:
    def test_delete_daily_removes_daily_key(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card_type="topics", tag="health", mode="random")
        sm.record(result, "session")

        delete_daily_stats(str(tmp_path), "TestProfile")
        data = json.loads((tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json").read_text())
        assert "daily" not in data

    def test_delete_lifetime_removes_lifetime_key(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card_type="topics", tag="health", mode="random")
        sm.record(result, "session")

        delete_lifetime_stats(str(tmp_path), "TestProfile")
        data = json.loads((tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json").read_text())
        assert "lifetime" not in data

    def test_delete_all_removes_file(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card_type="topics", tag="health", mode="random")
        sm.record(result, "session")

        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        assert stats_file.exists()
        delete_all_stats(str(tmp_path), "TestProfile")
        assert not stats_file.exists()

    def test_delete_daily_noop_when_no_file(self, tmp_path):
        """delete_daily_stats should not raise when no stats file exists."""
        delete_daily_stats(str(tmp_path), "TestProfile")  # should not raise

    def test_delete_lifetime_noop_when_no_file(self, tmp_path):
        delete_lifetime_stats(str(tmp_path), "TestProfile")  # should not raise

    def test_delete_all_noop_when_no_file(self, tmp_path):
        delete_all_stats(str(tmp_path), "TestProfile")  # should not raise

    def test_delete_daily_removes_daily_time_entry(self, tmp_path):
        """Deleting daily stats also removes the daily time entry from the time block."""
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        lt_time = {"type": {"topics": 5.0}, "tags": {}}
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": _empty(),
            "time": {
                "daily": {"date": _today(), "seconds": {"type": {"topics": 2.0}, "tags": {}}},
                "lifetime": lt_time,
            },
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        delete_daily_stats(str(tmp_path), "TestProfile")
        result = json.loads(stats_file.read_text())
        # daily time should be gone; lifetime time should remain
        assert "daily" not in result.get("time", {})
        assert result.get("time", {}).get("lifetime") == lt_time

    def test_delete_lifetime_removes_lifetime_time_entry(self, tmp_path):
        """Deleting lifetime stats also removes the lifetime time entry."""
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        daily_time = {"date": _today(), "seconds": {"type": {"topics": 1.0}, "tags": {}}}
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": _empty(),
            "time": {
                "daily": daily_time,
                "lifetime": {"type": {"topics": 10.0}, "tags": {}},
            },
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        delete_lifetime_stats(str(tmp_path), "TestProfile")
        result = json.loads(stats_file.read_text())
        assert "lifetime" not in result.get("time", {})
        assert result.get("time", {}).get("daily") == daily_time

    def test_delete_daily_exercises_empty_time_cleanup(self, tmp_path):
        """Exercise the branch where deleting daily leaves time dict empty (line 129)."""
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": _empty(),
            "time": {"daily": {"date": _today(), "seconds": {"type": {}, "tags": {}}}},
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        delete_daily_stats(str(tmp_path), "TestProfile")  # exercises `if not stats["time"]: del stats["time"]`

    def test_delete_lifetime_exercises_empty_time_cleanup(self, tmp_path):
        """Exercise the branch where deleting lifetime leaves time dict empty (line 149)."""
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": _empty(),
            "time": {"lifetime": {"type": {}, "tags": {}}},
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        delete_lifetime_stats(str(tmp_path), "TestProfile")  # exercises `if not stats["time"]: del stats["time"]`

    def test_save_stats_handles_db_failure_gracefully(self, tmp_path, monkeypatch):
        """save_stats DB write is best-effort; exceptions must be swallowed (lines 117-118)."""
        monkeypatch.setattr(_mod, "get_connection", lambda _: (_ for _ in ()).throw(Exception("DB gone")))
        # Should not raise; JSON file should still be written
        save_stats(str(tmp_path), "TestProfile", {"lifetime": _empty()})
        assert (tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json").exists()

    def test_delete_functions_handle_db_error_gracefully(self, tmp_path, monkeypatch):
        """DB operations in delete functions should be best-effort (no raise)."""
        def failing_conn(addon_dir):
            raise Exception("DB gone")
        monkeypatch.setattr(_mod, "get_connection", failing_conn)
        # Pre-populate file so the JSON path runs before DB
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        data = {"daily": {"date": _today(), "counts": _empty()}, "lifetime": _empty()}
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        # Should not raise even if DB fails
        delete_daily_stats(str(tmp_path), "TestProfile")
        delete_lifetime_stats(str(tmp_path), "TestProfile")
        delete_all_stats(str(tmp_path), "TestProfile")


class TestRecordTimeOnly:
    def test_records_time_for_valid_card(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card_type="topics", tag="health", mode="random")
        result.card = 42
        result.review_seconds = 0  # not used by record_time_only
        sm.record_time_only(result, 30.0)
        assert sm.daily_time["type"].get("topics", 0) == 30.0
        assert sm.lifetime_time["type"].get("topics", 0) == 30.0
        assert sm.session_time["type"].get("topics", 0) == 30.0

    def test_does_nothing_when_card_is_none(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card=None)
        sm.record_time_only(result, 30.0)
        assert sm.session_time == {"type": {}, "tags": {}}

    def test_does_nothing_for_zero_seconds(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result()
        sm.record_time_only(result, 0.0)
        assert sm.session_time == {"type": {}, "tags": {}}

    def test_saves_to_disk(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result()
        sm.record_time_only(result, 15.0)
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        assert stats_file.exists()

    def test_accumulates_time(self, tmp_path):
        sm = StatsManager(str(tmp_path), "TestProfile")
        result = make_result(card_type="topics", tag="health", mode="random")
        sm.record_time_only(result, 10.0)
        sm.record_time_only(result, 5.0)
        assert sm.lifetime_time["type"]["topics"] == 15.0


class TestDailyTimeLoading:
    def test_loads_todays_daily_time(self, tmp_path):
        """If the file contains today's daily_time, it should be loaded."""
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        time_block = {"type": {"topics": 120.0}, "tags": {"health": 60.0}}
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": _empty(),
            "time": {
                "daily": {"date": _today(), "seconds": time_block},
                "lifetime": {"type": {}, "tags": {}},
            },
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.daily_time == time_block

    def test_resets_daily_time_on_date_mismatch(self, tmp_path):
        stats_file = tmp_path / "user_files" / "TestProfile" / "custom_learn_stats.json"
        stats_file.parent.mkdir(parents=True)
        data = {
            "daily": {"date": _today(), "counts": _empty()},
            "lifetime": _empty(),
            "time": {
                "daily": {"date": "2000-01-01", "seconds": {"type": {"topics": 5}, "tags": {}}},
                "lifetime": {"type": {}, "tags": {}},
            },
        }
        stats_file.write_text(json.dumps(data), encoding="utf-8")
        sm = StatsManager(str(tmp_path), "TestProfile")
        assert sm.daily_time == {"type": {}, "tags": {}}
