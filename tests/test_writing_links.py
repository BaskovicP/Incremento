"""Writing excerpts retain one shared, profile-scoped source association."""
import sqlite3

import pytest

import db
from db_schema import initialize_schema

SOURCE = dict(kind='pdf', card_id=7, page=3, scroll=.25, quote='Original passage')


def test_start_marker_alone_does_not_activate_a_link_and_both_markers_are_metadata(tmp_path):
    from writing_links import create_link, marker, sync_links, list_links, strip_markers
    anchor = create_link(str(tmp_path), 'A', SOURCE, 8, source_title='Book')
    sync_links(str(tmp_path), 'A', 8, marker(anchor, start=True))
    assert list_links(str(tmp_path), 'A', source=SOURCE) == []
    text = marker(anchor, start=True) + '\nParaphrase\n' + marker(anchor)
    assert strip_markers(text) == '\nParaphrase\n'
    sync_links(str(tmp_path), 'A', 8, text)
    assert list_links(str(tmp_path), 'A', source=SOURCE)[0]['anchor'] == anchor


def test_saved_excerpt_is_visible_from_both_ends_and_survives_paraphrasing(tmp_path):
    from writing_links import create_link, marker, sync_links, list_links
    root = str(tmp_path)
    anchor = create_link(root, 'A', SOURCE, 8, source_title='A book')
    assert list_links(root, 'A', source=SOURCE) == []  # not durably saved yet
    sync_links(root, 'A', 8, 'Original passage\n' + marker(anchor))
    rows = list_links(root, 'A', writing_card_id=8)
    assert rows == list_links(root, 'A', source=SOURCE)
    assert rows[0]['source'] == {**SOURCE, 'scroll': .25}
    assert rows[0]['source_title'] == 'A book'
    sync_links(root, 'A', 8, 'My own wording\n' + marker(anchor))
    assert list_links(root, 'A', source=SOURCE) == rows
    assert list_links(root, 'A', source={**SOURCE, 'page': 4}) == []
    assert list_links(root, 'B', writing_card_id=8) == []
    sync_links(root, 'A', 8, 'My own wording')
    assert list_links(root, 'A', source=SOURCE) == []
    sync_links(root, 'A', 8, marker(anchor))  # native editor Redo restores the link
    assert list_links(root, 'A', source=SOURCE) == rows


def test_rebound_content_follows_both_ends_and_unlink_requires_its_owner(tmp_path):
    from writing_links import create_link, marker, sync_links, list_links, remove_link
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    for identity, kind, cid in [('book', 'pdf', 7), ('draft', 'writing', 8)]:
        conn.execute('INSERT INTO content_items VALUES (?,?,?,?,?,0,0)', (identity, kind, cid, cid * 10, identity))
    conn.commit()
    anchor = create_link(root, 'A', SOURCE, 8, source_title='Book')
    sync_links(root, 'A', 8, marker(anchor))
    conn.execute('UPDATE content_items SET card_id=card_id+10')
    conn.commit()
    assert list_links(root, 'A', source=SOURCE) == []
    row = list_links(root, 'A', source={**SOURCE, 'card_id': 17})[0]
    assert row['writing_card_id'] == 18 and row['source']['card_id'] == 17
    assert not remove_link(root, 'A', anchor, owner_card_id=8)
    assert not remove_link(root, 'A', anchor, owner_card_id=99)
    assert remove_link(root, 'A', anchor, owner_card_id=18)
    assert list_links(root, 'A', writing_card_id=18) == []


@pytest.mark.parametrize('change', [{'quote': ''}, {'quote': 'x' * 2001}, {'page': True}, {'scroll': float('nan')}, {'kind': 'web'}])
def test_invalid_sources_do_not_create_associations(tmp_path, change):
    from writing_links import create_link
    with pytest.raises(ValueError):
        create_link(str(tmp_path), 'A', {**SOURCE, **change}, 8, source_title='Book')
    assert db.get_connection(str(tmp_path), 'A').execute('SELECT count(*) FROM writing_links').fetchone() == (0,)


def test_writing_link_migration_rolls_back_table_indexes_and_ledger():
    with sqlite3.connect(':memory:') as conn:
        previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 24)
        initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)
        def fail(connection):
            db._migration_25_writing_links(connection)
            raise RuntimeError('interrupted')
        with pytest.raises(RuntimeError, match='interrupted'):
            initialize_schema(conn, bootstrap=db._create_tables, migrations=previous + ((25, 'writing_links', fail),))
        assert conn.execute('PRAGMA user_version').fetchone() == (24,)
        assert conn.execute('SELECT max(version) FROM schema_migrations').fetchone() == (24,)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name LIKE 'writing_links%'").fetchall() == []


def test_removing_excerpts_frees_the_limit_while_retaining_bounded_undo_history(tmp_path, monkeypatch):
    import writing_links as links
    monkeypatch.setattr(links, 'MAX_LINKS', 2)
    root = str(tmp_path)
    previous = []
    for _ in range(6):
        anchor = links.create_link(root, 'A', SOURCE, 8, source_title='Book')
        links.sync_links(root, 'A', 8, links.marker(anchor))
        links.sync_links(root, 'A', 8, '')
        previous.append(anchor)
    assert db.get_connection(root, 'A').execute('SELECT count(*) FROM writing_links').fetchone()[0] <= 4
    links.sync_links(root, 'A', 8, links.marker(previous[-1]))
    assert links.list_links(root, 'A', writing_card_id=8)[0]['anchor'] == previous[-1]


@pytest.mark.parametrize('rebound', [False, True], ids=['removed-history', 'rebound-active-history'])
def test_source_backlink_lookup_has_a_fixed_budget_even_with_many_removed_excerpts(tmp_path, rebound):
    import json
    from writing_links import create_link, marker, sync_links, list_links
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    # Many different drafts once quoted the same page; removed anchors must not
    # turn the reader's page-local lookup into a scan of that history.
    if rebound:
        conn.execute('INSERT INTO content_items VALUES (?,?,?,?,?,0,0)', ('book', 'pdf', 17, 170, 'book'))
    conn.executemany('INSERT INTO writing_links(anchor,source_card_id,source_content_id,source_kind,source_position,'
                     'source_json,source_title,writing_card_id,active) VALUES(?,?,?,?,?,?,?,?,?)',
                     [(f'{i:032x}', 7, 'book' if rebound else None, 'pdf', 3, json.dumps(SOURCE),
                       'Book', 1000 + i, int(rebound)) for i in range(5000)])
    conn.commit()
    anchor = create_link(root, 'A', SOURCE, 8, source_title='Book')
    sync_links(root, 'A', 8, marker(anchor))
    steps = 2000
    def budget():
        nonlocal steps
        steps -= 1
        return steps <= 0
    conn.set_progress_handler(budget, 1)
    try:
        rows = list_links(root, 'A', source=SOURCE)
    finally:
        conn.set_progress_handler(None, 0)
    assert [row['anchor'] for row in rows] == [anchor]
