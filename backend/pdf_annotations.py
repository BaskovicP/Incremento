"""Bounded, crash-recoverable interchange of editable PDF annotations.

The PDFs are written before the SQLite baseline. Stable per-page annotation
names make a retry idempotent if a crash interrupts that cross-store boundary.
Anki notes/cards are never modified here. Call only from a captured-profile
worker, never from Qt's main thread.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from html import escape
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
import uuid

try:
    from . import paths
    from .db import get_connection
    from .pdf_highlights import load_highlights
except ImportError:
    import paths
    from db import get_connection
    from pdf_highlights import load_highlights


MAX_PDF_BYTES = 256 * 1024 * 1024
MAX_PAGES = 5000
MAX_ANNOTATIONS = 10000
MAX_RECTS = 2000
MAX_BASELINE_CHARS = 8388608
SUPPORTED_KINDS = {'Highlight', 'Underline', 'Squiggly', 'StrikeOut', 'Text', 'FreeText', 'Square', 'Circle'}
MARKUP_KINDS = {'Highlight', 'Underline', 'Squiggly', 'StrikeOut'}
COLORS = {
    'yellow': ([1, 220 / 255, 0], .45), 'green': ([0, 200 / 255, 80 / 255], .4),
    'blue': ([30 / 255, 144 / 255, 1], .4), 'pink': ([1, 80 / 255, 140 / 255], .4),
    'aqua': ([45 / 255, 212 / 255, 191 / 255], .42), 'orange': ([251 / 255, 146 / 255, 60 / 255], .42),
    'red': ([248 / 255, 113 / 255, 113 / 255], .42), 'purple': ([168 / 255, 85 / 255, 247 / 255], .4),
    'snapshot': ([37 / 255, 99 / 255, 235 / 255], .95),
}

# PyMuPDF's process-global runtime and multi-file writes are serialized. SQLite
# readers and ordinary highlight edits never acquire this long-lived lock.
_sync_lock = threading.Lock()


class PdfAnnotationSyncError(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class PdfAnnotationSyncCancelled(PdfAnnotationSyncError):
    pass


def pdf_annotation_sync_state(addon_dir: str, profile: str, card_id: int) -> dict | None:
    row = get_connection(addon_dir, profile).execute(
        'SELECT filename, document_id, source_path, content_digest, baseline_json '
        'FROM pdf_annotation_sync WHERE card_id=?', (int(card_id),)).fetchone()
    if not row:
        return None
    return dict(zip(('filename', 'document_id', 'source_path', 'content_digest', 'baseline_json'), row))


def _managed_path(addon_dir, profile, filename):
    if not filename or Path(filename).name != filename or '\\' in filename:
        raise PdfAnnotationSyncError('unsafe_path')
    root = paths.get_pdf_dir(addon_dir, profile)
    target = root / filename
    _check_profile_path(addon_dir, profile, target)
    return target


def _check_profile_path(addon_dir, profile, target):
    root = paths.get_user_files_dir(addon_dir, profile)
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise PdfAnnotationSyncError('unsafe_path') from exc
    candidate = root
    for part in ('', *relative.parts):
        candidate = candidate / part
        if candidate.is_symlink():
            raise PdfAnnotationSyncError('unsafe_path')
    if root.parent.is_symlink():
        raise PdfAnnotationSyncError('unsafe_path')


def _check_file(target):
    if target.is_symlink() or not target.is_file() or target.suffix.lower() != '.pdf':
        raise PdfAnnotationSyncError('unsafe_path')
    if target.stat().st_size > MAX_PDF_BYTES:
        raise PdfAnnotationSyncError('limits')
    with target.open('rb') as stream:
        if not stream.read(1024).lstrip().startswith(b'%PDF-'):
            raise PdfAnnotationSyncError('invalid_pdf')


def _file_signature(target):
    if target.is_symlink():
        raise PdfAnnotationSyncError('unsafe_path')
    digest = sha256()
    before = target.stat()
    with target.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    after = target.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise PdfAnnotationSyncError('file_changed')
    return (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, digest.hexdigest())


def _checkpoint(cancel, deadline):
    if cancel is not None and cancel():
        raise PdfAnnotationSyncCancelled('cancelled')
    if time.monotonic() > deadline:
        raise PdfAnnotationSyncError('limits')


def _content_digest(doc, cancel, deadline):
    digest = sha256()
    resources = {}
    def resource_hash(xref, *, font=False):
        key = (xref, font)
        if key not in resources:
            _checkpoint(cancel, deadline)
            data = doc.extract_font(xref)[3] if font else doc.xref_stream(xref)
            data = data or b''
            if len(data) > MAX_PDF_BYTES:
                raise PdfAnnotationSyncError('limits')
            resources[key] = sha256(data).digest()
        return resources[key]
    if not doc.is_pdf or doc.page_count > MAX_PAGES:
        raise PdfAnnotationSyncError('limits')
    if doc.needs_pass or doc.get_sigflags() > 0 or not (doc.permissions & 32):
        raise PdfAnnotationSyncError('protected_pdf')
    for page in doc:
        _checkpoint(cancel, deadline)
        digest.update(json.dumps([list(page.cropbox), page.rotation]).encode())
        for xref in page.get_contents():
            content = doc.xref_stream(xref)
            if len(content) > MAX_PDF_BYTES:
                raise PdfAnnotationSyncError('limits')
            digest.update(content)
        # Also distinguish scanned PDFs whose page commands refer to different
        # image resources. Annotation appearance streams are deliberately absent.
        for image in page.get_images():
            digest.update(resource_hash(image[0]))
            if image[1]:
                digest.update(resource_hash(image[1]))
        for form in page.get_xobjects():
            digest.update(resource_hash(form[0]))
        for font in page.get_fonts():
            digest.update(json.dumps(font[1:6]).encode())
            digest.update(resource_hash(font[0], font=True))
        digest.update(b'\0PAGE\0')
    return digest.hexdigest()


def _rgb(value):
    value = list(value or [1, 1, 0])
    if len(value) == 1:
        value *= 3
    elif len(value) == 4:
        c, m, y, k = value
        value = [(1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)]
    if len(value) != 3 or not all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in value):
        raise PdfAnnotationSyncError('invalid_annotation')
    return value


def _name_key(page, name):
    return json.dumps([page, name], ensure_ascii=False)


def _normalize_text_rects(rects):
    """Match the viewer's line union for pre-interchange selection geometry."""
    lines = []
    for rect in sorted(rects, key=lambda r: (r['y'] + r['h'] / 2, r['x'])):
        reference = lines[-1][0] if lines else None
        overlap = min(reference['y'] + reference['h'], rect['y'] + rect['h']) - max(reference['y'], rect['y']) if reference else 0
        height = min(reference['h'], rect['h']) if reference else 0
        distance = abs(reference['y'] + reference['h'] / 2 - rect['y'] - rect['h'] / 2) if reference else math.inf
        if reference and overlap >= height * .6 and distance <= height * .5:
            lines[-1].append(rect)
        else:
            lines.append([rect])
    result = []
    for line in lines:
        merged = []
        for rect in sorted(line, key=lambda r: r['x']):
            previous = merged[-1] if merged else None
            if previous and rect['x'] - previous['x'] - previous['w'] <= min(previous['h'], rect['h']) * .5:
                right = max(previous['x'] + previous['w'], rect['x'] + rect['w'])
                bottom = max(previous['y'] + previous['h'], rect['y'] + rect['h'])
                previous['y'] = min(previous['y'], rect['y'])
                previous['w'], previous['h'] = right - previous['x'], bottom - previous['y']
            else:
                merged.append(dict(rect))
        result.extend(merged)
    return result


