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
        from aqt.qt import QApplication, QDialog, QPixmap, QProgressBar, QVBoxLayout
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
        ui.is_ready = lambda: True
        ui.recognize_snapshot = lambda image, **kw: uploads.append((image, kw)) or r'\frac{x}{2}'

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
        progress = scan.findChild(QProgressBar)
        assert progress is not None
        assert progress.isHidden()
        assert progress.minimum() == progress.maximum() == 0
        assert not scan._copy_inline.isEnabled()
        assert not hasattr(scan, '_secret')
        scan._scan.click()
        scan._scan.click()
        assert len(jobs) == 1 and not uploads
        assert not progress.isHidden()
        assert not scan._scan.isEnabled() and not scan._copy_inline.isEnabled()
        work, done, options = jobs.pop()
        assert options == {'uses_collection': False}
        future = Future()
        future.set_result(work())
        done(future)
        assert progress.isHidden()
        assert uploads[0][0].startswith(b'\x89PNG\r\n\x1a\n')
        assert uploads[0][1]['cancel'] is scan._cancel
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
        assert 'setup is running' in scan._status.text()
        assert progress.isHidden()

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
        assert scan._cancel.is_set() and not scan._result.toPlainText()
        current[0] = True

        # A profile switch drops completion and clears credentials/result.
        scan = ui.SnapshotMathDialog(picker, image, is_current=lambda: current[0])
        scan._scan.click()
        work, done, _ = jobs.pop()
        profile[0] = 'B'
        done(future)
        assert not scan._result.toPlainText() and scan._cancel.is_set()
        assert app.clipboard().text() == 'preserve'
        scan.close()
        picker.close()

        # A closed dialog makes a still-running request's completion harmless.
        profile[0] = 'A'
        scan = ui.SnapshotMathDialog(picker, image, is_current=lambda: True)
        scan._scan.click()
        work, done, _ = jobs.pop()
        scan.reject()
        done(future)
        assert scan._cancel.is_set() and not scan._result.toPlainText()
        assert app.clipboard().text() == 'preserve'

        # Missing setup does not install or recognize without a setup click.
        ui.is_ready = lambda: False
        saved = ui.SnapshotMathDialog(picker, image, is_current=lambda: True)
        saved._scan.click()
        assert not jobs
        assert 'First click' in saved._status.text()
        ui.setup_local_ocr = lambda cancel, **kwargs: None
        saved._setup_button.click()
        assert not saved.findChild(QProgressBar).isHidden()
        assert len(jobs) == 1
        work, done, options = jobs.pop()
        assert options == {'uses_collection': False}
        ready = Future()
        ready.set_result(work())
        done(ready)
        assert saved.findChild(QProgressBar).isHidden()
        assert 'is ready' in saved._status.text()
        assert saved._scan.isEnabled()
        saved.reject()

        # Both operations stop the busy indicator on failure, dispatch failure,
        # cancellation, and stale-profile completion; retries start it again.
        for operation in ('setup', 'scan'):
            for outcome in ('failure', 'dispatch', 'close', 'profile'):
                profile[0] = 'A'
                ui.is_ready = lambda: True
                jobs.clear()
                def dispatch(work, done, **options):
                    if outcome == 'dispatch':
                        raise RuntimeError('synthetic dispatch failure')
                    jobs.append((work, done, options))
                ui.mw.taskman.run_in_background = dispatch
                dialog = ui.SnapshotMathDialog(picker, image, is_current=lambda: True)
                bar = dialog.findChild(QProgressBar)
                start = dialog._open_setup if operation == 'setup' else dialog._start_scan
                start()
                if outcome == 'dispatch':
                    assert bar.isHidden()
                    assert dialog._scan.isEnabled() and dialog._setup_button.isEnabled()
                else:
                    assert not bar.isHidden()
                    work, done, _ = jobs.pop()
                    if outcome == 'close':
                        dialog.reject()
                    elif outcome == 'profile':
                        profile[0] = 'B'
                    failure = Future()
                    failure.set_exception(MathRecognitionError('process'))
                    done(failure)
                    assert bar.isHidden()
                    if outcome == 'failure':
                        assert dialog._scan.isEnabled() and dialog._setup_button.isEnabled()
                        start()
                        assert not bar.isHidden()
                dialog.reject()
                assert bar.isHidden()

        profile[0] = 'A'
        jobs.clear()
        ui.mw.taskman.run_in_background = lambda work, done, **kw: jobs.append((work, done, kw))
        callbacks = []
        ui.setup_local_ocr = lambda cancel, **kwargs: callbacks.append(kwargs['progress'])
        dialog = ui.SnapshotMathDialog(picker, image, is_current=lambda: True)
        dialog._open_setup()
        work, done, _ = jobs.pop()
        work()
        callbacks[0]({'stage': 'download_model', 'current': 25 * 1024**2, 'total': 100 * 1024**2})
        dialog._check_source()
        assert dialog._progress.maximum() == 100 and dialog._progress.value() == 25
        assert '25%' in dialog._status.text() and '25.0 / 100.0 MB' in dialog._status.text()
        assert 'Step 3 of 4' in dialog._status.text()
        assert 'Elapsed' in dialog._status.text()
        callbacks[0]({'stage': 'loading'})
        dialog._check_source()
        assert dialog._progress.minimum() == dialog._progress.maximum() == 0
        assert 'Step 4 of 4' in dialog._status.text()
        done(ready)
        completed = dialog._status.text()
        callbacks[0]({'stage': 'download_model', 'current': 10, 'total': 100})
        dialog._check_source()
        assert dialog._status.text() == completed and dialog._progress.isHidden()
        dialog.reject()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
