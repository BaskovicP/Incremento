import json
import math
import os
import threading
import time
from datetime import datetime, timedelta

try:
    from .db import get_connection
    from .paths import get_stats_path as _get_stats_path
except ImportError:
    from db import get_connection  # test environment (backend/ on sys.path)
    from paths import get_stats_path as _get_stats_path


_STATS_LOCKS_GUARD = threading.Lock()
_STATS_LOCKS: dict[str, threading.RLock] = {}


def _stats_lock(addon_dir: str, profile: str) -> threading.RLock:
    key = str(_get_stats_path(addon_dir, profile).resolve())
    with _STATS_LOCKS_GUARD:
        lock = _STATS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _STATS_LOCKS[key] = lock
        return lock


def _empty() -> dict:
    return {"type": {}, "tags": {}, "mode": {}}


def _empty_time() -> dict:
    return {"type": {}, "tags": {}}


def _clean_stat_key(key) -> str | None:
    try:
        text = str(key).strip()
    except Exception:
        return None
    if not text or text.startswith("__"):
        return None
    return text


def _coerce_nonnegative_number(value, *, integer: bool):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    if integer:
        return int(number)
    return float(number)


def _normalize_number_map(raw, *, integer: bool) -> dict:
    if not isinstance(raw, dict):
        return {}
    clean: dict = {}
    for key, value in raw.items():
        clean_key = _clean_stat_key(key)
        if clean_key is None:
            continue
        clean_value = _coerce_nonnegative_number(value, integer=integer)
        if clean_value is None:
            continue
        clean[clean_key] = clean.get(clean_key, 0) + clean_value
    return clean


def _normalize_counts_block(raw) -> dict:
    if not isinstance(raw, dict):
        return _empty()
    return {
        "type": _normalize_number_map(raw.get("type"), integer=True),
        "tags": _normalize_number_map(raw.get("tags"), integer=True),
        "mode": _normalize_number_map(raw.get("mode"), integer=True),
    }


def _normalize_time_block(raw) -> dict:
    if not isinstance(raw, dict):
        return _empty_time()
    return {
        "type": _normalize_number_map(raw.get("type"), integer=False),
        "tags": _normalize_number_map(raw.get("tags"), integer=False),
    }


def _normalize_stats(raw) -> dict:
    if not isinstance(raw, dict):
        return {}

    result: dict = {}

    if "daily" in raw:
        daily_raw = raw.get("daily")
        if isinstance(daily_raw, dict):
            result["daily"] = {
                "date": str(daily_raw.get("date") or ""),
                "counts": _normalize_counts_block(daily_raw.get("counts")),
            }
        else:
            result["daily"] = {"date": "", "counts": _empty()}

    if "lifetime" in raw:
        result["lifetime"] = _normalize_counts_block(raw.get("lifetime"))

    if "time" in raw:
        time_raw = raw.get("time")
        time_result: dict = {}
        if isinstance(time_raw, dict):
            if "daily" in time_raw:
                daily_time_raw = time_raw.get("daily")
                if isinstance(daily_time_raw, dict):
                    time_result["daily"] = {
                        "date": str(daily_time_raw.get("date") or ""),
                        "seconds": _normalize_time_block(
                            daily_time_raw.get("seconds")
                        ),
                    }
                else:
                    time_result["daily"] = {"date": "", "seconds": _empty_time()}
            if "lifetime" in time_raw:
                time_result["lifetime"] = _normalize_time_block(
                    time_raw.get("lifetime")
                )
        if time_result:
            result["time"] = time_result

    return result


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _effective_date(day_end: str = "04:00") -> str:
    """Return the logical date string, honouring a non-midnight day boundary.

    If day_end is "04:00" and the current time is 03:30, the logical date is
    yesterday — the user's 'day' hasn't ended yet.
    """
    now = datetime.now()
    h, m = map(int, day_end.split(":"))
    boundary_minutes = h * 60 + m
    current_minutes = now.hour * 60 + now.minute
    if current_minutes < boundary_minutes:
        return (now.date() - timedelta(days=1)).isoformat()
    return now.date().isoformat()


def _is_valid_counts_block(d) -> bool:
    return (
        isinstance(d, dict)
        and isinstance(d.get("type"), dict)
        and isinstance(d.get("tags"), dict)
        and isinstance(d.get("mode"), dict)
    )


def _is_valid_time_block(d) -> bool:
    return (
        isinstance(d, dict)
        and isinstance(d.get("type"), dict)
        and isinstance(d.get("tags"), dict)
    )


def load_stats(addon_dir: str, profile: str) -> dict:
    with _stats_lock(addon_dir, profile):
        return _load_stats_unlocked(addon_dir, profile)


