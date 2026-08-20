"""Real-Anki regression coverage for topic interval overrides and undo/redo."""

from __future__ import annotations

import os
import subprocess
import sys
from textwrap import dedent


def test_real_anki_topic_override_is_one_undoable_good_answer():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import os
        import sys
        import tempfile
        import time
        from types import SimpleNamespace

        from anki.collection import Collection

        sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
        import db
        import custom_schedule
        import topic_scheduler


        def make_collection(label):
            path = os.path.join(tempfile.mkdtemp(), f"{label}.anki2")
            col = Collection(path)
            deck_id = col.decks.id("Topics")
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = label
            note["Back"] = "answer"
            col.add_note(note, deck_id)
            return col, note.card_ids()[0], deck_id


        def answer_good_and_override(col, card_id, interval=12):
            card = col.get_card(card_id)
            card.start_timer()
            col.sched.answerCard(card, 3)
            answer_step = col.undo_status().last_step
            topic_scheduler.mw = SimpleNamespace(col=col)
            topic_scheduler._apply_topic_interval_to_anki_card(
                card_id,
                interval,
                answer_undo_step=answer_step,
            )

            final = col.get_card(card_id)
            assert (final.type, final.queue, final.ivl) == (2, 2, interval)
            assert final.due - col.sched.today == interval
            assert col.undo_status().undo == "Answer Card"
            assert col.db.scalar(
                "SELECT count() FROM revlog WHERE cid = ? AND ease = 3",
                card_id,
            ) == 1
            assert col.db.scalar(
                "SELECT count() FROM revlog WHERE cid = ? AND type = 4",
                card_id,
            ) == 0

            col.undo()
            undone = col.get_card(card_id)
            col.redo()
            redone = col.get_card(card_id)
            assert (redone.type, redone.queue, redone.ivl) == (2, 2, interval)
            assert redone.due - col.sched.today == interval
            assert col.db.scalar(
                "SELECT count() FROM revlog WHERE cid = ?",
                card_id,
            ) == 1
            return undone


        col, card_id, _deck_id = make_collection("new")
        undone = answer_good_and_override(col, card_id)
        assert (undone.type, undone.queue, undone.ivl) == (0, 0, 0)
        col.close()

        col, card_id, _deck_id = make_collection("review")
        card = col.get_card(card_id)
        card.type = 2
        card.queue = 2
        card.due = col.sched.today
        card.ivl = 10
        col.update_card(card)
        undone = answer_good_and_override(col, card_id)
        assert (undone.type, undone.queue, undone.ivl) == (2, 2, 10)
        col.close()

        col, card_id, _deck_id = make_collection("relearning")
        card = col.get_card(card_id)
        card.type = 3
        card.queue = 1
        card.due = int(time.time()) - 1
        card.ivl = 10
        card.left = 1001
        col.update_card(card)
        undone = answer_good_and_override(col, card_id)
        assert (undone.type, undone.queue, undone.ivl, undone.left) == (3, 1, 10, 1001)
        col.close()

        col, card_id, home_deck_id = make_collection("filtered")
        card = col.get_card(card_id)
        card.type = 2
        card.queue = 2
        card.due = col.sched.today
        card.ivl = 10
        col.update_card(card)
        filtered_deck_id = col.decks.new_filtered("Incremento Integration")
        filtered = col.decks.get(filtered_deck_id)
        filtered["terms"] = [[f"cid:{card_id}", 100, 0]]
        filtered["resched"] = True
        col.decks.save(filtered)
        assert col.sched.rebuild_filtered_deck(filtered_deck_id).count == 1
        filtered_card = col.get_card(card_id)
        assert filtered_card.odid == home_deck_id
        answer_good_and_override(col, card_id)
        final = col.get_card(card_id)
        assert final.did == home_deck_id
        assert final.odid == 0
        col.close()

        # Exercise the complete topic hook plus Incremento DB reconciliation.
        addon_dir = tempfile.mkdtemp()
        profile = "IntegrationProfile"
        topic_scheduler._ADDON_DIR = addon_dir
        topic_scheduler._active_profile = lambda: profile
        topic_scheduler.is_topic_card = lambda _card: True
        col, card_id, _deck_id = make_collection("complete-hook")
        topic_scheduler.mw = SimpleNamespace(col=col)
        rule = db.set_custom_schedule_rule(
            addon_dir,
            profile,
            card_id,
            mode="one_time",
            interval_value=2,
            interval_unit="days",
        )
        assert rule["mode"] == "one_time"
        card = col.get_card(card_id)
        card.start_timer()
        assert topic_scheduler.prepare_topic_answer(card, 1) == 3
        col.sched.answerCard(card, 3)
        topic_scheduler.on_topic_card_answered(None, col.get_card(card_id), 3)
        final = col.get_card(card_id)
        assert (final.type, final.queue, final.ivl) == (2, 2, 2)
        history = db.get_topic_review_history(addon_dir, profile, card_id)
        assert len(history) == 1
        assert history[0]["choice"] == "more"
        assert history[0]["anki_ease"] == 3
        assert history[0]["custom_schedule_mode"] == "one_time"
        assert history[0]["consumed_one_time"] is True
        assert db.get_custom_schedule_rule(addon_dir, profile, card_id) is None

        col.undo()
        topic_scheduler.reconcile_topic_state_after_anki_operation(
            SimpleNamespace(can_redo=bool(col.undo_status().redo))
        )
        assert db.topic_schedule_exists(addon_dir, profile, card_id) is False
        assert db.get_custom_schedule_rule(addon_dir, profile, card_id)["mode"] == "one_time"

        col.redo()
        topic_scheduler.reconcile_topic_state_after_anki_operation(
            SimpleNamespace(can_redo=bool(col.undo_status().redo))
        )
        assert db.get_topic_schedule(addon_dir, profile, card_id) == (3.15, 2)
        assert db.get_custom_schedule_rule(addon_dir, profile, card_id) is None
        col.close()
        db.close_connection()

        # Non-topic custom schedules use the same Answer Card transaction.
        addon_dir = tempfile.mkdtemp()
        profile = "CustomIntegrationProfile"
        custom_schedule._ADDON_DIR = addon_dir
        custom_schedule._active_profile = lambda: profile
        custom_schedule.is_topic_card = lambda _card: False
        custom_schedule.mw = SimpleNamespace()
        col, card_id, _deck_id = make_collection("custom-complete-hook")
        custom_schedule.mw.col = col
        custom_schedule.reset_custom_schedule_answer_runtime_state()
        rule = db.set_custom_schedule_rule(
            addon_dir,
            profile,
            card_id,
            mode="one_time",
            interval_value=2,
            interval_unit="days",
        )
        assert rule["mode"] == "one_time"
        card = col.get_card(card_id)
        custom_schedule.prepare_custom_schedule_answer(card)
        card.start_timer()
        col.sched.answerCard(card, 3)
        custom_schedule.apply_custom_schedule_after_answer(
            None,
            col.get_card(card_id),
            3,
        )
        final = col.get_card(card_id)
        assert (final.type, final.queue, final.ivl) == (2, 2, 2)
        assert final.due - col.sched.today == 2
        assert col.undo_status().undo == "Answer Card"
        assert col.db.scalar(
            "SELECT count() FROM revlog WHERE cid = ? AND ease = 3",
            card_id,
        ) == 1
        assert col.db.scalar(
            "SELECT count() FROM revlog WHERE cid = ? AND type = 4",
            card_id,
        ) == 0
        assert db.get_connection(addon_dir, profile).execute(
            "SELECT scheduled_interval FROM custom_schedule_review_history "
            "WHERE card_id = ?",
            (card_id,),
        ).fetchone()[0] == 2
        assert db.get_custom_schedule_rule(addon_dir, profile, card_id) is None

        col.undo()
        custom_schedule.reconcile_custom_schedule_state_after_anki_operation(
            SimpleNamespace(can_redo=bool(col.undo_status().redo))
        )
        undone = col.get_card(card_id)
        assert (undone.type, undone.queue, undone.ivl) == (0, 0, 0)
        restored = db.get_custom_schedule_rule(addon_dir, profile, card_id)
        assert restored is not None
        assert restored["mode"] == "one_time"

        col.redo()
        custom_schedule.reconcile_custom_schedule_state_after_anki_operation(
            SimpleNamespace(can_redo=bool(col.undo_status().redo))
        )
        redone = col.get_card(card_id)
        assert (redone.type, redone.queue, redone.ivl) == (2, 2, 2)
        assert redone.due - col.sched.today == 2
        assert db.get_custom_schedule_rule(addon_dir, profile, card_id) is None
        col.close()
        db.close_connection()

        # A non-rescheduling filtered deck is Anki Preview: Incremento must
        # record neither a topic transition nor consume the one-time rule.
        addon_dir = tempfile.mkdtemp()
        profile = "TopicPreviewProfile"
        topic_scheduler._ADDON_DIR = addon_dir
        topic_scheduler._active_profile = lambda: profile
        topic_scheduler.is_topic_card = lambda _card: True
        topic_scheduler.reset_topic_answer_runtime_state()
        col, card_id, home_deck_id = make_collection("topic-preview")
        topic_scheduler.mw = SimpleNamespace(col=col)
        card = col.get_card(card_id)
        card.type = 2
        card.queue = 2
        card.due = col.sched.today + 10
        card.ivl = 10
        col.update_card(card)
        original_due = card.due
        original_ivl = card.ivl
        rule = db.set_custom_schedule_rule(
            addon_dir,
            profile,
            card_id,
            mode="one_time",
            interval_value=2,
            interval_unit="days",
        )
        filtered_deck_id = col.decks.new_filtered("Incremento Topic Preview")
        filtered = col.decks.get(filtered_deck_id)
        filtered["terms"] = [[f"cid:{card_id}", 100, 0]]
        filtered["resched"] = False
        col.decks.save(filtered)
        assert col.sched.rebuild_filtered_deck(filtered_deck_id).count == 1
        preview_card = col.get_card(card_id)
        assert preview_card.odid == home_deck_id
        preview_card.start_timer()
        assert topic_scheduler.prepare_topic_answer(preview_card, 1) == 3
        col.sched.answerCard(preview_card, 3)
        topic_scheduler.on_topic_card_answered(None, col.get_card(card_id), 3)
        final = col.get_card(card_id)
        assert (final.did, final.odid, final.ivl, final.due) == (
            home_deck_id,
            0,
            original_ivl,
            original_due,
        )
        assert col.db.scalar(
            "SELECT count() FROM revlog WHERE cid = ? AND type = 3",
            card_id,
        ) == 1
        assert db.get_topic_review_history(addon_dir, profile, card_id) == []
        assert db.topic_schedule_exists(addon_dir, profile, card_id) is False
        assert db.get_custom_schedule_rule(addon_dir, profile, card_id)["revision"] == rule["revision"]
        topic_scheduler.reset_topic_answer_runtime_state()
        col.close()
        db.close_connection()

        # The same Preview contract applies to non-topic custom schedules.
        addon_dir = tempfile.mkdtemp()
        profile = "CustomPreviewProfile"
        custom_schedule._ADDON_DIR = addon_dir
        custom_schedule._active_profile = lambda: profile
        custom_schedule.is_topic_card = lambda _card: False
        custom_schedule.reset_custom_schedule_answer_runtime_state()
        col, card_id, home_deck_id = make_collection("custom-preview")
        custom_schedule.mw = SimpleNamespace(col=col)
        card = col.get_card(card_id)
        card.type = 2
        card.queue = 2
        card.due = col.sched.today + 10
        card.ivl = 10
        col.update_card(card)
        original_due = card.due
        original_ivl = card.ivl
        rule = db.set_custom_schedule_rule(
            addon_dir,
            profile,
            card_id,
            mode="one_time",
            interval_value=4,
            interval_unit="days",
        )
        filtered_deck_id = col.decks.new_filtered("Incremento Custom Preview")
        filtered = col.decks.get(filtered_deck_id)
        filtered["terms"] = [[f"cid:{card_id}", 100, 0]]
        filtered["resched"] = False
        col.decks.save(filtered)
        assert col.sched.rebuild_filtered_deck(filtered_deck_id).count == 1
        preview_card = col.get_card(card_id)
        custom_schedule.prepare_custom_schedule_answer(preview_card)
        preview_card.start_timer()
        col.sched.answerCard(preview_card, 3)
        custom_schedule.apply_custom_schedule_after_answer(
            None,
            col.get_card(card_id),
            3,
        )
        final = col.get_card(card_id)
        assert (final.did, final.odid, final.ivl, final.due) == (
            home_deck_id,
            0,
            original_ivl,
            original_due,
        )
        assert col.db.scalar(
            "SELECT count() FROM revlog WHERE cid = ? AND type = 3",
            card_id,
        ) == 1
        assert db.get_connection(addon_dir, profile).execute(
            "SELECT count() FROM custom_schedule_review_history WHERE card_id = ?",
            (card_id,),
        ).fetchone()[0] == 0
        assert db.get_custom_schedule_rule(addon_dir, profile, card_id)["revision"] == rule["revision"]
        col.close()
        db.close_connection()

        print("real Anki topic scheduling integration: ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "integration: ok" in result.stdout
