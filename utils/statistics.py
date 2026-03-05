import json
import os
import time
from pathlib import Path


def _empty() -> dict:
    return {"type": {}, "tags": {}, "mode": {}}


def _today() -> str:
    return time.strftime("%Y-%m-%d")


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


class StatsManager:
    def __init__(self, addon_dir: str):
        self._addon_dir = addon_dir
        self.session = _empty()

        raw = load_stats(addon_dir)

        lt = raw.get("lifetime")
        self.lifetime = lt if _is_valid_counts_block(lt) else _empty()

        daily_raw = raw.get("daily", {})
        if (
            isinstance(daily_raw, dict)
            and daily_raw.get("date") == _today()
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
                "date": _today(),
                "counts": self.daily,
            },
            "lifetime": self.lifetime,
        }
        save_stats(self._addon_dir, stats)
