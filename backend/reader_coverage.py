"""Per-document coverage; viewing, explicit reading and daily activity are distinct."""
import json
import math

try:
    from .db import get_connection
    from .document_links import _identity
except ImportError:
    from db import get_connection
    from document_links import _identity

# ponytail: 1,024 disjoint ranges per section/document; use an interval table if this ceiling is reached.
MAX_RANGES = 1024


def _document(conn, kind, card_id, filename):
    if (kind not in ('pdf', 'epub') or type(card_id) is not int or not 0 < card_id <= 2**63 - 1
            or not isinstance(filename, str) or not filename or len(filename) > 500
            or '\0' in filename or filename.startswith(('/', '\\'))
            or '..' in filename.replace('\\', '/').split('/')):
        raise ValueError('Invalid coverage document')
    content = _identity(conn, card_id)
    return 'content:' + content if content else 'card:' + str(card_id)


def merge_ranges(ranges):
    result = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    if len(result) > MAX_RANGES:
        raise ValueError('Coverage range limit reached')
    return result


def subtract_ranges(ranges, excluded):
    for start, end in excluded:
        ranges = [[a, b] for lo, hi in ranges for a, b in ((lo, min(hi, start)), (max(lo, end), hi)) if a < b]
    return ranges


def _ranges(raw):
    try:
        values = json.loads(raw)
        if not isinstance(values, list) or len(values) > MAX_RANGES:
            return []
        if any(not isinstance(r, list) or len(r) != 2 or type(r[0]) is not int
               or type(r[1]) is not int or not 0 <= r[0] < r[1] <= 50_000_000 for r in values):
            return []
        return merge_ranges(values)
    except (ValueError, TypeError):
        return []


def record_coverage(addon_dir, profile, kind, card_id, filename, *, position, start, end,
                    marked=False, remove=False):
    maximum = 1_000_000 if kind == 'pdf' else 50_000_000
    if (type(position) is not int or not 0 <= position <= 1_000_000
            or (kind == 'pdf' and position != 0) or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= maximum or type(marked) is not bool or type(remove) is not bool):
        raise ValueError('Invalid coverage range')
    conn = get_connection(addon_dir, profile)
    identity = _document(conn, kind, card_id, filename)
    with conn:
        if not conn.in_transaction:
            conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT viewed_json,read_json,unread_json FROM document_coverage WHERE '
            'document_key=? AND kind=? AND filename=? AND position=?',
            (identity, kind, filename, position)).fetchone()
        viewed, read, unread = (_ranges(value) for value in row) if row else ([], [], [])
        if remove:
            read = subtract_ranges(read, [[start, end]])
            unread = merge_ranges([*unread, [start, end]])
        else:
            viewed = merge_ranges([*viewed, [start, end]])
            if marked:
                read = merge_ranges([*read, [start, end]])
                unread = subtract_ranges(unread, [[start, end]])
        conn.execute('INSERT INTO document_coverage(document_key,kind,filename,position,viewed_json,read_json,unread_json) '
            'VALUES(?,?,?,?,?,?,?) ON CONFLICT(document_key,kind,filename,position) DO UPDATE SET '
            'viewed_json=excluded.viewed_json,read_json=excluded.read_json,unread_json=excluded.unread_json',
            (identity, kind, filename, position, json.dumps(viewed), json.dumps(read), json.dumps(unread)))


def coverage_summary(addon_dir, profile, kind, card_id, filename, *, total=None, lengths=(), legacy_read=None, _connection=None):
    conn = _connection if _connection is not None else get_connection(addon_dir, profile)
    identity = _document(conn, kind, card_id, filename)
    if legacy_read is None:
        if kind == 'pdf':
            row = conn.execute('SELECT read_page FROM pdf_progress WHERE card_id=?', (card_id,)).fetchone()
            legacy_read = row[0] if row else 0
        else:
            row = conn.execute('SELECT read_section_index,read_anchor_json,is_finished FROM epub_progress WHERE card_id=?',
                               (card_id,)).fetchone()
            try:
                from .document_statistics import epub_completion
            except ImportError:
                from document_statistics import epub_completion
            legacy_read = epub_completion(tuple(lengths), dict(zip(
                ('read_section_index', 'read_anchor_json', 'is_finished'), row)) if row else None)['read']
    rows = conn.execute('SELECT position,viewed_json,read_json,unread_json FROM document_coverage '
        'WHERE document_key=? AND kind=? AND filename=? ORDER BY position LIMIT 5001',
        (identity, kind, filename)).fetchall()
    by_position = {pos: (_ranges(view), _ranges(read), _ranges(unread)) for pos, view, read, unread in rows}
    nonlinear = any(read or unread for view, read, unread in by_position.values())
    if kind == 'pdf':
        sizes = (max(0, int(total or 0)),)
        weights = sizes
    else:
        sizes = tuple(max(1, int(n)) for n in lengths) if len(lengths) <= 5000 else ()
        weights = tuple(max(1, math.ceil(n / 1500)) for n in sizes)
    total_units = sum(weights)
    try:
        remaining = float(legacy_read or 0)
        remaining = max(0, min(total_units, remaining)) if math.isfinite(remaining) else 0
    except (TypeError, ValueError, OverflowError):
        remaining = 0
    viewed_count = marked_count = 0
    for position, (size, weight) in enumerate(zip(sizes, weights)):
        viewed, read, unread = by_position.get(position, ([], [], []))
        prefix = min(weight, remaining)
        remaining -= prefix
        legacy = [[0, round(size * prefix / weight)]] if prefix and weight else []
        marked_ranges = merge_ranges([*read, *legacy])
        viewed_ranges = merge_ranges([*viewed, *marked_ranges])
        marked_ranges = subtract_ranges(marked_ranges, unread)
        def count(ranges):
            return sum(max(0, min(size, hi) - min(size, lo)) for lo, hi in ranges) * weight / size if size else 0
        viewed_count += count(viewed_ranges)
        marked_count += count(marked_ranges)
    return dict(total=total_units or None, viewed=viewed_count, marked=marked_count,
        viewed_percent=100 * viewed_count / total_units if total_units else None,
        marked_percent=100 * marked_count / total_units if total_units else None, nonlinear_read=nonlinear)
