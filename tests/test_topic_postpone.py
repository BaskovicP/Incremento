from unittest.mock import MagicMock, patch

import db
import topic_postpone


def setup_function():
    topic_postpone.release_session_postponed_cards()
    db.close_connection()


def teardown_function():
    db.close_connection()


def _patch_topic_postpone_db(tmp_path):
    return patch("topic_postpone.get_connection", side_effect=lambda _addon_dir, _profile="TestProfile": db.get_connection(str(tmp_path), "TestProfile"))


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


def test_store_timed_topic_postpone_writes_db_and_buries(tmp_path):
    card = MagicMock()
    card.id = 42

    with _patch_topic_postpone_db(tmp_path), patch("topic_postpone.mw") as mock_mw:
        until_ts = topic_postpone.store_timed_topic_postpone(
            card,
            minutes=30,
            now=1_000.0,
        )

    assert until_ts == 2_800
    row = db.get_connection(str(tmp_path), "TestProfile").execute(
        "SELECT until_ts FROM topic_postpones WHERE card_id = ?",
        (42,),
    ).fetchone()
    assert row == (2_800,)
    mock_mw.col.sched.bury_cards.assert_called_once_with([42])


def test_release_expired_timed_postpones_clears_db_and_unburies(tmp_path):
    with _patch_topic_postpone_db(tmp_path), patch("topic_postpone.mw") as mock_mw:
        conn = db.get_connection(str(tmp_path), "TestProfile")
        conn.execute(
            "INSERT INTO topic_postpones (card_id, until_ts) VALUES (?, ?)",
            (42, 100),
        )
        conn.execute(
            "INSERT INTO topic_postpones (card_id, until_ts) VALUES (?, ?)",
            (43, 9_999),
        )
        conn.commit()

        restored = topic_postpone.release_expired_timed_postpones(now=500.0)

    assert restored == [42]
    rows = db.get_connection(str(tmp_path), "TestProfile").execute(
        "SELECT card_id, until_ts FROM topic_postpones ORDER BY card_id"
    ).fetchall()
    assert rows == [(43, 9_999)]
    mock_mw.col.sched.unbury_cards.assert_called_once_with([42])


def test_next_timed_postpone_at_returns_earliest_future_timestamp(tmp_path):
    with _patch_topic_postpone_db(tmp_path):
        conn = db.get_connection(str(tmp_path), "TestProfile")
        conn.executemany(
            "INSERT INTO topic_postpones (card_id, until_ts) VALUES (?, ?)",
            [(1, 100), (2, 900), (3, 700)],
        )
        conn.commit()

        assert topic_postpone.next_timed_postpone_at(now=500.0) == 700


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
