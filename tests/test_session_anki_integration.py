"""Real-Anki checks for the filtered-deck state Incremento preserves on exit."""

from __future__ import annotations

import os
import subprocess
import sys
from textwrap import dedent


def test_document_topic_hierarchy_respects_classification_endpoints_strict_quotas_and_refill():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import os
        import tempfile
        from unittest.mock import patch

        from anki.collection import Collection
        from backend.cards import get_all_pdf_cards
        from backend.scheduler import get_card_from_scheduler
        from backend.scheduler_config import SchedulerConfig
        from backend.session_selection import SessionPicker
        from backend.topic_scheduler import TopicCardClassifier
        from backend import session as incremento_session

        with tempfile.TemporaryDirectory(prefix="incremento-document-topic-mix-") as root:
            col = Collection(os.path.join(root, "collection.anki2"))
            try:
                basic = col.models.by_name("Basic")
                for name in ("Incremento PDF", "Incremento EPUB"):
                    model = col.models.copy(basic)
                    model["id"] = 0
                    model["name"] = name
                    col.models.add(model)

                counter = 0
                def add(model_name="Basic", tags=(), future=False):
                    global counter
                    counter += 1
                    note = col.new_note(col.models.by_name(model_name))
                    note["Front"] = f"fixture-{counter}"
                    note["Back"] = "answer"
                    note.tags = list(tags)
                    col.add_note(note, col.decks.id("Home"))
                    cid = int(note.card_ids()[0])
                    if future:
                        card = col.get_card(cid)
                        card.type = card.queue = 2
                        card.ivl = 30
                        card.due = col.sched.today + 30
                        col.update_card(card)
                    return cid

                item_document = add("Incremento EPUB", tags=("item", "work"))
                documents = {add(name, tags=("work",), future=True)
                             for name in ("Incremento PDF", "Incremento EPUB") for _ in range(6)}
                topics = {add(tags=("topic", "work")) for _ in range(100)}
                items = {item_document} | {add(tags=("work",)) for _ in range(100)}
                classifier = TopicCardClassifier(
                    enabled_note_type_names=frozenset({"Incremento PDF", "Incremento EPUB"}),
                    topic_tags=frozenset({"topic"}), item_tags=frozenset({"item"}), topics_deck_name="Topics",
                )
                assert set(get_all_pdf_cards(col=col, topic_only=True, topic_classifier=classifier)) == documents
                common = dict(col=col, topic_classifier=classifier, use_tags=False, force_mode="priority")

                assert get_card_from_scheduler(topics_rate=1, pdf_rate=1, ready_filter="cid:0", **common).card in documents
                assert get_card_from_scheduler(topics_rate=1, pdf_rate=1, topics_filter="tag:missing", **common).card is None
                assert get_card_from_scheduler(force_card_type="pdf", topics_filter="cid:0", **common).card in documents | {item_document}
                assert get_card_from_scheduler(topics_rate=1, pdf_rate=0, **common).card in topics
                item_pick = get_card_from_scheduler(topics_rate=0, pdf_rate=1, **common)
                assert item_pick.card == item_document
                assert item_pick.card_type == "epub" and item_pick.study_kind == "items"

                cfg = SchedulerConfig(
                    session_card_count=100, topics_rate=0.6, pdf_rate=0.1, random_rate=0,
                    enforce_priority=True, phase_order=["type"], use_tags=True,
                    tag_weights={"work": 1.0}, include_rest=False,
                )
                with patch("backend.scheduler.random.random", return_value=0.5):
                    picker = SessionPicker(cfg, root, col=col, topic_classifier=classifier, profile="Fixture")
                    picker.pick_until(100)
                    assert len(set(picker.selected_ids)) == 100
                    assert len(set(picker.selected_ids) & documents) == 6
                    assert len(set(picker.selected_ids) & topics) == 54
                    assert len(set(picker.selected_ids) & items) == 40
                    assert picker.picked_meta[item_document]["study_kind"] == "items"
                    assert picker.picked_meta[item_document]["card_type"] == "epub"
                    restored = SessionPicker(cfg, root, col=col, topic_classifier=classifier,
                                             profile="Fixture", snapshot=picker.snapshot())
                    restored.pick_until(110)
                    assert len(set(restored.selected_ids)) == 110
                    assert restored._picked_content_type_count("topics") == 66
                    assert restored._picked_content_type_count("items") == 44

                built = incremento_session._prepare_filtered_review_deck(
                    restored.selected_ids, deck_name="Incremento Session", preserve_order=True,
                    select_deck=False, col=col, return_result=True,
                )
                assert built.deck_id is not None
                assert set(col.find_cards('deck:"Incremento Session"')) == set(restored.selected_ids)
            finally:
                col.close()
        print("real Anki hierarchical document mix: ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=repo_root, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "hierarchical document mix: ok" in result.stdout


def test_anki_manages_completed_and_learning_cards_without_exit_rebuild():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import os
        import tempfile

        from anki.collection import Collection
        from backend import session as incremento_session


        def make_card(col, deck_id, label):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = label
            note["Back"] = "answer"
            col.add_note(note, deck_id)
            return int(note.card_ids()[0])


        def build_one_card_filtered_deck(col, card_id):
            result = incremento_session._prepare_filtered_review_deck(
                [card_id],
                deck_name="Incremento Session",
                preserve_order=True,
                select_deck=True,
                col=col,
                return_result=True,
            )
            assert result.deck_id is not None
            assert len(col.find_cards('deck:"Incremento Session"')) == 1
            return int(result.deck_id)


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


def test_anki_reclaims_selected_cards_by_emptying_their_foreign_filtered_deck():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import os
        import tempfile

        from anki.collection import Collection
        from backend import session as incremento_session


        def make_card(col, deck_id, label):
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"] = label
            note["Back"] = "answer"
            col.add_note(note, deck_id)
            return int(note.card_ids()[0])


        with tempfile.TemporaryDirectory(prefix="incremento-filtered-reclaim-") as root:
            col = Collection(os.path.join(root, "review.anki2"))
            try:
                home_deck_id = int(col.decks.id("Home"))
                selected_foreign_id = make_card(col, home_deck_id, "selected foreign")
                unselected_foreign_id = make_card(col, home_deck_id, "unselected foreign")
                normal_id = make_card(col, home_deck_id, "normal")

                foreign = incremento_session._prepare_filtered_review_deck(
                    [selected_foreign_id, unselected_foreign_id],
                    deck_name="Foreign Filtered Review",
                    preserve_order=True,
                    select_deck=False,
                    col=col,
                    return_result=True,
                )
                foreign_deck_id = int(foreign.deck_id)
                assert int(col.get_card(selected_foreign_id).did) == foreign_deck_id
                assert int(col.get_card(unselected_foreign_id).did) == foreign_deck_id

                target = incremento_session._prepare_filtered_review_deck(
                    [selected_foreign_id, normal_id],
                    deck_name="Incremento PDF Review",
                    preserve_order=True,
                    select_deck=False,
                    col=col,
                    return_result=True,
                    release_from_other_filtered_decks=True,
                )
                target_deck_id = int(target.deck_id)

                selected = col.get_card(selected_foreign_id)
                normal = col.get_card(normal_id)
                unselected = col.get_card(unselected_foreign_id)
                assert int(selected.did) == target_deck_id
                assert int(selected.odid) == home_deck_id
                assert int(normal.did) == target_deck_id
                assert int(normal.odid) == home_deck_id
                assert int(unselected.did) == home_deck_id
                assert int(unselected.odid) == 0
                assert col.decks.by_name("Foreign Filtered Review")["dyn"] == 1
            finally:
                col.close()

        print("real Anki filtered reclaim integration: ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "filtered reclaim integration: ok" in result.stdout
