"""Real Qt checks for the hierarchical session controls and translated summaries."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_document_topic_controls_sync_and_fit_in_both_views_and_all_bundled_languages():
    script = dedent('''
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch

        sys.path.insert(0, str(Path.cwd() / 'backend'))

        from aqt.qt import QApplication, QFont, QLabel, QStyleFactory
        from backend.i18n import initialize_language, t
        from frontend import learn_dialog

        app = QApplication([])
        settings = {'dialog': {'session_card_count': 100, 'topics_slider': 40,
                              'pdf_slider': 90, 'document_mix_version': 2}}
        manager = SimpleNamespace(getConfig=lambda _: settings, writeConfig=lambda *args: None)
        window = SimpleNamespace(addonManager=manager, col=SimpleNamespace(tags=SimpleNamespace(all=lambda: [])))
        dialog_type = learn_dialog.SchedulerConfigDialog
        styles = ['Fusion'] + (['macOS'] if 'macOS' in QStyleFactory.keys() else [])
        with patch.object(learn_dialog, 'mw', window), \\
             patch.object(dialog_type, '_refresh_counts', lambda self: None), \\
             patch.object(dialog_type, '_refresh_tag_count', lambda *args: None), \\
             patch.object(dialog_type, '_refresh_ct_counts', lambda self: None), \\
             patch.object(dialog_type, '_refresh_pdf_limit_targets', lambda self: None):
            for style in styles:
                app.setStyle(style)
                for locale in ('en', 'hr', 'zh-Hans'):
                    initialize_language(locale)
                    for size, width in ((13, 820), (18, 1100)):
                        app.setFont(QFont('Arial', size))
                        dialog = dialog_type()
                        dialog.resize(width, 700)
                        dialog.show()
                        for mode in ('basic', 'advanced'):
                            dialog._set_setup_mode(mode)
                            for _ in range(3):
                                app.processEvents()
                            assert dialog._pdf_slider.isEnabled()
                            assert dialog._basic_docs_slider.isEnabled()
                            assert t('session_documents_within_topics') in [label.text() for label in dialog.findChildren(QLabel)]
                            for label in dialog.findChildren(QLabel):
                                if label.isVisible() and label.wordWrap():
                                    assert label.height() >= label.heightForWidth(label.width()), (style, locale, mode, label.text())
                        dialog._basic_topics_slider.setValue(100)
                        app.processEvents()
                        assert dialog._topics_slider.value() == 100
                        assert not dialog._pdf_slider.isEnabled()
                        assert not dialog._basic_docs_slider.isEnabled()
                        assert dialog._basic_docs_left_label.text() == t('session_percent', value=0)
                        assert dialog._pdf_left_lbl.text() == t('session_percent', value=0)
                        assert dialog._pdf_slider.value() == 90
                        dialog._topics_slider.setValue(40)
                        app.processEvents()
                        assert dialog._basic_topics_slider.value() == 40
                        assert dialog._basic_docs_slider.value() == 90
                        assert dialog._basic_docs_slider.isEnabled()
                        assert dialog._pdf_left_lbl.text() == t('session_percent', value=10)
                        dialog.close()
                        dialog.deleteLater()
                        app.processEvents()
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
