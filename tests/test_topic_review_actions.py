"""Done tags the note and suspends one card; both actions share native Undo."""

from datetime import date
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize("done_tag", ["", "reading::finished", "TOPIC"], ids=["default", "custom", "existing"])
def test_real_anki_done_and_revisit_preserve_content_and_related_cards(done_tag):
    script = dedent(r'''
        import tempfile
        import sys
        from datetime import date
        from pathlib import Path
        from anki.collection import Collection
        from backend import topic_review_actions as actions

        requested_tag = sys.argv[1]
        done_tag = requested_tag or "topic/done"

        def snapshot(col, cid):
            c = col.get_card(cid)
            return tuple(getattr(c, f) for f in (
                    "did", "odid", "due", "odue", "ivl", "queue", "type", "reps", "lapses", "left", "custom_data"
            ))

        with tempfile.TemporaryDirectory() as root:
            for state in ("new", "learning", "review", "filtered", "preview"):
                col = Collection(str(Path(root) / (state + ".anki2")))
                try:
                    home = col.decks.id("Synthetic topics")
                    note = col.new_note(col.models.by_name("Basic (and reversed card)"))
                    note["Front"], note["Back"] = "Synthetic topic", "Keep the original content"
                    note.tags = ["topic"]
                    col.add_note(note, home)
                    cid, sibling = note.card_ids()
                    child = col.new_note(col.models.by_name("Basic"))
                    child["Front"], child["Back"] = "Synthetic extract", "Keep reviewing this"
                    col.add_note(child, home)
                    child_id = child.card_ids()[0]
                    card = col.get_card(cid)
                    if state == "learning":
                        card.type, card.queue, card.due, card.left = 1, 1, 1, 1001
                    elif state != "new":
                        card.type, card.queue, card.ivl, card.due = 2, 2, 17, col.sched.today
                    col.update_card(card)
                    if state in ("filtered", "preview"):
                        did = col.decks.new_filtered("Synthetic review")
                        deck = col.decks.get(did)
                        deck["terms"] = [[f"cid:{cid}", 1, 0]]
                        deck["resched"] = state != "preview"
                        col.decks.save(deck)
                        col.sched.rebuild_filtered_deck(did)
                    before = snapshot(col, cid)
                    others = (snapshot(col, sibling), snapshot(col, child_id))
                    fields, tags = list(note.fields), list(note.tags)
                    prior_undo = col.undo_status().undo
                    result = actions.complete_topic(col, cid, **({"done_tag": requested_tag} if requested_tag else {}))
                    assert col.get_card(cid).queue == -1, state
                    assert col.db.scalar("select count(*) from revlog") == 0
                    assert col.get_note(note.id).fields == fields
                    expected_tags = {t.casefold() for t in tags} | {done_tag.casefold()}
                    assert {t.casefold() for t in col.get_note(note.id).tags} == expected_tags
                    assert len(col.get_note(note.id).tags) == len(expected_tags)
                    assert col.get_card(sibling).note().has_tag(done_tag)
                    assert col.get_note(child.id).tags == []
                    assert (snapshot(col, sibling), snapshot(col, child_id)) == others
                    actions.undo_topic_action(col, result.undo_step)
                    assert snapshot(col, cid) == before, state
                    assert col.get_note(note.id).tags == tags
                    assert col.undo_status().undo == prior_undo
                    col.redo()
                    assert col.get_card(cid).queue == -1
                    assert {t.casefold() for t in col.get_note(note.id).tags} == expected_tags
                    col.undo()
                    assert col.get_note(note.id).tags == tags

                    result = actions.revisit_topic(col, cid, months=12, today=date(2028, 2, 29))
                    assert col.get_card(cid).due == col.sched.today + 365, state
                    assert col.get_card(cid).odid == 0
                    from backend import cards
                    for reader_pool in (cards.get_all_pdf_cards, cards.get_all_youtube_cards, cards.get_all_webpage_cards):
                        assert cid not in reader_pool(f"cid:{cid}", col=col), state
                    assert (snapshot(col, sibling), snapshot(col, child_id)) == others
                    actions.undo_topic_action(col, result.undo_step)
                    assert snapshot(col, cid) == before, state
                    assert cid in cards.get_all_pdf_cards(f"cid:{cid}", col=col)
                    col.redo()
                    assert col.get_card(cid).due == col.sched.today + 365
                finally:
                    col.close()
        print("topic actions lifecycle: ok")
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, done_tag], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "topic actions lifecycle: ok" in result.stdout


@pytest.mark.parametrize("invalid_tag", ["two tags", "bad\u0000tag", "::", "x" * 256])
def test_done_rejects_invalid_tag_before_suspending(invalid_tag):
    from unittest.mock import Mock
    import topic_review_actions as actions

    col = Mock()
    with pytest.raises(ValueError, match="tag"):
        actions.complete_topic(col, 42, done_tag=invalid_tag)
    col.sched.suspend_cards.assert_not_called()
    col.tags.bulk_add.assert_not_called()


@pytest.mark.parametrize("failing_stage", ["suspend", "tags", "merge"])
def test_real_anki_done_failure_rolls_back_suspension_and_tag(failing_stage):
    script = dedent(r'''
        import sys
        import tempfile
        from pathlib import Path
        from anki.collection import Collection
        from backend import topic_review_actions as actions

        with tempfile.TemporaryDirectory() as root:
            col = Collection(str(Path(root) / "synthetic.anki2"))
            try:
                note = col.new_note(col.models.by_name("Basic"))
                note["Front"] = "Synthetic topic"
                note.tags = ["topic", "manual"]
                col.add_note(note, 1)
                cid = note.card_ids()[0]
                before = col.get_card(cid)
                before_tags = list(col.get_note(note.id).tags)
                before_undo = col.undo_status().undo
                owner, method = {
                    "suspend": (col.sched, "suspend_cards"),
                    "tags": (col.tags, "bulk_add"),
                    "merge": (col, "merge_undo_entries"),
                }[sys.argv[1]]
                original = getattr(owner, method)
                def fail(*args, **kwargs):
                    raise RuntimeError("Synthetic failure")
                setattr(owner, method, fail)
                try:
                    actions.complete_topic(col, cid, done_tag="reading::finished")
                    raise AssertionError("failure was hidden")
                except RuntimeError:
                    pass
                finally:
                    setattr(owner, method, original)
                after = col.get_card(cid)
                for field in ("queue", "type", "due", "ivl", "reps", "lapses"):
                    assert getattr(after, field) == getattr(before, field), field
                assert col.get_note(note.id).tags == before_tags
                assert col.undo_status().undo == before_undo
                assert col.db.scalar("select count(*) from revlog") == 0
            finally:
                col.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, failing_stage], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("target", [date(2026, 9, 9), date(2026, 9, 10)])
