from __future__ import annotations

import copy
from collections import defaultdict
from typing import Iterable

try:
    from aqt import mw
except Exception:
    mw = None

try:
    from .cards import sort_cards_for_priority_mode
    from .db import (
        delete_knowledge_tree_postpone_preset,
        get_knowledge_tree_node,
        get_knowledge_tree_nodes,
        get_knowledge_tree_postpone_preset,
        get_knowledge_tree_postpone_presets,
        get_topic_schedule,
        save_knowledge_tree_postpone_preset,
        set_default_knowledge_tree_postpone_preset,
        set_topic_schedule,
    )
    from .knowledge_tree import (
        NODE_KIND_ITEM,
        NODE_KIND_TOPIC,
        ancestor_card_ids,
        get_card_metadata,
        normalize_node_kind,
        subtree_card_ids,
    )
    from .priority_manager import (
        configured_priority_lower_is_more_important,
        get_priority,
    )
    from .topic_scheduler import is_topic_card
except ImportError:
    from cards import sort_cards_for_priority_mode  # type: ignore
    from db import (  # type: ignore
        delete_knowledge_tree_postpone_preset,
        get_knowledge_tree_node,
        get_knowledge_tree_nodes,
        get_knowledge_tree_postpone_preset,
        get_knowledge_tree_postpone_presets,
        get_topic_schedule,
        save_knowledge_tree_postpone_preset,
        set_default_knowledge_tree_postpone_preset,
        set_topic_schedule,
    )
    from knowledge_tree import (  # type: ignore
        NODE_KIND_ITEM,
        NODE_KIND_TOPIC,
        ancestor_card_ids,
        get_card_metadata,
        normalize_node_kind,
        subtree_card_ids,
    )
    from priority_manager import (  # type: ignore
        configured_priority_lower_is_more_important,
        get_priority,
    )
    from topic_scheduler import is_topic_card  # type: ignore


SCOPE_ALL_OUTSTANDING = "all_outstanding"
SCOPE_SELECTED_BRANCH = "selected_branch"
SCOPE_CURRENT_BROWSER = "current_browser"

METHOD_SKIP_TOP = "skip_top"
METHOD_PARAMETERS = "parameters"

SUBTREE_MODE_RESPECT = "respect"
SUBTREE_MODE_IGNORE = "ignore"
SUBTREE_MODE_CONSERVATIVE = "conservative"
SUBTREE_MODE_LIBERAL = "liberal"

_SUPPORTED_SCOPES = {
    SCOPE_ALL_OUTSTANDING,
    SCOPE_SELECTED_BRANCH,
    SCOPE_CURRENT_BROWSER,
}
_SUPPORTED_METHODS = {METHOD_SKIP_TOP, METHOD_PARAMETERS}
_SUPPORTED_SUBTREE_MODES = {
    SUBTREE_MODE_RESPECT,
    SUBTREE_MODE_IGNORE,
    SUBTREE_MODE_CONSERVATIVE,
    SUBTREE_MODE_LIBERAL,
}

_DEFAULT_ITEM_SETTINGS = {
    "delay_factor": 1.2,
    "maximum_interval": 50,
    "minimum_interval": 1,
    "skip": False,
    "interval_beyond": 500,
    "postpone_count": 50,
    "priority_threshold": 6.0,
    "forgetting_index_below": None,
}
_DEFAULT_TOPIC_SETTINGS = {
    "delay_factor": 1.5,
    "maximum_interval": 100,
    "minimum_interval": 6,
    "skip": False,
    "interval_beyond": 800,
    "postpone_count": 100,
    "priority_threshold": 3.0,
    "a_factor_below": 1.01,
}
_DEFAULT_ADJUST_SETTINGS = {
    "subbranch_mode": SUBTREE_MODE_IGNORE,
    "include_non_outstanding": False,
    "modify_item_delay_by_fi": True,
    "modify_topic_delay_by_a_factor": True,
    "modify_delay_by_priority": False,
}


def _mean(values: Iterable[float]) -> float:
    numbers = [float(value) for value in list(values or [])]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def default_postpone_preset(*, branch_root_card_id: int | None = None) -> dict:
    return {
        "scope": (
            SCOPE_SELECTED_BRANCH
            if branch_root_card_id is not None
            else SCOPE_ALL_OUTSTANDING
        ),
        "method": METHOD_PARAMETERS,
        "skip_top_count": 50,
        "branch_root_card_id": (
            None if branch_root_card_id is None else int(branch_root_card_id)
        ),
        "item": copy.deepcopy(_DEFAULT_ITEM_SETTINGS),
        "topic": copy.deepcopy(_DEFAULT_TOPIC_SETTINGS),
        "adjust": copy.deepcopy(_DEFAULT_ADJUST_SETTINGS),
    }


