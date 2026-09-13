"""Real Qt import/export drafts stay local until Settings is accepted."""
import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_language_pack_import_export_and_rejection_keep_the_saved_profile_unchanged(tmp_path):
    script = dedent('''
        import csv, io, pathlib, sys
        from aqt.qt import QApplication, QComboBox
        from backend.language_packs import list_packs, parse_csv
        from frontend.language_pack_settings import LanguagePackControls

        app = QApplication([])
        root = pathlib.Path(sys.argv[1])
        combo = QComboBox()
        combo.addItem('English', 'en')
        combo.addItem('Hrvatski', 'hr')
        controls = LanguagePackControls(combo, str(root), 'Synthetic')
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        writer.writerow(['component','key','form','source','translation'])
        writer.writerows([
            ['meta','version','','Format','1'],
            ['meta','locale','','Language code','de'],
            ['meta','name','','Native name','Deutsch'],
            ['addon','settings_done','','Done','Fertig'],
        ])
        imported = root / 'de.csv'
        imported.write_bytes(buffer.getvalue().encode('utf-8-sig'))
        assert controls.import_file(imported)
        assert combo.currentData() == 'custom:de'
        assert controls.pending_pack['translations']['addon']['settings_done'] == 'Fertig'
        assert list_packs(str(root), 'Synthetic') == []
        exported = root / 'export.csv'
        assert controls.export_file(exported, template=False)
        assert parse_csv(exported.read_bytes())['translations']['addon']['settings_done'] == 'Fertig'
        before = controls.pending_pack
        imported.write_text('not a translation table')
        assert not controls.import_file(imported)
        assert controls.pending_pack == before
        assert combo.currentData() == 'custom:de'
        assert controls.status.text()
        controls.close()
        assert list_packs(str(root), 'Synthetic') == []
    ''')
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
