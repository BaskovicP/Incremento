"""Shared session card selection logic used by runtime and UI preview."""

from __future__ import annotations

from typing import NamedTuple

try:
    from .scheduler import DOCUMENT_FILTER, get_card_from_scheduler
    from .statistics import StatsManager
    from .paths import get_active_profile as _active_profile
except ImportError:
    from scheduler import DOCUMENT_FILTER, get_card_from_scheduler  # type: ignore
    from statistics import StatsManager  # type: ignore
    from paths import get_active_profile as _active_profile  # type: ignore


_YOUTUBE_FILTER = 'note:"Incremento Video"'
_WEBPAGE_FILTER = 'note:"Incremento Web"'


class SessionSelectionResult(NamedTuple):
    selected_ids: list[int]
    picked_meta: dict[int, dict]
    stats: StatsManager


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

    def _pick(
        use_tags: bool, tag_weights: dict, force_card_type=None, force_mode=None
    ) -> bool:
        counts = stats.counts_for(cfg.scheduler_scope)
        result = get_card_from_scheduler(
            counts=counts,
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
        counts["type"][result.card_type] = counts["type"].get(result.card_type, 0) + 1
        counts["mode"][result.mode] = counts["mode"].get(result.mode, 0) + 1
        if result.tag:
            counts["tags"][result.tag] = counts["tags"].get(result.tag, 0) + 1
        picked_meta[result.card] = {
            "card_type": result.card_type,
            "tag": result.tag,
            "mode": result.mode,
        }
        added_to_filtered.add(result.card)
        selected_ids.append(result.card)
        return True

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
                    for _ in range(ct_target * 3):
                        if ct_picked >= ct_target or len(selected_ids) >= target_count:
                            break
                        if not _pick(
                            use_tags=cfg.use_tags,
                            tag_weights=cfg.tag_weights,
                            force_card_type=ct,
                        ):
                            break
                        ct_picked += 1

            elif phase_id == "tags" and cfg.use_tags:
                ordered = sorted(cfg.tag_weights.items(), key=lambda x: x[1], reverse=True)
                for tag, weight in ordered:
                    tag_target = round(weight * target_count)
                    tag_picked = 0
                    for _ in range(tag_target * 3):
                        if tag_picked >= tag_target or len(selected_ids) >= target_count:
                            break
                        if not _pick(use_tags=True, tag_weights={tag: 1.0}):
                            break
                        tag_picked += 1

            elif phase_id == "type":
                topics_target = round(cfg.topics_rate * target_count)
                items_target = target_count - topics_target
                for forced_type, type_target in [
                    ("topics", topics_target),
                    ("items", items_target),
                ]:
                    type_picked = 0
                    for _ in range(type_target * 3):
                        if type_picked >= type_target or len(selected_ids) >= target_count:
                            break
                        if not _pick(
                            use_tags=cfg.use_tags,
                            tag_weights=cfg.tag_weights,
                            force_card_type=forced_type,
                        ):
                            break
                        type_picked += 1

            elif phase_id == "mode":
                priority_target = round((1 - cfg.random_rate) * target_count)
                random_target = target_count - priority_target
                for forced_mode, mode_target in [
                    ("priority", priority_target),
                    ("random", random_target),
                ]:
                    mode_picked = 0
                    for _ in range(mode_target * 3):
                        if mode_picked >= mode_target or len(selected_ids) >= target_count:
                            break
                        if not _pick(
                            use_tags=cfg.use_tags,
                            tag_weights=cfg.tag_weights,
                            force_mode=forced_mode,
                        ):
                            break
                        mode_picked += 1

        # Fill Remaining — always runs last in strict mode
        if cfg.include_rest or not cfg.use_tags:
            for _ in range(target_count * 3):
                if len(selected_ids) >= target_count:
                    break
                if not _pick(use_tags=False, tag_weights={}):
                    break

    else:
        # Soft mode — all dimensions handled by soft_pick (debt-based stochastic).
        # Phase order / enabled state is ignored; all weights blend together.
        for _ in range(target_count * 3):
            if len(selected_ids) >= target_count:
                break
            if not _pick(use_tags=cfg.use_tags, tag_weights=cfg.tag_weights):
                break
        if cfg.use_tags and cfg.include_rest and len(selected_ids) < target_count:
            for _ in range(target_count * 3):
                if len(selected_ids) >= target_count:
                    break
                if not _pick(use_tags=False, tag_weights={}):
                    break

    return SessionSelectionResult(
        selected_ids=selected_ids,
        picked_meta=picked_meta,
        stats=stats,
    )