def _to_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _to_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_optional_float(value, default: float | None = None) -> float | None:
    if value in (None, "", "N/A"):
        return default
    try:
        return float(value)
    except Exception:
        return default


def normalize_postpone_preset(
    config: dict | None,
    *,
    branch_root_card_id: int | None = None,
) -> dict:
    default = default_postpone_preset(branch_root_card_id=branch_root_card_id)
    raw = config if isinstance(config, dict) else {}

    scope = str(raw.get("scope") or default["scope"]).strip().lower()
    if scope not in _SUPPORTED_SCOPES:
        scope = default["scope"]

    method = str(raw.get("method") or default["method"]).strip().lower()
    if method not in _SUPPORTED_METHODS:
        method = default["method"]

    normalized = {
        "scope": scope,
        "method": method,
        "skip_top_count": max(0, _to_int(raw.get("skip_top_count"), default["skip_top_count"])),
        "branch_root_card_id": (
            branch_root_card_id
            if branch_root_card_id is not None
            else _to_int(raw.get("branch_root_card_id"), 0) or None
        ),
        "item": copy.deepcopy(_DEFAULT_ITEM_SETTINGS),
        "topic": copy.deepcopy(_DEFAULT_TOPIC_SETTINGS),
        "adjust": copy.deepcopy(_DEFAULT_ADJUST_SETTINGS),
    }

    for key, defaults in (("item", _DEFAULT_ITEM_SETTINGS), ("topic", _DEFAULT_TOPIC_SETTINGS)):
        values = raw.get(key)
        values = values if isinstance(values, dict) else {}
        normalized[key]["delay_factor"] = max(
            1.0,
            round(_to_float(values.get("delay_factor"), defaults["delay_factor"]), 4),
        )
        max_interval = max(
            0,
            _to_int(values.get("maximum_interval"), defaults["maximum_interval"]),
        )
        min_interval = max(
            0,
            _to_int(values.get("minimum_interval"), defaults["minimum_interval"]),
        )
        normalized[key]["maximum_interval"] = max(max_interval, min_interval)
        normalized[key]["minimum_interval"] = min(min_interval, normalized[key]["maximum_interval"])
        normalized[key]["skip"] = bool(values.get("skip", defaults["skip"]))
        normalized[key]["interval_beyond"] = max(
            0,
            _to_int(values.get("interval_beyond"), defaults["interval_beyond"]),
        )
        normalized[key]["postpone_count"] = max(
            0,
            _to_int(values.get("postpone_count"), defaults["postpone_count"]),
        )
        normalized[key]["priority_threshold"] = max(
            0.0,
            min(100.0, _to_float(values.get("priority_threshold"), defaults["priority_threshold"])),
        )
        if key == "topic":
            normalized[key]["a_factor_below"] = _to_optional_float(
                values.get("a_factor_below"),
                defaults["a_factor_below"],
            )
        else:
            normalized[key]["forgetting_index_below"] = None

    adjust_values = raw.get("adjust")
    adjust_values = adjust_values if isinstance(adjust_values, dict) else {}
    subbranch_mode = str(
        adjust_values.get("subbranch_mode")
        or default["adjust"]["subbranch_mode"]
    ).strip().lower()
    if subbranch_mode not in _SUPPORTED_SUBTREE_MODES:
        subbranch_mode = default["adjust"]["subbranch_mode"]
    normalized["adjust"]["subbranch_mode"] = subbranch_mode
    normalized["adjust"]["include_non_outstanding"] = bool(
        adjust_values.get(
            "include_non_outstanding",
            default["adjust"]["include_non_outstanding"],
        )
    )
    normalized["adjust"]["modify_item_delay_by_fi"] = bool(
        adjust_values.get(
            "modify_item_delay_by_fi",
            default["adjust"]["modify_item_delay_by_fi"],
        )
    )
    normalized["adjust"]["modify_topic_delay_by_a_factor"] = bool(
        adjust_values.get(
            "modify_topic_delay_by_a_factor",
            default["adjust"]["modify_topic_delay_by_a_factor"],
        )
    )
    normalized["adjust"]["modify_delay_by_priority"] = bool(
        adjust_values.get(
            "modify_delay_by_priority",
            default["adjust"]["modify_delay_by_priority"],
        )
    )
    return normalized


