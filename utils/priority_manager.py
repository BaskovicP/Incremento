import json
import os
from pathlib import Path


def _path(addon_dir: str) -> Path:
    p = Path(addon_dir) / "user_files" / "priorities.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_all(addon_dir: str) -> dict:
    p = _path(addon_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_all(addon_dir: str, data: dict) -> None:
    p = _path(addon_dir)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, p)


def get_priority(addon_dir: str, card_id: int) -> float:
    """Return card priority (0.0000 = most important, 100.0000 = least). Default 50.0."""
    return _load_all(addon_dir).get(str(card_id), 50.0)


def set_priority(addon_dir: str, card_id: int, priority: float) -> None:
    data = _load_all(addon_dir)
    data[str(card_id)] = round(float(priority), 4)
    _save_all(addon_dir, data)
