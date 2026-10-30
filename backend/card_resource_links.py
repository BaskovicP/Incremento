"""Explicit, bounded card-resource batches over the existing link repositories."""
from html import unescape
import re

try:
    from .db import get_connection
    from .document_links import add_document_link, list_document_links, _identity, _SOURCE_MATCH
    from .recording_links import add_recording_link, normalize_source, validate_segment, list_recording_links
    from .study_resources import resolve_document, resolve_recording, note_field, file_signature
except ImportError:
    from db import get_connection
    from document_links import add_document_link, list_document_links, _identity, _SOURCE_MATCH
    from recording_links import add_recording_link, normalize_source, validate_segment, list_recording_links
    from study_resources import resolve_document, resolve_recording, note_field, file_signature

MAX_BATCH = 32
MAX_LIBRARY = 500
_RESTORE_COLUMNS = {
    'pdf': ('document_links', 'source_card_id,source_content_id,source_kind,source_page,quote,'
            'target_card_id,target_content_id,target_page,target_scroll,source_y,target_y'),
    'recording': ('recording_links', 'source_card_id,source_content_id,source_kind,source_position,source_json,'
                  'recording_card_id,recording_content_id,start,end,label'),
}


def pdf_page_count(path):
    from PyQt6.QtPdf import QPdfDocument
    document = QPdfDocument(None)
    try:
        document.load(path)
        count = document.pageCount()
        if not 1 <= count <= 1_000_000:
            raise ValueError('PDF pages unavailable')
        return count
    finally:
        document.close()


def card_summary(collection, card_id):
    note = collection.get_note(collection.get_card(card_id).nid)
    text = str(next(iter(note.fields), ''))[:4000]
    return ' '.join(unescape(re.sub('<[^>]*>', ' ', text)).split())[:240]


def load_resource_library(addon_dir, profile, collection):
    ids = collection.db.list(
        'SELECT min(c.id) FROM cards c JOIN notes n ON n.id=c.nid JOIN notetypes m ON m.id=n.mid '
        'WHERE m.name IN (?,?,?) GROUP BY n.id ORDER BY n.id DESC LIMIT ?',
        'Incremento PDF', 'Incremento Video', 'Incremento Audio', MAX_LIBRARY + 1)
    result = []
    for cid in ids[:MAX_LIBRARY]:
        try:
            note = collection.get_note(collection.get_card(cid).nid)
            kind = {'Incremento PDF': 'pdf', 'Incremento Video': 'video', 'Incremento Audio': 'audio'}[
                note.note_type()['name']]
            row = dict(kind=kind, card_id=int(cid), title=note_field(note, 'Title')[:240], available=True)
            try:
                if kind == 'pdf':
                    resolve_document(addon_dir, profile, collection, dict(kind='pdf', card_id=int(cid), page=1))
                else:
                    resolve_recording(addon_dir, profile, collection, int(cid))
            except ValueError:
                row['available'] = False
            result.append(row)
        except (KeyError, ValueError):
            continue
    return result, len(ids) > MAX_LIBRARY


def _validated(addon_dir, profile, collection, selection):
    if not isinstance(selection, list) or not 1 <= len(selection) <= MAX_BATCH:
        raise ValueError('Choose between one and 32 resources')
    result = []
    for raw in selection:
        if not isinstance(raw, dict) or raw.get('kind') not in ('pdf', 'video', 'audio'):
            raise ValueError('Unsupported resource')
        row = dict(raw)
        label = row.get('label', '')
        maximum_label = 2000 if row['kind'] == 'pdf' and row.get('link_id') else 240
        if not isinstance(label, str) or len(label) > maximum_label or '\0' in label:
            raise ValueError('Invalid resource label')
        row['label'] = label.strip()
        if row['kind'] == 'pdf':
            source = normalize_source(dict(kind='pdf', card_id=row.get('card_id'), page=row.get('page', 1),
                scroll=row.get('scroll', 0), page_y=row.get('page_y')))
            snapshot = resolve_document(addon_dir, profile, collection, source)
            if source['page'] > min(pdf_page_count(snapshot['path']), snapshot['max_page']):
                raise ValueError('Page unavailable')
            row.update(source)
        else:
            snapshot = resolve_recording(addon_dir, profile, collection, row.get('card_id'))
            row['start'], row['end'] = validate_segment(row.get('start', 0), row.get('end'),
                                                       duration=row.get('duration'))
            row['label'] = row['label'] or snapshot['title'][:240]
        if raw.get('snapshot') is not None:
            expected = raw['snapshot']
            if (snapshot['path'] != expected['path'] or file_signature(snapshot['path']) != tuple(expected['signature'])):
                raise ValueError('Resource changed')
        link_id = row.get('link_id', 0)
        if type(link_id) is not int or link_id < 0:
            raise ValueError('Invalid link')
        result.append(row)
    return result


