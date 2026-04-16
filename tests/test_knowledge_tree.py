import tempfile

import db
import knowledge_tree
import priority_manager


def _fresh_dir():
    return tempfile.mkdtemp()


def _reset_db():
    db.close_connection()


class _FakeNote:
    def __init__(self, tags=None):
        self.tags = list(tags or [])


class TestTreeMutationHelpers:
    def setup_method(self):
        _reset_db()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db()

    def test_insert_knowledge_tree_node_adds_root_and_child(self):
        knowledge_tree.insert_knowledge_tree_node(
            self.addon_dir,
            "TestProfile",
            10,
            "topic",
        )
        knowledge_tree.insert_knowledge_tree_node(
            self.addon_dir,
            "TestProfile",
            11,
            "item",
            parent_card_id=10,
        )

        assert db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile") == [
            {
                "card_id": 10,
                "parent_card_id": None,
                "node_kind": "topic",
                "sort_order": 0,
                "created_at": db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")[0]["created_at"],
                "updated_at": db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")[0]["updated_at"],
            },
            {
                "card_id": 11,
                "parent_card_id": 10,
                "node_kind": "item",
                "sort_order": 0,
                "created_at": db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")[1]["created_at"],
                "updated_at": db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")[1]["updated_at"],
            },
        ]

    def test_delete_knowledge_tree_node_lifts_children_into_deleted_position(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 20, "parent_card_id": None, "node_kind": "topic", "sort_order": 1},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
            ],
        )

        removed = knowledge_tree.delete_knowledge_tree_node(
            self.addon_dir,
            "TestProfile",
            10,
        )

        rows = db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")

        assert removed is True
        assert [(row["card_id"], row["parent_card_id"], row["sort_order"]) for row in rows] == [
            (11, None, 0),
            (12, None, 1),
            (20, None, 2),
        ]

    def test_insert_knowledge_tree_node_rejects_duplicate_card(self):
        knowledge_tree.insert_knowledge_tree_node(
            self.addon_dir,
            "TestProfile",
            10,
            "topic",
        )

        try:
            knowledge_tree.insert_knowledge_tree_node(
                self.addon_dir,
                "TestProfile",
                10,
                "topic",
            )
            assert False, "Expected duplicate-card insertion to fail"
        except ValueError as exc:
            assert "already present" in str(exc)


def test_sync_note_kind_tags_adds_incremento_and_removes_opposite_kind():
    note = _FakeNote(["keep", "item", "Incremento"])

    tags = knowledge_tree.sync_note_kind_tags(
        note,
        "topic",
        topic_tags=["topic"],
        item_tags=["item"],
    )

    assert tags == ["keep", "Incremento", "topic"]
    assert note.tags == ["keep", "Incremento", "topic"]


def test_descendant_card_ids_returns_all_nested_children_in_tree_order():
    rows = [
        {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
        {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
        {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
        {"card_id": 13, "parent_card_id": 11, "node_kind": "item", "sort_order": 0},
        {"card_id": 14, "parent_card_id": 12, "node_kind": "item", "sort_order": 0},
    ]

    assert knowledge_tree.descendant_card_ids(rows, 10) == [11, 12, 13, 14]


def test_subtree_card_ids_includes_root_and_descendants_in_tree_order():
    rows = [
        {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
        {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
        {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
        {"card_id": 13, "parent_card_id": 11, "node_kind": "item", "sort_order": 0},
    ]

    assert knowledge_tree.subtree_card_ids(rows, 10) == [10, 11, 12, 13]
    assert knowledge_tree.subtree_card_ids(rows, 10, include_root=False) == [11, 12, 13]


def test_ancestor_card_ids_returns_root_to_parent_chain():
    rows = [
        {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
        {"card_id": 11, "parent_card_id": 10, "node_kind": "topic", "sort_order": 0},
        {"card_id": 12, "parent_card_id": 11, "node_kind": "item", "sort_order": 0},
    ]

    assert knowledge_tree.ancestor_card_ids(rows, 12) == [10, 11]


def test_describe_branch_summary_for_branch_with_descendants():
    summary = knowledge_tree.describe_branch_summary(
        {
            "total_count": 4,
            "descendant_count": 3,
            "direct_child_count": 2,
            "max_depth": 2,
            "selected_priority": 58.0,
            "min_priority": 40.0,
            "max_priority": 82.0,
        }
    )

    assert summary["size_line"] == "This branch contains 4 cards total."
    assert summary["children_line"] == "Children: 2 direct children and 1 deeper descendant."
    assert summary["levels_line"] == "Levels below this node: 2."
    assert summary["selected_priority_line"] == "Selected node priority: 58."
    assert summary["range_line"] == "Priority range across this branch: 40 to 82."
    assert summary["impact_line"] == "Study Branch and Postpone can affect 4 cards in this branch."


def test_describe_branch_summary_for_leaf_branch():
    summary = knowledge_tree.describe_branch_summary(
        {
            "total_count": 1,
            "descendant_count": 0,
            "direct_child_count": 0,
            "max_depth": 0,
            "selected_priority": 58.0,
            "min_priority": 58.0,
            "max_priority": 58.0,
        }
    )

    assert summary["size_line"] == "This branch contains 1 card total."
    assert summary["children_line"] == "Children: no child cards yet."
    assert summary["levels_line"] == "Levels below this node: 0."
    assert summary["selected_priority_line"] == "Selected node priority: 58."
    assert summary["range_line"] == ""
    assert (
        summary["impact_line"]
        == "Study Branch and Postpone will affect only this card until you add children."
    )


def test_describe_branch_summary_for_empty_selection():
    summary = knowledge_tree.describe_branch_summary({})

    assert summary["size_line"] == "Select a topic or item to inspect this branch."
    assert summary["children_line"] == ""
    assert summary["levels_line"] == ""
    assert summary["selected_priority_line"] == ""
    assert summary["range_line"] == ""
    assert "once a node is selected" in summary["impact_line"]


class TestPrioritySpread:
    def setup_method(self):
        _reset_db()
        self.addon_dir = _fresh_dir()

    def teardown_method(self):
        _reset_db()

    def test_spread_priority_delta_updates_all_descendants(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
                {"card_id": 13, "parent_card_id": 12, "node_kind": "item", "sort_order": 0},
            ],
        )
        priority_manager.set_priority(self.addon_dir, "TestProfile", 11, 55.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 12, 70.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 13, 95.0)

        updated = knowledge_tree.spread_priority_delta(
            self.addon_dir,
            "TestProfile",
            10,
            10.0,
        )

        assert updated == 3
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 11) == 65.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 12) == 80.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 13) == 100.0

    def test_spread_priority_delta_ignores_root_and_clamps_low_end(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
            ],
        )
        priority_manager.set_priority(self.addon_dir, "TestProfile", 10, 50.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 11, 5.0)

        updated = knowledge_tree.spread_priority_delta(
            self.addon_dir,
            "TestProfile",
            10,
            -20.0,
        )

        assert updated == 1
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 10) == 50.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 11) == 0.0


