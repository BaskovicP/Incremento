"""Tests for backend/session_selection.py shared pick-loop logic."""

import copy
import types
from unittest.mock import patch

import session_selection
from scheduler_config import SchedulerConfig


class _FakeStats:
    def __init__(self, *_args, **_kwargs):
        self.session = {"type": {}, "tags": {}, "mode": {}}
        self.daily = {"type": {}, "tags": {}, "mode": {}}
        self.lifetime = {"type": {}, "tags": {}, "mode": {}}
        self.session_time = {"type": {}, "tags": {}}

    def counts_for(self, scope: str) -> dict:
        if scope == "session":
            return self.session
        if scope == "daily":
            return self.daily
        if scope == "lifetime":
            return self.lifetime
        raise ValueError(scope)


def test_soft_mode_selection_tracks_counts_and_meta():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
    )
    queue = iter(
        [
            types.SimpleNamespace(card=10, card_type="items", tag=None, mode="random"),
            types.SimpleNamespace(card=11, card_type="topics", tag="math", mode="priority"),
            types.SimpleNamespace(card=12, card_type="pdf", tag=None, mode="random"),
        ]
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler", side_effect=lambda **_: next(queue)
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [10, 11, 12]
    assert result.picked_meta[11]["tag"] == "math"
    assert result.stats.session["type"] == {"items": 1, "topics": 1, "pdf": 1}
    assert result.stats.session["mode"] == {"random": 2, "priority": 1}
    assert result.stats.session["tags"] == {"math": 1}


def test_strict_content_type_phase_forces_requested_card_type():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=True,
        phase_order=["content_types"],
        phases_enabled={"content_types": True},
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        content_type_weights={"pdf": 1.0},
    )
    calls: list[str | None] = []
    queue = iter(
        [
            types.SimpleNamespace(card=201, card_type="pdf", tag=None, mode="random"),
            types.SimpleNamespace(card=202, card_type="pdf", tag=None, mode="priority"),
        ]
    )

    def _fake_get(**kwargs):
        calls.append(kwargs.get("force_card_type"))
        return next(queue)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler", side_effect=_fake_get
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [201, 202]
    assert calls == ["pdf", "pdf"]


def test_priority_direction_is_forwarded_to_scheduler():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        priority_lower_is_more_important=False,
    )
    captured = {}

    def _fake_get(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(card=10, card_type="items", tag=None, mode="priority")

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler", side_effect=_fake_get
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [10]
    assert captured["priority_lower_is_more_important"] is False
    assert captured["addon_dir"] == "/tmp/unused"


def test_lifetime_scope_uses_working_copy_but_keeps_session_snapshot():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=False,
        scheduler_scope="lifetime",
        use_tags=False,
        tag_weights={},
        include_rest=True,
    )
    queue = iter(
        [
            types.SimpleNamespace(card=21, card_type="topics", tag="math", mode="priority"),
            types.SimpleNamespace(card=22, card_type="items", tag=None, mode="random"),
        ]
    )
    captured_counts = []

    def _fake_get(**kwargs):
        captured_counts.append(kwargs["counts"])
        return next(queue)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler", side_effect=_fake_get
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [21, 22]
    assert result.stats.session["type"] == {"topics": 1, "items": 1}
    assert result.stats.session["tags"] == {"math": 1}
    assert result.stats.lifetime == {"type": {}, "tags": {}, "mode": {}}
    assert captured_counts[0] is not result.stats.lifetime


def test_branch_scope_restricts_all_scheduler_pools_to_subtree_card_ids():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        topics_filter="deck:Topics",
        items_filter="-deck:Topics",
    )
    captured = {}

    def _fake_get(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(card=10, card_type="items", tag=None, mode="priority")

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler", side_effect=_fake_get
    ):
        result = session_selection.select_session_cards(
            cfg,
            addon_dir="/tmp/unused",
            branch_scope={
                "root_card_id": 10,
                "root_title": "Medicine",
                "card_ids": [10, 11, 12],
            },
        )

    assert result.selected_ids == [10]
    assert "cid:10" in captured["topics_filter"]
    assert "cid:11" in captured["topics_filter"]
    assert "cid:12" in captured["items_filter"]
    assert "cid:10" in captured["pdf_filter"]
    assert "cid:10" in captured["youtube_filter"]
    assert "cid:10" in captured["webpage_filter"]


