import tempfile
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import db
import knowledge_tree
from note_metadata import (
    INCREMENTO_PARENT_CARD_ID_FIELD,
    INCREMENTO_PARENT_FIELD,
    INCREMENTO_SOURCE_TYPE_FIELD,
    build_incremento_metadata,
)
import priority_manager


def _fresh_dir():
    return tempfile.mkdtemp()


def _reset_db():
    db.close_connection()


class _FakeNote:
    def __init__(self, tags=None):
        self.tags = list(tags or [])


class _FakeLinkSearchDb:
    def __init__(self):
        self.queries: list[str] = []

    def all(self, sql, *params):
        self.queries.append(sql)
        if "n.sfld" not in sql:
            raise AssertionError("Knowledge-tree link search should use Anki's sfld column.")
        assert params[-1] == 6
        if "LIKE" in sql:
            assert params[0] == "%physics%"
        return [
            (30, "Physics topic", 100, 200),
            (20, "Already linked", 100, 200),
            (10, "Older item", 101, 201),
        ]


class _FakeLinkSearchCol:
    def __init__(self):
        self.db = _FakeLinkSearchDb()

    @property
    def models(self):
        return self

    @property
    def decks(self):
        return self

    def get(self, item_id):
        if int(item_id) in {100, 101}:
            return {"name": "Basic" if int(item_id) == 100 else "Cloze"}
        return {"name": "Default" if int(item_id) == 200 else "Archive"}


class _FakeKindCard:
    def __init__(self, note):
        self._note = note

    def note(self):
        return self._note


class _FakeKindCol:
    def __init__(self):
        self.notes = {
            10: _FakeNote(["item", "keep"]),
            20: _FakeNote(["topic"]),
        }
        self.updated_notes = []

    def get_card(self, card_id):
        if int(card_id) not in self.notes:
            raise KeyError(card_id)
        return _FakeKindCard(self.notes[int(card_id)])

    def update_note(self, note):
        self.updated_notes.append(note)


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

    def test_link_cards_to_tree_appends_multiple_children_under_parent(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
            ],
        )

        with patch.object(knowledge_tree, "card_exists", side_effect=lambda card_id: int(card_id) in {12, 13}), patch.object(
            knowledge_tree, "apply_node_kind_to_card"
        ) as apply_kind:
            result = knowledge_tree.link_cards_to_tree(
                self.addon_dir,
                "TestProfile",
                [12, 13],
                "topic",
                parent_card_id=10,
            )

        rows = db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")
        assert result["linked_card_ids"] == [12, 13]
        assert result["linked_count"] == 2
        assert result["error_count"] == 0
        assert [(row["card_id"], row["parent_card_id"], row["sort_order"]) for row in rows] == [
            (10, None, 0),
            (11, 10, 0),
            (12, 10, 1),
            (13, 10, 2),
        ]
        assert [call.args for call in apply_kind.call_args_list] == [(12, "topic"), (13, "topic")]

    def test_link_cards_to_tree_inserts_siblings_after_anchor_in_selected_order(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 20, "parent_card_id": None, "node_kind": "topic", "sort_order": 1},
                {"card_id": 30, "parent_card_id": None, "node_kind": "topic", "sort_order": 2},
            ],
        )

        with patch.object(knowledge_tree, "card_exists", side_effect=lambda card_id: int(card_id) in {40, 50}), patch.object(
            knowledge_tree, "apply_node_kind_to_card"
        ):
            result = knowledge_tree.link_cards_to_tree(
                self.addon_dir,
                "TestProfile",
                [50, 40],
                "topic",
                parent_card_id=None,
                insert_after_card_id=20,
            )

        rows = db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")
        assert result["linked_card_ids"] == [50, 40]
        assert [(row["card_id"], row["parent_card_id"], row["sort_order"]) for row in rows] == [
            (10, None, 0),
            (20, None, 1),
            (50, None, 2),
            (40, None, 3),
            (30, None, 4),
        ]

    def test_link_cards_to_tree_links_to_root_when_no_parent_is_selected(self):
        with patch.object(knowledge_tree, "card_exists", return_value=True), patch.object(
            knowledge_tree, "apply_node_kind_to_card"
        ):
            result = knowledge_tree.link_cards_to_tree(
                self.addon_dir,
                "TestProfile",
                [70, 71],
                "item",
                parent_card_id=None,
            )

        rows = db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")
        assert result["linked_count"] == 2
        assert [(row["card_id"], row["parent_card_id"], row["sort_order"]) for row in rows] == [
            (70, None, 0),
            (71, None, 1),
        ]

    def test_link_cards_to_tree_reports_partial_failures_and_keeps_valid_cards(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
            ],
        )

        def _exists(card_id):
            return int(card_id) in {10, 12}

        with patch.object(knowledge_tree, "card_exists", side_effect=_exists), patch.object(
            knowledge_tree, "apply_node_kind_to_card"
        ):
            result = knowledge_tree.link_cards_to_tree(
                self.addon_dir,
                "TestProfile",
                [10, 11, 12],
                "topic",
                parent_card_id=None,
            )

        rows = db.get_knowledge_tree_nodes(self.addon_dir, "TestProfile")
        assert result["linked_card_ids"] == [12]
        assert result["linked_count"] == 1
        assert result["error_count"] == 2
        assert result["errors"] == [
            {"card_id": 10, "error": "Card 10 is already present in the knowledge tree."},
            {"card_id": 11, "error": "Card 11 was not found in the current collection."},
        ]
        assert [(row["card_id"], row["parent_card_id"], row["sort_order"]) for row in rows] == [
            (10, None, 0),
            (12, None, 1),
        ]


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


