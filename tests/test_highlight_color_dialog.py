"""The shared Qt palette accepts HTML colors and preserves cancellation."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize('accepted', [True, False], ids=['hex-selected', 'cancelled'])
def test_picker_has_english_palette_and_working_hex_entry(accepted):
    result = subprocess.run([sys.executable, '-c', dedent('''
        import pathlib, sys
        from aqt.qt import QApplication, QColorDialog, QDialog, QLineEdit, QTimer, QWidget
        sys.path.extend([str(pathlib.Path.cwd() / 'backend'), str(pathlib.Path.cwd() / 'frontend')])
        from frontend.highlight_color_dialog import choose_highlight_color
        app = QApplication([])
        parent = QWidget()
        errors = []
        def interact():
            dialog = next(w for w in app.topLevelWidgets() if isinstance(w, QColorDialog))
            try:
                assert dialog.windowTitle() == 'Choose annotation color'
                assert dialog.testOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
                assert not dialog.testOption(QColorDialog.ColorDialogOption.ShowAlphaChannel)
                assert QColorDialog.standardColor(47).isValid()
                field = dialog.findChild(QLineEdit, 'qt_colorname_lineedit')
                assert field is not None and field.text() == '#123abc'
                field.setText('#F1A2B3')
                field.textEdited.emit(field.text())
                if sys.argv[1] == 'yes':
                    dialog.accept()
                else:
                    dialog.reject()
            except Exception as error:
                errors.append(error)
                dialog.reject()
        QTimer.singleShot(0, interact)
        selected = choose_highlight_color(parent, '#123ABC')
        assert not errors, repr(errors)
        assert selected == ('#f1a2b3' if sys.argv[1] == 'yes' else None), selected
    '''), 'yes' if accepted else 'no'], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
