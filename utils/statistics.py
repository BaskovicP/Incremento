import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path


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
    current_minutes  = now.hour * 60 + now.minute
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


def _stats_path(addon_dir: str) -> Path:
    path = Path(addon_dir) / "user_files" / "custom_learn_stats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_stats(addon_dir: str) -> dict:
    path = _stats_path(addon_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_stats(addon_dir: str, stats: dict) -> None:
    path = _stats_path(addon_dir)
    tmp = path.with_name(path.name + ".tmp")
    data = json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def delete_daily_stats(addon_dir: str) -> None:
    """Remove today's statistics from disk."""
    raw = load_stats(addon_dir)
    if "daily" not in raw:
        return
    del raw["daily"]
    save_stats(addon_dir, raw)


def delete_lifetime_stats(addon_dir: str) -> None:
    """Remove lifetime statistics from disk."""
    raw = load_stats(addon_dir)
    if "lifetime" not in raw:
        return
    del raw["lifetime"]
    save_stats(addon_dir, raw)


def delete_all_stats(addon_dir: str) -> None:
    """Delete the entire statistics file."""
    path = _stats_path(addon_dir)
    if path.exists():
        path.unlink()


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
            counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
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