def test_search_linkable_cards_uses_anki_sort_field_and_excludes_linked_cards():
    fake_col = _FakeLinkSearchCol()
    fake_mw = SimpleNamespace(col=fake_col)

    with patch.object(knowledge_tree, "mw", fake_mw):
        results = knowledge_tree.search_linkable_cards(
            "physics",
            exclude_card_ids={20},
            limit=2,
        )

    assert "n.sfld" in fake_col.db.queries[0]
    assert results == [
        {
            "card_id": 30,
            "title": "Physics topic",
            "note_type_name": "Basic",
            "deck_name": "Default",
        },
        {
            "card_id": 10,
            "title": "Older item",
            "note_type_name": "Cloze",
            "deck_name": "Archive",
        },
    ]


def test_apply_node_kind_to_cards_converts_multiple_cards_and_reports_errors():
    fake_col = _FakeKindCol()
    fake_mw = SimpleNamespace(col=fake_col)

    with patch.object(knowledge_tree, "mw", fake_mw):
        result = knowledge_tree.apply_node_kind_to_cards([10, 20, 10, 99], "topic")

    assert result["node_kind"] == "topic"
    assert result["changed_card_ids"] == [10, 20]
    assert result["changed_count"] == 2
    assert result["error_count"] == 1
    assert result["errors"][0]["card_id"] == 99
    assert fake_col.notes[10].tags == ["keep", "Incremento", "topic"]
    assert fake_col.notes[20].tags == ["topic", "Incremento"]
    assert len(fake_col.updated_notes) == 2


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


def test_create_card_for_node_applies_metadata_payload():
    note = MagicMock()
    note.id = 501
    note.note_type.return_value = {"did": 0}
    model = {"flds": [{"name": "Front"}]}
    fake_models = MagicMock()
    fake_models.by_name.return_value = model
    fake_decks = MagicMock()
    fake_decks.by_name.return_value = {"id": 9}
    fake_col = MagicMock(models=fake_models, decks=fake_decks)
    fake_col.new_note.return_value = note
    fake_col.add_note.return_value = 1
    fake_col.find_cards.return_value = [777]
    fake_mw = SimpleNamespace(col=fake_col)
    metadata = build_incremento_metadata(
        source_type="Knowledge Tree",
        parent="Parent Topic",
        parent_card_id=123,
    )

    with patch.object(knowledge_tree, "mw", fake_mw), patch.object(
        knowledge_tree, "ensure_incremento_metadata_fields", return_value=False
    ):
        card_id = knowledge_tree.create_card_for_node(
            "Basic",
            "Topics",
            "Child Topic",
            "topic",
            field_values={"Front": "Child Topic"},
            metadata=metadata,
        )

    assert card_id == 777
    setitem_calls = note.__setitem__.call_args_list
    assert any(call.args == ("Front", "Child Topic") for call in setitem_calls)
    assert any(call.args == (INCREMENTO_SOURCE_TYPE_FIELD, "Knowledge Tree") for call in setitem_calls)
    assert any(call.args == (INCREMENTO_PARENT_FIELD, "Parent Topic") for call in setitem_calls)
    assert any(call.args == (INCREMENTO_PARENT_CARD_ID_FIELD, "123") for call in setitem_calls)


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


class _FakeSubsetCard:
    def __init__(
        self,
        card_id: int,
        *,
        ivl: int,
        due: int,
        reps: int = 0,
        lapses: int = 0,
        queue: int = 2,
        card_type: int = 2,
    ):
        self.id = int(card_id)
        self.ivl = int(ivl)
        self.due = int(due)
        self.reps = int(reps)
        self.lapses = int(lapses)
        self.queue = int(queue)
        self.type = int(card_type)


