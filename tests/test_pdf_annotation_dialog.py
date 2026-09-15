"""PDF file location actions remain read-only and follow the current link."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


def run_dialog_script(script, tmp_path, *arguments):
    result = subprocess.run(
        [sys.executable, '-c', dedent(script), str(tmp_path), *arguments],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('platform,label', [
    ('darwin', 'Show in Finder'), ('win32', 'Show in File Explorer'),
    ('linux', 'Show containing folder'),
])
@pytest.mark.parametrize('linked', [False, True], ids=['managed-copy', 'original'])
def test_reveal_pdf_uses_existing_file_without_syncing(tmp_path, platform, label, linked):
    run_dialog_script('''
        import pathlib, sys
        from aqt.qt import QApplication, QWidget, QPushButton
        sys.path.extend([str(pathlib.Path.cwd() / 'backend'), str(pathlib.Path.cwd() / 'frontend')])
        from frontend import pdf_annotation_dialog as ui

        app = QApplication([])
        root = pathlib.Path(sys.argv[1])
        managed = root / 'managed.pdf'
        original = root / 'original.pdf'
        managed.write_bytes(b'%PDF-managed')
        original.write_bytes(b'%PDF-original')
        linked = sys.argv[4] == 'yes'
        requests, reveals = [], []
        ui.reveal_local_file = lambda path: reveals.append(path) or True
        sys.platform = sys.argv[2]
        parent = QWidget()
        ui.show_pdf_annotation_dialog(parent, str(managed), str(original) if linked else '',
                                      lambda *args: requests.append(args))
        dialog = parent._annotation_dialog
        app.processEvents()
        button = next((button for button in dialog.findChildren(QPushButton)
                       if button.text() == sys.argv[3]), None)
        assert button is not None, 'Missing file location action'
        button.click()
        assert reveals == [str(original if linked else managed)]
        assert requests == [], 'Locating the file must not rewrite or sync it'
        assert managed.read_bytes() == b'%PDF-managed'
        assert original.read_bytes() == b'%PDF-original'
        dialog.close()
    ''', tmp_path, platform, label, 'yes' if linked else 'no')


def test_reveal_follows_unlink_and_reports_missing_file_without_sync(tmp_path):
    run_dialog_script('''
        import pathlib, sys
        from aqt.qt import QApplication, QWidget, QPushButton, QLabel
        sys.path.extend([str(pathlib.Path.cwd() / 'backend'), str(pathlib.Path.cwd() / 'frontend')])
        from frontend import pdf_annotation_dialog as ui

        app = QApplication([])
        root = pathlib.Path(sys.argv[1])
        managed, original = root / 'managed.pdf', root / 'original.pdf'
        managed.write_bytes(b'%PDF-managed')
        original.write_bytes(b'%PDF-original')
        sys.platform = 'darwin'
        requests, reveals = [], []
        ui.reveal_local_file = lambda path: reveals.append(path) or True
        parent = QWidget()
        ui.show_pdf_annotation_dialog(parent, str(managed), str(original),
                                      lambda *args: requests.append(args))
        dialog = parent._annotation_dialog
        app.processEvents()
        buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
        buttons['Unlink original PDF'].click()
        assert len(requests) == 1 and requests[0][0] == ''
        assert not buttons['Show in Finder'].isEnabled()
        requests[0][1]({'source_path': ''}, None)
        buttons['Show in Finder'].click()
        assert reveals == [str(managed)]
        assert len(requests) == 1
        managed.unlink()
        buttons['Show in Finder'].click()
        assert reveals == [str(managed)]
        assert len(requests) == 1
        assert any(label.text() == 'Could not show the PDF in its folder. Check that it still exists and try again.'
                   for label in dialog.findChildren(QLabel))
        dialog.close()
    ''', tmp_path)
