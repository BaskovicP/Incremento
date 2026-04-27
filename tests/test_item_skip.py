from unittest.mock import MagicMock, patch

import db
import item_skip


def setup_function():
    db.close_connection()


def teardown_function():
    db.close_connection()


def _patch_item_skip_db(tmp_path):
    return patch(
        "item_skip.get_connection",
        side_effect=lambda _addon_dir, _profile="TestProfile": db.get_connection(
            str(tmp_path), "TestProfile"
        ),
    )


def test_item_skip_config_defaults():
    assert item_skip.configured_item_skip_enabled({}) is False
    assert item_skip.configured_item_skip_minutes({}) == 30


def test_item_skip_config_overrides():
    cfg = {
        "item_skip_enabled": True,
        "item_skip_minutes": 45,
    }
    assert item_skip.configured_item_skip_enabled(cfg) is True
    assert item_skip.configured_item_skip_minutes(cfg) == 45


def test_item_skip_due_label_uses_minutes():
    assert item_skip.item_skip_due_label({"item_skip_minutes": 15}) == "15m"


def test_store_timed_item_skip_writes_db_and_buries(tmp_path):
    card = MagicMock()
    card.id = 42

    with _patch_item_skip_db(tmp_path), patch("item_skip.mw") as mock_mw:
        until_ts = item_skip.store_timed_item_skip(card, minutes=30, now=1_000.0)

    assert until_ts == 2_800
    row = db.get_connection(str(tmp_path), "TestProfile").execute(
        "SELECT until_ts FROM item_postpones WHERE card_id = ?",
        (42,),
    ).fetchone()
    assert row == (2_800,)
    mock_mw.col.sched.bury_cards.assert_called_once_with([42])


def test_release_expired_timed_item_skips_clears_db_and_unburies(tmp_path):
    with _patch_item_skip_db(tmp_path), patch("item_skip.mw") as mock_mw:
        conn = db.get_connection(str(tmp_path), "TestProfile")
        conn.execute(
            "INSERT INTO item_postpones (card_id, until_ts) VALUES (?, ?)",
            (42, 100),
        )
        conn.execute(
            "INSERT INTO item_postpones (card_id, until_ts) VALUES (?, ?)",
            (43, 9_999),
        )
        conn.commit()

        restored = item_skip.release_expired_timed_item_skips(now=500.0)

    assert restored == [42]
    rows = db.get_connection(str(tmp_path), "TestProfile").execute(
        "SELECT card_id, until_ts FROM item_postpones ORDER BY card_id"
    ).fetchall()
    assert rows == [(43, 9_999)]
    mock_mw.col.sched.unbury_cards.assert_called_once_with([42])


def test_next_timed_item_skip_at_returns_earliest_future_timestamp(tmp_path):
    with _patch_item_skip_db(tmp_path):
        conn = db.get_connection(str(tmp_path), "TestProfile")
        conn.executemany(
            "INSERT INTO item_postpones (card_id, until_ts) VALUES (?, ?)",
            [(1, 100), (2, 900), (3, 700)],
        )
        conn.commit()

        assert item_skip.next_timed_item_skip_at(now=500.0) == 700
