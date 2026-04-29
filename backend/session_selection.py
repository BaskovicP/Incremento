"""Shared session card selection logic used by runtime and UI preview."""

from __future__ import annotations

import copy
from typing import NamedTuple

try:
    from . import cards as card_utils
    from .scheduler import DOCUMENT_FILTER, get_card_from_scheduler
    from .statistics import StatsManager
    from .paths import get_active_profile as _active_profile
except ImportError:
    import cards as card_utils  # type: ignore
    from scheduler import DOCUMENT_FILTER, get_card_from_scheduler  # type: ignore
    from statistics import StatsManager  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore


_YOUTUBE_FILTER = 'note:"Incremento Video"'
_WEBPAGE_FILTER = 'note:"Incremento Web"'


class SessionSelectionResult(NamedTuple):
    selected_ids: list[int]
    picked_meta: dict[int, dict]
    stats: StatsManager


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
) -> None:
    for counts in (scheduler_counts, session_counts):
        counts["type"][card_type] = counts["type"].get(card_type, 0) + 1
        counts["mode"][mode] = counts["mode"].get(mode, 0) + 1
        if tag:
            counts["tags"][tag] = counts["tags"].get(tag, 0) + 1
    picked_meta[card_id] = {
        "card_type": card_type,
        "tag": tag,
        "mode": mode,
        "selection_stage": stage,
    }
    added_to_filtered.add(card_id)
    selected_ids.append(card_id)


