"""Real-Anki regression coverage for topic interval overrides and undo/redo."""

from __future__ import annotations

import os
import subprocess
import sys
from textwrap import dedent


def test_review_all_reminder_preserves_schedules_and_rules_across_repeated_answers():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import os
        import tempfile
        import time
        from types import SimpleNamespace

        from anki.collection import Collection
        from backend import custom_schedule, db, session, topic_scheduler
        from backend.reviewer_buttons import remap_item_fail_pass_ease

        schedule_fields = (
            "did", "odid", "due", "odue", "type", "queue", "ivl",
            "factor", "reps", "lapses", "left",
        )

        def snapshot(card):
            return tuple(getattr(card, field) for field in schedule_fields)

        with tempfile.TemporaryDirectory(prefix="incremento-reminder-test-") as root:
            for kind in ("topic", "item"):
                for state in ("new", "learning", "relearning", "due", "future"):
                    addon_dir = os.path.join(root, kind, state)
                    os.makedirs(addon_dir)
                    col = Collection(os.path.join(addon_dir, "synthetic.anki2"))
                    profile = "SyntheticProfile"
                    try:
                        for module in (topic_scheduler, custom_schedule):
                            module._ADDON_DIR = addon_dir
                            module._active_profile = lambda: profile
                            module.mw = SimpleNamespace(col=col)
                            module.is_topic_card = lambda _card: kind == "topic"
                        topic_scheduler.reset_topic_answer_runtime_state()
                        custom_schedule.reset_custom_schedule_answer_runtime_state()
                        home = col.decks.id("Synthetic Home")
                        note = col.new_note(col.models.by_name("Basic"))
                        note["Front"] = "Synthetic reminder"
                        note["Back"] = "Synthetic answer"
                        col.add_note(note, home)
                        cid = note.card_ids()[0]
                        card = col.get_card(cid)
                        states = {
                            "new": (0, 0, 0, 1, 0),
                            "learning": (1, 1, 0, int(time.time()) + 600, 1001),
                            "relearning": (3, 1, 7, int(time.time()) + 600, 1001),
                            "due": (2, 2, 7, col.sched.today, 0),
                            "future": (2, 2, 7, col.sched.today + 6, 0),
                        }
                        card.type, card.queue, card.ivl, card.due, card.left = states[state]
                        col.update_card(card)
                        original = snapshot(card)
                        has_topic_state = kind == "topic" and state != "new"
                        if has_topic_state:
                            db.set_topic_schedule(
                                addon_dir, profile, cid, 3.5, 7, precise_interval=7.25,
                            )
                        topic_before = db.get_topic_schedule_state(addon_dir, profile, cid)
                        rule = db.set_custom_schedule_rule(
                            addon_dir, profile, cid, mode="one_time",
                            interval_value=2, interval_unit="days",
                        )

                        for attempt, button in enumerate((2, 2, 1, 3), start=1):
                            did = session._prepare_filtered_review_deck(
                                [cid], deck_name="Incremento PDF Review",
                                preserve_order=True, reschedule=False, col=col,
                            )
                            assert col.decks.get(did)["resched"] is False
                            queued = col.sched.get_queued_cards(fetch_limit=1)
                            assert len(queued.cards) == 1, (kind, state)
                            card = col.get_card(cid)
                            if kind == "topic":
                                assert topic_scheduler.topic_due_label(card, button) == ""
                                ease = topic_scheduler.prepare_topic_answer(card, button)
                            else:
                                custom_schedule.prepare_custom_schedule_answer(card)
                                ease = remap_item_fail_pass_ease(card, 2)
                            assert ease == 3
                            card.start_timer()
                            col.sched.answerCard(card, ease)
                            if kind == "topic":
                                topic_scheduler.on_topic_card_answered(None, col.get_card(cid), ease)
                            else:
                                custom_schedule.apply_custom_schedule_after_answer(
                                    None, col.get_card(cid), ease,
                                )
                            assert snapshot(col.get_card(cid)) == original, (kind, state, attempt)
                            assert db.topic_schedule_exists(addon_dir, profile, cid) == has_topic_state
                            assert db.get_topic_schedule_state(addon_dir, profile, cid) == topic_before
                            assert db.get_topic_review_history(addon_dir, profile, cid) == []
                            assert db.get_custom_schedule_rule(addon_dir, profile, cid) == rule
                            assert db.get_connection(addon_dir, profile).execute(
                                "SELECT count() FROM custom_schedule_review_history WHERE card_id = ?",
                                (cid,),
                            ).fetchone()[0] == 0
                            assert col.db.scalar(
                                "SELECT count() FROM revlog WHERE cid = ? AND type = 3", cid,
                            ) == attempt

                        # Reusing the same deck for normal review must re-enable
                        # scheduling and consume the still-present one-time rule.
                        did = session._prepare_filtered_review_deck(
                            [cid], deck_name="Incremento PDF Review",
                            preserve_order=True, col=col,
                        )
                        assert col.decks.get(did)["resched"] is True
                        card = col.get_card(cid)
                        if kind == "topic":
                            topic_scheduler.prepare_topic_answer(card, 2)
                        else:
                            custom_schedule.prepare_custom_schedule_answer(card)
                        card.start_timer()
                        col.sched.answerCard(card, 3)
                        if kind == "topic":
                            topic_scheduler.on_topic_card_answered(None, col.get_card(cid), 3)
                        else:
                            custom_schedule.apply_custom_schedule_after_answer(None, col.get_card(cid), 3)
                        final = col.get_card(cid)
                        assert (final.did, final.odid, final.ivl, final.due) == (
                            home, 0, 2, col.sched.today + 2,
                        )
                        assert db.get_custom_schedule_rule(addon_dir, profile, cid) is None
                    finally:
                        topic_scheduler.reset_topic_answer_runtime_state()
                        custom_schedule.reset_custom_schedule_answer_runtime_state()
                        col.close()
                        db.close_connection()
        print("Review All reminder lifecycle: ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=repo_root,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Review All reminder lifecycle: ok" in result.stdout


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
