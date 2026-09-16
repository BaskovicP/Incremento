"""DjVu's multiline guidance must fit the real Qt preview panel."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_djvu_preview_guidance_fits_in_all_bundled_languages():
    script = dedent('''
        import sys
        from types import SimpleNamespace
        import aqt
        from aqt.qt import QApplication
        app = QApplication([])
        aqt.mw = SimpleNamespace(col=SimpleNamespace(tags=SimpleNamespace(all=lambda: [])),
            addonManager=SimpleNamespace(getConfig=lambda *args: {}))
        from backend import priority_manager
        sys.modules['priority_manager'] = priority_manager
        from backend.i18n import initialize_language
        from frontend.pdf_dialog import AddPdfDialog
        expected_ocr_labels = {
            'en': ('OCR all possible', "Don't OCR anything"),
            'hr': ('OCR gdje god je moguće', 'Ne izvršavaj OCR'),
            'zh-Hans': ('尽可能全部 OCR', '全部不进行 OCR'),
        }
        for locale in ('en', 'hr', 'zh-Hans'):
            initialize_language(locale)
            dialog = AddPdfDialog('.', deck_names=['Topics'], parent=None)
            dialog._add_paths(['synthetic.djvu'])
            dialog.resize(900, 560)
            dialog.show()
            for _ in range(3):
                app.processEvents()
            assert (dialog._ocr_all_btn.text(), dialog._ocr_none_btn.text()) == expected_ocr_labels[locale]
            assert dialog._ocr_all_btn.isVisible()
            assert dialog._ocr_none_btn.isVisible()
            label = dialog._preview_lbl
            if not label.wordWrap():
                required = max(label.fontMetrics().horizontalAdvance(line) for line in label.text().splitlines())
                assert required <= label.width(), (locale, required, label.width())
            else:
                assert label.heightForWidth(label.width()) <= label.height()
            dialog.close()
            app.processEvents()
    ''')
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