def _load_stats_unlocked(addon_dir: str, profile: str) -> dict:
    path = str(_get_stats_path(addon_dir, profile))
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _normalize_stats(data)
        except Exception:
            return {}

    # Backward-compatible fallback for users that only have DB-backed stats.
    try:
        rows = (
            get_connection(addon_dir, profile)
            .execute("SELECT scope, date, data FROM stats")
            .fetchall()
        )
    except Exception:
        return {}

    result: dict = {}
    for scope, date, data in rows:
        try:
            parsed = json.loads(data)
        except Exception:
            parsed = {}
        if scope == "daily":
            result["daily"] = {"date": date, "counts": parsed}
        elif scope == "time":
            result["time"] = parsed if isinstance(parsed, dict) else {}
        else:
            result[scope] = parsed
    return _normalize_stats(result)


def save_stats(addon_dir: str, profile: str, stats: dict) -> None:
    with _stats_lock(addon_dir, profile):
        _save_stats_unlocked(addon_dir, profile, stats)


def _save_stats_unlocked(addon_dir: str, profile: str, stats: dict) -> None:
    stats = _normalize_stats(stats)
    path = str(_get_stats_path(addon_dir, profile))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)
    os.replace(tmp, path)

    # Keep DB export path functional (best effort).
    try:
        conn = get_connection(addon_dir, profile)
        if "daily" in stats:
            d = stats["daily"]
            conn.execute(
                "INSERT OR REPLACE INTO stats (scope, date, data) VALUES (?, ?, ?)",
                ("daily", d.get("date"), json.dumps(d.get("counts", {}))),
            )
        else:
            conn.execute("DELETE FROM stats WHERE scope = 'daily'")

        if "lifetime" in stats:
            conn.execute(
                "INSERT OR REPLACE INTO stats (scope, date, data) VALUES (?, ?, ?)",
                ("lifetime", None, json.dumps(stats["lifetime"])),
            )
        else:
            conn.execute("DELETE FROM stats WHERE scope = 'lifetime'")

        if "time" in stats:
            conn.execute(
                "INSERT OR REPLACE INTO stats (scope, date, data) VALUES (?, ?, ?)",
                ("time", None, json.dumps(stats["time"])),
            )
        else:
            conn.execute("DELETE FROM stats WHERE scope = 'time'")
        conn.commit()
    except Exception:
        pass


def mutate_stats(addon_dir: str, profile: str, mutator) -> dict:
    """Atomically read, mutate and persist one profile's aggregate stats."""
    with _stats_lock(addon_dir, profile):
        current = _load_stats_unlocked(addon_dir, profile)
        updated = mutator(_normalize_stats(current))
        normalized = _normalize_stats(updated)
        _save_stats_unlocked(addon_dir, profile, normalized)
        return normalized


def _increment_map(block: dict, group: str, key: str | None, amount) -> None:
    if key is None:
        return
    target = block.setdefault(group, {})
    target[key] = target.get(key, 0) + amount


def _record_persistent_delta(
    addon_dir: str,
    profile: str,
    *,
    day_end_time: str,
    result,
    include_count: bool,
    seconds: float,
) -> dict:
    logical_date = _effective_date(day_end_time)

    def apply_delta(stats: dict) -> dict:
        daily_raw = stats.get("daily") if isinstance(stats.get("daily"), dict) else {}
        if daily_raw.get("date") == logical_date:
            daily = _normalize_counts_block(daily_raw.get("counts"))
        else:
            daily = _empty()
        lifetime = _normalize_counts_block(stats.get("lifetime"))

        time_raw = stats.get("time") if isinstance(stats.get("time"), dict) else {}
        daily_time_raw = time_raw.get("daily") if isinstance(time_raw.get("daily"), dict) else {}
        if daily_time_raw.get("date") == logical_date:
            daily_time = _normalize_time_block(daily_time_raw.get("seconds"))
        else:
            daily_time = _empty_time()
        lifetime_time = _normalize_time_block(time_raw.get("lifetime"))

        if include_count:
            for block in (daily, lifetime):
                _increment_map(block, "type", result.card_type, 1)
                _increment_map(block, "mode", result.mode, 1)
                _increment_map(block, "tags", result.tag, 1)
        if seconds > 0:
            for block in (daily_time, lifetime_time):
                _increment_map(block, "type", result.card_type, seconds)
                _increment_map(block, "tags", result.tag, seconds)

        return {
            "daily": {"date": logical_date, "counts": daily},
            "lifetime": lifetime,
            "time": {
                "daily": {"date": logical_date, "seconds": daily_time},
                "lifetime": lifetime_time,
            },
        }

    return mutate_stats(addon_dir, profile, apply_delta)


def delete_daily_stats(addon_dir: str, profile: str) -> None:
    """Remove today's statistics."""
    def remove_daily(stats: dict) -> dict:
        stats.pop("daily", None)
        if isinstance(stats.get("time"), dict):
            stats["time"].pop("daily", None)
            if not stats["time"]:
                stats.pop("time", None)
        return stats

    mutate_stats(addon_dir, profile, remove_daily)


def delete_lifetime_stats(addon_dir: str, profile: str) -> None:
    """Remove lifetime statistics."""
    def remove_lifetime(stats: dict) -> dict:
        stats.pop("lifetime", None)
        if isinstance(stats.get("time"), dict):
            stats["time"].pop("lifetime", None)
            if not stats["time"]:
                stats.pop("time", None)
        return stats

    mutate_stats(addon_dir, profile, remove_lifetime)