def _prepare(highlight, document_id):
    hl = deepcopy(highlight)
    if not isinstance(hl.get('id'), str) or not hl['id'] or len(hl['id']) > 512:
        raise PdfAnnotationSyncError('invalid_annotation')
    if not isinstance(hl.get('page'), int) or hl['page'] <= 0:
        raise PdfAnnotationSyncError('invalid_annotation')
    if not isinstance(hl.get('note', ''), str) or len(hl.get('note', '')) > 65536:
        raise PdfAnnotationSyncError('limits')
    rects = hl.get('rects', [])
    if not isinstance(rects, list) or len(rects) > MAX_RECTS:
        raise PdfAnnotationSyncError('limits')
    for rect in rects:
        if not isinstance(rect, dict) or not all(isinstance(rect.get(k), (int, float)) and math.isfinite(rect[k]) for k in ('x', 'y', 'w', 'h')):
            raise PdfAnnotationSyncError('invalid_annotation')
        if rect['w'] <= 0 or rect['h'] <= 0:
            raise PdfAnnotationSyncError('invalid_annotation')
    metadata = hl.setdefault('pdf_annotation', {})
    if not isinstance(metadata, dict):
        raise PdfAnnotationSyncError('invalid_annotation')
    metadata.setdefault('kind', 'Square' if hl.get('color') == 'snapshot' else 'Highlight')
    metadata.setdefault('name', f'Incremento-{document_id}-{sha256(hl["id"].encode()).hexdigest()[:24]}')
    if metadata['kind'] not in SUPPORTED_KINDS or not isinstance(metadata['name'], str) or len(metadata['name']) > 1024:
        raise PdfAnnotationSyncError('invalid_annotation')
    color, opacity = COLORS.get(hl.get('color'), COLORS['yellow'])
    metadata['color'] = _rgb(metadata.get('color', color))
    if metadata.get('fill'):
        metadata['fill'] = _rgb(metadata['fill'])
    metadata.setdefault('opacity', opacity)
    metadata.setdefault('border_width', 2 if metadata['kind'] in {'Square', 'Circle'} else 0)
    if not isinstance(metadata['border_width'], (float, int)) or not math.isfinite(metadata['border_width']) or not 0 <= metadata['border_width'] <= 1000:
        raise PdfAnnotationSyncError('invalid_annotation')
    if metadata['kind'] == 'FreeText':
        metadata.setdefault('font_size', 11)
        if not isinstance(metadata['font_size'], (float, int)) or not math.isfinite(metadata['font_size']) or not 1 <= metadata['font_size'] <= 200:
            raise PdfAnnotationSyncError('invalid_annotation')
        metadata['text_color'] = _rgb(metadata.get('text_color', [0, 0, 0]))
        if metadata.get('font_family', 'sans-serif') not in {'sans-serif', 'serif', 'monospace'}:
            raise PdfAnnotationSyncError('invalid_annotation')
    if not isinstance(metadata['opacity'], (float, int)) or not math.isfinite(metadata['opacity']) or not 0 <= metadata['opacity'] <= 1:
        raise PdfAnnotationSyncError('invalid_annotation')
    if not rects:
        # Legacy empty highlights still belong in SQLite, but have no PDF hit
        # target and must not result in a fabricated annotation at page origin.
        return hl
    if metadata['kind'] == 'Highlight' and 'quads' not in metadata:
        rects = _normalize_text_rects(rects)
        hl['rects'] = rects
    metadata.setdefault('quads', [
        [[r['x'], r['y']], [r['x'] + r['w'], r['y']],
         [r['x'], r['y'] + r['h']], [r['x'] + r['w'], r['y'] + r['h']]] for r in rects])
    quads = metadata['quads']
    if not isinstance(quads, list) or len(quads) > MAX_RECTS:
        raise PdfAnnotationSyncError('invalid_annotation')
    for quad in quads:
        if not isinstance(quad, list) or len(quad) != 4 or not all(
            isinstance(p, (list, tuple)) and len(p) == 2 and all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in p) for p in quad):
            raise PdfAnnotationSyncError('invalid_annotation')
    if len(json.dumps(metadata)) > 262144:
        raise PdfAnnotationSyncError('limits')
    return hl