def test_revisit_rejects_non_future_date_without_mutating(target):
    from unittest.mock import Mock
    import topic_review_actions as actions

    col = Mock()
    with pytest.raises(ValueError):
        actions.revisit_topic(col, 42, on_date=target, today=date(2026, 9, 10))
    col.sched.set_due_date.assert_not_called()


@pytest.mark.parametrize("last_step, redo", [(9, ""), (8, "Suspend")])
def test_notification_undo_cannot_undo_a_newer_or_already_undone_action(last_step, redo):
    from types import SimpleNamespace
    from unittest.mock import Mock
    import topic_review_actions as actions

    col = Mock()
    col.undo_status.return_value = SimpleNamespace(last_step=last_step, undo="Answer Card", redo=redo)
    with pytest.raises(actions.StaleTopicAction):
        actions.undo_topic_action(col, 8)
    col.undo.assert_not_called()


def test_real_anki_revisit_expiry_existing_rules_and_failure_rollback():
    script = dedent(r'''
        import json
        import tempfile
        from datetime import date
        from pathlib import Path
        from types import SimpleNamespace
        from anki.collection import Collection
        from backend import cards, db, topic_review_actions as actions

        with tempfile.TemporaryDirectory() as root:
            col = Collection(str(Path(root) / "synthetic.anki2"))
            try:
                note = col.new_note(col.models.by_name("Basic"))
                note["Front"] = "Synthetic reading topic"
                note.tags = ["topic"]
                col.add_note(note, 1)
                cid = note.card_ids()[0]
                card = col.get_card(cid)
                card.type, card.queue, card.ivl, card.due = 2, 2, 17, col.sched.today + 10
                card.custom_data = '{"other":7}'
                col.update_card(card)
                db.set_topic_schedule(root, "Synthetic", cid, 2.5, 17, precise_interval=17.25)
                topic_before = db.get_topic_schedule_state(root, "Synthetic", cid)
                rule = db.set_custom_schedule_rule(root, "Synthetic", cid, mode="one_time", interval_value=2, interval_unit="days")
                pool = lambda: cards.get_all_pdf_cards(f"cid:{cid}", col=col)
                assert pool() == [cid]  # ordinary future media still participates

                result = actions.revisit_topic(col, cid, on_date=date(2027, 1, 31), today=date(2026, 9, 10))
                assert pool() == []
                for by_tag in (cards.get_pdf_cards_by_tag, cards.get_youtube_cards_by_tag, cards.get_webpage_cards_by_tag):
                    assert by_tag("topic", f"cid:{cid}", col=col) == []
                assert json.loads(col.get_card(cid).custom_data)["other"] == 7
                assert db.get_topic_schedule_state(root, "Synthetic", cid) == topic_before
                assert db.get_custom_schedule_rule(root, "Synthetic", cid) == rule
                assert col.db.scalar("select count(*) from revlog where ease > 0") == 0
                future_day = json.loads(col.get_card(cid).custom_data)[actions.REVISIT_DATA_KEY]
                # The marker expires without a background write, including if
                # the card is now scheduled even later by another action.
                fake_clock = SimpleNamespace(sched=SimpleNamespace(today=future_day - 1))
                assert col.find_cards(f"cid:{cid} {actions.reader_revisit_filter(fake_clock)}") == []
                fake_clock.sched.today = future_day
                assert col.find_cards(f"cid:{cid} {actions.reader_revisit_filter(fake_clock)}") == [cid]
                actions.undo_topic_action(col, result.undo_step)
                assert col.get_card(cid).custom_data == '{"other":7}'
                assert pool() == [cid]

                for failing_method in ("update_card", "merge_undo_entries"):
                    before = col.get_card(cid)
                    before_state = (before.due, before.ivl, before.queue, before.custom_data)
                    previous_revlogs = col.db.scalar("select count(*) from revlog")
                    original = getattr(col, failing_method)
                    def fail(*args, **kwargs):
                        raise RuntimeError("Synthetic write failure")
                    setattr(col, failing_method, fail)
                    try:
                        actions.revisit_topic(col, cid, months=3, today=date(2026, 9, 10))
                        raise AssertionError("failure was hidden")
                    except RuntimeError:
                        pass
                    finally:
                        setattr(col, failing_method, original)
                    after = col.get_card(cid)
                    after_state = (after.due, after.ivl, after.queue, after.custom_data)
                    assert after_state == before_state, (failing_method, before_state, after_state)
                    assert col.db.scalar("select count(*) from revlog") == previous_revlogs
                    assert pool() == [cid]
            finally:
                db.close_connection(root, "Synthetic")
                col.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
