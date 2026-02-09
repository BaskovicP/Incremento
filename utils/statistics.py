import json, os, time
from pathlib import Path


def _stats_path(addon_dir: str) -> Path:
    # addon_dir = os.path.dirname(__file__) from your add-on package
    path = Path(addon_dir) / "user_files" / "custom_learn_stats.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_stats(addon_dir: str) -> dict:
    path = _stats_path(addon_dir)
    if not path.exists():
        return {
            "lifetime": {"topic": 0, "item": 0, "priority": 0, "random": 0,
                         "by_tag": {"topic": {}, "item": {}}},
            "daily": {},
            "last_reset": None
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        # fallback: don’t crash if file is corrupted
        return {
            "lifetime": {"topic": 0, "item": 0, "priority": 0, "random": 0,
                         "by_tag": {"topic": {}, "item": {}}},
            "daily": {},
            "last_reset": None
        }


def save_stats(addon_dir: str, stats: dict) -> None:
    path = _stats_path(addon_dir)
    tmp = path.with_name(path.name + ".tmp")

    data = json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.write_text(data, encoding="utf-8")

    # atomic replace
    os.replace(tmp, path)


def get_daily_stats(stats: dict) -> dict:
    today = time.strftime("%Y-%m-%d")
    if stats.get("last_reset") != today:
        stats["daily"] = {}
        stats["last_reset"] = today
    return stats["daily"]


def get_daily_item_stats(stats: dict) -> dict:
    daily_stats = get_daily_stats(stats)
    if "item" not in daily_stats:
        daily_stats["item"] = {}
    return daily_stats["item"]


def get_daily_topic_stats(stats: dict) -> dict:
    daily_stats = get_daily_stats(stats)
    if "topic" not in daily_stats:
        daily_stats["topic"] = {}
    return daily_stats["topic"]


def get_lifetime_stats(stats: dict) -> dict:
    return stats["lifetime"]


def get_lifetime_item_stats(stats: dict) -> dict:
    return stats["lifetime"]["item"]


def get_lifetime_priority_stats(stats: dict) -> dict:
    return stats["lifetime"]["priority"]


def get_lifetime_topic_stats(stats: dict) -> dict:
    return stats["lifetime"]["topic"]
