"""Real-Anki coverage for the native SuperMemo import boundary."""

from __future__ import annotations

import os
import subprocess
import sys
from textwrap import dedent


def test_supermemo_import_maps_native_state_without_replacing_anki_scheduler() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    script = dedent(
        r"""
        import json
        import os
        import tempfile
        from datetime import date, datetime
        from pathlib import Path

        from anki.collection import Collection

        from backend import db
        from backend.priority_manager import get_priority
        from backend.supermemo_format import (
            OptimizationFile,
            SuperMemoCollection,
            SuperMemoElement,
            SuperMemoMedia,
            SuperMemoReference,
            SuperMemoReview,
        )
        from backend.supermemo_import import import_supermemo_collection


        root = Path(tempfile.mkdtemp(prefix="incremento-supermemo-import-"))
        addon_dir = root / "addon"
        addon_dir.mkdir()
        profile = "TestProfile"
        collection = Collection(str(root / "collection.anki2"))
        optimization_source = root / "Recall.dat"
        optimization_source.write_bytes(b"opaque-matrix")
        image_source = root / "diagram.png"
        image_source.write_bytes(b"\x89PNG\r\n\x1a\nfixture-image")

        topic = SuperMemoElement(
            element_id=1,
            element_type=0,
            status=2,
            parent_id=None,
            sort_order=0,
            priority_rank=1,
            a_factor=3.5,
            forgetting_index=10,
            current_interval=11,
            due_date=None,
            repetition_count=1,
            lapse_count=0,
            title="Imported topic",
            question="",
            answer="",
            body="Topic body",
            history=(
                SuperMemoReview(1, datetime(2024, 1, 1, 8), 10, 0, 11, None, None, False),
            ),
        )
        item = SuperMemoElement(
            element_id=2,
            element_type=1,
            status=1,
            parent_id=1,
            sort_order=1,
            priority_rank=0,
            a_factor=4.25,
            forgetting_index=8,
            current_interval=17,
            due_date=date(2024, 1, 20),
            repetition_count=2,
            lapse_count=1,
            title="Mention a [...]: Gets the attention of someone else",
            question="Mention a [...]: Gets the attention of someone else",
            answer="person",
            body="Source context",
            question_html="Mention a <strong>[...]</strong>: Gets the attention of someone else",
            answer_html="<em>person</em>",
            body_html="<p><u>Source</u> context<script>bad()</script></p>",
            media=(SuperMemoMedia(1, 14, "Diagram", image_source),),
            reference=SuperMemoReference(
                1,
                title="Reference title",
                date_text="January 5, 2024",
                url="https://example.com/reference",
                source="Reference author",
                comment="Reference comment",
            ),
            history=(
                SuperMemoReview(1, datetime(2024, 1, 2, 9), 8, 0, 3, None, 100, False),
                SuperMemoReview(2, datetime(2024, 1, 5, 10), 2, 3, 17, 25.0, 91, True),
            ),
        )
        parsed = SuperMemoCollection(
            name="Example",
            kno_path=root / "Example.Kno",
            collection_dir=root / "Example",
            fingerprint="a" * 64,
            structure_version=22,
            first_day=date(2024, 1, 1),
            last_day=date(2024, 1, 5),
            default_forgetting_index=10,
            elements=(topic, item),
            optimization_files=(
                OptimizationFile(
                    "alg17/Recall.dat",
                    optimization_source,
                    len(b"opaque-matrix"),
                    __import__("hashlib").sha256(b"opaque-matrix").hexdigest(),
                ),
            ),
        )

        try:
            result = import_supermemo_collection(
                str(addon_dir),
                profile,
                collection,
                parsed,
                deck_name="Imported::Example",
                calendar_today=date(2024, 1, 10),
            )
            assert result.created == 2
            assert result.skipped_existing == 0
            assert result.history_rows == 3
            assert result.optimization_files == 1
            assert result.cloze_cards == 1
            assert result.media_files == 1

            topic_card = collection.get_card(result.card_ids_by_element[1])
            item_card = collection.get_card(result.card_ids_by_element[2])
            assert topic_card.queue == 0
            assert item_card.queue == 2
            assert item_card.type == 2
            assert item_card.ivl == 17
            assert item_card.reps == 2
            assert item_card.lapses == 1
            assert item_card.factor == 4250
            assert item_card.due == collection.sched.today + 10
            custom = json.loads(item_card.custom_data)
            assert custom["incr"]["sm"] == {
                "af": 4.25,
                "fi": 8,
                "fp": "a" * 32,
                "id": 2,
            }

            item_note = collection.get_note(item_card.nid)
            assert item_note.note_type()["name"] == "Incremento SuperMemo Cloze"
            assert item_note.note_type()["type"] == 1
            assert item_note["Text"] == (
                "Mention a <strong>{{c1::<em>person</em>}}</strong>: "
                "Gets the attention of someone else"
            )
            assert item_note["Back Extra"] == "<p><u>Source</u> context</p>"
            assert item_note["Media"].startswith('<img src="incremento-supermemo-')
            media_name = item_note["Media"].split('src="', 1)[1].split('"', 1)[0]
            assert (Path(collection.media.dir()) / media_name).read_bytes() == image_source.read_bytes()
            assert item_note["Incremento_Source_Type"] == "SuperMemo"
            assert item_note["Incremento_Source_Title"] == "Reference title"
            assert item_note["Incremento_Source_Link"] == "https://example.com/reference"
            assert item_note["Incremento_Source_Author"] == "Reference author"
            assert "SuperMemo FI" not in item_note.keys()

            rows = collection.db.all(
                "select ease, ivl, lastIvl, type from revlog where cid=? order by id",
                item_card.id,
            )
            assert rows == [[0, 3, 0, 4], [1, 17, 3, 1]], rows
            assert get_priority(str(addon_dir), profile, item_card.id) == 0.0
            assert get_priority(str(addon_dir), profile, topic_card.id) == 100.0
            assert db.get_topic_schedule(str(addon_dir), profile, topic_card.id) == (3.5, 11)
            tree = {row["card_id"]: row for row in db.get_knowledge_tree_nodes(str(addon_dir), profile)}
            assert tree[item_card.id]["parent_card_id"] == topic_card.id
            assert tree[item_card.id]["node_kind"] == "item"

            manifest = (
                addon_dir
                / "user_files"
                / profile
                / "supermemo_imports"
                / ("a" * 64)
                / "optimization"
                / "manifest.json"
            )
            assert manifest.is_file()
            assert (manifest.parent / "alg17" / "Recall.dat").read_bytes() == b"opaque-matrix"

            second = import_supermemo_collection(
                str(addon_dir),
                profile,
                collection,
                parsed,
                deck_name="Imported::Example",
                calendar_today=date(2024, 1, 10),
            )
            assert second.created == 0
            assert second.skipped_existing == 2
            assert len(collection.find_cards("tag:Incremento::SuperMemo")) == 2
            assert collection.db.scalar("select count() from revlog") == 3
        finally:
            collection.close()
            db.close_connection()

        print("real Anki SuperMemo import: ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "real Anki SuperMemo import: ok" in result.stdout
