"""Tests for backend/session_selection.py shared pick-loop logic."""

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


def test_prioritized_tags_are_selected_before_scheduler_fill():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        prioritized_tags_first=["active_writing"],
    )
    queue = iter(
        [
            types.SimpleNamespace(card=999, card_type="items", tag=None, mode="random"),
        ]
    )

    def _fake_find_cards(query: str):
        if "tag:active_writing" in query and 'note:"Incremento PDF"' in query:
            return [302]
        if "tag:active_writing" in query and "deck:Topics" in query:
            return [301]
        return []

    fake_col = types.SimpleNamespace(find_cards=_fake_find_cards)

    with patch.object(session_selection, "mw", types.SimpleNamespace(col=fake_col)), patch(
        "session_selection.StatsManager", _FakeStats
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler", side_effect=lambda **_: next(queue)
    ):
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [302, 301, 999]
    assert result.picked_meta[302]["selection_stage"] == "prioritized_tags"
    assert result.picked_meta[301]["selection_stage"] == "prioritized_tags"
    assert result.picked_meta[999]["selection_stage"] == "scheduler"
    assert result.stats.session["tags"] == {"active_writing": 2}


def test_prioritized_tags_dedupe_cards_across_multiple_tags():
    cfg = SchedulerConfig(
        session_card_count=3,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        prioritized_tags_first=["alpha", "beta"],
    )

    def _fake_find_cards(query: str):
        if "tag:alpha" in query and "deck:Topics" in query:
            return [101]
        if "tag:beta" in query and "deck:Topics" in query:
            return [101, 102]
        return []

    fake_col = types.SimpleNamespace(find_cards=_fake_find_cards)

    with patch.object(session_selection, "mw", types.SimpleNamespace(col=fake_col)), patch(
        "session_selection.StatsManager", _FakeStats
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


def test_prioritized_tags_respect_session_card_count_cap():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        prioritized_tags_first=["alpha"],
    )

    def _fake_find_cards(query: str):
        if "tag:alpha" in query and "deck:Topics" in query:
            return [401, 402]
        return []

    fake_col = types.SimpleNamespace(find_cards=_fake_find_cards)

    with patch.object(session_selection, "mw", types.SimpleNamespace(col=fake_col)), patch(
        "session_selection.StatsManager", _FakeStats
    ), patch(
        "session_selection.card_utils.sort_cards_for_priority_mode",
        side_effect=lambda ids, **_: list(ids),
    ), patch(
        "session_selection.get_card_from_scheduler"
    ) as mock_get:
        result = session_selection.select_session_cards(cfg, addon_dir="/tmp/unused")

    assert result.selected_ids == [401]
    mock_get.assert_not_called()


def test_prioritized_tags_use_branch_scope_in_queries():
    cfg = SchedulerConfig(
        session_card_count=1,
        enforce_priority=False,
        scheduler_scope="session",
        use_tags=False,
        tag_weights={},
        include_rest=True,
        prioritized_tags_first=["medicine"],
        topics_filter="deck:Topics",
        items_filter="-deck:Topics",
    )
    seen_queries: list[str] = []

    def _fake_find_cards(query: str):
        seen_queries.append(query)
        if "tag:medicine" in query and "cid:10" in query:
            return [10]
        return []

    fake_col = types.SimpleNamespace(find_cards=_fake_find_cards)

    with patch.object(session_selection, "mw", types.SimpleNamespace(col=fake_col)), patch(
        "session_selection.StatsManager", _FakeStats
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
    assert any("tag:medicine" in query and "cid:10" in query and "cid:11" in query for query in seen_queries)


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
