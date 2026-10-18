"""Learning failures use Anki history and tags, including answer Undo/Redo."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_learning_leech_threshold_and_answer_lifecycle_in_real_anki(tmp_path):
    script = dedent(r'''
        import ast
        from pathlib import Path
        import sys
        from types import SimpleNamespace
        from anki.collection import Collection
        from backend.learning_leech import LearningLeechTracker

        tracker = LearningLeechTracker()
        config = {"learning_leech_enabled": True, "learning_leech_threshold": 5,
                  "learning_leech_tag": "learning_leech"}
        profile = "Synthetic"
        col = Collection(str(Path(sys.argv[1]) / "synthetic.anki2"))
        tree = ast.parse(Path("__init__.py").read_text())
        registrations = {ast.unparse(node) for node in tree.body if isinstance(node, ast.Expr)}
        assert "gui_hooks.reviewer_will_answer_card.append(_learning_leech_reviewer_will_answer_card)" in registrations
        assert "gui_hooks.reviewer_did_answer_card.append(_learning_leech_on_card_answered)" in registrations
        callbacks = [node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name in {"_learning_leech_reviewer_will_answer_card",
                              "_learning_leech_on_card_answered"}]
        assert len(callbacks) == 2
        namespace = {"_learning_leech_tracker": tracker,
            "_load_addon_config": lambda *_: config,
            "_current_profile_name": lambda: profile,
            "mw": SimpleNamespace(col=col, addonManager=None), "__name__": "incremento"}
        exec(compile(ast.Module(body=callbacks, type_ignores=[]), "__init__.py", "exec"), namespace)
        before = namespace["_learning_leech_reviewer_will_answer_card"]
        after = namespace["_learning_leech_on_card_answered"]

        def new_note(label, siblings=False):
            model = col.models.by_name("Basic (and reversed card)" if siblings else "Basic")
            note = col.new_note(model)
            note["Front"], note["Back"] = label, "Synthetic answer"
            note.tags = ["keep_me"]
            col.add_note(note, 1)
            return note

        def answer(cid, ease=1):
            card = col.get_card(cid)
            assert before((True, ease), None, card) == (True, ease)
            card.start_timer()
            col.sched.answerCard(card, ease)
            fields = ("type", "queue", "due", "ivl", "reps", "lapses", "did", "odid", "odue", "left")
            scheduled = tuple(getattr(col.get_card(cid), field) for field in fields)
            # Match Reviewer: the after hook receives the original card object.
            after(None, card, ease)
            assert tuple(getattr(col.get_card(cid), field) for field in fields) == scheduled

        try:
            note = new_note("Five learning failures")
            cid = note.card_ids()[0]
            for attempt in range(1, 5):
                answer(cid)
                assert col.get_note(note.id).tags == ["keep_me"], attempt
            # Recreating the tracker stands in for restarting Anki: history persists.
            namespace["_learning_leech_tracker"] = LearningLeechTracker()
            answer(cid)
            assert col.get_note(note.id).has_tag("learning_leech")
            assert col.get_note(note.id).has_tag("keep_me")
            assert col.undo_status().undo == "Answer Card"
            assert col.db.scalar("SELECT count() FROM revlog WHERE cid = ?", cid) == 5
            col.undo()
            assert col.get_note(note.id).tags == ["keep_me"]
            assert col.db.scalar("SELECT count() FROM revlog WHERE cid = ?", cid) == 4
            col.redo()
            assert col.get_note(note.id).has_tag("learning_leech")
            col.undo()
            answer(cid)
            assert col.get_note(note.id).has_tag("learning_leech")

            # A manual/pre-existing tag is never owned or removed by this feature.
            existing = new_note("Existing tag")
            existing.add_tag("LEARNING_LEECH")
            col.update_note(existing)
            config["learning_leech_threshold"] = 1
            answer(existing.card_ids()[0])
            col.undo()
            assert col.get_note(existing.id).has_tag("learning_leech")

            # Learning failures are cumulative, not required to be consecutive.
            config["learning_leech_threshold"] = 2
            cumulative = new_note("Good between failures")
            cumulative_cid = cumulative.card_ids()[0]
            answer(cumulative_cid)
            answer(cumulative_cid, 3)
            assert not col.get_note(cumulative.id).has_tag("learning_leech")
            answer(cumulative_cid)
            assert col.get_note(cumulative.id).has_tag("learning_leech")

            # Two cards of one note each need to meet the threshold themselves.
            siblings = new_note("Sibling independence", siblings=True)
            first, second = siblings.card_ids()
            answer(first)
            answer(second)
            assert col.get_note(siblings.id).tags == ["keep_me"]
            answer(second)
            assert col.get_note(siblings.id).has_tag("learning_leech")

            config.update(learning_leech_threshold=1, learning_leech_tag="needs::rewrite")
            for state in ("interday", "rescheduling_filtered"):
                candidate = new_note(state)
                candidate_cid = candidate.card_ids()[0]
                if state == "interday":
                    card = col.get_card(candidate_cid)
                    card.type, card.queue, card.due, card.left = 1, 3, col.sched.today, 1001
                    col.update_card(card)
                else:
                    did = col.decks.new_filtered("Learning review")
                    deck = col.decks.get(did)
                    deck["resched"] = True
                    deck["terms"] = [[f"cid:{candidate_cid}", 1, 0]]
                    col.decks.save(deck)
                    col.sched.rebuild_filtered_deck(did)
                    assert col.get_card(candidate_cid).odid == 1
                answer(candidate_cid)
                assert col.get_note(candidate.id).has_tag("needs::rewrite"), state

            for state in ("disabled", "review", "relearning", "preview", "cancelled",
                          "missing_answer", "profile_switch", "reset", "hard", "good", "easy"):
                candidate = new_note(state)
                candidate_cid = candidate.card_ids()[0]
                card = col.get_card(candidate_cid)
                config["learning_leech_enabled"] = state != "disabled"
                if state in ("review", "relearning"):
                    card.type, card.queue, card.ivl = (2, 2, 7) if state == "review" else (3, 1, 7)
                    card.due = col.sched.today if state == "review" else 1
                    card.left = 1001 if state == "relearning" else 0
                    col.update_card(card)
                if state == "preview":
                    did = col.decks.new_filtered("Preview")
                    deck = col.decks.get(did)
                    deck["resched"] = False
                    col.decks.save(deck)
                    card.odid, card.did, card.queue = 1, did, 4
                    col.update_card(card)
                if state == "cancelled":
                    assert before((False, 1), None, card) == (False, 1)
                else:
                    before((True, {"hard": 2, "good": 3, "easy": 4}.get(state, 1)), None, card)
                if state != "missing_answer":
                    card.start_timer()
                    col.sched.answerCard(card, {"hard": 2, "good": 3, "easy": 4}.get(state, 1))
                if state == "profile_switch":
                    profile = "OtherSynthetic"
                if state == "reset":
                    namespace["_learning_leech_tracker"].clear()
                after(None, card, {"hard": 2, "good": 3, "easy": 4}.get(state, 1))
                assert col.get_note(candidate.id).tags == ["keep_me"], state
                profile = "Synthetic"

            # Optional tagging failures must never interrupt a committed answer.
            for state in ("snapshot_failure", "after_query_failure", "undo_unavailable"):
                candidate = new_note(state)
                card = col.get_card(candidate.card_ids()[0])
                scalar, undo_status = col.db.scalar, col.undo_status
                def unavailable(*_args, **_kwargs):
                    raise RuntimeError("Synthetic database unavailable")
                try:
                    if state == "snapshot_failure":
                        col.db.scalar = unavailable
                    assert before((True, 1), None, card) == (True, 1)
                    col.db.scalar = scalar
                    card.start_timer()
                    col.sched.answerCard(card, 1)
                    if state == "after_query_failure":
                        col.db.scalar = unavailable
                    if state == "undo_unavailable":
                        col.undo_status = lambda: SimpleNamespace(last_step=0)
                    after(None, card, 1)
                finally:
                    col.db.scalar, col.undo_status = scalar, undo_status
                after(None, card, 1)
                assert col.get_note(candidate.id).tags == ["keep_me"], state

            custom = new_note("Custom tag")
            answer(custom.card_ids()[0])
            assert col.get_note(custom.id).has_tag("needs::rewrite")
            # Duplicate after-answer callbacks cannot create another tag/undo step.
            after(None, col.get_card(custom.card_ids()[0]), 1)
            assert col.undo_status().undo == "Answer Card"
            col.undo()
            assert col.get_note(custom.id).tags == ["keep_me"]
        finally:
            col.close()
    ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
