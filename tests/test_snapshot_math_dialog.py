"""Real widgets and deferred network callbacks, isolated from the live Anki UI."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent
import ast


def test_all_three_reader_snapshot_pickers_offer_the_shared_scanner():
    root = Path(__file__).resolve().parents[1]
    for filename, function, crop in (
        ('pdf_dock.py', '_show_pdf_snapshot_field_picker', 'preview_pixmap'),
        ('epub_dock.py', '_handle_epub_snapshot', 'snapshot'),
        ('web_dock.py', 'insert_snapshot_into_field', 'pixmap'),
    ):
        tree = ast.parse((root / 'frontend' / filename).read_text())
        target = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == function)
        calls = [node for node in ast.walk(target) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == 'add_snapshot_math_action']
        assert len(calls) == 1, filename
        assert ast.unparse(calls[0].args[2]) == crop, filename
        assert 'is_current' in {kw.arg for kw in calls[0].keywords}, filename


def test_snapshot_scan_preview_copy_retry_and_lifecycle_with_real_qt():
    script = dedent(r'''
        from concurrent.futures import Future
        from types import SimpleNamespace
        from aqt.qt import QApplication, QDialog, QPixmap, QVBoxLayout
        from backend.i18n import initialize_language
        from backend.math_ocr import MathRecognitionError
        from frontend import snapshot_math_dialog as ui

        app = QApplication([])
        initialize_language('en')
        jobs, uploads = [], []
        profile = ['A']
        current = [True]
        ui.mw = SimpleNamespace(col=object(), taskman=SimpleNamespace(
            run_in_background=lambda work, done, **kw: jobs.append((work, done, kw))))
        ui._active_profile = lambda: profile[0]
        ui.load_credentials = lambda *args: ('', '')
        ui.recognize_snapshot = lambda image, app_id, secret: uploads.append((image, app_id, secret)) or r'\frac{x}{2}'

        picker = QDialog()
        layout = QVBoxLayout(picker)
        image = QPixmap(600, 200)
        image.fill()
        button = ui.add_snapshot_math_action(picker, layout, image, is_current=lambda: current[0])
        assert button.text() == 'Scan for MathJax…'
        assert not jobs and not uploads
        button.click()
        scan = picker.findChild(ui.SnapshotMathDialog)
        assert scan is not None
        assert scan._secret.echoMode() == scan._secret.EchoMode.Password
        assert not scan._copy_inline.isEnabled()
        assert scan._setup_dialog is not None
        scan._setup_dialog.reject()
        scan._scan.click()
        assert not jobs  # Missing credentials must not dispatch an upload.
        scan._setup_dialog.reject()
        scan._app_id.setText('personal-app')
        scan._secret.setText('private-secret')
        scan._scan.click()
        scan._scan.click()
        assert len(jobs) == 1 and not uploads
        assert not scan._scan.isEnabled() and not scan._copy_inline.isEnabled()
        work, done, options = jobs.pop()
        assert options == {'uses_collection': False}
        future = Future()
        future.set_result(work())
        done(future)
        assert uploads[0][0].startswith(b'\x89PNG\r\n\x1a\n')
        assert uploads[0][1:] == ('personal-app', 'private-secret')
        assert scan._status.text() == 'MathJax found. Check the recognized LaTeX before copying.'
        assert scan._copy_inline.isEnabled()
        scan._result.setPlainText(r'\ce{2H2 + O2 -> 2H2O}')
        scan._copy_inline.click()
        assert app.clipboard().text() == r'\(\ce{2H2 + O2 -> 2H2O}\)'
        scan._copy_display.click()
        assert app.clipboard().text() == r'\[\ce{2H2 + O2 -> 2H2O}\]'
        scan._result.setPlainText('x < y & z')
        scan._copy_latex.click()
        assert app.clipboard().text() == 'x < y & z'
        assert '&lt;' in app.clipboard().mimeData().html()

        # A failed re-scan clears old results and supports an explicit retry.
        scan._scan.click()
        assert not scan._copy_inline.isEnabled() and not scan._result.toPlainText()
        work, done, _ = jobs.pop()
        failure = Future()
        failure.set_exception(MathRecognitionError('busy'))
        done(failure)
        assert scan._scan.isEnabled() and not scan._copy_inline.isEnabled()
        assert 'busy' in scan._status.text().lower()

        # Copying stale results may not overwrite the user's clipboard.
        scan._scan.click()
        work, done, _ = jobs.pop()
        future = Future()
        future.set_result(r'x^2')
        done(future)
        app.clipboard().setText('preserve')
        current[0] = False
        scan._copy_inline.click()
        assert app.clipboard().text() == 'preserve'
        assert not scan._secret.text() and not scan._result.toPlainText()
        current[0] = True

        # A profile switch drops completion and clears credentials/result.
        scan = ui.SnapshotMathDialog(picker, image, is_current=lambda: current[0])
        scan._app_id.setText('personal-app')
        scan._secret.setText('private-secret')
        scan._scan.click()
        work, done, _ = jobs.pop()
        profile[0] = 'B'
        done(future)
        assert not scan._result.toPlainText() and not scan._secret.text()
        assert app.clipboard().text() == 'preserve'
        scan.close()
        picker.close()

        # A closed dialog makes a still-running request's completion harmless.
        profile[0] = 'A'
        scan = ui.SnapshotMathDialog(picker, image, is_current=lambda: True)
        scan._app_id.setText('app')
        scan._secret.setText('secret')
        scan._scan.click()
        work, done, _ = jobs.pop()
        scan.reject()
        done(future)
        assert not scan._secret.text() and not scan._result.toPlainText()
        assert app.clipboard().text() == 'preserve'

        # Later snapshots reuse this profile's saved credentials without uploads.
        ui.load_credentials = lambda root, selected: ('stored-app', 'stored-secret') if selected == 'A' else ('', '')
        saved = ui.SnapshotMathDialog(picker, image, is_current=lambda: True)
        assert (saved._app_id.text(), saved._secret.text()) == ('stored-app', 'stored-secret')
        assert not jobs
        saved.reject()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
