"""Real Anki search and refill regressions for the scheduler's Other bucket."""

from pathlib import Path
import subprocess
import sys
from textwrap import dedent


ROOT = Path(__file__).resolve().parents[1]


def _run(script: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", dedent(script)], cwd=ROOT,
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_other_excludes_all_active_tags_across_card_types_and_cached_picks():
    _run(
        r'''
        import os
        import random
        import tempfile
        from unittest.mock import patch

        from anki.collection import Collection
        from backend import db, scheduler, topic_scheduler

        with tempfile.TemporaryDirectory(prefix="incremento-other-search-") as root:
            col = Collection(os.path.join(root, "synthetic.anki2"))
            try:
                classifier = topic_scheduler.TopicCardClassifier(
                    enabled_note_type_names=frozenset(), topic_tags=frozenset(),
                    item_tags=frozenset(), topics_deck_name="Topics",
                )
                for kind, model_name in (
                    ("topics", "Basic"), ("items", "Basic"),
                    ("pdf", "Incremento PDF"), ("epub", "Incremento EPUB"),
                    ("youtube", "Incremento Video"), ("webpage", "Incremento Web"),
                ):
                    model = col.models.by_name(model_name)
                    if model is None:
                        model = col.models.copy(col.models.by_name("Basic"))
                        model["name"] = model_name
                        col.models.update_dict(model)
                    deck = col.decks.id("Topics" if kind == "topics" else kind)
                    tagged_ids, other_ids = set(), set()
                    for tags in (
                        ["spiritual"], ["SpIrItUaL::Prayer"], ["health"],
                        ["health", "unselected"], ['quote"tag'],
                        ["other_category"], [],
                    ):
                        note = col.new_note(model)
                        note["Front"] = f"Synthetic {kind} {len(tagged_ids | other_ids)}"
                        note["Back"] = "Synthetic answer"
                        note.tags = tags
                        col.add_note(note, deck)
                        cid = note.card_ids()[0]
                        (other_ids if not tags or tags == ["other_category"] else tagged_ids).add(cid)

                    for mode in ("random", "priority"):
                        random.seed(7)
                        cache, picked = {}, set()
                        kwargs = dict(
                            force_card_type="pdf" if kind == "epub" else kind,
                            force_mode=mode, use_tags=True,
                            tag_weights={"spiritual": .1, "health": .1, 'quote"tag': .1},
                            topics_filter='deck:"Topics"', items_filter='deck:"items"',
                            pdf_filter=f'note:"{model_name}"',
                            addon_dir=root, profile="Synthetic", col=col,
                            topic_classifier=classifier, pool_cache=cache,
                            exclude_ids=picked,
                        )
                        # Choose Other at the randomness boundary; real Anki
                        # searches and real cached card selection run unchanged.
                        with patch.object(scheduler.random, "random", return_value=.999):
                            for _ in range(2):
                                result = scheduler.get_card_from_scheduler(**kwargs)
                                assert result.card in other_ids, (kind, mode, "selected an active tag")
                                assert result.tag == scheduler.NO_TAGS_KEY, (kind, mode)
                                assert result.card not in picked
                                picked.add(result.card)
                            result = scheduler.get_card_from_scheduler(**kwargs)
                            assert result.card is None, (kind, mode, "exhaustion leaked a tagged card")
                        assert picked == other_ids

                    # Choosing a real tag still permits its own cards.
                    with patch.object(scheduler.random, "random", return_value=0):
                        result = scheduler.get_card_from_scheduler(
                            **{**kwargs, "pool_cache": {}, "exclude_ids": set()},
                        )
                    assert result.card in tagged_ids
                    assert result.tag == "spiritual"
            finally:
                col.close()
                db.close_connection()
        '''
    )


def test_other_stays_outside_selected_tags_through_strict_and_soft_refill():
    _run(
        r'''
        import copy
        import os
        import random
        import tempfile

        from anki.collection import Collection
        from backend import db, scheduler, session, session_selection, topic_scheduler
        from backend.scheduler_config import SchedulerConfig

        for strict in (True, False):
            for phases in (["tags"], ["tags", "type", "mode"]):
                with tempfile.TemporaryDirectory(prefix="incremento-other-refill-") as root:
                    col = Collection(os.path.join(root, "synthetic.anki2"))
                    # Keep synthetic review-day numbers beyond the ten-card window.
                    col.crt -= 365 * 86400
                    try:
                        deck = col.decks.id("Synthetic")
                        spiritual = set()
                        for index in range(300):
                            note = col.new_note(col.models.by_name("Basic"))
                            note["Front"] = f"Synthetic {index}"
                            note["Back"] = "Synthetic answer"
                            note.tags = ["spiritual"] if index < 150 else ["unselected"]
                            col.add_note(note, deck)
                            cid = note.card_ids()[0]
                            if index < 150:
                                spiritual.add(cid)
                            card = col.get_card(cid)
                            card.type = card.queue = 2
                            card.ivl = 7
                            card.due = col.sched.today
                            col.update_card(card)
                        classifier = topic_scheduler.TopicCardClassifier(
                            enabled_note_type_names=frozenset(), topic_tags=frozenset(),
                            item_tags=frozenset(), topics_deck_name="Topics",
                        )
                        cfg = SchedulerConfig(
                            session_card_count=10, auto_refill_session=True,
                            topics_rate=0, random_rate=1, use_tags=True,
                            tag_weights={"spiritual": .2}, include_rest=True,
                            enforce_priority=strict, phase_order=phases,
                            scheduler_scope="daily", preserve_order=True,
                        )
                        random.seed(7)
                        picker = session_selection.SessionPicker(
                            cfg, addon_dir=root, profile="Synthetic", col=col,
                            topic_classifier=classifier,
                        )
                        picker.pick_until(10)
                        session._prepare_filtered_review_deck(
                            picker.selected_ids, deck_name="Incremento Session",
                            preserve_order=True, col=col,
                        )
                        state = session._ActiveIncrementoSessionState(
                            cfg=cfg, stats=picker.stats, picker=picker,
                            session_deck_name="Incremento Session", window_size=10,
                            preserve_order=True, picked_meta=copy.deepcopy(picker.picked_meta),
                            selected_ids=list(picker.selected_ids), auto_refill_enabled=True,
                        )

                        def verify_selected_buckets():
                            for cid, meta in picker.picked_meta.items():
                                assert (cid in spiritual) == (meta["tag"] == "spiritual"), (
                                    strict, phases, "actual tag differs from assigned bucket",
                                )
                            assigned = picker.session_counts["tags"]
                            assert assigned.get("spiritual", 0) + assigned.get(scheduler.NO_TAGS_KEY, 0) == len(picker.selected_ids)

                        verify_selected_buckets()
                        for _ in range(100):
                            queue = col.sched.get_queued_cards(fetch_limit=10)
                            card = col.get_card(queue.cards[0].card.id)
                            card.start_timer()
                            col.sched.answerCard(card, 3)
                            session._record_incremento_answer(state, None, card)
                            refill = session._maybe_auto_refill_active_session(state, col=col)
                            assert len(refill["new_ids"]) == 1
                            assert len(col.sched.get_queued_cards(fetch_limit=20).cards) == 10
                            verify_selected_buckets()
                        assert len(picker.selected_ids) == len(set(picker.selected_ids)) == 110
                    finally:
                        col.close()
                        db.close_connection()
        '''
    )