def test_empty_branch_scope_returns_no_selected_cards():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler"
    ) as mock_get:
        result = session_selection.select_session_cards(
            cfg,
            addon_dir="/tmp/unused",
            branch_scope={"root_card_id": 10, "root_title": "Medicine", "card_ids": []},
        )

    assert result.selected_ids == []
    mock_get.assert_not_called()


def test_ordered_priority_tags_are_selected_before_scheduler_fill():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"active_writing": 2 / 3},
        include_rest=True,
        priority_order_enabled=True,
        priority_order_entries=[{"kind": "tag", "value": "active_writing", "order": 1}],
    )
    queue = iter(
        [
            types.SimpleNamespace(card=999, card_type="items", tag=None, mode="random"),
        ]
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[302],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        return_value=[301],
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler", side_effect=lambda **_: next(queue)
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [302, 301, 999]
    assert result.picked_meta[302]["selection_stage"] == "ordered_priority"
    assert result.picked_meta[302]["priority_order"] == 1
    assert result.picked_meta[301]["selection_stage"] == "ordered_priority"
    assert result.picked_meta[999]["selection_stage"] == "scheduler"
    assert result.stats.session["tags"] == {"active_writing": 2}


def test_ordered_priority_tiers_run_in_ascending_order():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"first": 0.5, "second": 0.5},
        include_rest=True,
        priority_order_enabled=True,
        priority_order_entries=[
            {"kind": "tag", "value": "second", "order": 2},
            {"kind": "tag", "value": "first", "order": 1},
        ],
    )

    def _fake_topics(tag, **_kwargs):
        if tag == "first":
            return [201]
        if tag == "second":
            return [101]
        return []

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        side_effect=_fake_topics,
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [201, 101]
    assert result.picked_meta[201]["priority_order"] == 1
    assert result.picked_meta[101]["priority_order"] == 2


def test_ordered_priority_content_types_work_before_normal_scheduling():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        content_type_weights={"pdf": 0.5},
        priority_order_enabled=True,
        priority_order_entries=[{"kind": "content_type", "value": "pdf", "order": 1}],
    )
    queue = iter(
        [
            types.SimpleNamespace(card=999, card_type="items", tag=None, mode="random"),
        ]
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_all_pdf_cards",
        return_value=[501],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=lambda **_: next(queue),
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [501, 999]
    assert result.picked_meta[501]["card_type"] == "pdf"
    assert result.picked_meta[501]["selection_stage"] == "ordered_priority"


def test_ordered_priority_entries_are_ignored_when_disabled():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        priority_order_enabled=False,
        priority_order_entries=[{"kind": "tag", "value": "alpha", "order": 1}],
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_topic_cards_by_tag"
    ) as mock_tag_pool, patch(
        "session_selection.get_card_from_scheduler",
        return_value=types.SimpleNamespace(card=999, card_type="items", tag=None, mode="random"),
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [999]
    mock_tag_pool.assert_not_called()


def test_ordered_priority_tags_dedupe_cards_across_multiple_tags():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"alpha": 1 / 3, "beta": 1 / 3},
        include_rest=True,
        priority_order_enabled=True,
        priority_order_entries=[
            {"kind": "tag", "value": "alpha", "order": 1},
            {"kind": "tag", "value": "beta", "order": 1},
        ],
    )

    def _fake_topics(tag, **_kwargs):
        if tag == "alpha":
            return [101]
        if tag == "beta":
            return [101, 102]
        return []

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        side_effect=_fake_topics,
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler",
        return_value=types.SimpleNamespace(card=None, card_type=None, tag=None, mode=None),
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [101, 102]
    assert result.picked_meta[101]["tag"] == "alpha"
    assert result.picked_meta[102]["tag"] == "beta"


