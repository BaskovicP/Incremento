"""Source refresh with real Anki notes and a headless editor boundary."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_real_anki_extract_copies_rich_sources_on_open_and_each_card_change(tmp_path):
    script = dedent('''
        from pathlib import Path
        import importlib
        from types import ModuleType, SimpleNamespace
        import sys

        from anki.collection import Collection
        from backend.note_metadata import INCREMENTO_METADATA_FIELDS
        package = ModuleType('synthetic_extract_addon')
        package.__path__ = [str(Path.cwd())]
        sys.modules[package.__name__] = package
        dock = importlib.import_module('synthetic_extract_addon.frontend.add_card_dock')

        root = Path(sys.argv[1])
        col = Collection(str(root / 'synthetic.anki2'))
        try:
            model = col.models.new('Synthetic Sources')
            for name in ('Front', 'Back', 'Explanation', 'Sources', 'Priority',
                         *INCREMENTO_METADATA_FIELDS):
                col.models.add_field(model, col.models.new_field(name))
            template = col.models.new_template('Card 1')
            template.update(qfmt='{{Front}}', afmt='{{Back}}')
            col.models.add_template(model, template)
            col.models.add(model)
            cards = []
            for number in (1, 2, 3):
                note = col.new_note(model)
                note['Front'] = f'Synthetic topic {number}'
                note['Back'] = 'Source answer must stay out of the extract'
                note['Sources'] = (
                    f'<a href="https://example.test/video/{number}">Video title {number}</a>'
                    f'<br><a href="https://example.test/book/{number}">Book chapter</a>'
                )
                note['Incremento_Source_Type'] = 'Browser Capture'
                note['Incremento_Source_Link'] = f'https://example.test/video/{number}'
                col.add_note(note, col.decks.id('Default'))
                cards.append(col.get_card(note.card_ids()[0]))

            rendered = []
            editor = SimpleNamespace(note=col.new_note(model), addMode=True,
                                     web=SimpleNamespace(eval=lambda script: None),
                                     loadNote=lambda: rendered.append(list(editor.note.fields)))
            reviewer = SimpleNamespace(card=cards[0])
            dock.mw = SimpleNamespace(col=col, reviewer=reviewer, state='review')
            dock._ADDON_DIR = str(root)
            dock._active_profile = lambda: 'Synthetic'
            dock._config = lambda config=None: config or {'extract_default_type': 'item'}
            dock._dock_editor = lambda: editor
            dock.open_add_card_dock = lambda: None
            dock._priority_for_card_id = lambda card_id: 30
            dock.update_selection_state = lambda *args, **kwargs: None
            for name in ('_inject_transfer_buttons', '_schedule_editor_tag_widget_sync',
                         '_schedule_add_card_tag_button_refresh', '_schedule_extract_draft_autosave'):
                setattr(dock, name, lambda *args: None)

            parent = cards[0]
            dock.prepare_reviewer_extract(
                selected_text='Selected content must stay out of Front',
                note_type_name='', deck_name='',
                field_values=dock.initial_extract_field_values(parent.note(), 'Selected content'),
                metadata=dock._source_extract_metadata_for_card('reviewer', parent.id),
                parent_card_id=parent.id, priority=30, mark_topic=False,
                knowledge_tree_link_enabled=False, link_to_knowledge_tree=True,
            )

            for card in (cards[0], cards[1], cards[2], cards[0]):
                reviewer.card = card
                dock.refresh_reviewer_extract_source(card)
                assert editor.note.id == 0
                assert editor.note['Front'] == ''
                assert editor.note['Back'] == ''
                assert editor.note['Sources'] == card.note()['Sources']
                assert editor.note['Incremento_Source_Link'] == card.note()['Incremento_Source_Link']
                assert editor.note['Incremento_Parent_Card_ID'] == str(card.id)
                assert rendered[-1] == list(editor.note.fields)
                assert card.note()['Front'].startswith('Synthetic topic')
            assert len(col.find_notes('')) == 3
        finally:
            col.close()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