def load_postpone_presets(addon_dir: str, profile: str) -> list[dict]:
    presets = []
    for row in get_knowledge_tree_postpone_presets(addon_dir, profile):
        normalized = normalize_postpone_preset(
            row.get("config"),
            branch_root_card_id=row.get("branch_root_card_id"),
        )
        row_copy = dict(row)
        row_copy["config"] = normalized
        presets.append(row_copy)
    return presets


def load_default_postpone_preset(addon_dir: str, profile: str) -> dict | None:
    presets = load_postpone_presets(addon_dir, profile)
    for preset in presets:
        if preset.get("is_default"):
            return preset
    return None


def get_postpone_preset(addon_dir: str, profile: str, name: str) -> dict | None:
    row = get_knowledge_tree_postpone_preset(addon_dir, profile, name)
    if row is None:
        return None
    clone = dict(row)
    clone["config"] = normalize_postpone_preset(
        clone.get("config"),
        branch_root_card_id=clone.get("branch_root_card_id"),
    )
    return clone


def save_postpone_preset(
    addon_dir: str,
    profile: str,
    name: str,
    config: dict,
    *,
    branch_root_card_id: int | None = None,
    is_default: bool = False,
) -> dict:
    normalized = normalize_postpone_preset(
        config,
        branch_root_card_id=branch_root_card_id,
    )
    save_knowledge_tree_postpone_preset(
        addon_dir,
        profile,
        name,
        normalized,
        branch_root_card_id=branch_root_card_id,
        is_default=is_default,
    )
    return get_postpone_preset(addon_dir, profile, name) or {
        "name": str(name or "").strip(),
        "branch_root_card_id": branch_root_card_id,
        "config": normalized,
        "is_default": is_default,
    }


def delete_postpone_preset(addon_dir: str, profile: str, name: str) -> bool:
    return delete_knowledge_tree_postpone_preset(addon_dir, profile, name)


def set_default_postpone_preset(addon_dir: str, profile: str, name: str) -> bool:
    return set_default_knowledge_tree_postpone_preset(addon_dir, profile, name)


def get_branch_attached_preset(
    addon_dir: str,
    profile: str,
    branch_root_card_id: int,
) -> dict | None:
    for preset in load_postpone_presets(addon_dir, profile):
        if preset.get("branch_root_card_id") == int(branch_root_card_id):
            return preset
    return None


def list_subbranch_presets(
    addon_dir: str,
    profile: str,
    root_card_id: int,
) -> list[dict]:
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    subtree_ids = set(subtree_card_ids(rows, int(root_card_id)))
    results: list[dict] = []
    for preset in load_postpone_presets(addon_dir, profile):
        branch_root = preset.get("branch_root_card_id")
        if branch_root is None or int(branch_root) == int(root_card_id):
            continue
        if int(branch_root) not in subtree_ids:
            continue
        meta = get_card_metadata(int(branch_root), addon_dir=addon_dir, profile=profile) or {}
        results.append(
            {
                "branch_root_card_id": int(branch_root),
                "branch_title": str(meta.get("title") or f"Card {int(branch_root)}"),
                "preset_name": str(preset.get("name") or ""),
                "is_default": bool(preset.get("is_default")),
            }
        )
    results.sort(key=lambda item: item["branch_title"].casefold())
    return results


def _collection_available() -> bool:
    return bool(mw is not None and getattr(mw, "col", None) is not None)


def _group_rows(rows: list[dict]) -> dict[int | None, list[dict]]:
    grouped: dict[int | None, list[dict]] = defaultdict(list)
    for row in rows:
        parent = row.get("parent_card_id")
        grouped[parent].append(
            {
                "card_id": int(row["card_id"]),
                "parent_card_id": None if parent is None else int(parent),
                "node_kind": normalize_node_kind(row.get("node_kind") or NODE_KIND_TOPIC),
                "sort_order": int(row.get("sort_order", 0)),
            }
        )
    for children in grouped.values():
        children.sort(key=lambda row: (int(row.get("sort_order", 0)), int(row["card_id"])))
    return grouped


def _cid_clause(card_ids: Iterable[int]) -> str:
    ids = [int(card_id) for card_id in card_ids]
    if not ids:
        return ""
    return "(" + " OR ".join(f"cid:{card_id}" for card_id in ids) + ")"


def _search_card_ids(search: str) -> list[int]:
    if not _collection_available():
        return []
    try:
        return [int(card_id) for card_id in mw.col.find_cards(str(search or "").strip())]
    except Exception:
        return []