class _FakeSubsetDb:
    def __init__(self, latest_review_by_card: dict[int, int]):
        self._latest_review_by_card = {
            int(card_id): int(review_id)
            for card_id, review_id in dict(latest_review_by_card or {}).items()
        }

    def all(self, sql: str, *params):
        if "FROM revlog" not in str(sql):
            return []
        rows = []
        for card_id in params:
            value = self._latest_review_by_card.get(int(card_id))
            if value is not None:
                rows.append((int(card_id), int(value)))
        return rows


class _FakeSubsetSched:
    def __init__(self, today: int):
        self.today = int(today)


class _FakeSubsetCol:
    def __init__(self, cards: dict[int, _FakeSubsetCard], latest_review_by_card: dict[int, int], *, today: int):
        self._cards = {int(card_id): card for card_id, card in dict(cards).items()}
        self.db = _FakeSubsetDb(latest_review_by_card)
        self.sched = _FakeSubsetSched(today)

    def get_card(self, card_id: int):
        return self._cards[int(card_id)]


class _FakeSubsetMw:
    def __init__(self, cards: dict[int, _FakeSubsetCard], latest_review_by_card: dict[int, int], *, today: int):
        self.col = _FakeSubsetCol(cards, latest_review_by_card, today=today)


class TestSubsetReviewRows:
    def setup_method(self):
        _reset_db()
        self.addon_dir = _fresh_dir()
        self.cards = {
            10: _FakeSubsetCard(10, ivl=18, due=120, reps=4, lapses=1),
            11: _FakeSubsetCard(11, ivl=7, due=130, reps=2, lapses=0),
        }
        self.latest_reviews = {
            10: 1700000000000,
            11: 1705000000000,
        }
        self.fake_mw = _FakeSubsetMw(self.cards, self.latest_reviews, today=100)
        self._patchers = [
            patch.object(knowledge_tree, "mw", self.fake_mw),
            patch.object(knowledge_tree, "get_card_metadata", side_effect=self._card_metadata),
        ]
        for patcher in self._patchers:
            patcher.start()

    def teardown_method(self):
        for patcher in reversed(self._patchers):
            patcher.stop()
        _reset_db()

    def _card_metadata(self, card_id: int, *, addon_dir=None, profile=None):
        return {
            "card_id": int(card_id),
            "note_id": int(card_id) + 1000,
            "title": "Root Topic" if int(card_id) == 10 else "Child Item",
            "deck_name": "Default",
            "note_type_name": "Basic",
            "priority": priority_manager.get_priority(self.addon_dir, "TestProfile", int(card_id)),
        }

    def test_build_subset_review_rows_returns_real_card_and_review_data(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
            ],
        )
        db.set_topic_schedule(self.addon_dir, "TestProfile", 10, 1.2, 20)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 10, 58.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 11, 82.0)

        rows = knowledge_tree.build_subset_review_rows(
            self.addon_dir,
            "TestProfile",
            10,
        )

        expected_root_due = (date.today() + timedelta(days=20)).strftime("%b %d, %Y")
        expected_child_due = (date.today() + timedelta(days=30)).strftime("%b %d, %Y")
        expected_root_last = datetime.fromtimestamp(self.latest_reviews[10] / 1000.0).strftime("%b %d, %Y")
        expected_child_last = datetime.fromtimestamp(self.latest_reviews[11] / 1000.0).strftime("%b %d, %Y")

        assert [row["card_id"] for row in rows] == [10, 11]
        assert rows[0]["display_title"] == "Root Topic"
        assert rows[1]["display_title"] == "  Child Item"
        assert rows[0]["priority"] == 58.0
        assert rows[0]["interval"] == 20
        assert rows[0]["next_review"] == expected_root_due
        assert rows[0]["last_review"] == expected_root_last
        assert rows[0]["reps"] == 4
        assert rows[0]["lapses"] == 1
        assert rows[0]["a_factor"] == 1.2
        assert rows[1]["priority"] == 82.0
        assert rows[1]["interval"] == 7
        assert rows[1]["next_review"] == expected_child_due
        assert rows[1]["last_review"] == expected_child_last
        assert rows[1]["a_factor"] is None

    def test_build_subset_review_rows_can_limit_to_selected_node_only(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
            ],
        )
        db.set_topic_schedule(self.addon_dir, "TestProfile", 10, 1.2, 20)

        rows = knowledge_tree.build_subset_review_rows(
            self.addon_dir,
            "TestProfile",
            10,
            include_descendants=False,
        )

        assert len(rows) == 1
        assert rows[0]["card_id"] == 10
