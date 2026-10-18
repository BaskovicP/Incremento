"""Daily outcomes follow real Anki answers, classification and native Undo."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_daily_memory_grades_and_topic_exclusion_in_real_anki(tmp_path):
    script = dedent(r'''
        from pathlib import Path
        import sys
        from anki.collection import Collection
        from backend import statistics
        from backend.topic_scheduler import TopicCardClassifier

        col = Collection(str(Path(sys.argv[1]) / "synthetic.anki2"))
        classifier = TopicCardClassifier(frozenset(), frozenset({"topic"}), frozenset({"item"}), "Topics")
        statistics._logical_day_bounds_ms = lambda _: (0, 2**63 - 1)

        def add(label, tags, deck):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"], note["Back"] = label, "Synthetic answer"
            note.tags = tags
            col.add_note(note, deck)
            return note.card_ids()[0]

        def answer(cid, ease):
            card = col.get_card(cid)
            card.start_timer()
            col.sched.answerCard(card, ease)

        def load():
            return statistics.daily_learning_outcomes_from_collection(col, classifier=classifier)

        def history():
            return statistics.learning_outcome_history_from_collection(col, days=30, classifier=classifier)

        try:
            topics = col.decks.id("Topics::Synthetic")
            item = add("Memory item", [], 1)
            topic = add("Topic tag", ["topic"], 1)
            topic_deck = add("Topic deck", [], topics)
            override = add("Item override", ["topic", "item"], topics)
            answer(item, 1)
            answer(topic, 3)
            answer(topic_deck, 3)
            answer(override, 3)
            answer(item, 3)
            result = load()
            assert result["cards"] == 2, result
            assert result["failed_cards"] == 1, result
            assert result["stages"]["learning"] == {"again": 1, "hard": 0, "good": 2, "easy": 0}, result
            assert col.undo_status().undo == "Answer Card"
            assert history()[-1] == result
            col.undo()
            assert load()["stages"]["learning"]["good"] == 1
            assert history()[-1]["stages"]["learning"]["good"] == 1
            col.redo()
            assert load() == result
            assert history()[-1] == result

            # Normal Incremento sessions use rescheduling filtered decks.
            filtered_item = add("Filtered memory item", [], 1)
            did = col.decks.new_filtered("Synthetic review")
            deck = col.decks.get(did)
            deck["terms"] = [[f"cid:{filtered_item}", 1, 0]]
            deck["resched"] = True
            col.decks.update(deck)
            assert col.sched.rebuild_filtered_deck(did).count == 1
            answer(filtered_item, 1)
            assert load()["stages"]["learning"]["again"] == 2, load()

            # Reminder/Preview practice must not inflate memory performance.
            before_preview = load()
            preview_item = add("Preview memory item", [], 1)
            preview_did = col.decks.new_filtered("Synthetic preview")
            deck = col.decks.get(preview_did)
            deck["terms"] = [[f"cid:{preview_item}", 1, 0]]
            deck["resched"] = False
            col.decks.update(deck)
            assert col.sched.rebuild_filtered_deck(preview_did).count == 1
            answer(preview_item, 1)
            assert load() == before_preview
            assert history()[-1] == before_preview
        finally:
            col.close()
        ''')
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1], env=dict(os.environ),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_current_card_stages_follow_anki_and_keep_suspension_separate(tmp_path):
    script = dedent(r'''
        from pathlib import Path
        import sys
        from anki.collection import Collection
        from backend.statistics import learning_card_states_from_collection
        from backend.topic_scheduler import TopicCardClassifier
        col = Collection(str(Path(sys.argv[1]) / "stages.anki2"))
        classifier = TopicCardClassifier(frozenset(), frozenset({"topic"}), frozenset({"item"}), "Topics")
        def add(label, kind, queue, tags=(), deck=1):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"], note["Back"], note.tags = label, "Synthetic", list(tags)
            col.add_note(note, deck)
            card = col.get_card(note.card_ids()[0])
            card.type, card.queue = kind, queue
            col.update_card(card)
            return card.id
        def load(**kwargs):
            return learning_card_states_from_collection(col, classifier=classifier, **kwargs)
        try:
            new = add("New", 0, 0)
            add("Learning", 1, 1)
            add("Day learning", 1, 3)
            review = add("Review", 2, 2)
            add("Relearning", 3, 1)
            add("Suspended review", 2, -1)
            add("Buried new", 0, -2)
            add("Excluded topic", 0, 0, ["topic"])
            topics = col.decks.id("Topics::Synthetic")
            add("Excluded deck topic", 0, 0, deck=topics)
            add("Item override", 2, 2, ["topic", "item"], deck=topics)
            result = load()
            assert result == {"new": 2, "learning": 2, "review": 3, "relearning": 1,
                              "total": 8, "suspended": 1, "buried": 1}, result
            # A real answer and Undo change the snapshot; this is not a second ledger.
            card = col.get_card(new)
            card.start_timer()
            col.sched.answerCard(card, 1)
            assert load()["new"] == 1 and load()["learning"] == 3
            col.undo()
            assert load() == result
            col.redo()
            assert load()["learning"] == 3
            assert load(should_cancel=lambda: True) is None
            # Reader cards stay out of the memory snapshot even with an Item override.
            reader_model = col.models.copy(col.models.by_name("Basic"))
            reader_model["name"] = "Incremento PDF"
            col.models.update(reader_model)
            note = col.new_note(reader_model)
            note["Front"], note["Back"], note.tags = "Synthetic PDF", "Synthetic", ["item"]
            col.add_note(note, 1)
            assert load()["total"] == 8
            # A collection larger than one query batch must not be truncated.
            for index in range(510):
                add(f"Synthetic new {index}", 0, 0)
            assert load()["total"] == 518 and load()["new"] == 511
        finally:
            col.close()
        ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1], env=dict(os.environ),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
