from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Hashable, Iterable


SCOPE_WHOLE_TREE = "whole_tree"
SCOPE_SELECTED_BRANCH = "selected_branch"
VALID_SCOPES = frozenset({SCOPE_WHOLE_TREE, SCOPE_SELECTED_BRANCH})

SYNTHETIC_CENTER_KEY = "__incremento_mind_map_center__"

BRANCH_COLORS = (
    "#e45649",
    "#2d7ff9",
    "#22a06b",
    "#a15cdb",
    "#dc8b16",
    "#00a3bf",
    "#d13f83",
    "#6f8f24",
)

_HORIZONTAL_GAP = 238.0
_VERTICAL_GAP = 86.0
_LABEL_LIMIT = 64


@dataclass(frozen=True)
class MindMapNode:
    key: Hashable
    card_id: int | None
    parent_key: Hashable | None
    title: str
    full_title: str
    node_kind: str
    priority: float | None
    depth: int
    side: int
    x: float
    y: float
    color: str
    synthetic: bool = False
    child_count: int = 0
    hidden_descendant_count: int = 0
    collapsed: bool = False


@dataclass(frozen=True)
class MindMapEdge:
    parent_key: Hashable
    child_key: Hashable
    depth: int
    color: str


@dataclass(frozen=True)
class MindMapLayout:
    nodes: tuple[MindMapNode, ...]
    edges: tuple[MindMapEdge, ...]
    center_key: Hashable
    max_depth: int
    total_card_count: int
    visible_card_count: int

    @property
    def nodes_by_key(self) -> dict[Hashable, MindMapNode]:
        return {node.key: node for node in self.nodes}


@dataclass(frozen=True)
class _NormalizedRow:
    card_id: int
    parent_card_id: int | None
    node_kind: str
    sort_order: int
    input_order: int
    title: str
    priority: float | None


def _full_title(value: object, fallback: str) -> str:
    return " ".join(str(value or "").split()) or fallback


def _compact_title(value: object, fallback: str) -> str:
    title = _full_title(value, fallback)
    if len(title) <= _LABEL_LIMIT:
        return title
    return title[: _LABEL_LIMIT - 1].rstrip() + "…"


def _finite_priority(value: object) -> float | None:
    if not isinstance(value, (str, int, float)):
        return None
    try:
        priority = float(value)
    except (TypeError, ValueError):
        return None
    return priority if math.isfinite(priority) else None


