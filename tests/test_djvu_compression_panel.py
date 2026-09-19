"""Real Qt transitions, with only the background encoder/task queue faked."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_compression_panel_remembers_choices_and_rejects_stale_estimates(tmp_path):
    script = dedent('''
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from concurrent.futures import Future
        from aqt.qt import QApplication, QLabel
        from backend import djvu_manager as manager
        from backend.i18n import initialize_language
        from frontend.djvu_compression_panel import DjvuCompressionPanel

        app = QApplication(['compression-test'])
        root = Path(sys.argv[1])
        first, second = root / 'first.djvu', root / 'second.djvu'
        first.write_bytes(b'first')
        second.write_bytes(b'second')
        jobs, displayed = [], []
        current = [True]
        tasks = SimpleNamespace(run_in_background=lambda work, done, **kw: jobs.append((work, done, kw)))
        estimate = manager.CompressionEstimate(2_000_000, 1_500_000, 2_500_000, (b'preview',))
        original = manager.CompressionEstimate(1_000_000, 800_000, 1_200_000, (b'original',))
        risky = manager.CompressionEstimate(300 * 2**20, 280 * 2**20, 320 * 2**20, (b'preview',))
        result = manager.DjvuCompressionPreview(5, 1, (1,),
            dict(mrc=risky, compact_color=estimate, original=original,
                 balanced=estimate, small=estimate, black_white=estimate))
        manager.estimate_djvu_compression = lambda *a, **kw: result
        panel = DjvuCompressionPanel(tasks, lambda: current[0], displayed.append)
        panel.resize(320, 420)
        panel.show()
        panel.set_path(str(first))
        assert panel.choice_for(str(first)) == 'mrc'
        assert len(jobs) == 1  # The bounded estimate starts automatically.
        work, done, _ = jobs.pop()
        panel.preset.setCurrentIndex(panel.preset.findData('black_white'))
        assert panel.choice_for(str(first)) == 'black_white'
        assert panel.estimate.isEnabled() is False
        future = Future()
        future.set_result(work())
        panel.set_path(str(second))
        assert len(jobs) == 1 and jobs[0][2]['uses_collection'] is False
        second_work, second_done, _ = jobs.pop()
        done(future)
        assert panel.result is None and not displayed
        future = Future()
        future.set_result(second_work())
        second_done(future)
        assert panel.preset.currentData() == 'compact_color'
        assert panel.choice_for(str(second)) == 'compact_color'
        assert 'Automatically selected' in panel.summary.text()
        assert displayed == [b'preview']

        panel.set_path(str(first))
        assert panel.preset.currentData() == 'black_white'
        assert len(jobs) == 1 and jobs[0][2]['uses_collection'] is False
        assert panel.estimate.isEnabled() is False
        work, done, _ = jobs.pop()
        future = Future()
        future.set_result(work())
        done(future)
        assert displayed == [b'preview', b'preview']
        assert 'larger' in panel.summary.text()
        assert '1.4' in panel.summary.text() and '2.4' in panel.summary.text()
        panel.preset.setCurrentIndex(panel.preset.findData('mrc'))
        assert 'unusually large' in panel.summary.text()
        # Each language fits the narrow import preview panel.
        for locale in ('en', 'hr', 'zh-Hans'):
            initialize_language(locale)
            panel.refresh()
            app.processEvents()
            for label in panel.findChildren(QLabel):
                if label.isVisible() and label.wordWrap():
                    assert label.height() >= label.heightForWidth(label.width()), label.text()
        # A replaced source invalidates its estimate.
        first.write_bytes(b'changed')
        panel.set_path(str(first))
        assert panel.result is None
        assert len(jobs) == 1
        work, done, _ = jobs.pop()
        future = Future()
        future.set_result(work())
        current[0] = False
        done(future)
        assert panel.result is None
        panel.stop()
        panel.close()
    ''')
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stdout + result.stderr
