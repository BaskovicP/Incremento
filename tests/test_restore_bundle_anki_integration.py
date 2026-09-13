"""A real Anki export must pass pre-check and reopen after a staged restore."""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def test_real_anki_package_prechecks_and_reopens_in_temporary_profile():
    root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent("""
        import json
        import sqlite3
        import tempfile
        import zipfile
        from pathlib import Path

        from anki.collection import Collection
        from anki.exporting import AnkiPackageExporter
        from backend.restore_bundle import precheck_backup, stage_backup, swap_staged_backup

        with tempfile.TemporaryDirectory(prefix='incremento-restore-integration-') as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            collection = Collection(str(source / 'collection.anki2'))
            note = collection.new_note(collection.models.by_name('Basic'))
            note['Front'] = 'restore integration'
            note['Back'] = 'answer'
            collection.add_note(note, collection.decks.id('Restore Test'))
            package = root / 'all_decks.apkg'
            exporter = AnkiPackageExporter(collection)
            exporter.includeSched = True
            exporter.includeMedia = True
            exporter.did = None
            exporter.cids = None
            exporter.exportInto(str(package))
            collection.close()

            db_path = root / 'incremento.db'
            db = sqlite3.connect(db_path)
            db.execute('CREATE TABLE priorities (card_id INTEGER PRIMARY KEY)')
            db.execute('PRAGMA user_version=1')
            db.commit()
            db.close()
            backup = root / 'backup.zip'
            manifest = {
                'schema_version': 2, 'addon': 'Incremento', 'scope': 'current_profile',
                'profile': 'Source', 'profile_storage_key': 'Source',
                'database': {'schema_version': 1, 'integrity_check': 'ok'},
                'counts': {'anki_cards_exported': 1, 'user_files_copied': 1,
                           'user_files_bytes': db_path.stat().st_size},
            }
            with zipfile.ZipFile(backup, 'w') as archive:
                archive.write(package, 'anki/all_decks.apkg')
                archive.write(db_path, 'user_files/Source/incremento.db')
                archive.writestr('config.json', '{}')
                archive.writestr('manifest.json', json.dumps(manifest))

            target = root / 'target'
            target.mkdir()
            target_collection = target / 'collection.anki2'
            runtime = root / 'addon' / 'user_files' / 'Target'
            report = precheck_backup(backup, target_profile='Target')
            assert report.card_count == 1
            staged = stage_backup(backup, report, target_collection, runtime)
            swap = swap_staged_backup(
                staged, target_collection, target / 'collection.media', runtime
            )
            reopened = Collection(str(target_collection))
            try:
                assert reopened.card_count() == 1
                assert reopened.note_count() == 1
            finally:
                reopened.close()
            swap.commit()
            staged.cleanup()
    """)
    process = subprocess.run(
        [sys.executable, "-c", script], cwd=root,
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr


@pytest.mark.parametrize(("model_name", "cover_field"), [
    ("Incremento PDF", "PDF_Cover_Image"),
    ("Incremento EPUB", "EPUB_Cover_Image"),
])
def test_full_backup_includes_cover_named_in_a_plain_note_field(model_name, cover_field):
    root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent("""
        import json
        import tempfile
        import zipfile
        from pathlib import Path

        from anki.collection import Collection
        from backend.backup_media import FullBackupPackageExporter
        from backend.restore_bundle import _missing_cover_count

        with tempfile.TemporaryDirectory(prefix='incremento-cover-export-') as temporary:
            root = Path(temporary)
            collection = Collection(str(root / 'collection.anki2'))
            # Reuse the original Basic model ID. A new model created just
            # before export can collide with the exporter's disposable Basic
            # model ID in the same millisecond and lose the copied card.
            model = collection.models.by_name('Basic')
            model['name'] = '__MODEL_NAME__'
            collection.models.add_field(model, collection.models.new_field('__COVER_FIELD__'))
            collection.models.update_dict(model)
            cover = root / 'cover.png'
            cover.write_bytes(b'valid-image-placeholder')
            media_name = collection.media.add_file(str(cover))
            note = collection.new_note(model)
            note['Front'] = 'A long document source title'
            note['__COVER_FIELD__'] = media_name
            collection.add_note(note, collection.decks.id('Cover Test'))
            assert list(collection.media.files_in_str(model['id'], media_name)) == []

            package = root / 'all_decks.apkg'
            exporter = FullBackupPackageExporter(collection)
            exporter.includeSched = True
            exporter.includeMedia = True
            exporter.exportInto(str(package))
            collection.close()
            with zipfile.ZipFile(package) as archive:
                media_map = json.loads(archive.read('media'))
                assert media_name in media_map.values(), media_map
                index = next(key for key, name in media_map.items() if name == media_name)
                assert archive.read(index) == b'valid-image-placeholder'
                exported_db = root / 'exported.anki2'
                exported_db.write_bytes(archive.read('collection.anki21'))
                assert _missing_cover_count(exported_db, set()) == 1
                assert _missing_cover_count(exported_db, set(media_map.values())) == 0
    """).replace("__MODEL_NAME__", model_name).replace("__COVER_FIELD__", cover_field)
    process = subprocess.run(
        [sys.executable, "-c", script], cwd=root,
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert process.returncode == 0, process.stdout + process.stderr
