"""New direct UI text cannot silently bypass the translation catalogs."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('ui_inventory', Path(__file__).resolve().parents[1] / 'scripts/i18n_inventory.py')
inventory_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory_module)


def test_literal_exemption_is_scoped_to_exact_source_and_text(tmp_path):
    (tmp_path / 'frontend').mkdir()
    source = tmp_path / 'frontend/dialog.py'
    source.write_text('label = QLabel("PDF_Cover_Image")\n')
    exemptions = [{'file': 'frontend/dialog.py', 'sink': 'QLabel', 'text': 'PDF_Cover_Image', 'reason': 'Stable Anki field identifier.'}]
    inventory_module.check_inventory(tmp_path, exemptions)
    source.write_text('label = QLabel("Choose a file")\n')
    with pytest.raises(ValueError, match='Choose a file'):
        inventory_module.check_inventory(tmp_path, exemptions)


def test_translated_label_passes_without_exemption(tmp_path):
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/dialog.py').write_text('label = QLabel(t("choose_file"))\n')
    inventory_module.check_inventory(tmp_path, [])


def test_reviewer_submenu_and_visibility_actions_cannot_bypass_inventory(tmp_path):
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/reviewer_button_visibility.py').write_text('''
_BUTTONS = (("done", "Done", "done-cell"), ("extract", "Extract", "extract-cell"))
def add_visibility_menu(menu):
    submenu = menu.addMenu("Review buttons")
    submenu.addAction("Show review button group")
    for key, label, cell_id in _BUTTONS:
        submenu.addAction(f"Show {label} button")
''')

    rows = inventory_module.inventory(tmp_path)

    assert [(row['sink'], row['text']) for row in rows] == [
        ('addMenu', 'Review buttons'),
        ('addAction', 'Show review button group'),
        ('addAction', 'f"Show {label} button"'),
    ]
    with pytest.raises(ValueError, match='Review buttons'):
        inventory_module.check_inventory(tmp_path, [])


def test_tuple_loop_only_reports_labels_that_reach_ui(tmp_path):
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/reviewer.py').write_text('''
_BUTTONS = (("done", "Done", "done-cell"), ("extract", "Extract", "extract-cell"))
def add_menu(menu):
    for key, label, cell_id in _BUTTONS:
        action = menu.addAction(label)
        action.setObjectName(cell_id)
''')

    rows = inventory_module.inventory(tmp_path)

    assert [(row['sink'], row['text']) for row in rows] == [
        ('addAction', 'Done'), ('addAction', 'Extract'),
    ]


def test_local_text_assignment_is_reported_but_translation_and_runtime_values_are_not(tmp_path):
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/reviewer.py').write_text('''
def refresh(button, user_label):
    label = "Show Extract button"
    button.setText(label)
    label = t("show_extract")
    button.setText(label)
    button.setText(user_label)
    for key, title in (("done", t("done")), ("extract", t("extract"))):
        menu.addAction(title)
''')

    rows = inventory_module.inventory(tmp_path)

    assert [(row['sink'], row['text']) for row in rows] == [
        ('setText', 'Show Extract button'),
    ]


def test_function_parameters_do_not_inherit_same_named_global_label(tmp_path):
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/reviewer.py').write_text('''
label = "Global label"
def set_caption(button, label):
    button.setText(label)
''')

    inventory_module.check_inventory(tmp_path, [])


def test_direct_widget_literal_in_function_default_remains_visible(tmp_path):
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/reviewer.py').write_text('''
def show_dialog(button=QPushButton("Show Extract button")):
    return button
''')

    assert [row['text'] for row in inventory_module.inventory(tmp_path)] == ['Show Extract button']


def test_self_referencing_label_metadata_does_not_recurse_forever(tmp_path):
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/reviewer.py').write_text('''
labels = []
labels = [labels, "Show Extract button"]
menu.addItems(labels)
''')

    assert [row['text'] for row in inventory_module.inventory(tmp_path)] == ['Show Extract button']
