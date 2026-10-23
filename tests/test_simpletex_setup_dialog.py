"""First-scan setup with real widgets and a disposable profile."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent

import pytest


@pytest.mark.parametrize('outcome', ['save', 'cancel', 'write-failure', 'profile-switch'])
def test_missing_credentials_open_guided_setup_and_only_explicit_current_profile_save_persists(tmp_path, outcome):
    script = dedent(r'''
        import sys
        from types import SimpleNamespace
        from aqt.qt import QApplication, QDialog, QPixmap, QVBoxLayout
        from backend.i18n import initialize_language
        from backend.simpletex_credentials import load_credentials
        from frontend import snapshot_math_dialog as ui

        app = QApplication([])
        initialize_language('en')
        root, outcome = sys.argv[1:]
        profile, jobs, opened = ['A'], [], []
        ui._ADDON_DIR = root
        ui._active_profile = lambda: profile[0]
        ui.mw = SimpleNamespace(col=object(), taskman=SimpleNamespace(
            run_in_background=lambda *args, **kwargs: jobs.append((args, kwargs))))
        ui.open_companion_url = lambda url: opened.append(url) or True
        image = QPixmap(300, 100)
        image.fill()
        picker = QDialog()
        layout = QVBoxLayout(picker)
        button = ui.add_snapshot_math_action(picker, layout, image, is_current=lambda: True)
        button.click()
        scan = picker.findChildren(ui.SnapshotMathDialog)[-1]
        setup = scan._setup_dialog
        assert setup is not None
        assert 'Application List' in setup._application_help.text()
        assert 'once' in setup._secret_help.text().lower()
        assert not jobs and not opened
        setup._account_button.click()
        setup._docs_button.click()
        assert opened == ['https://simpletex.net/user/center', 'https://doc.simpletex.cn/en/api/']
        assert not jobs and load_credentials(root, 'A') == ('', '')
        setup._save_button.click()
        assert not jobs and load_credentials(root, 'A') == ('', '')
        setup._app_id.setText('personal-app')
        setup._secret.setText('private-secret')
        assert setup._secret.echoMode() == setup._secret.EchoMode.Password

        if outcome == 'save':
            setup._save_button.click()
            assert load_credentials(root, 'A') == ('personal-app', 'private-secret')
            assert (scan._app_id.text(), scan._secret.text()) == ('personal-app', 'private-secret')
            assert not jobs  # Setup saves credentials without uploading the crop.
            assert not setup._secret.text()
            assert scan._setup_dialog is None
            scan.reject()
            button.click()
            later = picker.findChildren(ui.SnapshotMathDialog)[-1]
            assert later._setup_dialog is None
            assert (later._app_id.text(), later._secret.text()) == ('personal-app', 'private-secret')
            later._scan.click()
            assert len(jobs) == 1
            later.reject()
            profile[0] = 'B'
            button.click()
            other = picker.findChildren(ui.SnapshotMathDialog)[-1]
            assert other._setup_dialog is not None
            assert load_credentials(root, 'B') == ('', '')
            other.reject()
        elif outcome == 'cancel':
            setup.reject()
            assert scan._setup_dialog is None
            assert not setup._secret.text()
            assert not jobs and load_credentials(root, 'A') == ('', '')
            scan._scan.click()
            assert scan._setup_dialog is not None
            assert not jobs
        elif outcome == 'write-failure':
            def fail(*args):
                raise ValueError('synthetic private-secret failure')
            ui.save_credentials = fail
            setup._save_button.click()
            assert 'could not save' in setup._status.text().lower()
            assert 'private-secret' not in setup._status.text()
            assert not jobs and load_credentials(root, 'A') == ('', '')
            assert not scan._secret.text()
        else:
            profile[0] = 'B'
            setup._save_button.click()
            assert not setup._secret.text()
            assert not jobs
            assert load_credentials(root, 'A') == load_credentials(root, 'B') == ('', '')
        scan.reject()
        picker.reject()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path), outcome],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
