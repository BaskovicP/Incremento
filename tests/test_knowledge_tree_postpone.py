import re
import tempfile
from unittest.mock import patch

import db
import knowledge_tree_postpone as ktp
import priority_manager


def _fresh_dir():
    return tempfile.mkdtemp()


def _reset_db():
    db.close_connection()


class _FakeCard:
    def __init__(self, card_id: int, *, ivl: int, state: str = "due", suspended: bool = False):
        self.id = int(card_id)
        self.ivl = int(ivl)
        self.state = str(state)
        self.suspended = bool(suspended)
        self.nid = self.id + 1000


class _FakeSched:
    def __init__(self):
        self.calls: list[tuple[list[int], str]] = []

    def set_due_date(self, card_ids, due):
        self.calls.append(([int(card_id) for card_id in list(card_ids or [])], str(due)))


class _FakeCol:
    def __init__(self, cards: dict[int, _FakeCard]):
        self._cards = {int(card_id): card for card_id, card in cards.items()}
        self.sched = _FakeSched()

    def get_card(self, card_id: int):
        return self._cards[int(card_id)]

    def find_cards(self, search: str):
        search = str(search or "")
        ids = {card_id for card_id, card in self._cards.items() if not card.suspended}
        if "is:due OR is:learn" in search:
            ids = {
                card_id
                for card_id in ids
                if self._cards[card_id].state in {"due", "learn"}
            }
        requested = {int(match) for match in re.findall(r"cid:(\d+)", search)}
        if requested:
            ids &= requested
        return sorted(ids)


class _FakeMw:
    def __init__(self, cards: dict[int, _FakeCard]):
        self.col = _FakeCol(cards)