def save_card_resource_links(addon_dir, profile, collection, card_id, selection, *, is_cancelled=lambda: False):
    """Validate all destinations first; write the mixed batch in one transaction."""
    source = normalize_source(dict(kind='card', card_id=card_id))
    if is_cancelled():
        return []
    collection.get_card(card_id)
    rows = _validated(addon_dir, profile, collection, selection)
    conn = get_connection(addon_dir, profile)
    saved = []
    with conn:
        documents = list_document_links(addon_dir, profile, card_id)
        recordings = list_recording_links(addon_dir, profile, source=source)
        for row in rows:
            if is_cancelled():
                raise ValueError('Resource linking cancelled')
            link_id = row.get('link_id', 0)
            if row['kind'] == 'pdf':
                if link_id:
                    if any(d['id'] != link_id and d['source_kind'] == 'card' and
                        (d['target_card_id'], d['target_page'], d['target_scroll'], d.get('target_y')) ==
                        (row['card_id'], row['page'], row['scroll'], row.get('page_y')) for d in documents):
                        raise ValueError('Resource location already linked')
                    cursor = conn.execute('UPDATE document_links SET target_card_id=?,target_content_id=?, '
                        'target_page=?,target_scroll=?,target_y=?,quote=? WHERE id=? AND source_kind=\'card\' AND ' + _SOURCE_MATCH,
                        (row['card_id'], _identity(conn, row['card_id']), row['page'], row['scroll'],
                         row.get('page_y'), row['label'], link_id, _identity(conn, card_id), card_id))
                    if cursor.rowcount != 1:
                        raise ValueError('Link no longer available')
                else:
                    duplicate = next((d for d in documents if d['source_kind'] == 'card'
                        and (d['target_card_id'], d['target_page'], d['target_scroll'], d.get('target_y')) ==
                            (row['card_id'], row['page'], row['scroll'], row.get('page_y'))), None)
                    link_id = duplicate['id'] if duplicate else add_document_link(addon_dir, profile,
                        source_card_id=card_id, source_kind='card', target_card_id=row['card_id'],
                        target_page=row['page'], target_scroll=row['scroll'], target_y=row.get('page_y'),
                        quote=row['label'], _connection=conn)
                    documents = list_document_links(addon_dir, profile, card_id)
            elif link_id:
                if not any(r['id'] == link_id for r in recordings):
                    raise ValueError('Link no longer available')
                if any(r['id'] != link_id and (r['recording_card_id'], r['start'], r['end']) ==
                    (row['card_id'], row['start'], row['end']) for r in recordings):
                    raise ValueError('Resource location already linked')
                conn.execute('UPDATE recording_links SET recording_card_id=?,recording_content_id=?,start=?,end=?,label=? WHERE id=?',
                    (row['card_id'], _identity(conn, row['card_id']), row['start'], row['end'], row['label'], link_id))
            else:
                link_id = add_recording_link(addon_dir, profile, source, row['card_id'], start=row['start'],
                    end=row['end'], label=row['label'], _connection=conn)
            saved.append(link_id)
            if row['kind'] == 'pdf':
                documents = list_document_links(addon_dir, profile, card_id)
            else:
                recordings = list_recording_links(addon_dir, profile, source=source)
        if is_cancelled():
            raise ValueError('Resource linking cancelled')
    return saved


def unlink_card_resource(addon_dir, profile, card_id, row):
    """Only direct card associations are editable here; citations stay intact."""
    conn = get_connection(addon_dir, profile)
    link_id = row.get('link_id', row.get('id', 0))
    with conn:
        if row.get('location') is not None:
            if row.get('owner_card_id') != card_id:
                return False
            kind = 'pdf'
        else:
            if row.get('source', {}).get('kind') != 'card' or row['source']['card_id'] != card_id:
                return False
            kind = 'recording'
        table, columns = _RESTORE_COLUMNS[kind]
        params = (link_id, _identity(conn, card_id), card_id)
        where = " WHERE id=? AND source_kind='card' AND " + _SOURCE_MATCH
        record = conn.execute(f'SELECT {columns} FROM {table}' + where, params).fetchone()
        if record is None:
            return False
        conn.execute(f'DELETE FROM {table}' + where, params)
    return dict(kind=kind, record=tuple(record), profile=profile)


def restore_card_resource_link(addon_dir, profile, collection, card_id, token):
    """Undo a deletion exactly, including an unavailable canonical target."""
    collection.get_card(card_id)
    if not isinstance(token, dict) or token.get('profile') != profile or token.get('kind') not in _RESTORE_COLUMNS:
        raise ValueError('Invalid unlink undo')
    table, columns = _RESTORE_COLUMNS[token['kind']]
    record = token.get('record')
    if not isinstance(record, (tuple, list)) or len(record) != len(columns.split(',')) or record[2] != 'card':
        raise ValueError('Invalid unlink undo')
    conn = get_connection(addon_dir, profile)
    identity = _identity(conn, card_id)
    if not ((record[1] is not None and record[1] == identity) or (record[1] is None and record[0] == card_id)):
        raise ValueError('Unlink owner changed')
    with conn:
        # Only the association is restored; no file is read, copied, or repaired.
        return conn.execute(f'INSERT INTO {table}({columns}) VALUES ({",".join("?" for _ in record)})', record).lastrowid