def delete_all_stats(addon_dir: str, profile: str) -> None:
    """Delete all statistics data."""
    with _stats_lock(addon_dir, profile):
        path = str(_get_stats_path(addon_dir, profile))
        if os.path.exists(path):
            os.remove(path)

        try:
            conn = get_connection(addon_dir, profile)
            conn.execute("DELETE FROM stats")
            conn.commit()
        except Exception:
            pass


class StatsManager:
    def __init__(self, addon_dir: str, profile: str, day_end_time: str = "04:00"):
        self._addon_dir = addon_dir
        self._profile = profile
        self._day_end_time = day_end_time
        self.session = _empty()
        self.session_time = _empty_time()

        raw = load_stats(addon_dir, profile)

        self.lifetime = _normalize_counts_block(raw.get("lifetime"))

        daily_raw = raw.get("daily", {})
        if (
            isinstance(daily_raw, dict)
            and daily_raw.get("date") == _effective_date(self._day_end_time)
            and _is_valid_counts_block(daily_raw.get("counts"))
        ):
            self.daily = _normalize_counts_block(daily_raw["counts"])
        else:
            self.daily = _empty()

        raw_time = raw.get("time") if isinstance(raw.get("time"), dict) else {}

        daily_time_raw = raw_time.get("daily") if isinstance(raw_time, dict) else {}
        if (
            isinstance(daily_time_raw, dict)
            and daily_time_raw.get("date") == _effective_date(self._day_end_time)
            and _is_valid_time_block(daily_time_raw.get("seconds"))
        ):
            self.daily_time = _normalize_time_block(daily_time_raw["seconds"])
        else:
            self.daily_time = _empty_time()

        lt_time = raw_time.get("lifetime") if isinstance(raw_time, dict) else None
        self.lifetime_time = _normalize_time_block(lt_time)

    def counts_for(self, scope: str) -> dict:
        """Return a LIVE reference to the counts dict for *scope*.

        IMPORTANT — the caller must mutate the returned dict in-place to drive
        soft_pick debt.  Do NOT store a copy; debt tracking depends on this
        reference pointing to the same object that record() reads from.
        """
        if scope == "session":
            return self.session
        if scope == "daily":
            return self.daily
        if scope == "lifetime":
            return self.lifetime
        raise ValueError(
            f"Unknown scope: {scope!r}. Must be 'session', 'daily', or 'lifetime'."
        )

    def record(self, result, scheduled_scope: str) -> None:
        if result.card is None:
            return

        # Session counts are the scheduler's live selection/debt state and are
        # intentionally not incremented here. Persistent counters are updated
        # from the latest shared state under the profile stats lock.

        seconds = max(0.0, float(getattr(result, "review_seconds", 0.0) or 0.0))
        if seconds > 0:
            self._record_session_time(result, seconds)

        persisted = _record_persistent_delta(
            self._addon_dir,
            self._profile,
            day_end_time=self._day_end_time,
            result=result,
            include_count=True,
            seconds=seconds,
        )
        self._load_persisted_state(persisted)

    def _record_session_time(self, result, seconds: float) -> None:
        self.session_time["type"][result.card_type] = (
            self.session_time["type"].get(result.card_type, 0.0) + seconds
        )
        if result.tag is not None:
            self.session_time["tags"][result.tag] = (
                self.session_time["tags"].get(result.tag, 0.0) + seconds
            )

    def _load_persisted_state(self, raw: dict) -> None:
        daily_raw = raw.get("daily") if isinstance(raw.get("daily"), dict) else {}
        self.daily = _normalize_counts_block(daily_raw.get("counts"))
        self.lifetime = _normalize_counts_block(raw.get("lifetime"))
        time_raw = raw.get("time") if isinstance(raw.get("time"), dict) else {}
        daily_time_raw = time_raw.get("daily") if isinstance(time_raw.get("daily"), dict) else {}
        self.daily_time = _normalize_time_block(daily_time_raw.get("seconds"))
        self.lifetime_time = _normalize_time_block(time_raw.get("lifetime"))

    def record_time_only(self, result, seconds: float) -> None:
        """Record time without incrementing card/mode/tag counts."""
        if result.card is None:
            return
        seconds = max(0.0, float(seconds or 0.0))
        if seconds <= 0:
            return
        self._record_session_time(result, seconds)
        persisted = _record_persistent_delta(
            self._addon_dir,
            self._profile,
            day_end_time=self._day_end_time,
            result=result,
            include_count=False,
            seconds=seconds,
        )
        self._load_persisted_state(persisted)

    def _save(self) -> None:
        stats = {
            "daily": {
                "date": _effective_date(self._day_end_time),
                "counts": self.daily,
            },
            "lifetime": self.lifetime,
            "time": {
                "daily": {
                    "date": _effective_date(self._day_end_time),
                    "seconds": self.daily_time,
                },
                "lifetime": self.lifetime_time,
            },
        }
        save_stats(self._addon_dir, self._profile, stats)
