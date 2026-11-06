"""Shared excerpt associations; Markdown anchors survive edits and native Undo/Redo."""
import json
import re
from uuid import uuid4

try:
    from .db import get_connection
    from .document_links import _identity
    from .recording_links import _integer, _match, _source_position, _text, normalize_source
except ImportError:
    from db import get_connection
    from document_links import _identity
    from recording_links import _integer, _match, _source_position, _text, normalize_source

MAX_LINKS = 200
_MARKER = re.compile(r'<!-- incremento-excerpt:([a-f0-9]{32}) -->')


def strip_markers(text):
    return re.sub(r'<!-- incremento-excerpt(?:-start)?:[a-f0-9]{32} -->', '', text)


def marker(anchor, *, start=False):
    if not isinstance(anchor, str) or not re.fullmatch('[a-f0-9]{32}', anchor):
        raise ValueError('Invalid writing anchor')
    return '<!-- incremento-excerpt' + ('-start' if start else '') + ':' + anchor + ' -->'


def create_link(addon_dir, profile, source, writing_card_id, *, source_title):
    source = normalize_source(source)
    if not source['quote']:
        raise ValueError('Select a passage first')
    writing_card_id = _integer(writing_card_id)
    title = _text(source_title, 240)
    conn = get_connection(addon_dir, profile)
    anchor = uuid4().hex
    with conn:
        identity = _identity(conn, writing_card_id)
        rows = conn.execute('SELECT anchor,active FROM writing_links WHERE ' + _match('writing') +
                            ' ORDER BY rowid DESC LIMIT ?', (identity, writing_card_id, MAX_LINKS * 2)).fetchall()
        if sum(active for _, active in rows) >= MAX_LINKS:
            raise ValueError('Writing excerpt limit reached')
        # ponytail: retain at most 200 removed anchors for native Undo/Redo;
        # older history can use a separate ledger if users need deeper recovery.
        inactive = [anchor for anchor, active in rows if not active]
        conn.executemany('DELETE FROM writing_links WHERE anchor=?',
                         [(anchor,) for anchor in inactive[MAX_LINKS - 1:]])
        conn.execute('INSERT INTO writing_links(anchor,source_card_id,source_content_id,source_kind,source_position,'
                     'source_json,source_title,writing_card_id,writing_content_id) VALUES (?,?,?,?,?,?,?,?,?)',
                     (anchor, source['card_id'], _identity(conn, source['card_id']), source['kind'],
                      _source_position(source), json.dumps(source, ensure_ascii=False), title, writing_card_id, identity))
    return anchor


def sync_links(addon_dir, profile, writing_card_id, text):
    """Called only after a durable Markdown save; missing markers deactivate, never delete."""
    writing_card_id = _integer(writing_card_id)
    if not isinstance(text, str):
        raise ValueError('Invalid writing text')
    # Only registered anchors can activate a link. Pasted/forged comments are inert.
    anchors = {match.group(1) for match in _MARKER.finditer(text)}
    conn = get_connection(addon_dir, profile)
    with conn:
        params = (_identity(conn, writing_card_id), writing_card_id)
        rows = conn.execute('SELECT anchor,active FROM writing_links WHERE ' + _match('writing') + ' LIMIT ?',
                            (*params, MAX_LINKS * 2)).fetchall()
        conn.executemany('UPDATE writing_links SET active=? WHERE anchor=?',
                         [(int(anchor in anchors), anchor) for anchor, active in rows if active != int(anchor in anchors)])


def list_links(addon_dir, profile, *, source=None, writing_card_id=None):
    if (source is None) == (writing_card_id is None):
        raise ValueError('Choose one endpoint')
    conn = get_connection(addon_dir, profile)
    if source is not None:
        source = normalize_source(source)
        side, card_id = 'source', source['card_id']
        scope = ' AND l.source_kind=? AND l.source_position=?'
        scope_params = (source['kind'], _source_position(source))
    else:
        side, card_id = 'writing', _integer(writing_card_id)
        scope, scope_params = '', ()
    identity = _identity(conn, card_id)
    matches = [(f'l.{side}_content_id IS NULL AND l.{side}_card_id=?', card_id)]
    if identity is not None:
        matches.append((f'l.{side}_content_id=?', identity))
    rows = []
    # Limit each indexed endpoint before merging, including inactive-history filters.
    for where, value in matches:
        rows.extend(conn.execute('SELECT l.rowid,l.anchor,l.source_json,l.source_title,'
            'CASE WHEN l.source_content_id IS NULL THEN l.source_card_id ELSE coalesce(s.card_id,0) END,'
            'CASE WHEN l.writing_content_id IS NULL THEN l.writing_card_id ELSE coalesce(w.card_id,0) END '
            'FROM writing_links l LEFT JOIN content_items s ON s.content_id=l.source_content_id '
            'LEFT JOIN content_items w ON w.content_id=l.writing_content_id '
            'WHERE l.active=1 AND ' + where + scope + ' ORDER BY l.rowid DESC LIMIT ?',
            (value, *scope_params, MAX_LINKS)).fetchall())
    result = []
    for _, anchor, encoded, title, source_id, writing_id in sorted(rows, reverse=True)[:MAX_LINKS]:
        try:
            marker(anchor)
            location = normalize_source(json.loads(encoded))
        except (ValueError, TypeError):
            continue
        location['card_id'] = source_id
        result.append(dict(anchor=anchor, source=location, source_title=title, writing_card_id=writing_id))
    return result


def remove_link(addon_dir, profile, anchor, *, owner_card_id):
    marker(anchor)
    owner_card_id = _integer(owner_card_id)
    conn = get_connection(addon_dir, profile)
    identity = _identity(conn, owner_card_id)
    with conn:
        return conn.execute('DELETE FROM writing_links WHERE anchor=? AND (' + _match('source') +
            ' OR ' + _match('writing') + ')', (anchor, identity, owner_card_id, identity, owner_card_id)).rowcount > 0
