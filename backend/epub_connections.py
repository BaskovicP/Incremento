"""Bounded bidirectional EPUB connections, anchored to sections and text offsets."""
import math

try:
    from .db import get_connection
    from .document_links import _identity
except ImportError:
    from db import get_connection
    from document_links import _identity


def normalize_location(value):
    if not isinstance(value, dict):
        raise ValueError('Invalid EPUB location')
    for key, minimum, maximum in (('card_id', 1, 2**53 - 1), ('section', 0, 1_000_000),
                                  ('offset', -1, 50_000_000)):
        if type(value.get(key)) is not int or not minimum <= value[key] <= maximum:
            raise ValueError('Invalid EPUB location')
    scroll = value.get('scroll')
    if type(scroll) not in (int, float) or not math.isfinite(scroll) or not 0 <= scroll <= 1:
        raise ValueError('Invalid EPUB scroll position')
    return {key: value[key] for key in ('card_id', 'section', 'offset', 'scroll')}


def _match(side):
    return f'({side}_content_id=? OR ({side}_content_id IS NULL AND {side}_card_id=?))'


def add_connection(addon_dir, profile, source, target, *, quote=''):
    source, target = normalize_location(source), normalize_location(target)
    if not isinstance(quote, str) or len(quote) > 2000 or '\x00' in quote:
        raise ValueError('Invalid EPUB excerpt')
    conn = get_connection(addon_dir, profile)
    with conn:
        identities = [_identity(conn, p['card_id']) for p in (source, target)]
        params = (identities[0], source['card_id'], source['section'], source['offset'],
                  identities[1], target['card_id'], target['section'], target['offset'])
        duplicate = conn.execute('SELECT id FROM epub_connections WHERE ' + _match('source') +
            ' AND source_section=? AND source_offset=? AND ' + _match('target') +
            ' AND target_section=? AND target_offset=? LIMIT 1', params).fetchone()
        if duplicate:
            return duplicate[0]
        for p, identity in zip((source, target), identities):
            count = conn.execute('SELECT count(*) FROM epub_connections WHERE ' + _match('source') +
                                 ' OR ' + _match('target'),
                                 (identity, p['card_id'], identity, p['card_id'])).fetchone()[0]
            if count >= 200:
                raise ValueError('EPUB connection limit reached')
        values = []
        for p, identity in zip((source, target), identities):
            values.extend((p['card_id'], identity, p['section'], p['offset'], p['scroll']))
        return conn.execute('INSERT INTO epub_connections(source_card_id,source_content_id,source_section,'
            'source_offset,source_scroll,target_card_id,target_content_id,target_section,target_offset,target_scroll,quote) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?)', (*values, quote)).lastrowid


def list_connections(addon_dir, profile, card_id, section):
    normalize_location(dict(card_id=card_id, section=section, offset=0, scroll=0))
    conn = get_connection(addon_dir, profile)
    identity, rows = _identity(conn, card_id), []
    for side, other, direction in (('source', 'target', 'outgoing'), ('target', 'source', 'incoming')):
        for row in conn.execute(
            f'SELECT l.id, CASE WHEN l.{other}_content_id IS NULL THEN l.{other}_card_id '
            f'ELSE coalesce(c.card_id,0) END, l.{other}_section, l.{other}_offset, l.{other}_scroll, l.quote '
            f'FROM epub_connections l LEFT JOIN content_items c ON c.content_id=l.{other}_content_id '
            f'WHERE {_match(side)} AND {side}_section=? ORDER BY l.id LIMIT 200',
            (identity, card_id, section)).fetchall():
            rows.append(dict(id=row[0], direction=direction,
                             target=dict(zip(('card_id', 'section', 'offset', 'scroll'), row[1:5])), quote=row[5]))
    return list({row['id']: row for row in sorted(rows, key=lambda r: r['id'])}.values())[:200]


def remove_connection(addon_dir, profile, card_id, section, link_id):
    conn = get_connection(addon_dir, profile)
    identity = _identity(conn, card_id)
    with conn:
        return conn.execute(f'DELETE FROM epub_connections WHERE id=? AND (({_match("source")} '
            f'AND source_section=?) OR ({_match("target")} AND target_section=?))',
            (link_id, identity, card_id, section, identity, card_id, section)).rowcount > 0
