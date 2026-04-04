import json
from unittest.mock import MagicMock, patch

import topic_postpone


def setup_function():
    topic_postpone.release_session_postponed_cards()


def test_topic_postpone_config_defaults():
    assert topic_postpone.configured_topic_postpone_enabled({}) is False
    assert topic_postpone.configured_topic_postpone_mode({}) == "timed"
    assert topic_postpone.configured_topic_postpone_minutes({}) == 30


def test_topic_postpone_config_overrides():
    cfg = {
        "topic_postpone_enabled": True,
        "topic_postpone_mode": "session",
        "topic_postpone_minutes": 45,
    }
    assert topic_postpone.configured_topic_postpone_enabled(cfg) is True
    assert topic_postpone.configured_topic_postpone_mode(cfg) == "session"
    assert topic_postpone.configured_topic_postpone_minutes(cfg) == 45


def test_topic_postpone_due_label_uses_mode():
    assert (
        topic_postpone.topic_postpone_due_label(
            {"topic_postpone_mode": "session", "topic_postpone_minutes": 15}
        )
        == "Session"
    )
    assert (
        topic_postpone.topic_postpone_due_label(
            {"topic_postpone_mode": "timed", "topic_postpone_minutes": 15}
        )
        == "15m"
    )


def test_store_timed_topic_postpone_updates_custom_data_and_buries():
    card = MagicMock()
    card.id = 42
    card.custom_data = json.dumps({"existing": 1})

    with patch("topic_postpone.mw") as mock_mw:
        until_ts = topic_postpone.store_timed_topic_postpone(
            card,
            minutes=30,
            now=1_000.0,
        )

    assert until_ts == 2_800
    payload = json.loads(card.custom_data)
    assert payload["existing"] == 1
    assert payload["_incremento_topic_postpone"]["until"] == 2_800
    mock_mw.col.update_card.assert_called_once_with(card)
    mock_mw.col.sched.bury_cards.assert_called_once_with([42])


def test_release_expired_timed_postpones_clears_and_unburies():
    expired = json.dumps(
        {
            "_incremento_topic_postpone": {"mode": "timed", "until": 100},
            "keep": "x",
        }
    )
    active = json.dumps(
        {
            "_incremento_topic_postpone": {"mode": "timed", "until": 9_999},
        }
    )
    card = MagicMock()
    card.id = 42
    card.custom_data = expired

    with patch("topic_postpone.mw") as mock_mw:
        mock_mw.col.db.all.return_value = [(42, expired), (43, active)]
        mock_mw.col.get_card.return_value = card
        restored = topic_postpone.release_expired_timed_postpones(now=500.0)

    assert restored == [42]
    payload = json.loads(card.custom_data)
    assert payload == {"keep": "x"}
    mock_mw.col.update_cards.assert_called_once()
    mock_mw.col.sched.unbury_cards.assert_called_once_with([42])


def test_session_postpone_round_trips_runtime_ids():
    card = MagicMock()
    card.id = 7

    with patch("topic_postpone.mw") as mock_mw:
        topic_postpone.postpone_topic_card_for_session(card)
        assert topic_postpone.has_session_postponed_cards() is True
        restored = topic_postpone.release_session_postponed_cards()

    assert restored == [7]
    mock_mw.col.sched.bury_cards.assert_called_once_with([7])
    mock_mw.col.sched.unbury_cards.assert_called_once_with([7])
