import pytest

from knowledge_tree_mind_map_model import (
    SCOPE_SELECTED_BRANCH,
    SCOPE_WHOLE_TREE,
    build_mind_map_layout,
    directional_node_key,
)


def _rows():
    return [
        {
            "card_id": 10,
            "parent_card_id": None,
            "node_kind": "topic",
            "sort_order": 0,
            "title": "Memory systems",
            "priority": 80,
        },
        {
            "card_id": 11,
            "parent_card_id": 10,
            "node_kind": "topic",
            "sort_order": 0,
            "title": "Encoding",
            "priority": 70,
        },
        {
            "card_id": 12,
            "parent_card_id": 10,
            "node_kind": "item",
            "sort_order": 1,
            "title": "Retrieval practice",
            "priority": 40,
        },
        {
            "card_id": 13,
            "parent_card_id": 11,
            "node_kind": "item",
            "sort_order": 0,
            "title": "Elaborative encoding",
            "priority": 65,
        },
        {
            "card_id": 20,
            "parent_card_id": None,
            "node_kind": "topic",
            "sort_order": 1,
            "title": "Attention",
            "priority": 55,
        },
    ]


def test_whole_forest_uses_a_central_idea_and_balanced_radiant_branches():
    layout = build_mind_map_layout(
        _rows(),
        scope=SCOPE_WHOLE_TREE,
        center_title="Knowledge Tree",
    )

    center = layout.nodes_by_key[layout.center_key]
    memory = layout.nodes_by_key[10]
    attention = layout.nodes_by_key[20]
    encoding = layout.nodes_by_key[11]
    elaboration = layout.nodes_by_key[13]

    assert center.synthetic is True
    assert (center.x, center.y, center.depth, center.title) == (
        0.0,
        0.0,
        0,
        "Knowledge Tree",
    )
    assert {memory.side, attention.side} == {-1, 1}
    assert abs(encoding.x) > abs(memory.x)
    assert abs(elaboration.x) > abs(encoding.x)
    assert memory.color == encoding.color == elaboration.color
    assert memory.color != attention.color
    assert {(edge.parent_key, edge.child_key) for edge in layout.edges} == {
        (layout.center_key, 10),
        (10, 11),
        (11, 13),
        (10, 12),
        (layout.center_key, 20),
    }


def test_selected_branch_becomes_the_center_and_excludes_unrelated_nodes():
    layout = build_mind_map_layout(
        _rows(),
        scope=SCOPE_SELECTED_BRANCH,
        selected_card_id=11,
        center_title="Knowledge Tree",
    )

    assert layout.center_key == 11
    assert set(layout.nodes_by_key) == {11, 13}
    assert layout.nodes_by_key[11].synthetic is False
    assert layout.nodes_by_key[11].priority == 70.0
    assert layout.nodes_by_key[13].parent_key == 11
    assert layout.nodes_by_key[13].depth == 1


def test_one_root_is_the_central_image_instead_of_adding_a_synthetic_center():
    rows = _rows()[:-1]

    layout = build_mind_map_layout(rows, scope=SCOPE_WHOLE_TREE)

    assert layout.center_key == 10
    assert layout.nodes_by_key[10].synthetic is False
    assert (layout.nodes_by_key[10].x, layout.nodes_by_key[10].y) == (0.0, 0.0)
    assert {layout.nodes_by_key[11].side, layout.nodes_by_key[12].side} == {-1, 1}


def test_selected_scope_requires_a_node_that_exists_in_the_map():
    with pytest.raises(ValueError, match="selected_card_id"):
        build_mind_map_layout(
            _rows(),
            scope=SCOPE_SELECTED_BRANCH,
            selected_card_id=999,
        )


def test_malformed_cycles_are_broken_into_renderable_roots():
    rows = [
        {"card_id": 1, "parent_card_id": 2, "title": "One", "node_kind": "topic"},
        {"card_id": 2, "parent_card_id": 1, "title": "Two", "node_kind": "item"},
    ]

    layout = build_mind_map_layout(rows)

    assert set(layout.nodes_by_key) == {layout.center_key, 1, 2}
    assert len(layout.edges) == 2


def test_collapsed_branch_stays_visible_and_reports_hidden_descendants():
    layout = build_mind_map_layout(
        _rows(),
        collapsed_card_ids={11},
    )

    assert 11 in layout.nodes_by_key
    assert 13 not in layout.nodes_by_key
    assert layout.nodes_by_key[11].collapsed is True
    assert layout.nodes_by_key[11].child_count == 1
    assert layout.nodes_by_key[11].hidden_descendant_count == 1
    assert layout.total_card_count == 5
    assert layout.visible_card_count == 4


def test_long_titles_keep_full_hover_text_while_branch_label_is_compact():
    title = "A deliberately long branch title " * 5
    rows = [
        {"card_id": 1, "parent_card_id": None, "title": "Root", "node_kind": "topic"},
        {"card_id": 2, "parent_card_id": 1, "title": title, "node_kind": "item"},
    ]

    layout = build_mind_map_layout(rows)

    assert layout.nodes_by_key[2].full_title == " ".join(title.split())
    assert layout.nodes_by_key[2].title.endswith("…")
    assert len(layout.nodes_by_key[2].title) == 64


def test_directional_navigation_chooses_nearest_node_in_requested_half_plane():
    layout = build_mind_map_layout(_rows())
    center = layout.center_key
    right = directional_node_key(layout, center, dx=1, dy=0)
    left = directional_node_key(layout, center, dx=-1, dy=0)

    assert right in {10, 20}
    assert left in {10, 20}
    assert right != left
    assert directional_node_key(layout, right, dx=-1, dy=0) == center