class TestBranchPriorityOperations:
    def setup_method(self):
        _reset_db()
        self.addon_dir = _fresh_dir()
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
                {"card_id": 13, "parent_card_id": 12, "node_kind": "item", "sort_order": 0},
            ],
        )
        priority_manager.set_priority(self.addon_dir, "TestProfile", 10, 60.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 11, 50.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 12, 40.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 13, 30.0)

    def teardown_method(self):
        _reset_db()

    def test_get_parent_card_id_returns_parent(self):
        assert knowledge_tree.get_parent_card_id(self.addon_dir, "TestProfile", 13) == 12
        assert knowledge_tree.get_parent_card_id(self.addon_dir, "TestProfile", 10) is None

    def test_subtree_priority_stats_reports_counts_and_range(self):
        stats = knowledge_tree.subtree_priority_stats(
            self.addon_dir,
            "TestProfile",
            10,
        )

        assert stats["exists"] is True
        assert stats["total_count"] == 4
        assert stats["descendant_count"] == 3
        assert stats["direct_child_count"] == 2
        assert stats["max_depth"] == 2
        assert stats["min_priority"] == 30.0
        assert stats["max_priority"] == 60.0
        assert stats["selected_priority"] == 60.0

    def test_shift_subtree_priorities_updates_selected_node_and_descendants(self):
        changed = knowledge_tree.shift_subtree_priorities(
            self.addon_dir,
            "TestProfile",
            10,
            -15.0,
        )

        assert changed == 4
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 10) == 45.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 11) == 35.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 12) == 25.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 13) == 15.0

    def test_spread_subtree_priorities_uses_leaf_end_value_when_root_excluded(self):
        changed = knowledge_tree.spread_subtree_priorities(
            self.addon_dir,
            "TestProfile",
            10,
            20.0,
            80.0,
            include_root=False,
        )

        assert changed == 3
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 11) == 20.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 12) == 20.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 13) == 80.0

    def test_randomize_subtree_priorities_is_seedable_for_regressions(self):
        changed = knowledge_tree.randomize_subtree_priorities(
            self.addon_dir,
            "TestProfile",
            10,
            10.0,
            20.0,
            seed=123,
        )

        values = [
            priority_manager.get_priority(self.addon_dir, "TestProfile", card_id)
            for card_id in (10, 11, 12, 13)
        ]

        assert changed == 4
        assert values == [10.5236, 10.8719, 14.0724, 11.077]

    def test_focus_subtree_priorities_moves_whole_branch_toward_important_end(self):
        changed = knowledge_tree.focus_subtree_priorities(
            self.addon_dir,
            "TestProfile",
            10,
            lower_is_more_important=True,
        )

        assert changed == 4
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 10) == 12.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 11) == 17.5
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 12) == 14.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 13) == 15.0

    def test_fade_child_priorities_keeps_root_and_reduces_descendants(self):
        changed = knowledge_tree.fade_child_priorities(
            self.addon_dir,
            "TestProfile",
            10,
            lower_is_more_important=True,
        )

        assert changed == 3
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 10) == 60.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 11) == 62.5
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 12) == 55.0
        assert priority_manager.get_priority(self.addon_dir, "TestProfile", 13) == 58.0
