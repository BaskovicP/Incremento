"""The real Qt tree publishes only the current background snapshot."""

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent


def test_tree_load_search_refresh_and_close_use_one_current_snapshot(tmp_path):
    script = dedent(r'''
        import sys
        from types import SimpleNamespace, ModuleType
        import importlib
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        from anki.collection import Collection
        from aqt.qt import QApplication
        import aqt.operations
        app = QApplication(['snapshot-test'])
        package = ModuleType('snapshot_addon'); package.__path__ = [str(Path.cwd())]
        sys.modules['snapshot_addon'] = package
        ui = importlib.import_module('snapshot_addon.frontend.knowledge_tree_dialog')
        db = importlib.import_module('snapshot_addon.backend.db')
        backend = importlib.import_module('snapshot_addon.backend.knowledge_tree')
        jobs = []
        class QueryOp:
            def __init__(self, *, parent, op, success):
                self.op, self.success = op, success
            def failure(self, callback):
                self.failed = callback; return self
            def run_in_background(self):
                jobs.append(self)
        aqt.operations.QueryOp = QueryOp
        root = Path(sys.argv[1]); addon = str(root/'addon')
        col = Collection(str(root/'collection.anki2'))
        try:
            note = col.new_note(col.models.by_name('Basic'))
            note.fields = ['Initial title', 'Original body']
            col.add_note(note, 1); cid = col.find_cards(f'nid:{note.id}')[0]
            db.set_knowledge_tree_structure(addon, 'SnapshotTest', [
                dict(card_id=cid, parent_card_id=None, node_kind='topic', sort_order=0)])
            current_profile = ['SnapshotTest']
            ui.active_profile = lambda: current_profile[0]
            ui.mw = SimpleNamespace(col=col)
            backend.mw = ui.mw
            dialog = ui.KnowledgeTreeDialog(addon, profile='SnapshotTest', select_card_id=cid)
            dialog._selected_pdf_target = lambda **kwargs: None
            assert len(jobs) == 1 and dialog._rows_cache == []
            with ThreadPoolExecutor(max_workers=1) as pool:
                def complete(job):
                    value = pool.submit(job.op, col).result(timeout=10)
                    job.success(value)
                complete(jobs[0])
                assert dialog._selected_card_id() == cid
                dialog._search_edit.setText('Initial')
                assert [r['card_id'] for r in dialog._search_results_cache] == [cid]
                # Search must use the exact already-loaded snapshot, with no collection fetch.
                original_get_card, original_get_note = col.get_card, col.get_note
                def forbidden(*args): raise AssertionError('Search fetched Anki metadata')
                col.get_card = col.get_note = forbidden
                dialog._search_edit.setText('missing')
                assert dialog._search_results_cache == []
                col.get_card, col.get_note = original_get_card, original_get_note
                note['Front'] = 'Renamed title'; col.update_note(note)
                dialog._on_collection_changed(SimpleNamespace(note=True), None)
                app.processEvents()
                assert len(jobs) == 2
                assert dialog._snapshot is None
                complete(jobs[-1])
                dialog._search_edit.setText('Renamed')
                assert [r['title'] for r in dialog._search_results_cache] == ['Renamed title']
                # A deleted first root promotes its child before the next root.
                missing = col.new_note(col.models.by_name('Basic'))
                missing.fields = ['Deleted root', '']; col.add_note(missing, 1)
                missing_cid = col.find_cards(f'nid:{missing.id}')[0]
                right = col.new_note(col.models.by_name('Basic'))
                right.fields = ['Right root', '']; col.add_note(right, 1)
                right_cid = col.find_cards(f'nid:{right.id}')[0]
                db.set_knowledge_tree_structure(addon, 'SnapshotTest', [
                    dict(card_id=missing_cid, parent_card_id=None, node_kind='topic', sort_order=0),
                    dict(card_id=right_cid, parent_card_id=None, node_kind='topic', sort_order=1),
                    dict(card_id=cid, parent_card_id=missing_cid, node_kind='item', sort_order=0)])
                col.remove_notes([missing.id])
                dialog.reload(); complete(jobs[-1])
                assert [dialog._tree.topLevelItem(i).data(0, ui._ROLE_CARD_ID)
                        for i in range(dialog._tree.topLevelItemCount())] == [cid, right_cid]
                assert len(db.get_knowledge_tree_nodes(addon, 'SnapshotTest')) == 3
                # Reloading during a pending read coalesces and discards the obsolete load.
                dialog.reload(); old = jobs[-1]
                old_data = pool.submit(old.op, col).result(timeout=10)
                dialog.reload(); count = len(jobs)
                old.success(old_data)
                assert len(jobs) == count + 1
                assert dialog._snapshot is None
                complete(jobs[-1])
                dialog.reload(); pending = jobs[-1]
                data = pool.submit(pending.op, col).result(timeout=10)
                current_profile[0] = 'OtherProfile'
                pending.success(data)
                assert dialog._snapshot is None
                current_profile[0] = 'SnapshotTest'
                dialog.reload(); pending = jobs[-1]
                data = pool.submit(pending.op, col).result(timeout=10)
                dialog.accept()
                pending.success(data)
                assert dialog._snapshot is None
                assert dialog._closed
                # Closing must not remove the current callback during hook iteration
                # and accidentally skip another dialog's profile-close handler.
                another = ui.KnowledgeTreeDialog(addon, profile='SnapshotTest')
                observed = []
                follower = lambda: observed.append('closed')
                ui.gui_hooks.profile_will_close.append(follower)
                ui.gui_hooks.profile_will_close()
                assert another._closed and observed == ['closed']
                ui.gui_hooks.profile_will_close.remove(follower)
                app.processEvents()
            print('snapshot UI: ok')
        finally:
            col.close(); db.close_connection()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'snapshot UI: ok' in result.stdout
