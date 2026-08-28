"""Real-Anki regression checks for batch Topic/Item classification."""

from __future__ import annotations

import os
import subprocess
import sys
from textwrap import dedent


def test_batch_topic_item_classification_matches_runtime_rules():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import os
        import tempfile

        from anki.collection import Collection

        from backend.cards import (
            clear_topic_item_cache,
            get_all_item_cards,
            get_all_topic_cards,
        )
        from backend.topic_scheduler import TopicCardClassifier


        root = tempfile.mkdtemp(prefix="incremento-card-classification-")
        col = Collection(os.path.join(root, "collection.anki2"))
        try:
            basic = col.models.by_name("Basic")
            topic_model = col.models.copy(basic)
            topic_model["id"] = 0
            topic_model["name"] = "Incremento PDF"
            col.models.add(topic_model)
            topic_model = col.models.by_name("Incremento PDF")

            counter = 0

            def add_card(model, deck_name, tags=()):
                global counter
                counter += 1
                note = col.new_note(model)
                note["Front"] = f"card-{counter}"
                note["Back"] = "answer"
                note.tags = list(tags)
                col.add_note(note, col.decks.id(deck_name))
                return int(note.card_ids()[0])

            by_note_type = add_card(topic_model, "General")
            by_tag = add_card(basic, "General", ["topic"])
            by_child_deck = add_card(basic, "Topics::Child")
            item_override = add_card(topic_model, "General", ["topic", "item"])
            ordinary_item = add_card(basic, "General")

            classifier = TopicCardClassifier(
                enabled_note_type_names=frozenset({"Incremento PDF"}),
                topic_tags=frozenset({"topic"}),
                item_tags=frozenset({"item"}),
                topics_deck_name="Topics",
            )
            clear_topic_item_cache()
            topics = get_all_topic_cards(
                ready_filter="is:new -is:suspended",
                col=col,
                topic_classifier=classifier,
            )
            items = get_all_item_cards(
                ready_filter="is:new -is:suspended",
                col=col,
                topic_classifier=classifier,
            )

            assert set(topics) == {by_note_type, by_tag, by_child_deck}
            assert set(items) == {item_override, ordinary_item}
            assert set(topics).isdisjoint(items)
        finally:
            col.close()

        print("real Anki batch card classification: ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "batch card classification: ok" in result.stdout
