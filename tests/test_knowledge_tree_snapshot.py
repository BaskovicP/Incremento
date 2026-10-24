"""Real Anki evidence for the tree's read-only shared snapshot."""

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_snapshot_matches_live_metadata_and_search_and_rebuilds_after_changes(tmp_path):
    script = dedent(r'''
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from threading import Event
        from concurrent.futures import CancelledError
        from anki.collection import Collection, AddNoteRequest
        from backend import db, knowledge_tree as tree
        from backend.priority_manager import set_priority

        root = Path(sys.argv[1])
        addon = str(root / 'addon')
        profile = 'SnapshotTest'
        col = Collection(str(root / 'collection.anki2'))
        try:
            model = col.models.by_name('Basic')
            col.models.add_field(model, col.models.new_field('Incremento_Source_Title'))
            col.models.save(model)
            deck = col.decks.id('Physics')
            requests = []
            for i in range(905):
                note = col.new_note(model)
                note.fields = [f'<b>Energy {i}</b>', f'Visible body {i}', 'secret-provenance']
                requests.append(AddNoteRequest(note, deck))
            col.add_notes(requests)
            pairs = col.db.all('SELECT id,nid FROM cards ORDER BY id')
            rows = [dict(card_id=cid, parent_card_id=pairs[0][0] if i else None,
                         node_kind='item' if i else 'topic', sort_order=i)
                    for i, (cid,nid) in enumerate(pairs)]
            db.set_knowledge_tree_structure(addon, profile, rows)
            set_priority(addon, profile, pairs[1][0], 17.5)
            tree.mw = SimpleNamespace(col=col)
            expected = tree.load_knowledge_tree_nodes(addon, profile, cleanup_missing=False)
            queries = [('energy', {}), ('Physics', dict(include_metadata=True)),
                       ('body 904', dict(include_note_text=True)),
                       ('secret-provenance', dict(include_note_text=True))]
            expected_search = [tree.search_knowledge_tree_nodes(addon, profile, q, limit=100, **opts)
                               for q,opts in queries]
            calls = []
            class BatchedDb:
                def all(self, sql, *args):
                    calls.append(len(args))
                    assert len(args) <= 900
                    return col.db.all(sql, *args)
            # No get_card/get_note capability: the snapshot must project in batches.
            operation_col = SimpleNamespace(db=BatchedDb(), models=col.models, decks=col.decks)
            snap = tree.load_knowledge_tree_snapshot(addon, profile, operation_col)
            assert list(snap.rows) == expected
            assert len(calls) == 2
            for (q,opts), wanted in zip(queries, expected_search):
                assert tree.search_knowledge_tree_nodes(addon, profile, q, snapshot=snap,
                                                        limit=100, **opts) == wanted
            assert len(calls) == 2, 'Searching the shared snapshot must not fetch collection data'
            try:
                tree.search_knowledge_tree_nodes(addon, 'Other', 'energy', snapshot=snap)
                raise AssertionError('Cross-profile snapshot accepted')
            except ValueError:
                pass
            note = col.get_note(pairs[1][1]); note['Front'] = 'Renamed'; note['Back'] = 'Updated text'
            col.update_note(note)
            set_priority(addon, profile, pairs[1][0], 23)
            newer = tree.load_knowledge_tree_snapshot(addon, profile, operation_col)
            assert tree.search_knowledge_tree_nodes(addon, profile, 'Renamed', snapshot=snap) == []
            found = tree.search_knowledge_tree_nodes(addon, profile, 'Renamed', snapshot=newer)
            assert [r['card_id'] for r in found] == [pairs[1][0]]
            assert next(r for r in newer.rows if r['card_id'] == pairs[1][0])['priority'] == 23
            # Missing parents disappear from the view without deleting persistent structure.
            col.remove_notes([pairs[0][1]])
            missing = tree.load_knowledge_tree_snapshot(addon, profile, operation_col)
            assert len(missing.rows) == 904
            assert all(r['parent_card_id'] is None for r in missing.rows)
            assert len(db.get_knowledge_tree_nodes(addon, profile)) == 905
            cancelled = Event(); cancelled.set()
            try:
                tree.load_knowledge_tree_snapshot(addon, profile, operation_col, cancel=cancelled)
                raise AssertionError('Cancelled read ran')
            except CancelledError:
                pass
            # A subsequent field reorder must refresh ordinals and hidden-field exclusions.
            model = col.models.get(note.mid)
            col.models.reposition_field(model, model['flds'][1], 0); col.models.save(model)
            reordered = tree.load_knowledge_tree_snapshot(addon, profile, operation_col)
            assert next(r for r in reordered.rows if r['card_id'] == pairs[1][0])['title'] == 'Updated text'
        finally:
            col.close(); db.close_connection()
        print('snapshot: ok')
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'snapshot: ok' in result.stdout