def _normalize_browser_card_ids(browser_card_ids: Iterable[int] | None) -> list[int]:
    normalized: list[int] = []
    seen: set[int] = set()
    for raw_card_id in list(browser_card_ids or []):
        try:
            card_id = int(raw_card_id)
        except Exception:
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        normalized.append(card_id)
    return normalized


def _eligible_scope_ids(
    candidate_card_ids: Iterable[int] | None,
    *,
    include_non_outstanding: bool,
) -> list[int]:
    base_filter = "-is:suspended"
    if not include_non_outstanding:
        base_filter += " (is:due OR is:learn)"
    ids = _normalize_browser_card_ids(candidate_card_ids)
    if not ids:
        return _search_card_ids(base_filter)
    return _search_card_ids(f"{base_filter} {_cid_clause(ids)}")


def _resolve_scope_card_ids(
    addon_dir: str,
    profile: str,
    config: dict,
    *,
    branch_root_card_id: int | None = None,
    browser_card_ids: Iterable[int] | None = None,
) -> tuple[list[int], int | None]:
    scope = config["scope"]
    include_non_outstanding = bool(config["adjust"]["include_non_outstanding"])

    if scope == SCOPE_ALL_OUTSTANDING:
        return _eligible_scope_ids(None, include_non_outstanding=include_non_outstanding), None

    if scope == SCOPE_CURRENT_BROWSER:
        return (
            _eligible_scope_ids(
                _normalize_browser_card_ids(browser_card_ids),
                include_non_outstanding=include_non_outstanding,
            ),
            None,
        )

    root_card_id = (
        int(branch_root_card_id)
        if branch_root_card_id is not None
        else int(config.get("branch_root_card_id") or 0)
    )
    if not root_card_id:
        return [], None
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    subtree_ids = subtree_card_ids(rows, root_card_id)
    return (
        _eligible_scope_ids(
            subtree_ids,
            include_non_outstanding=include_non_outstanding,
        ),
        root_card_id,
    )


def _classify_card_kind(tree_row_by_card_id: dict[int, dict], card) -> str:
    tree_row = tree_row_by_card_id.get(int(card.id))
    if tree_row is not None:
        return normalize_node_kind(tree_row.get("node_kind") or NODE_KIND_TOPIC)
    try:
        return NODE_KIND_TOPIC if is_topic_card(card) else NODE_KIND_ITEM
    except Exception:
        return NODE_KIND_ITEM


def _card_info_map(
    addon_dir: str,
    profile: str,
    card_ids: Iterable[int],
) -> dict[int, dict]:
    if not _collection_available():
        return {}
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    tree_row_by_card_id = {int(row["card_id"]): row for row in rows}

    info_map: dict[int, dict] = {}
    for raw_card_id in card_ids:
        try:
            card_id = int(raw_card_id)
            card = mw.col.get_card(card_id)
        except Exception:
            continue
        kind = _classify_card_kind(tree_row_by_card_id, card)
        priority = float(get_priority(addon_dir, profile, card_id))
        current_interval = max(1, _to_int(getattr(card, "ivl", 1), 1))
        a_factor = None
        if kind == NODE_KIND_TOPIC:
            a_factor, scheduled_interval = get_topic_schedule(addon_dir, profile, card_id)
            current_interval = max(current_interval, max(1, int(scheduled_interval or 1)))
        info_map[card_id] = {
            "card_id": card_id,
            "node_kind": kind,
            "priority": priority,
            "current_interval": current_interval,
            "a_factor": a_factor,
        }
    return info_map


def _priority_threshold_allows(
    priority: float,
    threshold: float | None,
    *,
    lower_is_more_important: bool,
) -> bool:
    if threshold is None:
        return True
    if lower_is_more_important:
        return float(priority) >= float(threshold)
    return float(priority) <= float(threshold)


def _delay_priority_scale(priority: float, *, lower_is_more_important: bool) -> float:
    p = max(0.0, min(100.0, float(priority)))
    return (0.5 + (p / 100.0)) if lower_is_more_important else (1.5 - (p / 100.0))


def _topic_a_factor_scale(a_factor: float | None) -> float:
    if a_factor is None:
        return 1.0
    return max(0.5, min(2.0, float(a_factor) / 3.5))


