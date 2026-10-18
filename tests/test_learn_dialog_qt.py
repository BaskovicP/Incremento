"""Exercise session tag entry with real Qt widgets, without opening Anki."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_tag_quota_picker_supports_typing_completion_and_add_remove():
    script = dedent(
        """
        import sys
        from types import SimpleNamespace
        from aqt.qt import QApplication, QPushButton
        from PyQt6.QtTest import QTest

        sys.path[:0] = ['backend', 'frontend']
        import learn_dialog as learn

        app = QApplication([])
        tags = ['blockchain', 'Study::Biology', 'Study::Biochemistry']
        learn.mw = SimpleNamespace(
            addonManager=object(),
            col=SimpleNamespace(tags=SimpleNamespace(all=lambda: tags), find_cards=lambda _query: []),
        )
        learn.load_addon_config = lambda *_args: {'dialog': {'setup_mode': 'advanced'}}
        for name in ('count_ready_topic_cards', 'count_ready_item_cards',
                     'count_ready_topic_cards_by_tag', 'count_ready_item_cards_by_tag'):
            setattr(learn._card_utils, name, lambda *_args, **_kwargs: 0)

        dialog = learn.SchedulerConfigDialog()
        combo = dialog._tag_combo
        assert combo.isEditable(), 'Tag quotas must accept typed tag names'
        panel_layout = combo.parentWidget().layout()
        add_row = next(panel_layout.itemAt(i).layout() for i in range(panel_layout.count())
                       if panel_layout.itemAt(i).layout() is not None
                       and panel_layout.itemAt(i).layout().indexOf(combo) >= 0)
        add_button = add_row.itemAt(add_row.indexOf(combo) + 1).widget()
        assert add_button.text() == learn.t('common_add')
        original_count = combo.count()
        combo.lineEdit().selectAll()
        QTest.keyClicks(combo.lineEdit(), 'BIO')
        assert combo.currentText() == 'BIO'
        completer = combo.completer()
        completer.setCompletionPrefix(combo.currentText())
        matches = [completer.completionModel().index(row, 0).data()
                   for row in range(completer.completionCount())]
        assert matches == ['Study::Biochemistry', 'Study::Biology'], matches

        combo.setEditText('  study::biology  ')
        add_button.click()
        assert [row['tag'] for row in dialog._linked_rows] == ['Study::Biology', learn.NO_TAGS_KEY]
        assert combo.findText('Study::Biology') == -1
        assert combo.count() == original_count - 1
        assert dialog._build_current_dict()['tag_rows'][0]['tag'] == 'Study::Biology'

        # Typing cannot bypass the existing-tag and duplicate checks.
        for text in ('STUDY::BIOLOGY', 'nonexistent-tag', ''):
            combo.setEditText(text)
            add_button.click()
            assert len(dialog._linked_rows) == 2
            assert combo.count() == original_count - 1

        row = dialog._linked_rows[0]
        remove_button = next(button for button in row['widget'].findChildren(QPushButton)
                             if button.text() == '✕')
        remove_button.click()
        assert [combo.itemText(i) for i in range(combo.count())] == sorted(tags)
        completer.setCompletionPrefix('BIO')
        assert completer.completionCount() == 2
        assert dialog._linked_rows[0]['tag'] == learn.NO_TAGS_KEY
        assert dialog._linked_rows[0]['slider'].value() == 100
        assert not dialog._linked_rows[0]['slider'].isEnabled()
        dialog.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_session_estimate_uses_real_anki_availability_and_reacts_to_filters():
    script = dedent(
        """
        import os
        import sys
        import tempfile
        from types import SimpleNamespace
        from anki.collection import Collection
        from aqt.qt import QApplication

        sys.path[:0] = ['backend', 'frontend']
        import learn_dialog as learn

        app = QApplication([])
        with tempfile.TemporaryDirectory(prefix='incremento-session-estimate-') as root:
            col = Collection(os.path.join(root, 'collection.anki2'))
            try:
                for index in range(20):
                    note = col.new_note(col.models.by_name('Basic'))
                    note['Front'] = f'fixture-{index}'
                    note['Back'] = 'answer'
                    note.tags = ['blockchain']
                    col.add_note(note, col.decks.id('Topics' if index < 7 else 'Default'))
                # Other tags and suspended cards must not inflate the preview.
                for index in range(3):
                    note = col.new_note(col.models.by_name('Basic'))
                    note['Front'] = f'excluded-{index}'
                    note.tags = ['unrelated'] if index else ['blockchain']
                    col.add_note(note, col.decks.id('Default'))
                    if index == 0:
                        col.sched.suspend_cards(note.card_ids())

                learn._ADDON_DIR = root
                learn._active_profile = lambda: 'Fixture'
                learn.mw = SimpleNamespace(addonManager=object(), col=col)
                learn.load_addon_config = lambda *_args: {'dialog': {
                    'setup_mode': 'advanced', 'session_card_count': 500,
                    'topics_slider': 54, 'pdf_slider': 100,
                    'document_mix_version': 1, 'random_slider': 0,
                    'tag_rows': [{'tag': 'blockchain', 'weight': 100}],
                    'no_tags_checked': False,
                }}
                # These separate header counts are unrelated to the table's selection.
                for name in ('count_ready_topic_cards', 'count_ready_item_cards',
                             'count_ready_topic_cards_by_tag', 'count_ready_item_cards_by_tag'):
                    setattr(learn._card_utils, name, lambda *_args, **_kwargs: 0)
                results = []
                def run_query(*, parent, op, success, failure):
                    result = op(col)
                    results.append(result)
                    success(result)
                learn._run_session_preview_query = run_query

                dialog = learn.SchedulerConfigDialog()
                assert dialog._mix_preview_timer.isActive()
                assert dialog._tag_content_table.rowCount() == 0
                dialog._mix_preview_timer.timeout.emit()
                table = dialog._tag_content_table
                assert '20 / 500' in dialog._expected_counts_lbl.text(), dialog._expected_counts_lbl.text()
                assert [table.item(0, c).text() for c in range(1, 5)] == ['0', '7', '13', '20']
                assert len(set(results[-1]['selection']['selected_ids'])) == 20
                assert dialog._count_spin.value() == 500

                dialog._cb_new.setChecked(False)
                assert table.rowCount() == 0
                dialog._mix_preview_timer.timeout.emit()
                assert '0 / 500' in dialog._expected_counts_lbl.text()
                assert table.item(0, 4).text() == '0'

                dialog._cb_new.setChecked(True)
                dialog._topics_filter_edit.setText('tag:missing')
                dialog._items_filter_edit.setText('tag:missing')
                dialog._mix_preview_timer.timeout.emit()
                assert table.item(0, 4).text() == '0'

                dialog._topics_filter_edit.clear()
                dialog._items_filter_edit.clear()
                dialog._count_spin.setValue(5)
                dialog._mix_preview_timer.timeout.emit()
                assert '5 / 5' in dialog._expected_counts_lbl.text()
                assert table.item(0, 4).text() == '5'
                assert len(set(results[-1]['selection']['selected_ids'])) == 5
                dialog.reject()
                assert not dialog._mix_preview_timer.isActive()
            finally:
                col.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_table_live_preview_and_session_share_counts_and_card_ids():
    script = dedent(
        """
        import os
        import random
        import sys
        import tempfile
        from collections import Counter
        from types import SimpleNamespace
        from anki.collection import Collection
        from aqt.qt import QApplication

        import types
        addon = types.ModuleType('incremento')
        addon.__path__ = [os.getcwd()]
        sys.modules['incremento'] = addon
        from incremento.frontend import learn_dialog as learn
        from incremento.backend import session

        app = QApplication([])
        with tempfile.TemporaryDirectory(prefix='incremento-preview-consistency-') as root:
            col = Collection(os.path.join(root, 'collection.anki2'))
            try:
                for model_name in ('Incremento PDF', 'Incremento EPUB'):
                    model = col.models.copy(col.models.by_name('Basic'))
                    model['id'] = 0
                    model['name'] = model_name
                    col.models.add(model)
                for index in range(30):
                    model_name = ('Incremento PDF' if index == 0 else
                                  'Incremento EPUB' if index in (1, 2) else 'Basic')
                    note = col.new_note(col.models.by_name(model_name))
                    note['Front'] = f'fixture-{index}'
                    note['Back'] = 'answer'
                    note.tags = ['alpha' if index % 2 else 'beta']
                    if index == 2:
                        note.tags.append('item')
                    col.add_note(note, col.decks.id('Topics' if index < 12 else 'Default'))

                fake_mw = SimpleNamespace(addonManager=object(), col=col)
                learn._ADDON_DIR = session._ADDON_DIR = root
                learn._active_profile = session._active_profile = lambda: 'Fixture'
                learn.mw = session.mw = fake_mw
                for name in ('count_ready_topic_cards', 'count_ready_item_cards',
                             'count_ready_topic_cards_by_tag', 'count_ready_item_cards_by_tag'):
                    setattr(learn._card_utils, name, lambda *_args, **_kwargs: 0)
                requests = []
                learn._run_session_preview_query = lambda **kwargs: requests.append(kwargs)
                def drain():
                    while requests:
                        request = requests.pop(0)
                        request['success'](request['op'](col))
                actual_select = learn.select_session_cards
                selections = []
                def select(*args, **kwargs):
                    selections.append(True)
                    kwargs.setdefault('col', col)
                    kwargs.setdefault('profile', 'Fixture')
                    return actual_select(*args, **kwargs)
                learn.select_session_cards = select

                reserved_id = col.find_cards('tag:alpha')[0]
                reserved_deck = session._prepare_filtered_review_deck(
                    [reserved_id], deck_name='Other filtered deck', preserve_order=True,
                    select_deck=False, col=col,
                )
                own_id = col.find_cards('tag:beta')[0]
                session._prepare_filtered_review_deck(
                    [own_id], deck_name='Incremento Session', preserve_order=True,
                    select_deck=False, col=col,
                )

                for strict, random_rate, target, require_preview in (
                    (False, 0, 500, False), (False, 100, 9, False),
                    (True, 100, 9, True), (True, 0, 500, True),
                ):
                    random.seed(42)
                    config = {'scheduler_presets': {'Focus': {}}, 'dialog': {
                        'setup_mode': 'advanced', 'session_card_count': target,
                        'topics_slider': 40, 'pdf_slider': 70,
                        'document_mix_version': learn.DOCUMENT_MIX_VERSION,
                        'random_slider': random_rate, 'enforce_priority': strict,
                        'tag_rows': [{'tag': 'alpha', 'weight': 60}, {'tag': 'beta', 'weight': 40}],
                        'no_tags_checked': False, 'use_live_preview': require_preview,
                    }}
                    learn.load_addon_config = session.load_addon_config = lambda *_args: config
                    dialog = learn.SchedulerConfigDialog()
                    dialog._mix_preview_timer.timeout.emit()
                    drain()
                    cache = dialog.get_preview_override()
                    assert cache is not None, 'The displayed selection must be reused by a normal launch'
                    expected_ids = cache['selected_ids']
                    expected_meta = cache['picked_meta']
                    if len(selections) == 1:
                        assert own_id in expected_ids, 'Cards already in this session deck remain eligible'
                    calls_before_live = len(selections)
                    live = learn._LiveSchedulerPreviewDialog(dialog)
                    dialog._live_preview_dialog = live
                    live.load_cached_or_refresh()
                    drain()
                    assert len(selections) == calls_before_live, 'Opening Live preview must not reroll selection'
                    assert [entry['card_id'] for entry in live._entries] == expected_ids
                    live.refresh_now()
                    assert dialog._tag_content_table.rowCount() == live._table.rowCount() == 0
                    drain()
                    assert len(selections) == calls_before_live + 1
                    dialog._profile_combo.setCurrentIndex(dialog._profile_combo.findText('Focus'))
                    assert dialog._tag_content_table.rowCount() == live._table.rowCount() == 0
                    # Automatic refresh must consume the same pending selection too.
                    live.isVisible = lambda: True
                    dialog._refresh_live_preview_if_open()
                    drain()
                    cache = dialog.get_preview_override()
                    expected_ids, expected_meta = cache['selected_ids'], cache['picked_meta']
                    assert [entry['card_id'] for entry in live._entries] == expected_ids
                    def group(meta):
                        return ('Items' if meta.get('study_kind') == 'items' or meta['card_type'] == 'items'
                                else 'PDF' if meta['card_type'] in ('pdf', 'epub') else 'Topics')
                    expected_counts = Counter(
                        group(meta) for meta in expected_meta.values())
                    assert Counter(group(entry) for entry in live._entries) == expected_counts
                    table = dialog._tag_content_table
                    assert [int(table.item(0, c).text()) for c in range(1, 5)] == [
                        expected_counts['PDF'], expected_counts['Topics'], expected_counts['Items'], len(expected_ids)]
                    for row in range(1, table.rowCount()):
                        tag = table.item(row, 0).text()
                        expected = sum(meta.get('tag') == tag for meta in expected_meta.values())
                        if tag == learn.t('session_other'):
                            expected = sum(meta.get('tag') in (None, learn.NO_TAGS_KEY) for meta in expected_meta.values())
                        assert int(table.item(row, 4).text()) == expected
                        for column, kind in enumerate(('PDF', 'Topics', 'Items'), start=1):
                            count = sum(group(meta) == kind and (
                                meta.get('tag') == tag or
                                (tag == learn.t('session_other') and meta.get('tag') in (None, learn.NO_TAGS_KEY)))
                                for meta in expected_meta.values())
                            total = expected_counts[kind]
                            text = str(count) if not total else f'{count} ({count / total * 100:.0f}%)'
                            assert table.item(row, column).text() == text

                    # Exercise the production launch callbacks and Anki's real filtered-deck builder.
                    built = []
                    def run_operation(*, op, success, **kwargs):
                        success(op(col))
                    session._run_collection_query = session._run_collection_mutation_without_progress = run_operation
                    session._defer_profile_ui_action = lambda _profile, callback: callback()
                    session._activate_incremento_session = lambda result, **kwargs: built.append(result)
                    session.release_expired_timed_postpones = lambda: None
                    dialog.exec = lambda: 1
                    dialog.save_config = lambda **kwargs: None
                    # A new draw is deliberately forbidden after either preview has been shown.
                    original_pick = session.SessionPicker.pick_until
                    session.SessionPicker.pick_until = lambda *args: (_ for _ in ()).throw(AssertionError('unexpected reroll'))
                    session.learnFunction(dialog_factory=lambda *args, **kwargs: dialog)
                    session.SessionPicker.pick_until = original_pick
                    assert len(built) == 1
                    assert built[0].selected_ids == expected_ids
                    actual_ids = col.find_cards('deck:"Incremento Session (Focus)"')
                    assert set(actual_ids) == set(expected_ids)
                    assert len(actual_ids) == int(table.item(0, 4).text())
                    assert reserved_id not in expected_ids
                    assert col.get_card(reserved_id).did == reserved_deck
                    col.sched.empty_filtered_deck(built[0].deck_id)
                    dialog.reject()
            finally:
                col.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
