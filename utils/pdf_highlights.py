import json
import os
from pathlib import Path


def _path(addon_dir: str) -> Path:
    p = Path(addon_dir) / "user_files" / "pdf_highlights.json"
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
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def load_highlights(addon_dir: str, card_id: int) -> list:
    return _load_all(addon_dir).get(str(card_id), [])


def add_highlight(addon_dir: str, card_id: int, hl: dict) -> None:
    data = _load_all(addon_dir)
    data.setdefault(str(card_id), []).append(hl)
    _save_all(addon_dir, data)


def remove_highlight(addon_dir: str, card_id: int, hl_id: str) -> None:
    data = _load_all(addon_dir)
    key = str(card_id)
    if key in data:
        data[key] = [h for h in data[key] if h.get("id") != hl_id]
        if not data[key]:
            del data[key]
    _save_all(addon_dir, data)