def _delay_days_for_card(
    info: dict,
    config: dict,
    *,
    lower_is_more_important: bool,
) -> int:
    kind_cfg = config["topic"] if info["node_kind"] == NODE_KIND_TOPIC else config["item"]
    ratio = max(0.0, float(kind_cfg["delay_factor"]) - 1.0)
    scale = 1.0
    if info["node_kind"] == NODE_KIND_TOPIC and config["adjust"]["modify_topic_delay_by_a_factor"]:
        scale *= _topic_a_factor_scale(info.get("a_factor"))
    if config["adjust"]["modify_delay_by_priority"]:
        scale *= _delay_priority_scale(
            float(info["priority"]),
            lower_is_more_important=lower_is_more_important,
        )
    raw_delay = float(info["current_interval"]) * max(0.0, ratio * scale)
    delay_days = int(round(raw_delay))
    delay_days = max(int(kind_cfg["minimum_interval"]), delay_days)
    delay_days = min(int(kind_cfg["maximum_interval"]), delay_days)
    return max(0, delay_days)


def _qualifies_parameter_filter(
    info: dict,
    config: dict,
    *,
    lower_is_more_important: bool,
) -> bool:
    kind_cfg = config["topic"] if info["node_kind"] == NODE_KIND_TOPIC else config["item"]
    if kind_cfg["skip"]:
        return False
    if int(info["current_interval"]) < int(kind_cfg["interval_beyond"]):
        return False
    if not _priority_threshold_allows(
        float(info["priority"]),
        kind_cfg.get("priority_threshold"),
        lower_is_more_important=lower_is_more_important,
    ):
        return False
    if info["node_kind"] == NODE_KIND_TOPIC:
        threshold = kind_cfg.get("a_factor_below")
        if threshold is not None and float(info.get("a_factor") or 0.0) < float(threshold):
            return False
    return True


def _top_level_preset_children(
    rows: list[dict],
    *,
    selected_root_card_id: int,
    preset_roots: set[int],
) -> dict[int, list[int]]:
    children: dict[int, list[int]] = defaultdict(list)
    subtree_order = {
        int(card_id): index
        for index, card_id in enumerate(subtree_card_ids(rows, selected_root_card_id))
    }
    for preset_root in sorted(preset_roots, key=lambda card_id: subtree_order.get(card_id, 10**9)):
        owner = int(selected_root_card_id)
        for ancestor in reversed(ancestor_card_ids(rows, int(preset_root))):
            if int(ancestor) in preset_roots:
                owner = int(ancestor)
                break
            if int(ancestor) == int(selected_root_card_id):
                owner = int(selected_root_card_id)
        children[owner].append(int(preset_root))
    return children


def _collect_segment_card_ids(
    grouped: dict[int | None, list[dict]],
    *,
    segment_root_card_id: int,
    nested_preset_roots: set[int],
    candidate_ids: set[int],
) -> list[int]:
    collected: list[int] = []

    def visit(card_id: int) -> None:
        if card_id in candidate_ids:
            collected.append(card_id)
        for child in grouped.get(card_id, []):
            child_id = int(child["card_id"])
            if child_id in nested_preset_roots and child_id != int(segment_root_card_id):
                continue
            visit(child_id)

    visit(int(segment_root_card_id))
    return collected


