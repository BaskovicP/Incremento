"""Stable, bidirectional EPUB passages must survive reflow and stay profile scoped."""
import sqlite3
import pytest
import db
import epub_highlights


def point(card, section=0, offset=0, scroll=0.25):
    return {'card_id': card, 'section': section, 'offset': offset, 'scroll': scroll}


def test_connections_return_exact_opposite_passage_and_remove_from_either_end(tmp_path):
    import epub_connections as links
    root = str(tmp_path)
    source, target = point(7, 0, 42), point(8, 3, 205, 0.8)
    link_id = links.add_connection(root, 'A', source, target, quote='A passage')
    assert links.list_connections(root, 'A', 7, 0) == [
        {'id': link_id, 'direction': 'outgoing', 'target': target, 'quote': 'A passage'}]
    assert links.list_connections(root, 'A', 8, 3) == [
        {'id': link_id, 'direction': 'incoming', 'target': source, 'quote': 'A passage'}]
    assert links.list_connections(root, 'B', 7, 0) == []
    assert links.list_connections(root, 'A', 7, 1) == []
    assert not links.remove_connection(root, 'A', 99, 0, link_id)
    assert links.remove_connection(root, 'A', 8, 3, link_id)
    assert links.list_connections(root, 'A', 7, 0) == []


@pytest.mark.parametrize('key,value', [('card_id', True), ('section', -1), ('offset', 50_000_001),
                                      ('scroll', float('nan')), ('scroll', 1.01)])
def test_invalid_passages_never_write(tmp_path, key, value):
    import epub_connections as links
    source = point(7)
    source[key] = value
    with pytest.raises(ValueError):
        links.add_connection(str(tmp_path), 'A', source, point(8))
    assert links.list_connections(str(tmp_path), 'A', 7, 0) == []


def test_duplicate_connection_is_idempotent_and_highlight_color_preserves_other_fields(tmp_path):
    import epub_connections as links
    root = str(tmp_path)
    first = links.add_connection(root, 'A', point(7), point(8))
    assert links.add_connection(root, 'A', point(7), point(8)) == first
    highlight = dict(id='h', sectionIndex=0, startOffset=4, endOffset=20,
                     text='quoted words', note='my note', color='yellow')
    epub_highlights.add_highlight(root, 'A', 7, highlight)
    assert epub_highlights.update_highlight_color(root, 'A', 7, 'h', '#12AB34')
    assert epub_highlights.load_highlights(root, 'A', 7) == [highlight | {'color': '#12ab34'}]
    assert not epub_highlights.update_highlight_color(root, 'A', 8, 'h', 'blue')
    assert links.list_connections(root, 'A', 7, 0)[0]['id'] == first


def test_connection_migration_rolls_back_with_ledger():
    with sqlite3.connect(':memory:') as conn:
        previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 17)
        db.initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)
        def fail(connection):
            db._migration_18_epub_connections(connection)
            raise RuntimeError('interrupted')
        with pytest.raises(RuntimeError, match='interrupted'):
            db.initialize_schema(conn, bootstrap=db._create_tables,
                                 migrations=previous + ((18, 'epub_connections', fail),))
        assert conn.execute('PRAGMA user_version').fetchone() == (17,)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='epub_connections'").fetchall() == []
        assert conn.execute('SELECT max(version) FROM schema_migrations').fetchone() == (17,)
        assert 'appearance_mode' not in [row[1] for row in conn.execute('PRAGMA table_info(epub_progress)')]


def test_epub_appearance_is_per_card_profile_and_does_not_reset_position(tmp_path):
    import epub_appearance
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    conn.execute('INSERT INTO epub_progress(card_id,section_index,scroll_ratio) VALUES(7,3,.7)')
    conn.commit()
    assert epub_appearance.get_appearance(root, 'A', 7) == 'original'
    epub_appearance.set_appearance(root, 'A', 7, 'night')
    assert epub_appearance.get_appearance(root, 'A', 7) == 'night'
    assert epub_appearance.get_appearance(root, 'B', 7) == 'original'
    assert epub_appearance.get_appearance(root, 'A', 8) == 'original'
    conn = db.get_connection(root, 'A')
    assert conn.execute('SELECT section_index,scroll_ratio FROM epub_progress WHERE card_id=7').fetchone() == (3,.7)
    with pytest.raises(ValueError):
        epub_appearance.set_appearance(root, 'A', 7, 'url(https://example.com)')


def test_connections_follow_canonical_identity_after_card_rebinding(tmp_path):
    import epub_connections as links
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    conn.execute("INSERT INTO content_items VALUES ('source', 'epub', 7, 70, 'a.epub', 0, 0)")
    conn.execute("INSERT INTO content_items VALUES ('target', 'epub', 8, 80, 'b.epub', 0, 0)")
    conn.commit()
    link_id = links.add_connection(root, 'A', point(7, 2, 45), point(8, 4, 200))
    conn.execute("UPDATE content_items SET card_id=17 WHERE content_id='source'")
    conn.execute("UPDATE content_items SET card_id=18 WHERE content_id='target'")
    conn.commit()
    assert links.list_connections(root, 'A', 7, 2) == []
    assert links.list_connections(root, 'A', 17, 2)[0]['target'] == point(18, 4, 200)
    assert links.list_connections(root, 'A', 18, 4)[0]['target'] == point(17, 2, 45)
    assert links.remove_connection(root, 'A', 18, 4, link_id)


def test_epub_connections_cap_each_endpoint_without_losing_existing_links(tmp_path):
    import epub_connections as links
    root = str(tmp_path)
    for index in range(200):
        links.add_connection(root, 'A', point(7, 0, index), point(index + 20))
    with pytest.raises(ValueError, match='limit'):
        links.add_connection(root, 'A', point(7, 0, 201), point(999))
    with pytest.raises(ValueError, match='limit'):
        links.add_connection(root, 'A', point(999), point(7, 0, 201))
    assert len(links.list_connections(root, 'A', 7, 0)) == 200
