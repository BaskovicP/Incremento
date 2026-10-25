"""Bounded, cancellable process isolation for native PDF annotation work."""
from collections import OrderedDict
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time

try:
    from . import paths
    from .deps import _installer_python, _subprocess_env
    from .pdf_annotations import (PdfAnnotationSyncError, MAX_SYNC_LOCK_WAIT_SECONDS,
        MAX_SYNC_PROCESSING_SECONDS, _managed_path, _check_file, _check_profile_path, pdf_annotation_sync_state)
except ImportError:
    import paths
    from deps import _installer_python, _subprocess_env
    from pdf_annotations import (PdfAnnotationSyncError, MAX_SYNC_LOCK_WAIT_SECONDS,
        MAX_SYNC_PROCESSING_SECONDS, _managed_path, _check_file, _check_profile_path, pdf_annotation_sync_state)

_lock = threading.Lock()
_cache = OrderedDict()
_cache_lock = threading.Lock()
_cache_generation = 0
_ERRORS = frozenset({'dependency', 'document_changed', 'protected_pdf', 'password_protected',
    'digitally_signed', 'annotation_restricted', 'file_changed', 'cancelled', 'limits', 'unsafe_path',
    'invalid_annotation', 'duplicate_identity', 'invalid_pdf', 'write_failed'})


def _python():
    return _installer_python()


def clear_annotation_process_cache():
    global _cache_generation
    with _cache_lock:
        _cache_generation += 1
        _cache.clear()


def _decode_result(data, expected_reader):
    try:
        if len(data) > 32 * 1024:
            raise ValueError()
        response = json.loads(data)
        if not isinstance(response, dict) or response.get('ok') is not True:
            reason = response.get('error') if isinstance(response, dict) else None
            raise PdfAnnotationSyncError(reason if reason in _ERRORS else 'write_failed')
        result = response['result']
        if not isinstance(result, dict) or result.get('reader_path') != str(expected_reader):
            raise ValueError()
        for key in ('changed', 'reader_changed', 'appearance_changed', 'retry_needed'):
            if type(result.get(key)) is not bool:
                raise ValueError()
        for key in ('conflicts', 'imported'):
            if type(result.get(key)) is not int or not 0 <= result[key] <= 10000:
                raise ValueError()
        if not isinstance(result.get('source_path', ''), str) or len(result.get('source_path', '')) > 8192:
            raise ValueError()
        clean = {key: result[key] for key in ('reader_path', 'changed', 'reader_changed', 'appearance_changed',
            'retry_needed', 'conflicts', 'imported')}
        clean['source_path'] = result.get('source_path', '')
        return clean, response.get('fingerprints', {})
    except (ValueError, KeyError, TypeError):
        raise PdfAnnotationSyncError('write_failed') from None


def _allocate(destination, owned):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.incremento-worker-', suffix='.pdf', dir=destination.parent)
    info = os.fstat(descriptor)
    os.close(descriptor)
    path = Path(name)
    owned.append((path, info.st_dev, info.st_ino))
    return str(path)


def sync_pdf_annotations_in_process(addon_dir, profile, card_id, filename, *, source_path=None, cancel=None):
    def cancelled():
        return cancel is not None and cancel()
    if cancelled():
        raise PdfAnnotationSyncError('cancelled')
    deadline = time.monotonic() + MAX_SYNC_LOCK_WAIT_SECONDS
    while not _lock.acquire(timeout=.1):
        if cancelled():
            raise PdfAnnotationSyncError('cancelled')
        if time.monotonic() >= deadline:
            raise PdfAnnotationSyncError('limits')
    owned = []
    process = None
    try:
        if cancelled():
            raise PdfAnnotationSyncError('cancelled')
        python = _python()
        spec = importlib.util.find_spec('pymupdf')
        if not python or spec is None or not spec.origin:
            raise PdfAnnotationSyncError('dependency')
        managed = _managed_path(addon_dir, profile, filename)
        _check_file(managed)
        state = pdf_annotation_sync_state(addon_dir, profile, card_id)
        source = source_path if source_path is not None else (state or {}).get('source_path', '')
        reader = paths.get_pdf_annotation_reader_path(addon_dir, profile, card_id)
        _check_profile_path(addon_dir, profile, reader)
        targets = [managed, reader]
        if source:
            original = Path(source)
            if (not original.is_absolute() or original.is_symlink()
                    or original.resolve().is_relative_to((Path(addon_dir) / 'user_files').resolve())):
                raise PdfAnnotationSyncError('unsafe_path')
            _check_file(original)
            if original.resolve() != managed:
                targets.append(original.resolve())
        stage = {str(target): _allocate(target, owned) for target in targets}
        backups = {}
        for is_source in (False, True):
            target = paths.get_pdf_annotation_backup_path(addon_dir, profile, card_id, source=is_source)
            _check_profile_path(addon_dir, profile, target)
            backups[str(target)] = _allocate(target, owned)
        key = (str(Path(addon_dir).resolve()), profile)
        with _cache_lock:
            generation = _cache_generation
            facts = dict(_cache.get(key, {}))
        with tempfile.TemporaryDirectory(prefix='incremento-pdf-worker-') as temporary:
            output = Path(temporary) / 'result.json'
            stop = Path(temporary) / 'cancel'
            request = {'addon_dir': str(addon_dir), 'profile': profile, 'card_id': int(card_id),
                'filename': filename, 'source_path': source_path, 'stage': stage, 'backups': backups,
                'cancel_path': str(stop), 'output': str(output), 'fingerprints': facts,
                'packages': str(Path(spec.origin).parent.parent)}
            command = [python, '-I', '-B', str(Path(__file__).with_name('pdf_annotation_worker.py'))]
            flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, env=_subprocess_env(), **flags)
            pending = json.dumps(request).encode()
            deadline = time.monotonic() + MAX_SYNC_PROCESSING_SECONDS + 10
            while True:
                if cancelled() and not stop.exists():
                    stop.touch(mode=0o600)
                if time.monotonic() >= deadline:
                    raise PdfAnnotationSyncError('limits')
                try:
                    process.communicate(pending, timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    pending = None
            if cancelled():
                raise PdfAnnotationSyncError('cancelled')
            if process.returncode or not output.is_file() or output.is_symlink() or output.stat().st_size > 32 * 1024:
                raise PdfAnnotationSyncError('write_failed')
            result, verified = _decode_result(output.read_bytes(), reader)
            if result['source_path'] != (str(Path(source).resolve()) if source else ''):
                raise PdfAnnotationSyncError('write_failed')
            if isinstance(verified, dict):
                safe = {sha: digest for sha, digest in list(verified.items())[-16:]
                    if isinstance(sha, str) and isinstance(digest, str)
                    and re.fullmatch('[0-9a-f]{64}', sha) and re.fullmatch('[0-9a-f]{64}', digest)}
                with _cache_lock:
                    if generation == _cache_generation:
                        _cache[key] = safe
                        _cache.move_to_end(key)
                        while len(_cache) > 4:
                            _cache.popitem(last=False)
            return result
    except OSError:
        raise PdfAnnotationSyncError('write_failed') from None
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for path, device, inode in owned:
            try:
                info = path.lstat()
                if not path.is_symlink() and (info.st_dev, info.st_ino) == (device, inode):
                    path.unlink()
            except OSError:
                pass
        _lock.release()