def _merge_postpone_configs(base_config: dict, local_config: dict, *, conservative: bool) -> dict:
    merged = normalize_postpone_preset(base_config, branch_root_card_id=base_config.get("branch_root_card_id"))
    if conservative:
        if METHOD_PARAMETERS in {base_config["method"], local_config["method"]}:
            merged["method"] = METHOD_PARAMETERS
        merged["skip_top_count"] = max(int(base_config["skip_top_count"]), int(local_config["skip_top_count"]))
    else:
        if METHOD_SKIP_TOP in {base_config["method"], local_config["method"]}:
            merged["method"] = METHOD_SKIP_TOP
        merged["skip_top_count"] = min(int(base_config["skip_top_count"]), int(local_config["skip_top_count"]))

    for key in ("item", "topic"):
        if conservative:
            merged[key]["delay_factor"] = min(float(base_config[key]["delay_factor"]), float(local_config[key]["delay_factor"]))
            merged[key]["maximum_interval"] = min(int(base_config[key]["maximum_interval"]), int(local_config[key]["maximum_interval"]))
            merged[key]["minimum_interval"] = max(int(base_config[key]["minimum_interval"]), int(local_config[key]["minimum_interval"]))
            merged[key]["interval_beyond"] = max(int(base_config[key]["interval_beyond"]), int(local_config[key]["interval_beyond"]))
            merged[key]["postpone_count"] = min(int(base_config[key]["postpone_count"]), int(local_config[key]["postpone_count"]))
            merged[key]["priority_threshold"] = (
                max(float(base_config[key]["priority_threshold"]), float(local_config[key]["priority_threshold"]))
                if configured_priority_lower_is_more_important()
                else min(float(base_config[key]["priority_threshold"]), float(local_config[key]["priority_threshold"]))
            )
        else:
            merged[key]["delay_factor"] = max(float(base_config[key]["delay_factor"]), float(local_config[key]["delay_factor"]))
            merged[key]["maximum_interval"] = max(int(base_config[key]["maximum_interval"]), int(local_config[key]["maximum_interval"]))
            merged[key]["minimum_interval"] = min(int(base_config[key]["minimum_interval"]), int(local_config[key]["minimum_interval"]))
            merged[key]["interval_beyond"] = min(int(base_config[key]["interval_beyond"]), int(local_config[key]["interval_beyond"]))
            merged[key]["postpone_count"] = max(int(base_config[key]["postpone_count"]), int(local_config[key]["postpone_count"]))
            merged[key]["priority_threshold"] = (
                min(float(base_config[key]["priority_threshold"]), float(local_config[key]["priority_threshold"]))
                if configured_priority_lower_is_more_important()
                else max(float(base_config[key]["priority_threshold"]), float(local_config[key]["priority_threshold"]))
            )
        merged[key]["skip"] = bool(base_config[key]["skip"] or local_config[key]["skip"]) if conservative else bool(base_config[key]["skip"] and local_config[key]["skip"])
        if key == "topic":
            base_threshold = base_config[key].get("a_factor_below")
            local_threshold = local_config[key].get("a_factor_below")
            if conservative:
                merged[key]["a_factor_below"] = max(float(base_threshold or 0.0), float(local_threshold or 0.0))
            else:
                non_null = [value for value in (base_threshold, local_threshold) if value is not None]
                merged[key]["a_factor_below"] = min(non_null) if non_null else None

    merged["adjust"]["include_non_outstanding"] = (
        bool(base_config["adjust"]["include_non_outstanding"] and local_config["adjust"]["include_non_outstanding"])
        if conservative
        else bool(base_config["adjust"]["include_non_outstanding"] or local_config["adjust"]["include_non_outstanding"])
    )
    merged["adjust"]["modify_item_delay_by_fi"] = bool(
        base_config["adjust"]["modify_item_delay_by_fi"]
        or local_config["adjust"]["modify_item_delay_by_fi"]
    )
    merged["adjust"]["modify_topic_delay_by_a_factor"] = bool(
        base_config["adjust"]["modify_topic_delay_by_a_factor"]
        or local_config["adjust"]["modify_topic_delay_by_a_factor"]
    )
    merged["adjust"]["modify_delay_by_priority"] = bool(
        base_config["adjust"]["modify_delay_by_priority"]
        or local_config["adjust"]["modify_delay_by_priority"]
    )
    return merged


def _build_segments(
    addon_dir: str,
    profile: str,
    config: dict,
    *,
    selected_root_card_id: int | None,
    candidate_ids: list[int],
) -> list[dict]:
    if selected_root_card_id is None or config["scope"] != SCOPE_SELECTED_BRANCH:
        return [{"root_card_id": selected_root_card_id, "config": config, "card_ids": list(candidate_ids)}]

    mode = config["adjust"]["subbranch_mode"]
    if mode == SUBTREE_MODE_IGNORE:
        return [{"root_card_id": selected_root_card_id, "config": config, "card_ids": list(candidate_ids)}]

    rows = get_knowledge_tree_nodes(addon_dir, profile)
    grouped = _group_rows(rows)
    preset_by_root = {
        int(preset["branch_root_card_id"]): preset
        for preset in load_postpone_presets(addon_dir, profile)
        if preset.get("branch_root_card_id") is not None
    }
    subtree_ids = set(subtree_card_ids(rows, int(selected_root_card_id)))
    preset_roots = {
        card_id
        for card_id in preset_by_root
        if card_id in subtree_ids and card_id != int(selected_root_card_id)
    }
    if not preset_roots:
        return [{"root_card_id": selected_root_card_id, "config": config, "card_ids": list(candidate_ids)}]

    candidate_id_set = {int(card_id) for card_id in candidate_ids}
    child_map = _top_level_preset_children(
        rows,
        selected_root_card_id=int(selected_root_card_id),
        preset_roots=preset_roots,
    )
    segments: list[dict] = []

    def build(root_card_id: int, effective_config: dict) -> None:
        nested_roots = set(child_map.get(int(root_card_id), []))
        segment_card_ids = _collect_segment_card_ids(
            grouped,
            segment_root_card_id=int(root_card_id),
            nested_preset_roots=nested_roots,
            candidate_ids=candidate_id_set,
        )
        segments.append(
            {
                "root_card_id": int(root_card_id),
                "config": normalize_postpone_preset(
                    effective_config,
                    branch_root_card_id=int(root_card_id),
                ),
                "card_ids": segment_card_ids,
            }
        )
        for child_root in child_map.get(int(root_card_id), []):
            child_preset = preset_by_root[int(child_root)]
            child_config = normalize_postpone_preset(
                child_preset.get("config"),
                branch_root_card_id=int(child_root),
            )
            if mode == SUBTREE_MODE_RESPECT:
                next_config = child_config
            elif mode == SUBTREE_MODE_CONSERVATIVE:
                next_config = _merge_postpone_configs(
                    effective_config,
                    child_config,
                    conservative=True,
                )
            else:
                next_config = _merge_postpone_configs(
                    effective_config,
                    child_config,
                    conservative=False,
                )
            build(int(child_root), next_config)

    build(int(selected_root_card_id), config)
    return [segment for segment in segments if segment["card_ids"]]


