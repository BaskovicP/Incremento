"""Exercise real Qt sizing; widget stubs cannot detect translated text clipping."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_translated_settings_fit_wrapped_text_at_supported_window_and_font_sizes(tmp_path):
    script = dedent('''
        import sys
        from aqt.qt import QApplication, QFont, QLabel, QStyleFactory
        from backend.i18n import initialize_language
        from frontend.settings_dialog import IncrementoSettingsDialog

        app = QApplication([])
        # QFormLayout's native macOS field sizing exposed the reported bug.
        styles = ['Fusion'] + (['macOS'] if 'macOS' in QStyleFactory.keys() else [])
        failures = []
        for style in styles:
            app.setStyle(style)
            for locale in ('en', 'hr', 'zh-Hans'):
                initialize_language(locale)
                for font_size, width in ((13, 720), (13, 1000), (18, 790)):
                    app.setFont(QFont('Arial', font_size))
                    dialog = IncrementoSettingsDialog({}, current_ui_language=locale,
                        language_pack_context=(sys.argv[1], 'Synthetic'))
                    dialog.resize(width, 640)
                    dialog.show()
                    for tab_index in range(dialog._tabs.count()):
                        dialog._tabs.setCurrentIndex(tab_index)
                        for _ in range(3):
                            app.processEvents()
                        for label in dialog._tabs.currentWidget().findChildren(QLabel):
                            if label.isVisible() and label.wordWrap():
                                required = label.heightForWidth(label.width())
                                if label.height() < required:
                                    failures.append((style, locale, font_size, width,
                                        tab_index, label.text(), label.height(), required))
                    dialog.close()
                    dialog.deleteLater()
                    app.processEvents()
        assert not failures, failures
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