def _normalize_rows(rows: Iterable[dict]) -> dict[int, _NormalizedRow]:
    normalized: dict[int, _NormalizedRow] = {}
    for input_order, raw in enumerate(rows):
        try:
            card_id = int(raw["card_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if card_id in normalized:
            continue
        raw_parent = raw.get("parent_card_id")
        try:
            parent_card_id = None if raw_parent is None else int(raw_parent)
        except (TypeError, ValueError):
            parent_card_id = None
        try:
            sort_order = int(raw.get("sort_order") or 0)
        except (TypeError, ValueError):
            sort_order = 0
        normalized[card_id] = _NormalizedRow(
            card_id=card_id,
            parent_card_id=parent_card_id,
            node_kind=(
                "topic"
                if str(raw.get("node_kind") or "").strip().lower() == "topic"
                else "item"
            ),
            sort_order=sort_order,
            input_order=input_order,
            title=_full_title(raw.get("title"), str(card_id)),
            priority=_finite_priority(raw.get("priority")),
        )
    return normalized


def _cycle_members(parent_by_id: dict[int, int | None]) -> set[int]:
    cycles: set[int] = set()
    settled: set[int] = set()
    for start in parent_by_id:
        if start in settled:
            continue
        path: list[int] = []
        positions: dict[int, int] = {}
        current: int | None = start
        while current is not None and current in parent_by_id:
            if current in positions:
                cycles.update(path[positions[current] :])
                break
            if current in settled:
                break
            positions[current] = len(path)
            path.append(current)
            current = parent_by_id[current]
        settled.update(path)
    return cycles


def _sort_key(row: _NormalizedRow) -> tuple[int, int, int]:
    return row.sort_order, row.input_order, row.card_id


def build_mind_map_layout(
    rows: Iterable[dict],
    *,
    scope: str = SCOPE_WHOLE_TREE,
    selected_card_id: int | None = None,
    center_title: str = "Knowledge Tree",
    collapsed_card_ids: Iterable[int] = (),
) -> MindMapLayout:
    """Build a deterministic, radial presentation model from tree rows.

    The model is deliberately independent of Qt. A single root (or a selected
    branch root) becomes the central idea. A forest gets one synthetic center so
    every top-level topic can radiate from a common visual anchor.
    """
    if scope not in VALID_SCOPES:
        raise ValueError(f"Unsupported mind-map scope: {scope}")

    row_by_id = _normalize_rows(rows)
    if scope == SCOPE_SELECTED_BRANCH:
        try:
            selected_id = int(selected_card_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError("selected_card_id is required for selected-branch scope") from None
        if selected_id not in row_by_id:
            raise ValueError("selected_card_id is not present in the knowledge tree")
    else:
        selected_id = None

    parent_by_id: dict[int, int | None] = {}
    for card_id, row in row_by_id.items():
        parent = row.parent_card_id
        parent_by_id[card_id] = parent if parent in row_by_id else None
    for card_id in _cycle_members(parent_by_id):
        parent_by_id[card_id] = None

    children_by_id: dict[int, list[int]] = {card_id: [] for card_id in row_by_id}
    for card_id, parent_id in parent_by_id.items():
        if parent_id is not None:
            children_by_id[parent_id].append(card_id)
    for child_ids in children_by_id.values():
        child_ids.sort(key=lambda card_id: _sort_key(row_by_id[card_id]))

    if selected_id is not None:
        visible_ids: set[int] = set()
        pending = [selected_id]
        while pending:
            card_id = pending.pop()
            if card_id in visible_ids:
                continue
            visible_ids.add(card_id)
            pending.extend(reversed(children_by_id.get(card_id, ())))
        row_by_id = {
            card_id: row for card_id, row in row_by_id.items() if card_id in visible_ids
        }
        children_by_id = {
            card_id: [child for child in children_by_id[card_id] if child in visible_ids]
            for card_id in visible_ids
        }
        roots = [selected_id]
    else:
        roots = sorted(
            (card_id for card_id, parent in parent_by_id.items() if parent is None),
            key=lambda card_id: _sort_key(row_by_id[card_id]),
        )

    collapsed_ids: set[int] = set()
    for raw_card_id in collapsed_card_ids:
        try:
            card_id = int(raw_card_id)
        except (TypeError, ValueError):
            continue
        if card_id in row_by_id:
            collapsed_ids.add(card_id)
    all_children_by_id = children_by_id

    descendant_counts: dict[int, int] = {}

    def descendant_count(card_id: int) -> int:
        cached = descendant_counts.get(card_id)
        if cached is not None:
            return cached
        count = sum(
            1 + descendant_count(child)
            for child in all_children_by_id.get(card_id, ())
        )
        descendant_counts[card_id] = count
        return count

    for card_id in row_by_id:
        descendant_count(card_id)

    children_by_id = {
        card_id: (
            []
            if card_id in collapsed_ids
            else list(all_children_by_id.get(card_id, ()))
        )
        for card_id in row_by_id
    }

    def node_fields(card_id: int) -> dict:
        row = row_by_id[card_id]
        child_count = len(all_children_by_id.get(card_id, ()))
        return {
            "title": _compact_title(row.title, str(card_id)),
            "full_title": row.title,
            "node_kind": row.node_kind,
            "priority": row.priority,
            "child_count": child_count,
            "hidden_descendant_count": (
                descendant_counts[card_id] if card_id in collapsed_ids else 0
            ),
            "collapsed": bool(child_count and card_id in collapsed_ids),
        }

    use_synthetic_center = len(roots) != 1
    if use_synthetic_center:
        center_key: Hashable = SYNTHETIC_CENTER_KEY
        synthetic_title = _full_title(center_title, "Knowledge Tree")
        center = MindMapNode(
            key=center_key,
            card_id=None,
            parent_key=None,
            title=_compact_title(synthetic_title, "Knowledge Tree"),
            full_title=synthetic_title,
            node_kind="topic",
            priority=None,
            depth=0,
            side=0,
            x=0.0,
            y=0.0,
            color="#f1b83b",
            synthetic=True,
        )
        primary_ids = list(roots)
    else:
        center_id = roots[0]
        center_key = center_id
        center = MindMapNode(
            key=center_id,
            card_id=center_id,
            parent_key=None,
            **node_fields(center_id),
            depth=0,
            side=0,
            x=0.0,
            y=0.0,
            color="#f1b83b",
            synthetic=False,
        )
        primary_ids = list(children_by_id.get(center_id, ()))

    nodes: list[MindMapNode] = [center]
    edges: list[MindMapEdge] = []

    weights: dict[int, int] = {}

    def leaf_weight(card_id: int) -> int:
        cached = weights.get(card_id)
        if cached is not None:
            return cached
        children = children_by_id.get(card_id, ())
        weight = sum(leaf_weight(child) for child in children) if children else 1
        weights[card_id] = max(1, weight)
        return weights[card_id]

    branches: list[tuple[int, int, str]] = []
    side_weight = {1: 0, -1: 0}
    for index, card_id in enumerate(primary_ids):
        side = 1 if side_weight[1] <= side_weight[-1] else -1
        color = BRANCH_COLORS[index % len(BRANCH_COLORS)]
        branches.append((card_id, side, color))
        side_weight[side] += leaf_weight(card_id)

    def place_branch(
        card_id: int,
        *,
        parent_key: Hashable,
        side: int,
        depth: int,
        y: float,
        color: str,
    ) -> None:
        nodes.append(
            MindMapNode(
                key=card_id,
                card_id=card_id,
                parent_key=parent_key,
                **node_fields(card_id),
                depth=depth,
                side=side,
                x=float(side * depth * _HORIZONTAL_GAP),
                y=float(y),
                color=color,
            )
        )
        edges.append(
            MindMapEdge(
                parent_key=parent_key,
                child_key=card_id,
                depth=depth,
                color=color,
            )
        )
        children = children_by_id.get(card_id, ())
        if not children:
            return
        total_weight = sum(leaf_weight(child) for child in children)
        cursor = y - (total_weight * _VERTICAL_GAP) / 2.0
        for child in children:
            span = leaf_weight(child) * _VERTICAL_GAP
            child_y = cursor + span / 2.0
            place_branch(
                child,
                parent_key=card_id,
                side=side,
                depth=depth + 1,
                y=child_y,
                color=color,
            )
            cursor += span

    for side in (1, -1):
        side_branches = [branch for branch in branches if branch[1] == side]
        total_weight = sum(leaf_weight(card_id) for card_id, _, _ in side_branches)
        cursor = -(total_weight * _VERTICAL_GAP) / 2.0
        for card_id, _, color in side_branches:
            span = leaf_weight(card_id) * _VERTICAL_GAP
            place_branch(
                card_id,
                parent_key=center_key,
                side=side,
                depth=1,
                y=cursor + span / 2.0,
                color=color,
            )
            cursor += span

    return MindMapLayout(
        nodes=tuple(nodes),
        edges=tuple(edges),
        center_key=center_key,
        max_depth=max((node.depth for node in nodes), default=0),
        total_card_count=len(row_by_id),
        visible_card_count=sum(1 for node in nodes if not node.synthetic),
    )


def directional_node_key(
    layout: MindMapLayout,
    current_key: Hashable,
    *,
    dx: int,
    dy: int,
) -> Hashable | None:
    """Return the closest visually predictable node in one arrow direction."""
    if not dx and not dy:
        return None
    nodes = layout.nodes_by_key
    current = nodes.get(current_key)
    if current is None:
        return layout.center_key

    candidates: list[tuple[float, float, Hashable]] = []
    for node in layout.nodes:
        if node.key == current_key:
            continue
        delta_x = node.x - current.x
        delta_y = node.y - current.y
        forward = delta_x * dx + delta_y * dy
        if forward <= 0:
            continue
        cross = abs(delta_y) if dx else abs(delta_x)
        distance = math.hypot(delta_x, delta_y)
        candidates.append((cross / max(1.0, forward), distance, node.key))
    if not candidates:
        return None
    candidates.sort(key=lambda candidate: (candidate[0], candidate[1], str(candidate[2])))
    return candidates[0][2]