def test_ordered_priority_same_tier_tag_and_content_dedupe_and_priority_sort():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"alpha": 1 / 3},
        include_rest=True,
        content_type_weights={"pdf": 2 / 3},
        priority_order_enabled=True,
        priority_order_entries=[
            {"kind": "content_type", "value": "pdf", "order": 1},
            {"kind": "tag", "value": "alpha", "order": 1},
        ],
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_all_pdf_cards",
        return_value=[301, 302],
    ), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[302],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        return_value=[303],
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: sorted(ids, reverse=True),
    ), patch(
        "session_selection.get_card_from_scheduler",
        return_value=types.SimpleNamespace(card=None, card_type=None, tag=None, mode=None),
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [303, 302, 301]
    assert result.selected_ids.count(302) == 1
    assert result.picked_meta[303]["tag"] == "alpha"
    assert result.picked_meta[302]["card_type"] == "pdf"


def test_ordered_priority_respects_session_card_count_cap():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"alpha": 1.0},
        include_rest=True,
        priority_order_enabled=True,
        priority_order_entries=[{"kind": "tag", "value": "alpha", "order": 1}],
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        return_value=[401, 402],
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler"
    ) as mock_get:
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [401]
    mock_get.assert_not_called()


def test_ordered_priority_tags_use_branch_scope_in_queries():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"medicine": 1.0},
        include_rest=True,
        priority_order_enabled=True,
        priority_order_entries=[{"kind": "tag", "value": "medicine", "order": 1}],
        topics_filter="deck:Topics",
        items_filter="-deck:Topics",
    )
    seen_kwargs: list[dict] = []

    def _fake_topics(tag, **kwargs):
        seen_kwargs.append({"tag": tag, **kwargs})
        return [10] if tag == "medicine" else []

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        side_effect=_fake_topics,
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ):
        result = session_selection.select_session_cards(
            cfg,
            addon_dir="/tmp/unused",
            branch_scope={"root_card_id": 10, "root_title": "Medicine", "card_ids": [10, 11]},
        )

    assert result.selected_ids == [10]
    assert any(
        entry["tag"] == "medicine"
        and "cid:10" in entry["topics_filter"]
        and "cid:11" in entry["topics_filter"]
        for entry in seen_kwargs
    )


def test_ordered_priority_tag_frontloads_only_its_configured_share():
    cfg = SchedulerConfig(
        session_card_count=5,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"writing": 0.4},
        include_rest=True,
        priority_order_enabled=True,
        priority_order_entries=[{"kind": "tag", "value": "writing", "order": 1}],
    )
    queue = iter(
        [
            types.SimpleNamespace(card=901, card_type="items", tag=None, mode="random"),
            types.SimpleNamespace(card=902, card_type="items", tag=None, mode="random"),
            types.SimpleNamespace(card=903, card_type="items", tag=None, mode="random"),
        ]
    )

    scheduler_calls = []

    def _fake_scheduler(**kwargs):
        scheduler_calls.append(kwargs)
        return next(queue)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        return_value=[801, 802, 803, 804],
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler", side_effect=_fake_scheduler
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [801, 802, 901, 902, 903]
    assert result.picked_meta[801]["selection_stage"] == "ordered_priority"
    assert result.picked_meta[802]["selection_stage"] == "ordered_priority"
    assert result.picked_meta[901]["selection_stage"] == "scheduler"
    assert 803 not in result.selected_ids
    assert 804 not in result.selected_ids
    assert scheduler_calls
    assert scheduler_calls[0]["tag_weights"] == {}
    assert "-tag:writing" in scheduler_calls[0]["topics_filter"]
    assert "-tag:writing" in scheduler_calls[0]["items_filter"]


