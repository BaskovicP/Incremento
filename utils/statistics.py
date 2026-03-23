import json
import os
import time
from datetime import datetime, timedelta

try:
    from .db import get_connection
except ImportError:
    from db import get_connection  # test environment (utils/ on sys.path)


def _empty() -> dict:
    return {"type": {}, "tags": {}, "mode": {}}


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _effective_date(day_end: str = "00:00") -> str:
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


def _stats_path(addon_dir: str) -> str:
    return os.path.join(addon_dir, "user_files", "custom_learn_stats.json")


def load_stats(addon_dir: str) -> dict:
    path = _stats_path(addon_dir)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    # Backward-compatible fallback for users that only have DB-backed stats.
    try:
        rows = (
            get_connection(addon_dir)
            .execute("SELECT scope, date, data FROM stats")
            .fetchall()
        )
    except Exception:
        return {}

    result: dict = {}
    for scope, date, data in rows:
        if scope == "daily":
            result["daily"] = {"date": date, "counts": json.loads(data)}
        else:
            result[scope] = json.loads(data)
    return result


def save_stats(addon_dir: str, stats: dict) -> None:
    path = _stats_path(addon_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False)
    os.replace(tmp, path)

    # Keep DB export path functional (best effort).
    try:
        conn = get_connection(addon_dir)
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
        conn.commit()
    except Exception:
        pass


def delete_daily_stats(addon_dir: str) -> None:
    """Remove today's statistics."""
    stats = load_stats(addon_dir)
    if "daily" in stats:
        del stats["daily"]
        save_stats(addon_dir, stats)

    try:
        conn = get_connection(addon_dir)
        conn.execute("DELETE FROM stats WHERE scope = 'daily'")
        conn.commit()
    except Exception:
        pass


def delete_lifetime_stats(addon_dir: str) -> None:
    """Remove lifetime statistics."""
    stats = load_stats(addon_dir)
    if "lifetime" in stats:
        del stats["lifetime"]
        save_stats(addon_dir, stats)

    try:
        conn = get_connection(addon_dir)
        conn.execute("DELETE FROM stats WHERE scope = 'lifetime'")
        conn.commit()
    except Exception:
        pass


def delete_all_stats(addon_dir: str) -> None:
    """Delete all statistics data."""
    path = _stats_path(addon_dir)
    if os.path.exists(path):
        os.remove(path)

    try:
        conn = get_connection(addon_dir)
        conn.execute("DELETE FROM stats")
        conn.commit()
    except Exception:
        pass


class StatsManager:
    def __init__(self, addon_dir: str, day_end_time: str = "00:00"):
        self._addon_dir = addon_dir
        self._day_end_time = day_end_time
        self.session = _empty()

        raw = load_stats(addon_dir)

        lt = raw.get("lifetime")
        self.lifetime = lt if _is_valid_counts_block(lt) else _empty()

        daily_raw = raw.get("daily", {})
        if (
            isinstance(daily_raw, dict)
            and daily_raw.get("date") == _effective_date(self._day_end_time)
            and _is_valid_counts_block(daily_raw.get("counts"))
        ):
            self.daily = daily_raw["counts"]
        else:
            self.daily = _empty()

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

        for scope_name in ("session", "daily", "lifetime"):
            if scope_name == scheduled_scope:
                continue
            counts = self.counts_for(scope_name)
            counts["type"][result.card_type] = (
                counts["type"].get(result.card_type, 0) + 1
            )
            counts["mode"][result.mode] = counts["mode"].get(result.mode, 0) + 1
            if result.tag is not None:
                counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1

        self._save()

    def _save(self) -> None:
        stats = {
            "daily": {
                "date": _effective_date(self._day_end_time),
                "counts": self.daily,
            },
            "lifetime": self.lifetime,
        }
        save_stats(self._addon_dir, stats)
