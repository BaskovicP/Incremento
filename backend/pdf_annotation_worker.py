"""Private, single-request native PDF worker. Never imports Anki or Qt."""
import json
import os
from pathlib import Path
import statistics  # Resolve stdlib before adding backend/ (which also has statistics.py).
import sys


def main():
    request = json.loads(sys.stdin.buffer.read(64 * 1024))
    output = Path(request['output'])
    response = {'ok': False, 'error': 'write_failed'}
    try:
        sys.path.insert(0, request['packages'])
        import pymupdf  # noqa: F401
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pdf_annotations as annotations
        if hasattr(os, 'nice'):
            try:
                os.nice(10)
            except OSError:
                pass
        parent = os.getppid()
        def cancelled():
            return Path(request['cancel_path']).exists() or os.getppid() != parent
        stage, backup = annotations._stage_pdf, annotations._backup
        def stage_pdf(doc, destination):
            return stage(doc, destination, temporary_path=request['stage'][str(destination)])
        def backup_pdf(addon_dir, profile, card_id, destination, expected_signature, *, source):
            target = annotations.paths.get_pdf_annotation_backup_path(addon_dir, profile, card_id, source=source)
            return backup(addon_dir, profile, card_id, destination, expected_signature, source=source,
                temporary_path=request['backups'][str(target)])
        annotations._stage_pdf, annotations._backup = stage_pdf, backup_pdf
        facts = request.get('fingerprints', {})
        result = annotations.sync_pdf_annotations(request['addon_dir'], request['profile'], request['card_id'],
            request['filename'], source_path=request['source_path'], cancel=cancelled, fingerprints=facts)
        response = {'ok': True, 'result': result, 'fingerprints': dict(list(facts.items())[-16:])}
    except Exception as error:
        response = {'ok': False, 'error': getattr(error, 'reason', 'write_failed')}
    with output.open('w', encoding='utf-8') as stream:
        os.chmod(output, 0o600)
        json.dump(response, stream)


if __name__ == '__main__':
    main()