class TestKnowledgeTreePostpone:
    def setup_method(self):
        _reset_db()
        self.addon_dir = _fresh_dir()
        self.cards: dict[int, _FakeCard] = {}
        self.topic_ids: set[int] = set()
        self.fake_mw = _FakeMw(self.cards)
        self._patchers = [
            patch.object(ktp, "mw", self.fake_mw),
            patch.object(
                ktp,
                "sort_cards_for_priority_mode",
                side_effect=self._sort_by_priority,
            ),
            patch.object(
                ktp,
                "is_topic_card",
                side_effect=lambda card: int(card.id) in self.topic_ids,
            ),
            patch.object(ktp, "get_card_metadata", side_effect=self._card_metadata),
        ]
        for patcher in self._patchers:
            patcher.start()

    def teardown_method(self):
        for patcher in reversed(self._patchers):
            patcher.stop()
        _reset_db()

    def _sort_by_priority(self, card_ids, addon_dir=None, lower_is_more_important=True):
        ids = list(card_ids or [])
        return sorted(
            ids,
            key=lambda cid: (
                priority_manager.get_priority(self.addon_dir, "TestProfile", int(cid)),
                int(cid),
            ),
            reverse=not bool(lower_is_more_important),
        )

    def _card_metadata(self, card_id: int, *, addon_dir=None, profile=None):
        return {
            "card_id": int(card_id),
            "note_id": int(card_id) + 1000,
            "title": f"Card {int(card_id)}",
            "deck_name": "Default",
            "note_type_name": "Basic",
            "priority": priority_manager.get_priority(self.addon_dir, "TestProfile", int(card_id)),
        }

    def _set_cards(self, cards: list[_FakeCard], *, topic_ids: set[int] | None = None) -> None:
        self.cards.clear()
        for card in cards:
            self.cards[int(card.id)] = card
        self.fake_mw.col = _FakeCol(self.cards)
        self.topic_ids = {int(card_id) for card_id in (topic_ids or set())}

    def test_simulate_branch_postpone_filters_and_summarizes(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
            ],
        )
        db.set_topic_schedule(self.addon_dir, "TestProfile", 10, 1.2, 8)
        db.set_topic_schedule(self.addon_dir, "TestProfile", 12, 2.0, 20)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 10, 2.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 11, 20.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 12, 4.0)
        self._set_cards(
            [
                _FakeCard(10, ivl=8, state="due"),
                _FakeCard(11, ivl=10, state="due"),
                _FakeCard(12, ivl=20, state="due"),
            ],
            topic_ids={10, 12},
        )

        config = ktp.default_postpone_preset(branch_root_card_id=10)
        config["scope"] = ktp.SCOPE_SELECTED_BRANCH
        config["item"]["interval_beyond"] = 1
        config["item"]["priority_threshold"] = 1.0
        config["topic"]["interval_beyond"] = 1
        config["topic"]["priority_threshold"] = 3.0
        config["adjust"]["modify_topic_delay_by_a_factor"] = False

        summary = ktp.simulate_postpone_plan(
            self.addon_dir,
            "TestProfile",
            config,
            branch_root_card_id=10,
        )

        details = {info["card_id"]: info for info in summary["details"]}

        assert summary["elements_to_postpone"] == 2
        assert summary["average_delay_interval"] == 6.0
        assert summary["average_delay"] == 35.0
        assert summary["items_skipped"] == 0
        assert summary["topics_skipped"] == 1
        assert details[11]["delay_days"] == 2
        assert details[11]["new_interval"] == 12
        assert details[12]["delay_days"] == 10
        assert details[12]["new_interval"] == 30

    def test_apply_postpone_plan_updates_due_dates_and_topic_schedule(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                {"card_id": 12, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
            ],
        )
        db.set_topic_schedule(self.addon_dir, "TestProfile", 10, 1.2, 8)
        db.set_topic_schedule(self.addon_dir, "TestProfile", 12, 2.0, 20)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 10, 2.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 11, 20.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 12, 4.0)
        self._set_cards(
            [
                _FakeCard(10, ivl=8, state="due"),
                _FakeCard(11, ivl=10, state="due"),
                _FakeCard(12, ivl=20, state="due"),
            ],
            topic_ids={10, 12},
        )

        config = ktp.default_postpone_preset(branch_root_card_id=10)
        config["scope"] = ktp.SCOPE_SELECTED_BRANCH
        config["item"]["interval_beyond"] = 1
        config["item"]["priority_threshold"] = 1.0
        config["topic"]["interval_beyond"] = 1
        config["topic"]["priority_threshold"] = 3.0
        config["adjust"]["modify_topic_delay_by_a_factor"] = False

        summary = ktp.apply_postpone_plan(
            self.addon_dir,
            "TestProfile",
            config,
            branch_root_card_id=10,
        )

        due_calls = self.fake_mw.col.sched.calls
        topic_a_factor, topic_interval = db.get_topic_schedule(self.addon_dir, "TestProfile", 12)

        assert summary["applied_count"] == 2
        assert ([12], "30") in due_calls
        assert ([11], "12") in due_calls
        assert topic_a_factor == 2.0
        assert topic_interval == 30

    def test_simulate_postpone_plan_respects_browser_scope_ids(self):
        priority_manager.set_priority(self.addon_dir, "TestProfile", 21, 15.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 22, 30.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 23, 5.0)
        db.set_topic_schedule(self.addon_dir, "TestProfile", 22, 2.5, 12)
        self._set_cards(
            [
                _FakeCard(21, ivl=10, state="due"),
                _FakeCard(22, ivl=12, state="learn"),
                _FakeCard(23, ivl=6, state="due"),
            ],
            topic_ids={22},
        )

        config = ktp.default_postpone_preset()
        config["scope"] = ktp.SCOPE_CURRENT_BROWSER
        config["item"]["interval_beyond"] = 1
        config["topic"]["interval_beyond"] = 1
        config["item"]["postpone_count"] = 10
        config["topic"]["postpone_count"] = 10
        config["item"]["priority_threshold"] = 0.0
        config["topic"]["priority_threshold"] = 0.0

        summary = ktp.simulate_postpone_plan(
            self.addon_dir,
            "TestProfile",
            config,
            browser_card_ids=[21, 22],
        )

        assert summary["candidate_count"] == 2
        assert summary["applied_ids"] == [21, 22]

    def test_respect_settings_uses_attached_subbranch_preset(self):
        db.set_knowledge_tree_structure(
            self.addon_dir,
            "TestProfile",
            [
                {"card_id": 10, "parent_card_id": None, "node_kind": "topic", "sort_order": 0},
                {"card_id": 11, "parent_card_id": 10, "node_kind": "item", "sort_order": 0},
                {"card_id": 20, "parent_card_id": 10, "node_kind": "topic", "sort_order": 1},
                {"card_id": 21, "parent_card_id": 20, "node_kind": "item", "sort_order": 0},
            ],
        )
        priority_manager.set_priority(self.addon_dir, "TestProfile", 10, 1.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 11, 40.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 20, 2.0)
        priority_manager.set_priority(self.addon_dir, "TestProfile", 21, 50.0)
        self._set_cards(
            [
                _FakeCard(10, ivl=10, state="due"),
                _FakeCard(11, ivl=10, state="due"),
                _FakeCard(20, ivl=10, state="due"),
                _FakeCard(21, ivl=10, state="due"),
            ],
            topic_ids={10, 20},
        )

        child_config = ktp.default_postpone_preset(branch_root_card_id=20)
        child_config["scope"] = ktp.SCOPE_SELECTED_BRANCH
        child_config["item"]["delay_factor"] = 2.0
        child_config["item"]["interval_beyond"] = 1
        child_config["item"]["priority_threshold"] = 0.0
        child_config["topic"]["skip"] = True
        ktp.save_postpone_preset(
            self.addon_dir,
            "TestProfile",
            "Child Branch",
            child_config,
            branch_root_card_id=20,
        )

        root_config = ktp.default_postpone_preset(branch_root_card_id=10)
        root_config["scope"] = ktp.SCOPE_SELECTED_BRANCH
        root_config["item"]["delay_factor"] = 1.2
        root_config["item"]["interval_beyond"] = 1
        root_config["item"]["priority_threshold"] = 0.0
        root_config["topic"]["skip"] = True
        root_config["adjust"]["subbranch_mode"] = ktp.SUBTREE_MODE_RESPECT

        summary = ktp.simulate_postpone_plan(
            self.addon_dir,
            "TestProfile",
            root_config,
            branch_root_card_id=10,
        )

        details = {info["card_id"]: info for info in summary["details"]}

        assert details[11]["delay_days"] == 2
        assert details[21]["delay_days"] == 10