def test_ordered_priority_tag_quota_matches_content_estimate_total():
    cfg = SchedulerConfig(
        session_card_count=50,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"writing": 0.41, "ai": 0.59},
        include_rest=True,
        pdf_rate=0.54,
        topics_rate=9 / 23,
        priority_order_enabled=True,
        priority_order_entries=[{"kind": "tag", "value": "writing", "order": 1}],
    )
    writing_ids = list(range(1000, 1030))
    fill_ids = iter(
        types.SimpleNamespace(card=card_id, card_type="items", tag="ai", mode="random")
        for card_id in range(2000, 2029)
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=writing_ids,
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=lambda **_: next(fill_ids),
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids[:21] == writing_ids[:21]
    assert result.picked_meta[writing_ids[20]]["selection_stage"] == "ordered_priority"
    assert result.picked_meta[2000]["selection_stage"] == "scheduler"
    assert writing_ids[21] not in result.selected_ids
    assert result.stats.session["tags"]["writing"] == 21


def test_topic_tagged_cards_can_enter_topic_pool_without_topics_deck_filter():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        topics_filter="",
        items_filter="",
    )
    captured = {}

    def _fake_get(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(card=777, card_type="topics", tag=None, mode="priority")

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=_fake_get,
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [777]
    assert captured["topics_filter"] == ""
    assert captured["items_filter"] == ""


def test_soft_mode_keeps_trying_after_a_scheduler_miss():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
    )
    queue = iter(
        [
            types.SimpleNamespace(card=None, card_type="items", tag=None, mode="priority"),
            types.SimpleNamespace(card=501, card_type="items", tag=None, mode="priority"),
            types.SimpleNamespace(card=502, card_type="topics", tag="writing", mode="random"),
        ]
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler", side_effect=lambda **_: next(queue)
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [501, 502]
    assert result.picked_meta[501]["selection_stage"] == "scheduler"
    assert result.picked_meta[502]["selection_stage"] == "scheduler"


def test_ordered_priority_quota_continues_across_repeated_pick_until_calls():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"writing": 2 / 3},
        include_rest=True,
        priority_order_enabled=True,
        priority_order_entries=[{"kind": "tag", "value": "writing", "order": 1}],
    )
    queue = iter(
        [
            types.SimpleNamespace(card=900, card_type="items", tag=None, mode="random"),
        ]
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.card_utils.get_pdf_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_topic_cards_by_tag",
        return_value=[101, 102, 103],
    ), patch(
        "session_selection.card_utils.get_item_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_youtube_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.get_webpage_cards_by_tag",
        return_value=[],
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=lambda **_: next(queue),
    ):
        picker = session_selection.SessionPicker(cfg, addon_dir="/tmp/unused")
        assert picker.pick_until(2) == [101, 900]
        assert picker.pick_until(3) == [102]

    assert picker.selected_ids == [101, 900, 102]
    assert picker.picked_meta[101]["selection_stage"] == "ordered_priority"
    assert picker.picked_meta[102]["selection_stage"] == "ordered_priority"


def test_strict_content_type_quota_continues_across_refill_calls():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=True,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        phase_order=["content_types"],
        phases_enabled={"content_types": True},
        content_type_weights={"pdf": 1.0},
    )
    calls = []
    queue = iter(
        [
            types.SimpleNamespace(card=501, card_type="pdf", tag=None, mode="random"),
            types.SimpleNamespace(card=502, card_type="pdf", tag=None, mode="priority"),
        ]
    )

    def _fake_get(**kwargs):
        calls.append(kwargs.get("force_card_type"))
        return next(queue)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=_fake_get,
    ):
        picker = session_selection.SessionPicker(cfg, addon_dir="/tmp/unused")
        assert picker.pick_until(1) == [501]
        assert picker.pick_until(2) == [502]

    assert calls == ["pdf", "pdf"]


def test_strict_tag_quota_continues_cumulatively():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=True,
        scheduler_scope="session",
        use_tags=True,
        tag_weights={"alpha": 1.0},
        include_rest=True,
        phase_order=["tags"],
        phases_enabled={"tags": True},
    )
    calls = []
    queue = iter(
        [
            types.SimpleNamespace(card=601, card_type="topics", tag="alpha", mode="priority"),
            types.SimpleNamespace(card=602, card_type="topics", tag="alpha", mode="priority"),
        ]
    )

    def _fake_get(**kwargs):
        calls.append(dict(kwargs.get("tag_weights") or {}))
        return next(queue)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=_fake_get,
    ):
        picker = session_selection.SessionPicker(cfg, addon_dir="/tmp/unused")
        assert picker.pick_until(1) == [601]
        assert picker.pick_until(2) == [602]

    assert calls == [{"alpha": 1.0}, {"alpha": 1.0}]


