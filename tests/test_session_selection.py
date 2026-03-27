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
