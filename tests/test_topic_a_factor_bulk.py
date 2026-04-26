import importlib.util
import os
from types import SimpleNamespace

import db


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


topic_bulk = _load("_incremento_topic_a_factor_bulk", "backend/topic_a_factor_bulk.py")


def teardown_function():
    db.close_connection()


def test_bulk_a_factor_preserves_existing_intervals_and_skips_non_topics(tmp_path):
    addon_dir = str(tmp_path)
    db.set_topic_schedule(addon_dir, "TestProfile", 10, 2.0, 7)
    db.set_topic_schedule(addon_dir, "TestProfile", 12, 4.0, 14)
    cards = {
        10: SimpleNamespace(id=10, topic=True),
        11: SimpleNamespace(id=11, topic=False),
        12: SimpleNamespace(id=12, topic=True),
    }

    result = topic_bulk.apply_bulk_topic_a_factor(
        addon_dir,
        "TestProfile",
        [10, 11, 12],
        1.75,
        get_card=cards.__getitem__,
        is_topic_card=lambda card: card.topic,
    )

    assert result == {"selected": 3, "updated": 2, "skipped": 1, "errors": 0}
    assert db.get_topic_schedule(addon_dir, "TestProfile", 10) == (1.75, 7)
    assert db.get_topic_schedule(addon_dir, "TestProfile", 12) == (1.75, 14)
    assert db.get_topic_schedule(addon_dir, "TestProfile", 11) == (3.5, 1)
    rows = db.get_connection(addon_dir, "TestProfile").execute(
        "SELECT card_id FROM topic_schedule ORDER BY card_id"
    ).fetchall()
    assert rows == [(10,), (12,)]


def test_bulk_a_factor_deduplicates_and_uses_default_interval_for_new_topic(tmp_path):
    addon_dir = str(tmp_path)
    calls = []
    cards = {20: SimpleNamespace(id=20, topic=True)}

    def get_card(card_id):
        calls.append(card_id)
        return cards[card_id]

    result = topic_bulk.apply_bulk_topic_a_factor(
        addon_dir,
        "TestProfile",
        ["20", 20, "bad"],
        2.12345,
        get_card=get_card,
        is_topic_card=lambda card: card.topic,
    )

    assert result == {"selected": 1, "updated": 1, "skipped": 0, "errors": 0}
    assert calls == [20]
    assert db.get_topic_schedule(addon_dir, "TestProfile", 20) == (2.123, 1)


def test_bulk_a_factor_rejects_out_of_range_value(tmp_path):
    try:
        topic_bulk.apply_bulk_topic_a_factor(
            str(tmp_path),
            "TestProfile",
            [1],
            1.0,
            get_card=lambda card_id: SimpleNamespace(id=card_id, topic=True),
            is_topic_card=lambda card: card.topic,
        )
    except ValueError as exc:
        assert "between 1.1 and 100.0" in str(exc)
    else:
        raise AssertionError("expected out-of-range A-Factor to be rejected")