def test_strict_type_and_mode_quotas_continue_cumulatively():
    type_cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=True,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        phase_order=["type"],
        phases_enabled={"type": True},
        topics_rate=1.0,
    )
    mode_cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=True,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        phase_order=["mode"],
        phases_enabled={"mode": True},
        random_rate=0.0,
    )
    type_calls = []
    mode_calls = []
    type_queue = iter(
        [
            types.SimpleNamespace(card=701, card_type="topics", tag=None, mode="random"),
            types.SimpleNamespace(card=702, card_type="topics", tag=None, mode="random"),
        ]
    )
    mode_queue = iter(
        [
            types.SimpleNamespace(card=801, card_type="items", tag=None, mode="priority"),
            types.SimpleNamespace(card=802, card_type="items", tag=None, mode="priority"),
        ]
    )

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=lambda **kwargs: type_calls.append(kwargs.get("force_card_type")) or next(type_queue),
    ):
        picker = session_selection.SessionPicker(type_cfg, addon_dir="/tmp/unused")
        assert picker.pick_until(1) == [701]
        assert picker.pick_until(2) == [702]

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=lambda **kwargs: mode_calls.append(kwargs.get("force_mode")) or next(mode_queue),
    ):
        picker = session_selection.SessionPicker(mode_cfg, addon_dir="/tmp/unused")
        assert picker.pick_until(1) == [801]
        assert picker.pick_until(2) == [802]

    assert type_calls == ["topics", "topics"]
    assert mode_calls == ["priority", "priority"]


def test_soft_mode_continues_from_prior_scheduler_counts():
    cfg = SchedulerConfig(
        session_card_count=2,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
    )
    seen_counts = []
    queue = iter(
        [
            types.SimpleNamespace(card=901, card_type="topics", tag=None, mode="random"),
            types.SimpleNamespace(card=902, card_type="items", tag=None, mode="priority"),
        ]
    )

    def _fake_get(**kwargs):
        seen_counts.append(copy.deepcopy(kwargs["counts"]))
        return next(queue)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=_fake_get,
    ):
        picker = session_selection.SessionPicker(cfg, addon_dir="/tmp/unused")
        assert picker.pick_until(1) == [901]
        assert picker.pick_until(2) == [902]

    assert seen_counts[0]["type"] == {}
    assert seen_counts[1]["type"] == {"topics": 1}


def test_pick_next_prevents_duplicates_across_many_calls():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
    )

    def _fake_get(**kwargs):
        exclude_ids = set(kwargs.get("exclude_ids") or set())
        if 701 not in exclude_ids:
            return types.SimpleNamespace(card=701, card_type="items", tag=None, mode="random")
        if 702 not in exclude_ids:
            return types.SimpleNamespace(card=702, card_type="items", tag=None, mode="random")
        return types.SimpleNamespace(card=None, card_type=None, tag=None, mode=None)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=_fake_get,
    ):
        picker = session_selection.SessionPicker(cfg, addon_dir="/tmp/unused")
        assert picker.pick_next() == 701
        assert picker.pick_next() == 702
        assert picker.pick_next() is None

    assert picker.selected_ids == [701, 702]


def test_snapshot_restore_reproduces_continued_picking():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
    )

    def _fake_get(**kwargs):
        exclude_ids = set(kwargs.get("exclude_ids") or set())
        for cid, card_type in ((801, "topics"), (802, "items"), (803, "pdf")):
            if cid not in exclude_ids:
                return types.SimpleNamespace(card=cid, card_type=card_type, tag=None, mode="random")
        return types.SimpleNamespace(card=None, card_type=None, tag=None, mode=None)

    with patch("session_selection.StatsManager", _FakeStats), patch(
        "session_selection.get_card_from_scheduler",
        side_effect=_fake_get,
    ):
        picker = session_selection.SessionPicker(cfg, addon_dir="/tmp/unused")
        assert picker.pick_until(2) == [801, 802]
        snapshot = picker.snapshot()

        restored = session_selection.SessionPicker(
            cfg,
            addon_dir="/tmp/unused",
            snapshot=snapshot,
        )
        assert restored.pick_until(3) == [803]

    assert restored.selected_ids == [801, 802, 803]
