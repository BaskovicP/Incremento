"""The shared Qt palette accepts HTML colors and preserves cancellation."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize('accepted', [True, False], ids=['hex-selected', 'cancelled'])
def test_picker_has_english_palette_and_working_hex_entry(accepted, tmp_path):
    result = subprocess.run([sys.executable, '-c', dedent('''
        import pathlib, sys
        from aqt.qt import QApplication, QColorDialog, QDialog, QLineEdit, QSettings, QTimer, QWidget
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, sys.argv[2])
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
        selected = choose_highlight_color(parent, '#123ABC', addon_dir=sys.argv[2], profile='Profile A')
        assert not errors, repr(errors)
        assert selected == ('#f1a2b3' if sys.argv[1] == 'yes' else None), selected
    '''), 'yes' if accepted else 'no', str(tmp_path)], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('accepted', [True, False], ids=['saved-on-ok', 'saved-on-cancel'])
def test_palette_survives_new_process_and_does_not_leak_between_profiles(accepted, tmp_path):
    script = dedent('''
        import pathlib, sys
        from aqt.qt import QApplication, QColor, QColorDialog, QPushButton, QSettings, QTimer, QWidget
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, sys.argv[1])
        sys.path.extend([str(pathlib.Path.cwd() / 'backend'), str(pathlib.Path.cwd() / 'frontend')])
        from frontend.highlight_color_dialog import choose_highlight_color
        from db import close_connection, get_reader_custom_colors
        app = QApplication([])
        parent = QWidget()
        phase, accepted = sys.argv[2], sys.argv[3] == 'yes'
        # A fresh process starts with unrelated Qt-global colors, not our saved palette.
        initial = ['#ffffff'] * 16 if phase == 'save' else ['#ff0000'] * 16
        initial[7] = '#aabbcc'
        for slot, color in enumerate(initial):
            QColorDialog.setCustomColor(slot, QColor(color))
        saved = list(initial) if phase == 'save' else ['#ffffff'] * 16
        saved[0], saved[7], saved[15] = '#123abc', '#aabbcc', '#000000'

        def palette():
            return [QColorDialog.customColor(i).name() for i in range(16)]

        def pick(profile, expected, changes, accept):
            errors = []
            def interact():
                dialog = next(w for w in app.topLevelWidgets() if isinstance(w, QColorDialog) and w.isVisible())
                try:
                    assert palette() == expected, palette()
                    for slot, color in changes.items():
                        if slot == 0:
                            dialog.setCurrentColor(QColor(color))
                            add = next(button for button in dialog.findChildren(QPushButton)
                                       if button.text().replace('&', '') == 'Add to Custom Colors')
                            add.click()
                            assert QColorDialog.customColor(0).name() == color
                        else:
                            QColorDialog.setCustomColor(slot, QColor(color))
                    dialog.setCurrentColor(QColor('#654321'))
                    dialog.accept() if accept else dialog.reject()
                except Exception as error:
                    errors.append(error)
                    dialog.reject()
            QTimer.singleShot(0, interact)
            selected = choose_highlight_color(parent, 'yellow', addon_dir=sys.argv[1], profile=profile)
            assert not errors, repr(errors)
            assert selected == ('#654321' if accept else None), selected
            # Incremento must not leave this profile's colors in unrelated Qt dialogs.
            assert palette() == initial, palette()

        if phase == 'save':
            pick('Profile A', initial, {0: '#123abc', 15: '#000000'}, accepted)
            # An unsaved second profile inherits only the original legacy Qt palette.
            pick('Profile B', initial, {0: '#abcdef'}, True)
        else:
            pick('Profile A', saved, {}, False)
            other = ['#ffffff'] * 16
            other[0], other[7] = '#abcdef', '#aabbcc'
            pick('Profile B', other, {}, False)
        close_connection()
        assert get_reader_custom_colors(sys.argv[1], 'Profile A') == saved
        close_connection()
    ''')
    for phase in ('save', 'restore'):
        result = subprocess.run([sys.executable, '-c', script, str(tmp_path), phase,
                                 'yes' if accepted else 'no'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