def _segment_apply_infos(
    addon_dir: str,
    profile: str,
    segment: dict,
    info_map: dict[int, dict],
    *,
    lower_is_more_important: bool,
) -> list[dict]:
    card_ids = [
        int(card_id)
        for card_id in sort_cards_for_priority_mode(
            list(segment["card_ids"]),
            addon_dir=addon_dir,
            lower_is_more_important=lower_is_more_important,
        )
        if int(card_id) in info_map
    ]
    if not card_ids:
        return []

    config = segment["config"]
    if config["method"] == METHOD_SKIP_TOP:
        chosen_ids = card_ids[int(config["skip_top_count"]):]
    else:
        chosen: set[int] = set()
        for kind in (NODE_KIND_ITEM, NODE_KIND_TOPIC):
            kind_ids = [
                card_id
                for card_id in card_ids
                if info_map[int(card_id)]["node_kind"] == kind
            ]
            filtered = [
                int(card_id)
                for card_id in kind_ids
                if _qualifies_parameter_filter(
                    info_map[int(card_id)],
                    config,
                    lower_is_more_important=lower_is_more_important,
                )
            ]
            limit = int(config["item" if kind == NODE_KIND_ITEM else "topic"]["postpone_count"])
            chosen.update(filtered[:limit] if limit else [])
        chosen_ids = [card_id for card_id in card_ids if int(card_id) in chosen]

    apply_infos: list[dict] = []
    for card_id in chosen_ids:
        info = dict(info_map[int(card_id)])
        delay_days = _delay_days_for_card(
            info,
            config,
            lower_is_more_important=lower_is_more_important,
        )
        info["delay_days"] = delay_days
        info["new_interval"] = int(info["current_interval"]) + int(delay_days)
        info["segment_root_card_id"] = segment.get("root_card_id")
        apply_infos.append(info)
    return apply_infos


def _summary_dict(all_candidates: list[dict], apply_infos: list[dict]) -> dict:
    applied_ids = {int(info["card_id"]) for info in apply_infos}
    item_candidates = [info for info in all_candidates if info["node_kind"] == NODE_KIND_ITEM]
    topic_candidates = [info for info in all_candidates if info["node_kind"] == NODE_KIND_TOPIC]
    applied_item_count = sum(1 for info in apply_infos if info["node_kind"] == NODE_KIND_ITEM)
    applied_topic_count = sum(1 for info in apply_infos if info["node_kind"] == NODE_KIND_TOPIC)

    average_delay_interval = round(_mean([float(info["delay_days"]) for info in apply_infos]), 1) if apply_infos else 0.0
    average_delay = round(
        _mean(
            [
                (float(info["delay_days"]) / float(info["current_interval"])) * 100.0
                for info in apply_infos
                if float(info["current_interval"]) > 0.0
            ]
        ),
        1,
    ) if apply_infos else 0.0

    return {
        "elements_to_postpone": len(apply_infos),
        "average_delay_interval": average_delay_interval,
        "average_delay": average_delay,
        "items_skipped": max(0, len(item_candidates) - applied_item_count),
        "topics_skipped": max(0, len(topic_candidates) - applied_topic_count),
        "max_interval_qualified": max([int(info["current_interval"]) for info in apply_infos], default=0),
        "max_interval_found": max([int(info["current_interval"]) for info in all_candidates], default=0),
        "applied_ids": sorted(applied_ids),
    }