def _collect_prioritized_tag_candidates(
    cfg,
    addon_dir: str,
    *,
    prioritized_tags: list[str],
    topics_filter: str,
    items_filter: str,
    pdf_filter: str,
    youtube_filter: str,
    webpage_filter: str,
) -> list[tuple[int, str, str]]:
    tag_to_candidates: dict[str, dict[int, str]] = {}
    for tag in prioritized_tags:
        tag_map = tag_to_candidates.setdefault(tag, {})
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
                if cid <= 0 or cid in tag_map:
                    continue
                tag_map[cid] = card_type

    ordered_ids = card_utils.sort_cards_for_priority_mode(
        [
            cid
            for tag in prioritized_tags
            for cid in tag_to_candidates.get(tag, {}).keys()
        ],
        addon_dir=addon_dir,
        lower_is_more_important=cfg.priority_lower_is_more_important,
    )
    seen: set[int] = set()
    ordered_candidates: list[tuple[int, str, str]] = []
    for cid in ordered_ids:
        if cid in seen:
            continue
        seen.add(cid)
        for tag in prioritized_tags:
            card_type = tag_to_candidates.get(tag, {}).get(cid)
            if card_type:
                ordered_candidates.append((cid, card_type, tag))
                break
    return ordered_candidates


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

    return {
        "root_card_id": (
            None
            if branch_scope.get("root_card_id") is None
            else int(branch_scope["root_card_id"])
        ),
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


def select_session_cards(
    cfg,
    addon_dir: str,
    *,
    branch_scope: dict | None = None,
) -> SessionSelectionResult:
    """Run the scheduler pick loop and return selected card IDs + pick metadata."""
    card_utils.clear_topic_item_cache()
    target_count = cfg.session_card_count
    stats = StatsManager(addon_dir, _active_profile(), day_end_time=cfg.day_end_time)
    normalized_branch_scope = _normalize_branch_scope(branch_scope)
    if branch_scope is not None and (
        normalized_branch_scope is None or not normalized_branch_scope["card_ids"]
    ):
        return SessionSelectionResult(
            selected_ids=[],
            picked_meta={},
            stats=stats,
        )

    branch_clause = _cid_clause(
        list((normalized_branch_scope or {}).get("card_ids") or [])
    )
    topics_filter = _compose_filter(cfg.topics_filter, branch_clause)
    items_filter = _compose_filter(cfg.items_filter, branch_clause)
    pdf_filter = _compose_filter(DOCUMENT_FILTER, branch_clause)
    youtube_filter = _compose_filter(_YOUTUBE_FILTER, branch_clause)
    webpage_filter = _compose_filter(_WEBPAGE_FILTER, branch_clause)

    selected_ids: list[int] = []
    added_to_filtered: set[int] = set()
    picked_meta: dict[int, dict] = {}
    scheduler_counts = copy.deepcopy(stats.counts_for(cfg.scheduler_scope))
    session_counts = stats.session

    def _pick(
        use_tags: bool, tag_weights: dict, force_card_type=None, force_mode=None
    ) -> bool:
        result = get_card_from_scheduler(
            counts=scheduler_counts,
            topics_rate=cfg.topics_rate,
            random_rate=cfg.random_rate,
            use_tags=use_tags,
            tag_weights=tag_weights,
            exclude_ids=added_to_filtered,
            force_card_type=force_card_type,
            force_mode=force_mode,
            topics_filter=topics_filter,
            items_filter=items_filter,
            ready_filter=cfg.ready_filter,
            pdf_rate=cfg.pdf_rate,
            pdf_filter=pdf_filter,
            youtube_filter=youtube_filter,
            webpage_filter=webpage_filter,
            addon_dir=addon_dir,
            priority_lower_is_more_important=cfg.priority_lower_is_more_important,
        )
        if result.card is None:
            return False
        _record_selected_card(
            card_id=result.card,
            card_type=result.card_type,
            tag=result.tag,
            mode=result.mode,
            stage="scheduler",
            selected_ids=selected_ids,
            picked_meta=picked_meta,
            added_to_filtered=added_to_filtered,
            scheduler_counts=scheduler_counts,
            session_counts=session_counts,
        )
        return True

    prioritized_tags = [
        str(tag or "").strip()
        for tag in list(getattr(cfg, "prioritized_tags_first", []) or [])
        if str(tag or "").strip()
    ]
    if prioritized_tags and len(selected_ids) < target_count:
        prioritized_candidates = _collect_prioritized_tag_candidates(
            cfg,
            addon_dir,
            prioritized_tags=prioritized_tags,
            topics_filter=topics_filter,
            items_filter=items_filter,
            pdf_filter=pdf_filter,
            youtube_filter=youtube_filter,
            webpage_filter=webpage_filter,
        )
        for card_id, card_type, tag in prioritized_candidates:
            if len(selected_ids) >= target_count:
                break
            if card_id in added_to_filtered:
                continue
            _record_selected_card(
                card_id=card_id,
                card_type=card_type,
                tag=tag,
                mode="priority",
                stage="prioritized_tags",
                selected_ids=selected_ids,
                picked_meta=picked_meta,
                added_to_filtered=added_to_filtered,
                scheduler_counts=scheduler_counts,
                session_counts=session_counts,
            )

    if cfg.enforce_priority:
        # Strict mode — run each funnel phase in order, filling its quota before the next.
        for phase_id in cfg.phase_order:
            if not cfg.phases_enabled.get(phase_id, True):
                continue
            if len(selected_ids) >= target_count:
                break

            if phase_id == "content_types" and cfg.content_type_weights:
                for ct, weight in cfg.content_type_weights.items():
                    if weight <= 0:
                        continue
                    ct_target = round(weight * target_count)
                    ct_picked = 0

                    def _phase_pick() -> bool:
                        nonlocal ct_picked
                        if ct_picked >= ct_target or len(selected_ids) >= target_count:
                            return False
                        ok = _pick(
                            use_tags=cfg.use_tags,
                            tag_weights=cfg.tag_weights,
                            force_card_type=ct,
                        )
                        if ok:
                            ct_picked += 1
                        return ok

                    _attempt_pick_loop(
                        pick_fn=_phase_pick,
                        target_reached_fn=lambda: ct_picked >= ct_target or len(selected_ids) >= target_count,
                        max_attempts=max(ct_target * 12, 24),
                        max_consecutive_misses=max(ct_target * 4, 8),
                    )

            elif phase_id == "tags" and cfg.use_tags:
                ordered = sorted(cfg.tag_weights.items(), key=lambda x: x[1], reverse=True)
                for tag, weight in ordered:
                    tag_target = round(weight * target_count)
                    tag_picked = 0

                    def _phase_pick() -> bool:
                        nonlocal tag_picked
                        if tag_picked >= tag_target or len(selected_ids) >= target_count:
                            return False
                        ok = _pick(use_tags=True, tag_weights={tag: 1.0})
                        if ok:
                            tag_picked += 1
                        return ok

                    _attempt_pick_loop(
                        pick_fn=_phase_pick,
                        target_reached_fn=lambda: tag_picked >= tag_target or len(selected_ids) >= target_count,
                        max_attempts=max(tag_target * 12, 24),
                        max_consecutive_misses=max(tag_target * 4, 8),
                    )

            elif phase_id == "type":
                topics_target = round(cfg.topics_rate * target_count)
                items_target = target_count - topics_target
                for forced_type, type_target in [
                    ("topics", topics_target),
                    ("items", items_target),
                ]:
                    type_picked = 0

                    def _phase_pick() -> bool:
                        nonlocal type_picked
                        if type_picked >= type_target or len(selected_ids) >= target_count:
                            return False
                        ok = _pick(
                            use_tags=cfg.use_tags,
                            tag_weights=cfg.tag_weights,
                            force_card_type=forced_type,
                        )
                        if ok:
                            type_picked += 1
                        return ok

                    _attempt_pick_loop(
                        pick_fn=_phase_pick,
                        target_reached_fn=lambda: type_picked >= type_target or len(selected_ids) >= target_count,
                        max_attempts=max(type_target * 12, 24),
                        max_consecutive_misses=max(type_target * 4, 8),
                    )

            elif phase_id == "mode":
                priority_target = round((1 - cfg.random_rate) * target_count)
                random_target = target_count - priority_target
                for forced_mode, mode_target in [
                    ("priority", priority_target),
                    ("random", random_target),
                ]:
                    mode_picked = 0

                    def _phase_pick() -> bool:
                        nonlocal mode_picked
                        if mode_picked >= mode_target or len(selected_ids) >= target_count:
                            return False
                        ok = _pick(
                            use_tags=cfg.use_tags,
                            tag_weights=cfg.tag_weights,
                            force_mode=forced_mode,
                        )
                        if ok:
                            mode_picked += 1
                        return ok

                    _attempt_pick_loop(
                        pick_fn=_phase_pick,
                        target_reached_fn=lambda: mode_picked >= mode_target or len(selected_ids) >= target_count,
                        max_attempts=max(mode_target * 12, 24),
                        max_consecutive_misses=max(mode_target * 4, 8),
                    )

        # Fill Remaining — always runs last in strict mode
        if cfg.include_rest or not cfg.use_tags:
            _attempt_pick_loop(
                pick_fn=lambda: _pick(use_tags=False, tag_weights={}),
                target_reached_fn=lambda: len(selected_ids) >= target_count,
                max_attempts=max(target_count * 12, 120),
                max_consecutive_misses=max(target_count * 2, 20),
            )

    else:
        # Soft mode — all dimensions handled by soft_pick (debt-based stochastic).
        # Phase order / enabled state is ignored; all weights blend together.
        _attempt_pick_loop(
            pick_fn=lambda: _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights),
            target_reached_fn=lambda: len(selected_ids) >= target_count,
            max_attempts=max(target_count * 20, 200),
            max_consecutive_misses=max(target_count * 3, 30),
        )
        if cfg.use_tags and cfg.include_rest and len(selected_ids) < target_count:
            _attempt_pick_loop(
                pick_fn=lambda: _pick(use_tags=False, tag_weights={}),
                target_reached_fn=lambda: len(selected_ids) >= target_count,
                max_attempts=max(target_count * 12, 120),
                max_consecutive_misses=max(target_count * 2, 20),
            )

    return SessionSelectionResult(
        selected_ids=selected_ids,
        picked_meta=picked_meta,
        stats=stats,
    )