def _semantic(hl, *, note=True):
    if hl is None:
        return None
    metadata = hl['pdf_annotation']
    def rounded(value):
        if isinstance(value, (int, float)):
            return round(value, 3)
        if isinstance(value, dict):
            return {k: rounded(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [rounded(v) for v in value]
        return value
    return rounded({'page': hl['page'], 'rects': hl['rects'], 'kind': metadata['kind'],
                    'quads': metadata.get('quads', []), 'color': metadata['color'],
                    'fill': metadata.get('fill', []), 'border_width': metadata.get('border_width', 0),
                    **({key: metadata.get(key, default) for key, default in (
                        ('font_size', 11), ('text_color', [0, 0, 0]), ('font_family', 'sans-serif'))}
                       if metadata['kind'] == 'FreeText' else {}),
                    'opacity': metadata['opacity'], **({'note': hl.get('note', '')} if note else {})})


def _read_native(doc, known, content_digest, cancel, deadline):
    import pymupdf as fitz

    result = {}
    count = 0
    for index, page in enumerate(doc):
        _checkpoint(cancel, deadline)
        names = set()
        for annot in page.annots() or []:
            count += 1
            if count > MAX_ANNOTATIONS:
                raise PdfAnnotationSyncError('limits')
            kind = annot.type[1]
            if kind not in SUPPORTED_KINDS:
                continue
            if kind in MARKUP_KINDS:
                vertices = annot.vertices or []
                if not vertices or len(vertices) % 4 or len(vertices) // 4 > MAX_RECTS:
                    raise PdfAnnotationSyncError('invalid_annotation')
                native_quads = [fitz.Quad(vertices[i:i + 4]) for i in range(0, len(vertices), 4)]
            else:
                rect = annot.rect
                if kind in {'Square', 'Circle'}:
                    # Shape Rect includes the border's appearance padding. RD
                    # identifies the original selected region, avoiding drift.
                    inset = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', doc.xref_get_key(annot.xref, 'RD')[1])
                    if len(inset) == 4:
                        left, bottom, right, top = map(float, inset)
                        rect = fitz.Rect(rect.x0 + left, rect.y0 + top, rect.x1 - right, rect.y1 - bottom)
                native_quads = [fitz.Quad(rect.tl, rect.tr, rect.bl, rect.br)]
            quads = [quad * page.rotation_matrix for quad in native_quads]
            name = annot.info.get('id') or (
                'Incremento-native-' + sha256(f'{content_digest}:{index}:{annot.xref}'.encode()).hexdigest()[:32])
            if name in names:
                raise PdfAnnotationSyncError('duplicate_identity')
            names.add(name)
            hl_id = known.get(_name_key(index + 1, name), 'native-' + sha256(_name_key(index + 1, name).encode()).hexdigest()[:32])
            color = _rgb(annot.colors.get('stroke') or annot.colors.get('fill'))
            opacity = annot.opacity if annot.opacity >= 0 else 1
            palette = min((key for key in COLORS if key != 'snapshot'), key=lambda key: sum(
                (a - b) ** 2 for a, b in zip(COLORS[key][0], color)))
            old = known.get(('row', hl_id))
            if old and old.get('color') == 'snapshot':
                palette = 'snapshot'
            text = '\n'.join(page.get_text('text', clip=quad.rect).strip() for quad in native_quads) if kind in MARKUP_KINDS else ''
            row = {'id': hl_id, 'page': index + 1, 'color': palette, 'text': text,
                   'note': annot.info.get('content', ''), 'rects': [
                       {'x': q.rect.x0, 'y': q.rect.y0, 'w': q.rect.width, 'h': q.rect.height} for q in quads],
                   'pdf_annotation': {'name': name, 'kind': kind, 'color': color, 'opacity': opacity,
                       'quads': [[[p.x, p.y] for p in quad] for quad in quads],
                       'author': annot.info.get('title', ''), 'subject': annot.info.get('subject', ''),
                       'fill': _rgb(annot.colors['fill']) if annot.colors.get('fill') else [],
                       'border_width': annot.border.get('width', 0), 'xref': annot.xref}}
            if kind == 'FreeText':
                spans = [span for block in annot.get_text('dict').get('blocks', [])
                         for line in block.get('lines', []) for span in line.get('spans', [])]
                span = spans[0] if spans else {}
                font = span.get('font', '').lower()
                text_color = span.get('color', 0)
                row['pdf_annotation'].update(font_size=span.get('size', 11),
                    text_color=[(text_color >> shift & 255) / 255 for shift in (16, 8, 0)],
                    font_family='monospace' if 'courier' in font or 'mono' in font else
                                'serif' if 'times' in font or 'serif' in font and 'sans' not in font else 'sans-serif')
                if not row['note']:
                    row['note'] = annot.get_text().strip()
            if old and _semantic(old, note=False) == _semantic(row, note=False):
                row['text'] = old.get('text', text)
            result[hl_id] = row
    return result


def _merge(baseline, local, *pdfs):
    merged = {}
    conflicts = 0
    for hl_id in sorted(set(baseline) | set(local) | set().union(*(set(pdf) for pdf in pdfs))):
        old = baseline.get(hl_id)
        candidates = [local.get(hl_id), *(pdf.get(hl_id) for pdf in pdfs)]
        changed = [row for row in candidates if _semantic(row) != _semantic(old)]
        distinct = []
        for row in changed:
            if not any(_semantic(row) == _semantic(other) for other in distinct):
                distinct.append(row)
        if not distinct:
            selected = local.get(hl_id) or old
        elif len(distinct) == 1:
            selected = distinct[0]
        else:
            conflicts += 1
            surviving = [deepcopy(row) for row in distinct if row is not None]
            selected = surviving[0] if surviving else None
            if selected and all(_semantic(row, note=False) == _semantic(selected, note=False) for row in surviving):
                # Concurrent comments on the same passage remain one highlight.
                selected['note'] = '\n\n'.join(dict.fromkeys(row.get('note', '') for row in surviving if row.get('note')))
            elif selected:
                for row in surviving[1:]:
                    digest = sha256(json.dumps(_semantic(row), sort_keys=True).encode()).hexdigest()[:24]
                    identity = sha256(f'{hl_id}:{digest}'.encode()).hexdigest()[:32]
                    row['id'] = 'conflict-' + identity
                    row['pdf_annotation']['name'] = 'Incremento-conflict-' + identity
                    merged[row['id']] = row
        if selected is not None:
            merged[hl_id] = deepcopy(selected)
    return merged, conflicts


def _create_native(page, row):
    import pymupdf as fitz

    metadata = row['pdf_annotation']
    kind = metadata['kind']
    quads = [fitz.Quad(points) * page.derotation_matrix for points in metadata['quads']]
    rect = quads[0].rect
    if kind in MARKUP_KINDS:
        method = {'Highlight': 'add_highlight_annot', 'Underline': 'add_underline_annot',
                  'Squiggly': 'add_squiggly_annot', 'StrikeOut': 'add_strikeout_annot'}[kind]
        annot = getattr(page, method)(quads)
    elif kind == 'Text':
        annot = page.add_text_annot(rect.tl - fitz.Point(1, 1), row.get('note', ''))
    elif kind == 'FreeText':
        # Treat user text as text, never as an HTML resource/URL. Rich text adds
        # the font fallback needed for Arabic and CJK when copying a comment.
        rgb_hex = ''.join(f'{round(value * 255):02x}' for value in metadata['text_color'])
        style = f"font-size: {metadata['font_size']}pt; font-family: {metadata.get('font_family', 'sans-serif')}; color: #{rgb_hex};"
        annot = page.add_freetext_annot(rect, '<p>' + escape(row.get('note', '')).replace('\n', '<br>') + '</p>',
                                        richtext=True, style=style, fill_color=metadata.get('fill') or None)
    elif kind == 'Circle':
        annot = page.add_circle_annot(rect)
    else:
        annot = page.add_rect_annot(rect)
    annot.set_info(content=row.get('note', ''), title=metadata.get('author', 'Incremento'),
                   subject=metadata.get('subject', ''))
    page.parent.xref_set_key(annot.xref, 'NM', fitz.get_pdf_str(metadata['name']))
    if kind != 'FreeText':
        annot.set_colors(stroke=metadata['color'], fill=metadata.get('fill') or None)
    if kind in {'Square', 'Circle'}:
        annot.set_border(width=metadata['border_width'])
    annot.update(opacity=metadata['opacity'])
    return annot


def _rewrite(doc, target, current):
    import pymupdf as fitz

    by_name = {_name_key(row['page'], row['pdf_annotation']['name']): row for row in target.values() if row['rects']}
    handled = set()
    existing = {(row['page'], row['pdf_annotation'].get('xref')): row for row in current.values() if row['rects']}
    for index, page in enumerate(doc):
        # Do not update while iterating Page.annots(): AP updates can reload it.
        xrefs = [a.xref for a in (page.annots() or []) if a.type[1] in SUPPORTED_KINDS]
        for xref in xrefs:
            annot = page.load_annot(xref)
            native = existing.get((index + 1, xref))
            if native is None:
                continue
            key = _name_key(index + 1, native['pdf_annotation']['name'])
            desired = by_name.get(key)
            if desired is None:
                page.delete_annot(annot)
                continue
            handled.add(key)
            if _semantic(native) != _semantic(desired):
                if _semantic(native, note=False) == _semantic(desired, note=False) and annot.type[1] != 'FreeText':
                    annot.set_info(content=desired.get('note', ''))
                    annot.update()
                else:
                    page.delete_annot(annot)
                    _create_native(page, desired)
            elif not annot.info.get('id'):
                doc.xref_set_key(xref, 'NM', fitz.get_pdf_str(desired['pdf_annotation']['name']))
    for key, row in by_name.items():
        if key not in handled:
            if row['page'] > doc.page_count:
                raise PdfAnnotationSyncError('invalid_annotation')
            page = doc[row['page'] - 1]
            _create_native(page, row)


def _stage_pdf(doc, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.incremento-annotations-', suffix='.pdf', dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        import pymupdf as fitz

        doc.save(temporary, encryption=fitz.PDF_ENCRYPT_KEEP, no_new_id=True, garbage=3, deflate=True)
        _check_file(temporary)
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_replace_pdf(temporary, destination, expected_signature):
    if destination.is_symlink():
        raise PdfAnnotationSyncError('unsafe_path')
    current = _file_signature(destination) if destination.exists() else None
    if current != expected_signature:
        raise PdfAnnotationSyncError('file_changed')
    if destination.exists():
        os.chmod(temporary, destination.stat().st_mode & 0o777)
    os.replace(temporary, destination)


def _backup(addon_dir, profile, card_id, destination, expected_signature, *, source):
    target = paths.get_pdf_annotation_backup_path(addon_dir, profile, card_id, source=source)
    _check_profile_path(addon_dir, profile, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=target.parent, prefix='.backup-', suffix='.pdf')
    os.close(fd)
    temporary = Path(name)
    try:
        shutil.copyfile(destination, temporary)
        if _file_signature(temporary)[-1] != expected_signature[-1]:
            raise PdfAnnotationSyncError('file_changed')
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def sync_pdf_annotations(addon_dir: str, profile: str, card_id: int, filename: str,
                         *, source_path: str | None = None, cancel=None) -> dict:
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise PdfAnnotationSyncError('dependency') from exc
    if tuple(int(part) for part in fitz.VersionBind.split('.')[:2]) < (1, 26):
        raise PdfAnnotationSyncError('dependency')
    deadline = time.monotonic() + 60
    while not _sync_lock.acquire(timeout=.1):
        _checkpoint(cancel, deadline)
    documents = []
    staged = []
    try:
        return _sync_locked(addon_dir, profile, int(card_id), filename, source_path, cancel, deadline, documents, staged)
    finally:
        for doc in documents:
            doc.close()
        for path in staged:
            path.unlink(missing_ok=True)
        _sync_lock.release()


def _sync_locked(addon_dir, profile, card_id, filename, source_path, cancel, deadline, documents, staged):
    import pymupdf as fitz

    managed = _managed_path(addon_dir, profile, filename)
    _check_file(managed)
    conn = get_connection(addon_dir, profile)
    state = pdf_annotation_sync_state(addon_dir, profile, card_id)
    if state and state['filename'] != filename:
        raise PdfAnnotationSyncError('document_changed')
    if not state:
        with conn:
            conn.execute('INSERT INTO pdf_annotation_sync(card_id, filename, document_id) VALUES (?, ?, ?)',
                         (card_id, filename, uuid.uuid4().hex))
        state = pdf_annotation_sync_state(addon_dir, profile, card_id)
    source = state['source_path'] if source_path is None else source_path
    targets = [managed]
    if source:
        original = Path(source)
        if not original.is_absolute() or original.is_symlink():
            raise PdfAnnotationSyncError('unsafe_path')
        # Linking another profile's runtime PDF would violate profile isolation.
        if original.resolve().is_relative_to((Path(addon_dir) / 'user_files').resolve()):
            raise PdfAnnotationSyncError('unsafe_path')
        _check_file(original)
        original = original.resolve()
        source = str(original)
        if original.resolve() != managed.resolve():
            targets.append(original)
    baseline_raw = json.loads(state['baseline_json'])
    if not isinstance(baseline_raw, dict) or len(baseline_raw) > MAX_ANNOTATIONS:
        raise PdfAnnotationSyncError('invalid_annotation')
    document_id = state['document_id']
    baseline = {key: _prepare(row, document_id) for key, row in baseline_raw.items()}
    raw_local = {row['id']: row for row in load_highlights(addon_dir, profile, card_id)}
    if len(raw_local) > MAX_ANNOTATIONS:
        raise PdfAnnotationSyncError('limits')
    local = {key: _prepare(row, document_id) for key, row in raw_local.items()}
    known = {}
    for row in [*baseline.values(), *local.values()]:
        key = _name_key(row['page'], row['pdf_annotation']['name'])
        if key in known and known[key] != row['id']:
            raise PdfAnnotationSyncError('duplicate_identity')
        known[key] = row['id']
        known[('row', row['id'])] = row
    signatures = []
    digest = ''
    native = []
    stamps = []
    stamp_key = 'IncrementoAnnotationSync/' + document_id
    old_stamp = sha256(state['baseline_json'].encode()).hexdigest()
    for target in targets:
        _checkpoint(cancel, deadline)
        signature = _file_signature(target)
        doc = fitz.open(target)
        documents.append(doc)
        current_digest = _content_digest(doc, cancel, deadline)
        if (digest and current_digest != digest) or (state['content_digest'] and current_digest != state['content_digest']):
            raise PdfAnnotationSyncError('document_changed')
        digest = current_digest
        signatures.append(signature)
        stamps.append(doc.xref_get_key(doc.pdf_catalog(), stamp_key)[1])
        native.append(_read_native(doc, known, digest, cancel, deadline))
        if _file_signature(target) != signature:
            raise PdfAnnotationSyncError('file_changed')
    merge_native = [dict(rows) for rows in native]
    for rows, stamp in zip(merge_native, stamps):
        if stamp != old_stamp:
            # A stale snapshot (or a reader that stripped our private stamp)
            # has no evidence of a deliberate deletion of newer annotations.
            for key, row in baseline.items():
                rows.setdefault(key, row)
    if source and source != state['source_path']:
        # A newly linked file has no shared deletion history. Its missing
        # annotations must not erase work already synced into the managed PDF.
        merge_native[-1] = {**baseline, **merge_native[-1]}
    # Empty legacy/citation records are not backed by a native PDF annotation.
    for pdf_rows in merge_native:
        pdf_rows.update({key: row for key, row in local.items() if not row['rects']})
    merged, conflicts = _merge(baseline, local, *merge_native)
    merged = {key: _prepare(row, document_id) for key, row in merged.items()}
    baseline_json = json.dumps(merged, ensure_ascii=False, sort_keys=True)
    new_stamp = sha256(baseline_json.encode()).hexdigest()
    if len(merged) > MAX_ANNOTATIONS or len(baseline_json) > MAX_BASELINE_CHARS:
        raise PdfAnnotationSyncError('limits')
    writes = []
    appearance_changed = False
    for doc, target, current, signature in zip(documents, targets, native, signatures):
        _checkpoint(cancel, deadline)
        before_appearance = {key: _semantic(row) for key, row in current.items()
                             if row['pdf_annotation']['kind'] != 'Highlight' and row.get('color') != 'snapshot'}
        after_appearance = {key: _semantic(row) for key, row in merged.items()
                            if row['pdf_annotation']['kind'] != 'Highlight' and row.get('color') != 'snapshot'}
        if target == managed:
            appearance_changed = before_appearance != after_appearance
        _rewrite(doc, merged, current)
        if (merged or baseline or doc.is_dirty) and doc.xref_get_key(doc.pdf_catalog(), stamp_key)[1] != new_stamp:
            if doc.xref_get_key(doc.pdf_catalog(), 'IncrementoAnnotationSync')[0] != 'dict':
                doc.xref_set_key(doc.pdf_catalog(), 'IncrementoAnnotationSync', '<<>>')
            doc.xref_set_key(doc.pdf_catalog(), stamp_key, fitz.get_pdf_str(new_stamp))
        if doc.is_dirty:
            temporary = _stage_pdf(doc, target)
            staged.append(temporary)
            with fitz.open(temporary) as check:
                if _content_digest(check, cancel, deadline) != digest:
                    raise PdfAnnotationSyncError('invalid_pdf')
                reread = _read_native(check, known, digest, cancel, deadline)
                by_name = {_name_key(row['page'], row['pdf_annotation']['name']): row for row in reread.values()}
                for row in merged.values():
                    if row['rects'] and by_name.get(_name_key(row['page'], row['pdf_annotation']['name']), {}).get('note') != row.get('note', ''):
                        raise PdfAnnotationSyncError('invalid_pdf')
            writes.append((temporary, target, signature))
    reader = paths.get_pdf_annotation_reader_path(addon_dir, profile, card_id)
    _check_profile_path(addon_dir, profile, reader)
    # Retain native appearances for other annotation kinds. Highlights and
    # Incremento snapshot frames are rendered by the reader's interactive layer.
    managed_doc = documents[0]
    snapshot_names = {row['pdf_annotation']['name'] for row in merged.values() if row.get('color') == 'snapshot'}
    for page in managed_doc:
        xrefs = [a.xref for a in (page.annots() or []) if a.type[1] == 'Highlight' or a.info.get('id') in snapshot_names]
        for xref in xrefs:
            page.delete_annot(page.load_annot(xref))
    reader_temp = _stage_pdf(managed_doc, reader)
    staged.append(reader_temp)
    _checkpoint(cancel, deadline)
    # Validate all original snapshots again before beginning the commit phase.
    for target, signature in zip(targets, signatures):
        if _file_signature(target) != signature:
            raise PdfAnnotationSyncError('file_changed')
    current_state = pdf_annotation_sync_state(addon_dir, profile, card_id)
    if not current_state or (current_state['filename'], current_state['document_id']) != (filename, document_id):
        raise PdfAnnotationSyncError('document_changed')
    for temporary, target, signature in writes:
        _backup(addon_dir, profile, card_id, target, signature, source=target != managed)
        _atomic_replace_pdf(temporary, target, signature)
    _atomic_replace_pdf(reader_temp, reader, _file_signature(reader) if reader.exists() else None)
    retry_needed = False
    with conn:
        # Acquire only the short SQLite commit lock, then compare against the
        # original snapshot. A note edited during file I/O always survives.
        conn.execute('UPDATE pdf_annotation_sync SET card_id=card_id WHERE card_id=?', (card_id,))
        current_state = pdf_annotation_sync_state(addon_dir, profile, card_id)
        if not current_state or (current_state['filename'], current_state['document_id']) != (filename, document_id):
            raise PdfAnnotationSyncError('document_changed')
        latest = {row['id']: row for row in load_highlights(addon_dir, profile, card_id)}
        for key in set(raw_local) | set(merged):
            if latest.get(key) != raw_local.get(key):
                retry_needed = True
                continue
            row = merged.get(key)
            if row is None:
                conn.execute('DELETE FROM pdf_highlights WHERE card_id=? AND id=?', (card_id, key))
            else:
                conn.execute('INSERT OR REPLACE INTO pdf_highlights '
                             '(id, card_id, page, color, text, note, rects, annotation_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                             (key, card_id, row['page'], row.get('color', 'yellow'), row.get('text', ''), row.get('note', ''),
                              json.dumps(row['rects']), json.dumps(row['pdf_annotation'])))
        conn.execute('UPDATE pdf_annotation_sync SET source_path=?, content_digest=?, baseline_json=? WHERE card_id=?',
                     (str(source or ''), digest, baseline_json, card_id))
    return {'reader_path': str(reader), 'source_path': str(source or ''), 'conflicts': conflicts,
            'changed': bool(writes), 'retry_needed': retry_needed,
            'appearance_changed': appearance_changed,
            'imported': len(set(merged) - set(local))}
