"""Shared session card selection logic used by runtime and UI preview."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import NamedTuple

try:
    from . import cards as card_utils
    from .scheduler import DOCUMENT_FILTER, NO_TAGS_KEY, get_card_from_scheduler
    from .statistics import StatsManager
    from .paths import get_active_profile as _active_profile
except ImportError:
    import cards as card_utils  # type: ignore
    from scheduler import DOCUMENT_FILTER, NO_TAGS_KEY, get_card_from_scheduler  # type: ignore
    from statistics import StatsManager  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore


_YOUTUBE_FILTER = 'note:"Incremento Video"'
_WEBPAGE_FILTER = 'note:"Incremento Web"'


@dataclass
class SessionPickerSnapshot:
    scheduler_counts: dict = field(default_factory=dict)
    session_counts: dict = field(default_factory=dict)
    selected_ids: list[int] = field(default_factory=list)
    picked_meta: dict[int, dict] = field(default_factory=dict)
    ordered_priority_picked: dict[str, int] = field(default_factory=dict)


class SessionSelectionResult(NamedTuple):
    selected_ids: list[int]
    picked_meta: dict[int, dict]
    stats: StatsManager
    picker_snapshot: SessionPickerSnapshot


def _attempt_pick_loop(
    *,
    pick_fn,
    target_reached_fn,
    max_attempts: int,
    max_consecutive_misses: int,
) -> None:
    attempts = 0
    consecutive_misses = 0
    while attempts < max_attempts and consecutive_misses < max_consecutive_misses:
        if target_reached_fn():
            break
        attempts += 1
        if pick_fn():
            consecutive_misses = 0
        else:
            consecutive_misses += 1


def _record_selected_card(
    *,
    card_id: int,
    card_type: str,
    tag: str | None,
    mode: str,
    stage: str,
    selected_ids: list[int],
    picked_meta: dict[int, dict],
    added_to_filtered: set[int],
    scheduler_counts: dict,
    session_counts: dict,
    extra_meta: dict | None = None,
) -> None:
    for counts in (scheduler_counts, session_counts):
        counts["type"][card_type] = counts["type"].get(card_type, 0) + 1
        counts["mode"][mode] = counts["mode"].get(mode, 0) + 1
        if tag:
            counts["tags"][tag] = counts["tags"].get(tag, 0) + 1
    meta = {
        "card_type": card_type,
        "tag": tag,
        "mode": mode,
        "selection_stage": stage,
    }
    if extra_meta:
        meta.update(extra_meta)
    picked_meta[card_id] = meta
    added_to_filtered.add(card_id)
    selected_ids.append(card_id)


def _resolved_document_type(card_id: int, fallback: str = "pdf") -> str:
    try:
        return card_utils.get_document_card_type(int(card_id)) or fallback
    except Exception:
        return fallback


def _collect_tag_priority_candidates(
    cfg,
    *,
    tag: str,
    topics_filter: str,
    items_filter: str,
    pdf_filter: str,
    youtube_filter: str,
    webpage_filter: str,
) -> dict[int, tuple[str, str | None]]:
    candidates: dict[int, tuple[str, str | None]] = {}
    pool_ids = [
        ("pdf", card_utils.get_pdf_cards_by_tag(tag, pdf_filter=pdf_filter)),
        ("youtube", card_utils.get_youtube_cards_by_tag(tag, youtube_filter=youtube_filter)),
        ("webpage", card_utils.get_webpage_cards_by_tag(tag, webpage_filter=webpage_filter)),
        (
            "topics",
            card_utils.get_topic_cards_by_tag(
                tag,
                topics_filter=topics_filter,
                ready_filter=cfg.ready_filter,
            ),
        ),
        (
            "items",
            card_utils.get_item_cards_by_tag(
                tag,
                items_filter=items_filter,
                ready_filter=cfg.ready_filter,
            ),
        ),
    ]
    for card_type, ids in pool_ids:
        for card_id in ids:
            try:
                cid = int(card_id)
            except Exception:
                continue
            if cid <= 0 or cid in candidates:
                continue
            resolved_type = (
                _resolved_document_type(cid) if card_type == "pdf" else card_type
            )
            candidates[cid] = (resolved_type, tag)
    return candidates


def _collect_content_type_priority_candidates(
    *,
    content_type: str,
    pdf_filter: str,
    youtube_filter: str,
    webpage_filter: str,
) -> dict[int, tuple[str, str | None]]:
    if content_type == "pdf":
        ids = card_utils.get_all_pdf_cards(pdf_filter=pdf_filter)
    elif content_type == "youtube":
        ids = card_utils.get_all_youtube_cards(youtube_filter=youtube_filter)
    elif content_type == "webpage":
        ids = card_utils.get_all_webpage_cards(webpage_filter=webpage_filter)
    else:
        return {}
    candidates: dict[int, tuple[str, str | None]] = {}
    for card_id in ids:
        try:
            cid = int(card_id)
        except Exception:
            continue
        if cid <= 0 or cid in candidates:
            continue
        resolved_type = (
            _resolved_document_type(cid) if content_type == "pdf" else content_type
        )
        candidates[cid] = (resolved_type, None)
    return candidates


def _normalized_priority_order_entries(cfg) -> list[dict]:
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in list(getattr(cfg, "priority_order_entries", []) or []):
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip()
        value = str(raw.get("value") or "").strip()
        try:
            order = int(raw.get("order"))
        except Exception:
            continue
        if order <= 0:
            continue
        if kind == "tag":
            if not value:
                continue
            key_value = value.casefold()
        elif kind == "content_type":
            value = value.lower()
            if value not in {"pdf", "youtube", "webpage"}:
                continue
            key_value = value
        else:
            continue
        key = (kind, key_value)
        if key in seen:
            continue
        seen.add(key)
        entries.append({"kind": kind, "value": value, "order": order})
    return entries


def _ordered_priority_tiers(cfg) -> list[tuple[int, list[dict]]]:
    if not bool(getattr(cfg, "priority_order_enabled", False)):
        return []
    entries = _normalized_priority_order_entries(cfg)
    grouped: dict[int, list[dict]] = {}
    for entry in entries:
        grouped.setdefault(int(entry["order"]), []).append(entry)
    return [(order, grouped[order]) for order in sorted(grouped)]


def _apportion_counts(total: int, shares: dict[str, float]) -> dict[str, int]:
    if total <= 0:
        return {key: 0 for key in shares}
    raw = {key: max(0.0, float(value or 0.0)) * total for key, value in shares.items()}
    counts = {key: int(raw[key]) for key in shares}
    remainder = int(total) - sum(counts.values())
    if remainder <= 0:
        return counts
    ranked = sorted(
        shares.keys(),
        key=lambda key: (raw[key] - counts[key], key),
        reverse=True,
    )
    for index in range(remainder):
        counts[ranked[index % len(ranked)]] += 1
    return counts


def _expected_content_counts(cfg, total_target_count: int) -> dict[str, int]:
    target_count = max(0, int(total_target_count or 0))
    pdf_rate = float(getattr(cfg, "pdf_rate", 0.0) or 0.0)
    topics_rate = float(getattr(cfg, "topics_rate", 0.0) or 0.0)
    shares = {
        "pdf": pdf_rate,
        "topics": topics_rate * (1.0 - pdf_rate),
        "items": (1.0 - topics_rate) * (1.0 - pdf_rate),
    }
    return _apportion_counts(target_count, shares)


def _ordered_tag_quota_target(cfg, tag: str, total_target_count: int) -> int:
    tag_weights = dict(getattr(cfg, "tag_weights", {}) or {})
    normalized_tag = str(tag or "")
    if normalized_tag not in tag_weights:
        return 0

    real_weights = {
        str(key): max(0.0, float(value or 0.0))
        for key, value in tag_weights.items()
        if str(key)
    }
    total_weight = sum(real_weights.values())
    if total_weight <= 0.0:
        return 0
    if total_weight <= 1.0:
        shares = dict(real_weights)
        if bool(getattr(cfg, "include_rest", True)):
            shares[NO_TAGS_KEY] = max(0.0, 1.0 - total_weight)
    else:
        shares = {key: value / total_weight for key, value in real_weights.items()}
        if bool(getattr(cfg, "include_rest", True)):
            shares[NO_TAGS_KEY] = 0.0

    target = 0
    for content_total in _expected_content_counts(cfg, total_target_count).values():
        target += _apportion_counts(content_total, shares).get(normalized_tag, 0)
    return max(0, int(target))


def _ordered_priority_quota_target(cfg, entry: dict, total_target_count: int) -> int:
    kind = entry.get("kind")
    value = entry.get("value")
    if kind == "tag":
        return _ordered_tag_quota_target(cfg, str(value or ""), total_target_count)
    if kind == "content_type":
        weight = float(
            (getattr(cfg, "content_type_weights", {}) or {}).get(value, 0.0) or 0.0
        )
        return max(0, round(weight * max(0, int(total_target_count or 0))))
    return 0


def _normalize_branch_scope(branch_scope: dict | None) -> dict | None:
    if not isinstance(branch_scope, dict):
        return None

    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_card_id in list(branch_scope.get("card_ids") or []):
        try:
            card_id = int(raw_card_id)
        except Exception:
            continue
        if card_id in seen:
            continue
        seen.add(card_id)
        normalized_ids.append(card_id)

    root_card_id = branch_scope.get("root_card_id")
    try:
        normalized_root = None if root_card_id is None else int(root_card_id)
    except Exception:
        normalized_root = None

    return {
        "root_card_id": normalized_root,
        "root_title": str(branch_scope.get("root_title") or "").strip(),
        "card_ids": normalized_ids,
    }


def _cid_clause(card_ids: list[int]) -> str:
    if not card_ids:
        return ""
    return "(" + " OR ".join(f"cid:{int(card_id)}" for card_id in card_ids) + ")"


def _compose_filter(base_filter: str, branch_clause: str) -> str:
    base = str(base_filter or "").strip()
    branch = str(branch_clause or "").strip()
    if base and branch:
        return f"({base}) {branch}"
    if branch:
        return branch
    return base


def _tag_exclusion_clause(tags: set[str]) -> str:
    normalized = [str(tag).strip() for tag in sorted(tags) if str(tag).strip()]
    if not normalized:
        return ""
    if len(normalized) == 1:
        return f"-tag:{normalized[0]}"
    return "-(" + " OR ".join(f"tag:{tag}" for tag in normalized) + ")"


def _priority_entry_key(kind: str, value: str) -> str:
    normalized_kind = str(kind or "").strip()
    normalized_value = str(value or "").strip()
    if normalized_kind == "tag":
        normalized_value = normalized_value.casefold()
    elif normalized_kind == "content_type":
        normalized_value = normalized_value.lower()
    return f"{normalized_kind}:{normalized_value}"


class SessionPicker:
    def __init__(
        self,
        cfg,
        addon_dir: str,
        *,
        branch_scope: dict | None = None,
        snapshot: SessionPickerSnapshot | dict | None = None,
    ) -> None:
        card_utils.clear_topic_item_cache()
        self.cfg = cfg
        self.addon_dir = addon_dir
        self.branch_scope = _normalize_branch_scope(branch_scope)
        self._branch_scope_requested = branch_scope is not None
        self._branch_scope_empty = bool(
            self._branch_scope_requested
            and (self.branch_scope is None or not self.branch_scope.get("card_ids"))
        )

        self.stats = StatsManager(addon_dir, _active_profile(), day_end_time=cfg.day_end_time)
        self.scheduler_counts = copy.deepcopy(self.stats.counts_for(cfg.scheduler_scope))
        self.session_counts = self.stats.session
        self.selected_ids: list[int] = []
        self.picked_meta: dict[int, dict] = {}
        self.picked_ids: set[int] = set()
        self.ordered_priority_entries = _normalized_priority_order_entries(cfg)
        self.ordered_priority_picked: dict[str, int] = {}

        branch_clause = _cid_clause(list((self.branch_scope or {}).get("card_ids") or []))
        self.topics_filter = _compose_filter(cfg.topics_filter, branch_clause)
        self.items_filter = _compose_filter(cfg.items_filter, branch_clause)
        self.pdf_filter = _compose_filter(DOCUMENT_FILTER, branch_clause)
        self.youtube_filter = _compose_filter(_YOUTUBE_FILTER, branch_clause)
        self.webpage_filter = _compose_filter(_WEBPAGE_FILTER, branch_clause)

        ordered_tag_values = {
            str(entry["value"])
            for entry in self.ordered_priority_entries
            if str(entry.get("kind")) == "tag"
        }
        self.remaining_tag_weights = {
            str(tag): weight
            for tag, weight in (getattr(cfg, "tag_weights", {}) or {}).items()
            if str(tag) not in ordered_tag_values
        }
        self.remaining_use_tags = bool(self.remaining_tag_weights)

        remaining_tag_exclusion = _tag_exclusion_clause(ordered_tag_values)
        self.remaining_topics_filter = _compose_filter(self.topics_filter, remaining_tag_exclusion)
        self.remaining_items_filter = _compose_filter(self.items_filter, remaining_tag_exclusion)
        self.remaining_pdf_filter = _compose_filter(self.pdf_filter, remaining_tag_exclusion)
        self.remaining_youtube_filter = _compose_filter(self.youtube_filter, remaining_tag_exclusion)
        self.remaining_webpage_filter = _compose_filter(self.webpage_filter, remaining_tag_exclusion)

        if snapshot is not None:
            self._restore_snapshot(snapshot)

    def pick_until(self, total_target_count: int) -> list[int]:
        if self._branch_scope_empty:
            return []
        target_count = max(0, int(total_target_count or 0))
        start_len = len(self.selected_ids)
        if target_count <= start_len:
            return []

        self._pick_ordered_priority_until(target_count)
        if len(self.selected_ids) < target_count:
            if self.cfg.enforce_priority:
                self._pick_strict_until(target_count)
            else:
                self._pick_soft_until(target_count)

        return list(self.selected_ids[start_len:])

    def pick_next(self) -> int | None:
        new_ids = self.pick_until(len(self.selected_ids) + 1)
        return new_ids[0] if new_ids else None

    def snapshot(self) -> SessionPickerSnapshot:
        return SessionPickerSnapshot(
            scheduler_counts=copy.deepcopy(self.scheduler_counts),
            session_counts=copy.deepcopy(self.session_counts),
            selected_ids=list(self.selected_ids),
            picked_meta=copy.deepcopy(self.picked_meta),
            ordered_priority_picked=copy.deepcopy(self.ordered_priority_picked),
        )

    def result(self) -> SessionSelectionResult:
        return SessionSelectionResult(
            selected_ids=list(self.selected_ids),
            picked_meta=copy.deepcopy(self.picked_meta),
            stats=self.stats,
            picker_snapshot=self.snapshot(),
        )

    def _restore_snapshot(self, snapshot: SessionPickerSnapshot | dict) -> None:
        snap = snapshot.__dict__ if isinstance(snapshot, SessionPickerSnapshot) else dict(snapshot or {})

        scheduler_counts = copy.deepcopy(snap.get("scheduler_counts") or {})
        session_counts = copy.deepcopy(snap.get("session_counts") or {})
        selected_ids = []
        picked_ids: set[int] = set()
        for raw_card_id in list(snap.get("selected_ids") or []):
            try:
                cid = int(raw_card_id)
            except Exception:
                continue
            if cid <= 0 or cid in picked_ids:
                continue
            picked_ids.add(cid)
            selected_ids.append(cid)

        picked_meta: dict[int, dict] = {}
        for raw_card_id, meta in dict(snap.get("picked_meta") or {}).items():
            try:
                cid = int(raw_card_id)
            except Exception:
                continue
            if cid <= 0 or cid not in picked_ids:
                continue
            picked_meta[cid] = copy.deepcopy(meta or {})

        self.scheduler_counts = scheduler_counts or copy.deepcopy(self.stats.counts_for(self.cfg.scheduler_scope))
        self.session_counts = session_counts or {"type": {}, "tags": {}, "mode": {}}
        self.stats.session = self.session_counts
        self.selected_ids = selected_ids
        self.picked_ids = set(selected_ids)
        self.picked_meta = picked_meta
        self.ordered_priority_picked = {
            str(key): max(0, int(value or 0))
            for key, value in dict(snap.get("ordered_priority_picked") or {}).items()
        }

    def _pick(
        self,
        use_tags: bool,
        tag_weights: dict,
        force_card_type=None,
        force_mode=None,
        *,
        topics_filter_override: str | None = None,
        items_filter_override: str | None = None,
        pdf_filter_override: str | None = None,
        youtube_filter_override: str | None = None,
        webpage_filter_override: str | None = None,
    ) -> bool:
        result = get_card_from_scheduler(
            counts=self.scheduler_counts,
            topics_rate=self.cfg.topics_rate,
            random_rate=self.cfg.random_rate,
            use_tags=use_tags,
            tag_weights=tag_weights,
            exclude_ids=self.picked_ids,
            force_card_type=force_card_type,
            force_mode=force_mode,
            topics_filter=self.topics_filter if topics_filter_override is None else topics_filter_override,
            items_filter=self.items_filter if items_filter_override is None else items_filter_override,
            ready_filter=self.cfg.ready_filter,
            pdf_rate=self.cfg.pdf_rate,
            pdf_filter=self.pdf_filter if pdf_filter_override is None else pdf_filter_override,
            youtube_filter=self.youtube_filter if youtube_filter_override is None else youtube_filter_override,
            webpage_filter=self.webpage_filter if webpage_filter_override is None else webpage_filter_override,
            addon_dir=self.addon_dir,
            priority_lower_is_more_important=self.cfg.priority_lower_is_more_important,
        )
        if result.card is None:
            return False
        _record_selected_card(
            card_id=result.card,
            card_type=result.card_type,
            tag=result.tag,
            mode=result.mode,
            stage="scheduler",
            selected_ids=self.selected_ids,
            picked_meta=self.picked_meta,
            added_to_filtered=self.picked_ids,
            scheduler_counts=self.scheduler_counts,
            session_counts=self.session_counts,
        )
        return True

    def _phase_retry_budget(self, target: int, current: int) -> tuple[int, int]:
        deficit = max(1, target - current)
        return max(deficit * 12, 24), max(deficit * 4, 8)

    def _picked_content_type_count(self, content_type: str) -> int:
        if content_type == "pdf":
            return sum(
                int((self.session_counts.get("type") or {}).get(kind, 0) or 0)
                for kind in ("pdf", "epub")
            )
        return int((self.session_counts.get("type") or {}).get(content_type, 0) or 0)

    def _pick_ordered_priority_until(self, total_target_count: int) -> None:
        for order, tier_entries in _ordered_priority_tiers(self.cfg):
            if len(self.selected_ids) >= total_target_count:
                break

            quota_targets: dict[str, int] = {}
            tier_candidates: dict[int, tuple[str, str | None]] = {}
            candidate_matches: dict[int, list[str]] = {}
            entry_meta: dict[str, dict] = {}
            for entry in tier_entries:
                entry_key = _priority_entry_key(entry.get("kind", ""), entry.get("value", ""))
                quota_target = _ordered_priority_quota_target(self.cfg, entry, total_target_count)
                if quota_target <= self.ordered_priority_picked.get(entry_key, 0):
                    continue
                quota_targets[entry_key] = quota_target
                entry_meta[entry_key] = entry

                if entry["kind"] == "tag":
                    entry_candidates = _collect_tag_priority_candidates(
                        self.cfg,
                        tag=entry["value"],
                        topics_filter=self.topics_filter,
                        items_filter=self.items_filter,
                        pdf_filter=self.pdf_filter,
                        youtube_filter=self.youtube_filter,
                        webpage_filter=self.webpage_filter,
                    )
                else:
                    entry_candidates = _collect_content_type_priority_candidates(
                        content_type=entry["value"],
                        pdf_filter=self.pdf_filter,
                        youtube_filter=self.youtube_filter,
                        webpage_filter=self.webpage_filter,
                    )

                for card_id, meta in entry_candidates.items():
                    if card_id in self.picked_ids:
                        continue
                    if card_id not in tier_candidates:
                        tier_candidates[card_id] = meta
                    candidate_matches.setdefault(card_id, []).append(entry_key)

            if not quota_targets:
                continue

            ordered_tier_ids = card_utils.sort_cards_for_priority_mode(
                list(tier_candidates.keys()),
                addon_dir=self.addon_dir,
                lower_is_more_important=self.cfg.priority_lower_is_more_important,
            )
            for card_id in ordered_tier_ids:
                if len(self.selected_ids) >= total_target_count:
                    break
                if card_id in self.picked_ids:
                    continue

                selected_entry_key = next(
                    (
                        entry_key
                        for entry_key in candidate_matches.get(card_id, [])
                        if self.ordered_priority_picked.get(entry_key, 0) < quota_targets.get(entry_key, 0)
                    ),
                    None,
                )
                if selected_entry_key is None:
                    continue

                self.ordered_priority_picked[selected_entry_key] = (
                    self.ordered_priority_picked.get(selected_entry_key, 0) + 1
                )
                card_type, tag = tier_candidates[card_id]
                _record_selected_card(
                    card_id=card_id,
                    card_type=card_type,
                    tag=tag,
                    mode="priority",
                    stage="ordered_priority",
                    selected_ids=self.selected_ids,
                    picked_meta=self.picked_meta,
                    added_to_filtered=self.picked_ids,
                    scheduler_counts=self.scheduler_counts,
                    session_counts=self.session_counts,
                    extra_meta={
                        "priority_order": order,
                        "priority_order_kind": entry_meta[selected_entry_key]["kind"],
                        "priority_order_value": entry_meta[selected_entry_key]["value"],
                    },
                )

    def _pick_strict_until(self, total_target_count: int) -> None:
        for phase_id in self.cfg.phase_order:
            if not self.cfg.phases_enabled.get(phase_id, True):
                continue
            if len(self.selected_ids) >= total_target_count:
                break

            if phase_id == "content_types" and self.cfg.content_type_weights:
                for ct, weight in self.cfg.content_type_weights.items():
                    if weight <= 0:
                        continue
                    ct_target = round(weight * total_target_count)
                    current_count = self._picked_content_type_count(ct)
                    max_attempts, max_misses = self._phase_retry_budget(ct_target, current_count)
                    _attempt_pick_loop(
                        pick_fn=lambda ct=ct, ct_target=ct_target: (
                            False
                            if self._picked_content_type_count(ct) >= ct_target or len(self.selected_ids) >= total_target_count
                            else self._pick(
                                use_tags=self.remaining_use_tags,
                                tag_weights=self.remaining_tag_weights,
                                force_card_type=ct,
                                topics_filter_override=self.remaining_topics_filter,
                                items_filter_override=self.remaining_items_filter,
                                pdf_filter_override=self.remaining_pdf_filter,
                                youtube_filter_override=self.remaining_youtube_filter,
                                webpage_filter_override=self.remaining_webpage_filter,
                            )
                        ),
                        target_reached_fn=lambda ct=ct, ct_target=ct_target: (
                            self._picked_content_type_count(ct) >= ct_target
                            or len(self.selected_ids) >= total_target_count
                        ),
                        max_attempts=max_attempts,
                        max_consecutive_misses=max_misses,
                    )

            elif phase_id == "tags" and self.cfg.use_tags:
                ordered = sorted(self.remaining_tag_weights.items(), key=lambda x: x[1], reverse=True)
                for tag, weight in ordered:
                    tag_target = round(weight * total_target_count)
                    current_count = int((self.session_counts.get("tags") or {}).get(tag, 0) or 0)
                    max_attempts, max_misses = self._phase_retry_budget(tag_target, current_count)
                    _attempt_pick_loop(
                        pick_fn=lambda tag=tag, tag_target=tag_target: (
                            False
                            if int((self.session_counts.get("tags") or {}).get(tag, 0) or 0) >= tag_target
                            or len(self.selected_ids) >= total_target_count
                            else self._pick(use_tags=True, tag_weights={tag: 1.0})
                        ),
                        target_reached_fn=lambda tag=tag, tag_target=tag_target: (
                            int((self.session_counts.get("tags") or {}).get(tag, 0) or 0) >= tag_target
                            or len(self.selected_ids) >= total_target_count
                        ),
                        max_attempts=max_attempts,
                        max_consecutive_misses=max_misses,
                    )

            elif phase_id == "type":
                topics_target = round(self.cfg.topics_rate * total_target_count)
                items_target = total_target_count - topics_target
                for forced_type, type_target in [
                    ("topics", topics_target),
                    ("items", items_target),
                ]:
                    current_count = int((self.session_counts.get("type") or {}).get(forced_type, 0) or 0)
                    max_attempts, max_misses = self._phase_retry_budget(type_target, current_count)
                    _attempt_pick_loop(
                        pick_fn=lambda forced_type=forced_type, type_target=type_target: (
                            False
                            if int((self.session_counts.get("type") or {}).get(forced_type, 0) or 0) >= type_target
                            or len(self.selected_ids) >= total_target_count
                            else self._pick(
                                use_tags=self.remaining_use_tags,
                                tag_weights=self.remaining_tag_weights,
                                force_card_type=forced_type,
                                topics_filter_override=self.remaining_topics_filter,
                                items_filter_override=self.remaining_items_filter,
                                pdf_filter_override=self.remaining_pdf_filter,
                                youtube_filter_override=self.remaining_youtube_filter,
                                webpage_filter_override=self.remaining_webpage_filter,
                            )
                        ),
                        target_reached_fn=lambda forced_type=forced_type, type_target=type_target: (
                            int((self.session_counts.get("type") or {}).get(forced_type, 0) or 0) >= type_target
                            or len(self.selected_ids) >= total_target_count
                        ),
                        max_attempts=max_attempts,
                        max_consecutive_misses=max_misses,
                    )

            elif phase_id == "mode":
                priority_target = round((1 - self.cfg.random_rate) * total_target_count)
                random_target = total_target_count - priority_target
                for forced_mode, mode_target in [
                    ("priority", priority_target),
                    ("random", random_target),
                ]:
                    current_count = int((self.session_counts.get("mode") or {}).get(forced_mode, 0) or 0)
                    max_attempts, max_misses = self._phase_retry_budget(mode_target, current_count)
                    _attempt_pick_loop(
                        pick_fn=lambda forced_mode=forced_mode, mode_target=mode_target: (
                            False
                            if int((self.session_counts.get("mode") or {}).get(forced_mode, 0) or 0) >= mode_target
                            or len(self.selected_ids) >= total_target_count
                            else self._pick(
                                use_tags=self.remaining_use_tags,
                                tag_weights=self.remaining_tag_weights,
                                force_mode=forced_mode,
                                topics_filter_override=self.remaining_topics_filter,
                                items_filter_override=self.remaining_items_filter,
                                pdf_filter_override=self.remaining_pdf_filter,
                                youtube_filter_override=self.remaining_youtube_filter,
                                webpage_filter_override=self.remaining_webpage_filter,
                            )
                        ),
                        target_reached_fn=lambda forced_mode=forced_mode, mode_target=mode_target: (
                            int((self.session_counts.get("mode") or {}).get(forced_mode, 0) or 0) >= mode_target
                            or len(self.selected_ids) >= total_target_count
                        ),
                        max_attempts=max_attempts,
                        max_consecutive_misses=max_misses,
                    )

        if self.cfg.include_rest or not self.cfg.use_tags:
            _attempt_pick_loop(
                pick_fn=lambda: self._pick(
                    use_tags=False,
                    tag_weights={},
                    topics_filter_override=self.remaining_topics_filter,
                    items_filter_override=self.remaining_items_filter,
                    pdf_filter_override=self.remaining_pdf_filter,
                    youtube_filter_override=self.remaining_youtube_filter,
                    webpage_filter_override=self.remaining_webpage_filter,
                ),
                target_reached_fn=lambda: len(self.selected_ids) >= total_target_count,
                max_attempts=max(total_target_count * 12, 120),
                max_consecutive_misses=max(total_target_count * 2, 20),
            )

    def _pick_soft_until(self, total_target_count: int) -> None:
        _attempt_pick_loop(
            pick_fn=lambda: self._pick(
                use_tags=self.remaining_use_tags,
                tag_weights=self.remaining_tag_weights,
                topics_filter_override=self.remaining_topics_filter,
                items_filter_override=self.remaining_items_filter,
                pdf_filter_override=self.remaining_pdf_filter,
                youtube_filter_override=self.remaining_youtube_filter,
                webpage_filter_override=self.remaining_webpage_filter,
            ),
            target_reached_fn=lambda: len(self.selected_ids) >= total_target_count,
            max_attempts=max(total_target_count * 20, 200),
            max_consecutive_misses=max(total_target_count * 3, 30),
        )
        if self.remaining_use_tags and self.cfg.include_rest and len(self.selected_ids) < total_target_count:
            _attempt_pick_loop(
                pick_fn=lambda: self._pick(
                    use_tags=False,
                    tag_weights={},
                    topics_filter_override=self.remaining_topics_filter,
                    items_filter_override=self.remaining_items_filter,
                    pdf_filter_override=self.remaining_pdf_filter,
                    youtube_filter_override=self.remaining_youtube_filter,
                    webpage_filter_override=self.remaining_webpage_filter,
                ),
                target_reached_fn=lambda: len(self.selected_ids) >= total_target_count,
                max_attempts=max(total_target_count * 12, 120),
                max_consecutive_misses=max(total_target_count * 2, 20),
            )


def select_session_cards(
    cfg,
    addon_dir: str,
    *,
    branch_scope: dict | None = None,
) -> SessionSelectionResult:
    """Run the scheduler pick loop and return selected card IDs + pick metadata."""
    picker = SessionPicker(cfg, addon_dir, branch_scope=branch_scope)
    picker.pick_until(cfg.session_card_count)
    return picker.result()
