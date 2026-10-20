"""Exercise extension export through real Qt without a live Anki profile."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_setup_exports_firefox_and_preserves_files_on_cancel_or_failure(tmp_path):
    script = dedent('''
        import sys
        from pathlib import Path
        from unittest.mock import patch
        from zipfile import ZipFile
        from aqt.qt import QApplication, QPlainTextEdit, QPushButton
        from backend.i18n import initialize_language, t
        from frontend.companion_setup import CompanionSetupDialog

        app = QApplication([])
        output = Path(sys.argv[1]) / 'companion'
        initialize_language('en')
        dialog = CompanionSetupDialog('firefox')
        with patch('frontend.companion_setup.QFileDialog.getSaveFileName', return_value=(str(output), '')):
            dialog._export()
        archive = output.with_suffix('.xpi')
        assert dialog._path.text() == str(archive)
        assert dialog._status.text() == t('companion_setup_saved')
        with ZipFile(archive) as exported:
            assert 'manifest.json' in exported.namelist()
            assert 'dist/background.js' in exported.namelist()
        original = archive.read_bytes()
        with patch('frontend.companion_setup.QFileDialog.getSaveFileName', return_value=('', '')):
            dialog._export()
        assert archive.read_bytes() == original
        assert dialog._status.text() == t('companion_setup_saved')
        with patch('frontend.companion_setup.QFileDialog.getSaveFileName', return_value=(str(archive), '')):
            dialog._export()
        assert archive.read_bytes() == original
        assert dialog._status.text() == t('companion_setup_failed')
        assert list(output.parent.iterdir()) == [archive]
        for locale in ('en', 'hr', 'zh-Hans'):
            initialize_language(locale)
            for browser in ('chrome', 'firefox'):
                guide = CompanionSetupDialog(browser)
                guide.show()
                app.processEvents()
                text = guide.findChild(QPlainTextEdit).toPlainText()
                assert 'Firefox' in text if browser == 'firefox' else 'Chrome' in text
                assert 'companion_setup_' not in text
                assert all(button.width() >= button.sizeHint().width()
                           for button in guide.findChildren(QPushButton))
                if browser == 'chrome':
                    with patch('frontend.companion_setup.reveal_local_file', return_value=False) as reveal:
                        guide._show_folder()
                    assert Path(reveal.call_args.args[0]).name == 'manifest.json'
                    assert guide._status.text() == t('companion_setup_failed')
                guide.close()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
