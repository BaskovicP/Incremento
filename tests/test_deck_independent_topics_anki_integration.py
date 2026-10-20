"""Topic frequency choices must have the same result in any Anki deck."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_topic_interval_ignores_deck_steps_and_caps_with_native_undo_redo():
    script = dedent(r'''
        import os
        import tempfile
        from types import SimpleNamespace

        from anki.collection import Collection
        from backend import db, session, topic_scheduler

        config = {
            "topic_card_tags": ["topic"],
            "add_card_item_tags": ["item"],
            "default_topic_a_factor": 2.0,
            "topic_maximum_interval_days": 90,
        }
        topic_scheduler._resolved_config = lambda supplied=None: config if supplied is None else supplied
        profile = "SyntheticProfile"
        topic_scheduler._active_profile = lambda: profile

        with tempfile.TemporaryDirectory(prefix="incremento-topic-decks-") as root:
            for deck_name in ("Topics", "Ordinary deck"):
                for filtered in (False, True):
                    for choice, interval in ((1, 18), (2, 20), (3, 22)):
                        case = os.path.join(root, f"{deck_name}-{filtered}-{choice}")
                        os.makedirs(case)
                        col = Collection(os.path.join(case, "synthetic.anki2"))
                        topic_scheduler._ADDON_DIR = case
                        topic_scheduler.mw = SimpleNamespace(col=col)
                        topic_scheduler.reset_topic_answer_runtime_state()
                        try:
                            home = col.decks.id(deck_name)
                            options = col.decks.config_dict_for_deck_id(home)
                            options["new"]["delays"] = [1440] * 45
                            options["rev"]["maxIvl"] = 1
                            col.decks.update_config(options)
                            col.set_config("fsrs", True)
                            note = col.new_note(col.models.by_name("Basic"))
                            note["Front"] = "Synthetic topic"
                            note["Back"] = "Synthetic content"
                            note.tags = ["topic"]
                            col.add_note(note, home)
                            cid = note.card_ids()[0]
                            db.set_topic_schedule(case, profile, cid, 2.0, 10, precise_interval=10.0)
                            if filtered:
                                session._prepare_filtered_review_deck(
                                    [cid], deck_name="Synthetic session", preserve_order=True, col=col,
                                )
                            card = col.get_card(cid)
                            before = (card.did, card.odid, card.type, card.queue, card.ivl, card.due)
                            assert topic_scheduler.is_topic_card(card)
                            assert topic_scheduler.topic_due_label(card, choice) == f"{interval}d"
                            assert topic_scheduler.prepare_topic_answer(card, choice) == 3
                            card.start_timer()
                            col.sched.answerCard(card, 3)
                            topic_scheduler.on_topic_card_answered(None, col.get_card(cid), 3)
                            final = col.get_card(cid)
                            assert (final.did, final.odid, final.type, final.queue, final.ivl) == (
                                home, 0, 2, 2, interval,
                            )
                            assert final.due == col.sched.today + interval
                            assert col.db.all("SELECT ease FROM revlog WHERE cid = ?", cid) == [[3]]
                            assert col.undo_status().undo == "Answer Card"
                            assert db.get_topic_review_history(case, profile, cid)[0]["scheduled_interval"] == interval
                            col.undo()
                            topic_scheduler.reconcile_topic_state_after_anki_operation(
                                SimpleNamespace(can_redo=bool(col.undo_status().redo))
                            )
                            restored = col.get_card(cid)
                            assert (restored.did, restored.odid, restored.type, restored.queue,
                                    restored.ivl, restored.due) == before
                            assert db.get_topic_schedule_state(case, profile, cid) == (2.0, 10.0, 10)
                            assert col.db.scalar("SELECT count() FROM revlog WHERE cid = ?", cid) == 0
                            col.redo()
                            topic_scheduler.reconcile_topic_state_after_anki_operation(
                                SimpleNamespace(can_redo=bool(col.undo_status().redo))
                            )
                            assert col.get_card(cid).ivl == interval
                            assert db.get_topic_schedule(case, profile, cid)[1] == interval
                        finally:
                            topic_scheduler.reset_topic_answer_runtime_state()
                            col.close()
                            db.close_connection()
        print("Deck-independent topic scheduling: ok")
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Deck-independent topic scheduling: ok" in result.stdout
