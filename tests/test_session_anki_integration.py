"""Real-Anki checks for the filtered-deck state Incremento preserves on exit."""

from __future__ import annotations

import os
import subprocess
import sys
from textwrap import dedent


def test_anki_manages_completed_and_learning_cards_without_exit_rebuild():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import os
        import tempfile

        from anki.collection import Collection


        def make_card(col, deck_id, label):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = label
            note["Back"] = "answer"
            col.add_note(note, deck_id)
            return int(note.card_ids()[0])


        def build_one_card_filtered_deck(col, card_id):
            deck_id = int(col.decks.new_filtered("Incremento Session"))
            filtered = col.sched.get_or_create_filtered_deck(deck_id)
            filtered.config.reschedule = True
            del filtered.config.search_terms[:]
            filtered.config.search_terms.add(
                search=f"cid:{card_id}",
                limit=1,
                order=6,
            )
            operation = col.sched.add_or_update_filtered_deck(filtered)
            assert col.sched.rebuild_filtered_deck(operation.id).count == 1
            col.decks.select(deck_id)
            return deck_id


        def answer_only_queued_card(col, ease):
            queued = col.sched.get_queued_cards(fetch_limit=10)
            assert len(queued.cards) == 1
            card_id = int(queued.cards[0].card.id)
            card = col.get_card(card_id)
            card.start_timer()
            col.sched.answerCard(card, ease)
            return card_id


        root = tempfile.mkdtemp(prefix="incremento-session-exit-")
        review_col = Collection(os.path.join(root, "review.anki2"))
        try:
            home_deck_id = int(review_col.decks.id("Home"))
            review_card_id = make_card(review_col, home_deck_id, "review")
            review_card = review_col.get_card(review_card_id)
            review_card.type = 2
            review_card.queue = 2
            review_card.ivl = 5
            review_card.due = review_col.sched.today
            review_col.update_card(review_card)

            build_one_card_filtered_deck(review_col, review_card_id)
            assert answer_only_queued_card(review_col, 3) == review_card_id

            completed = review_col.get_card(review_card_id)
            assert int(completed.did) == home_deck_id
            assert int(completed.odid) == 0
        finally:
            review_col.close()

        learning_col = Collection(os.path.join(root, "learning.anki2"))
        try:
            home_deck_id = int(learning_col.decks.id("Home"))
            learning_card_id = make_card(learning_col, home_deck_id, "learning")
            filtered_deck_id = build_one_card_filtered_deck(
                learning_col,
                learning_card_id,
            )
            assert answer_only_queued_card(learning_col, 1) == learning_card_id

            unfinished = learning_col.get_card(learning_card_id)
            assert int(unfinished.did) == filtered_deck_id
            assert int(unfinished.odid) == home_deck_id
            assert int(unfinished.queue) == 1
        finally:
            learning_col.close()

        print("real Anki session exit integration: ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "session exit integration: ok" in result.stdout