def format_simulation_summary(summary: dict) -> str:
    return "\n".join(
        [
            f"Elements to postpone: {int(summary.get('elements_to_postpone') or 0)}",
            f"Average delay interval: {float(summary.get('average_delay_interval') or 0.0):.1f} days",
            f"Average delay: {float(summary.get('average_delay') or 0.0):.1f}%",
            f"Items skipped: {int(summary.get('items_skipped') or 0)}",
            f"Topics skipped: {int(summary.get('topics_skipped') or 0)}",
            f"Max interval qualified: {int(summary.get('max_interval_qualified') or 0)}",
            f"Max interval found: {int(summary.get('max_interval_found') or 0)}",
        ]
    )


def simulate_postpone_plan(
    addon_dir: str,
    profile: str,
    config: dict,
    *,
    branch_root_card_id: int | None = None,
    browser_card_ids: Iterable[int] | None = None,
) -> dict:
    normalized = normalize_postpone_preset(
        config,
        branch_root_card_id=branch_root_card_id,
    )
    candidate_ids, selected_root = _resolve_scope_card_ids(
        addon_dir,
        profile,
        normalized,
        branch_root_card_id=branch_root_card_id,
        browser_card_ids=browser_card_ids,
    )
    info_map = _card_info_map(addon_dir, profile, candidate_ids)
    all_candidates = [info_map[card_id] for card_id in candidate_ids if int(card_id) in info_map]
    lower_is_more_important = configured_priority_lower_is_more_important()
    segments = _build_segments(
        addon_dir,
        profile,
        normalized,
        selected_root_card_id=selected_root,
        candidate_ids=[info["card_id"] for info in all_candidates],
    )

    apply_infos_by_id: dict[int, dict] = {}
    for segment in segments:
        for info in _segment_apply_infos(
            addon_dir,
            profile,
            segment,
            info_map,
            lower_is_more_important=lower_is_more_important,
        ):
            apply_infos_by_id[int(info["card_id"])] = info

    ordered_apply_infos = [
        apply_infos_by_id[int(card_id)]
        for card_id in sort_cards_for_priority_mode(
            list(apply_infos_by_id.keys()),
            addon_dir=addon_dir,
            lower_is_more_important=lower_is_more_important,
        )
    ]
    summary = _summary_dict(all_candidates, ordered_apply_infos)
    summary["summary_text"] = format_simulation_summary(summary)
    summary["candidate_count"] = len(all_candidates)
    summary["segment_count"] = len(segments)
    summary["details"] = ordered_apply_infos
    return summary


def apply_postpone_plan(
    addon_dir: str,
    profile: str,
    config: dict,
    *,
    branch_root_card_id: int | None = None,
    browser_card_ids: Iterable[int] | None = None,
) -> dict:
    if not _collection_available():
        raise RuntimeError("Anki collection is not available.")
    summary = simulate_postpone_plan(
        addon_dir,
        profile,
        config,
        branch_root_card_id=branch_root_card_id,
        browser_card_ids=browser_card_ids,
    )
    for info in summary.get("details", []):
        card_id = int(info["card_id"])
        new_interval = int(info["new_interval"])
        mw.col.sched.set_due_date([card_id], str(new_interval))
        if info["node_kind"] == NODE_KIND_TOPIC:
            a_factor, _current_interval = get_topic_schedule(addon_dir, profile, card_id)
            set_topic_schedule(addon_dir, profile, card_id, float(a_factor), new_interval)
    summary["applied_count"] = int(summary.get("elements_to_postpone") or 0)
    return summary


def branch_scope_label(
    addon_dir: str,
    profile: str,
    branch_root_card_id: int | None,
) -> str:
    if branch_root_card_id is None:
        return "Global"
    meta = get_card_metadata(int(branch_root_card_id), addon_dir=addon_dir, profile=profile) or {}
    return str(meta.get("title") or f"Card {int(branch_root_card_id)}")


def browser_scope_label(browser_card_ids: Iterable[int] | None) -> str:
    count = len(_normalize_browser_card_ids(browser_card_ids))
    return f"Current Browser ({count} card{'s' if count != 1 else ''})"


def branch_root_for_card(addon_dir: str, profile: str, card_id: int) -> int | None:
    row = get_knowledge_tree_node(addon_dir, profile, int(card_id))
    if row is None:
        return None
    current = int(card_id)
    rows = get_knowledge_tree_nodes(addon_dir, profile)
    row_by_card_id = {int(row["card_id"]): row for row in rows}
    while True:
        row = row_by_card_id.get(current)
        if row is None or row.get("parent_card_id") is None:
            return current
        current = int(row["parent_card_id"])
