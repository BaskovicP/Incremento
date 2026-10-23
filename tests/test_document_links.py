import sqlite3

import pytest

import db
from document_links import add_document_link, list_document_links, remove_document_link, replace_document_target


def test_precise_pdf_destinations_survive_loading_and_retargeting_from_either_end(tmp_path):
    from document_links import list_pdf_page_links, replace_pdf_page_link
    root = str(tmp_path)
    link = add_document_link(root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             source_y=.2, target_card_id=8, target_page=42, target_scroll=.6, target_y=.75)
    assert list_document_links(root, 'A', 7)[0]['target_y'] == .75
    assert list_pdf_page_links(root, 'A', 8, 42)[0]['target_y'] == .2
    assert replace_pdf_page_link(root, 'A', 7, 3, link, direction='outgoing',
                                 target_card_id=9, target_page=5, target_y=.4, target_scroll=.3)
    assert list_pdf_page_links(root, 'A', 9, 5)[0]['target_y'] == .2
    assert replace_pdf_page_link(root, 'A', 9, 5, link, direction='incoming',
                                 target_card_id=10, target_page=6, target_y=.8)
    assert list_pdf_page_links(root, 'A', 9, 5)[0]['target_y'] == .8
    assert list_pdf_page_links(root, 'A', 10, 6)[0]['target_y'] == .4


@pytest.mark.parametrize('point', [True, -0.1, 1.1, float('nan'), float('inf'), '0.5'])
def test_invalid_destination_points_do_not_create_links(tmp_path, point):
    root = str(tmp_path)
    with pytest.raises(ValueError):
        add_document_link(root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                          target_card_id=8, target_page=42, target_y=point)
    assert list_document_links(root, 'A', 7) == []


def test_precise_destination_migration_rolls_back_and_preserves_legacy_scroll_positions():
    from db_schema import initialize_schema
    conn = sqlite3.connect(':memory:')
    base = (2, 'links', db._migration_14_document_links)
    initialize_schema(conn, bootstrap=lambda c: None, migrations=(base,))
    conn.execute("INSERT INTO document_links(source_card_id,source_kind,source_page,target_card_id,target_page,target_scroll) "
                 "VALUES (7,'pdf',3,8,42,0.6)")
    conn.commit()
    def interrupted(c):
        db._migration_16_document_link_positions(c)
        raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):
        initialize_schema(conn, bootstrap=lambda c: None, migrations=(base, (3, 'positions', interrupted)))
    assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
    assert 'target_y' not in {row[1] for row in conn.execute('PRAGMA table_info(document_links)')}
    initialize_schema(conn, bootstrap=lambda c: None,
                      migrations=(base, (3, 'positions', db._migration_16_document_link_positions)))
    assert conn.execute('SELECT target_scroll,target_y,source_y FROM document_links').fetchall() == [(.6, None, None)]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute('UPDATE document_links SET target_y=2')


def test_pdf_page_connection_is_visible_at_both_ends_and_only_on_its_pages(tmp_path):
    from document_links import list_pdf_page_links
    root = str(tmp_path)
    link = add_document_link(root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42, target_scroll=.25)
    forward = list_pdf_page_links(root, 'A', 7, 3)
    reverse = list_pdf_page_links(root, 'A', 8, 42)
    assert [(r['id'], r['direction'], r['target_card_id'], r['target_page'], r['target_scroll'])
            for r in forward] == [(link, 'outgoing', 8, 42, .25)]
    assert [(r['id'], r['direction'], r['target_card_id'], r['target_page'], r['target_scroll'])
            for r in reverse] == [(link, 'incoming', 7, 3, 0)]
    assert list_pdf_page_links(root, 'A', 8, 41) == []
    assert list_pdf_page_links(root, 'B', 8, 42) == []
    remove_document_link(root, 'A', link, source_card_id=7)
    assert list_pdf_page_links(root, 'A', 8, 42) == []


def test_reverse_page_connection_follows_both_content_identities_without_reusing_old_cards(tmp_path):
    from document_links import list_pdf_page_links
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    for identity, cid in [('source', 7), ('target', 8)]:
        conn.execute('INSERT INTO content_items VALUES (?, \'pdf\', ?, ?, ?, 0, 0)',
                     (identity, cid, cid * 10, identity + '.pdf'))
    conn.commit()
    add_document_link(root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                      target_card_id=8, target_page=42)
    conn.execute('UPDATE content_items SET card_id=card_id+10')
    for identity, cid in [('other-source', 7), ('other-target', 8)]:
        conn.execute('INSERT INTO content_items VALUES (?, \'pdf\', ?, ?, ?, 0, 0)',
                     (identity, cid, cid * 10 + 1, identity + '.pdf'))
    conn.commit()
    assert list_pdf_page_links(root, 'A', 17, 3)[0]['target_card_id'] == 18
    assert list_pdf_page_links(root, 'A', 18, 42)[0]['target_card_id'] == 17
    assert list_pdf_page_links(root, 'A', 7, 3) == []
    assert list_pdf_page_links(root, 'A', 8, 42) == []


def test_web_and_whole_document_sources_do_not_create_false_pdf_return_pages(tmp_path):
    from document_links import list_pdf_page_links
    root = str(tmp_path)
    for kind, page in [('web', 3), ('card', 3), ('pdf', 0)]:
        add_document_link(root, 'A', source_card_id=7, source_kind=kind, source_page=page,
                          target_card_id=8, target_page=42)
    assert list_pdf_page_links(root, 'A', 8, 42) == []


def test_incoming_page_connections_are_bounded(tmp_path):
    from document_links import list_pdf_page_links
    root = str(tmp_path)
    for cid in range(1, 206):
        add_document_link(root, 'A', source_card_id=cid, source_kind='pdf', source_page=3,
                          target_card_id=900, target_page=42)
    assert len(list_pdf_page_links(root, 'A', 900, 42)) == 200


def test_connection_can_be_changed_or_removed_from_either_visible_endpoint(tmp_path):
    from document_links import list_pdf_page_links, replace_pdf_page_link, remove_pdf_page_link
    root = str(tmp_path)
    link = add_document_link(root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42)
    assert not replace_pdf_page_link(root, 'A', 8, 41, link, direction='incoming',
                                     target_card_id=9, target_page=5)
    assert replace_pdf_page_link(root, 'A', 8, 42, link, direction='incoming',
                                 target_card_id=9, target_page=5)
    assert list_pdf_page_links(root, 'A', 7, 3) == []
    assert list_pdf_page_links(root, 'A', 8, 42)[0]['target_card_id'] == 9
    assert list_pdf_page_links(root, 'A', 9, 5)[0]['target_card_id'] == 8
    assert not remove_pdf_page_link(root, 'B', 8, 42, link)
    assert not remove_pdf_page_link(root, 'A', 99, 42, link)
    assert remove_pdf_page_link(root, 'A', 8, 42, link)
    assert list_pdf_page_links(root, 'A', 9, 5) == []


def test_missing_source_can_be_removed_from_its_remaining_destination_page(tmp_path):
    from document_links import list_pdf_page_links, remove_pdf_page_link
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    conn.execute("INSERT INTO content_items VALUES ('source', 'pdf', 7, 70, 'source.pdf', 0, 0)")
    conn.commit()
    link = add_document_link(root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                             target_card_id=8, target_page=42)
    conn.execute("DELETE FROM content_items WHERE content_id='source'")
    conn.commit()
    assert list_pdf_page_links(root, 'A', 8, 42)[0]['target_card_id'] == 0
    assert remove_pdf_page_link(root, 'A', 8, 42, link)
    assert list_pdf_page_links(root, 'A', 8, 42) == []


@pytest.mark.parametrize('link_id', [True, 0, -1, '1', 2**63])
def test_invalid_page_link_identity_cannot_modify_an_existing_connection(tmp_path, link_id):
    from document_links import remove_pdf_page_link, replace_pdf_page_link
    root = str(tmp_path)
    add_document_link(root, 'A', source_card_id=7, source_kind='pdf', source_page=3,
                      target_card_id=8, target_page=42)
    with pytest.raises(ValueError):
        remove_pdf_page_link(root, 'A', 7, 3, link_id)
    with pytest.raises(ValueError):
        replace_pdf_page_link(root, 'A', 7, 3, link_id, direction='outgoing', target_card_id=9, target_page=5)
    assert list_document_links(root, 'A', 7)[0]['target_card_id'] == 8


def test_reverse_link_indexes_upgrade_atomically_and_keep_existing_connections(tmp_path):
    from db_schema import initialize_schema
    conn = sqlite3.connect(':memory:')
    initialize_schema(conn, bootstrap=lambda c: None,
                      migrations=((2, 'links', db._migration_14_document_links),))
    conn.execute("INSERT INTO document_links(source_card_id,source_kind,source_page,target_card_id,target_page) "
                 "VALUES (7,'pdf',3,8,42)")
    conn.commit()
    def interrupted(c):
        db._migration_15_document_link_targets(c)
        raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):
        initialize_schema(conn, bootstrap=lambda c: None, migrations=(
            (2, 'links', db._migration_14_document_links), (3, 'reverse', interrupted)))
    assert conn.execute('PRAGMA user_version').fetchone()[0] == 2
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='document_links_target'").fetchall() == []
    initialize_schema(conn, bootstrap=lambda c: None, migrations=(
        (2, 'links', db._migration_14_document_links), (3, 'reverse', db._migration_15_document_link_targets)))
    assert conn.execute('SELECT source_page,target_page FROM document_links').fetchall() == [(3, 42)]
    assert {'document_links_target', 'document_links_target_content'} <= {
        row[1] for row in conn.execute('PRAGMA index_list(document_links)')}


def test_links_preserve_page_positions_and_are_profile_scoped(tmp_path):
    root = str(tmp_path)
    link = add_document_link(root, "A", source_card_id=7, source_kind="pdf", source_page=3,
                             quote="A footnote", target_card_id=8, target_page=42, target_scroll=.25)
    rows = list_document_links(root, "A", 7, source_page=3)
    assert len(rows) == 1
    assert rows[0]["id"] == link
    assert (rows[0]["target_card_id"], rows[0]["target_page"], rows[0]["target_scroll"]) == (8, 42, .25)
    assert rows[0]["quote"] == "A footnote"
    assert list_document_links(root, "A", 7, source_page=4) == []
    assert list_document_links(root, "B", 7) == []
    assert not remove_document_link(root, "A", link, source_card_id=99)
    assert remove_document_link(root, "A", link, source_card_id=7)
    assert list_document_links(root, "A", 7) == []


def test_link_identity_follows_canonical_content_rebinding(tmp_path):
    root = str(tmp_path)
    conn = db.get_connection(root, "A")
    conn.execute("INSERT INTO content_items VALUES ('target', 'pdf', 8, 80, 'book.pdf', 0, 0)")
    conn.commit()
    add_document_link(root, "A", source_card_id=7, source_kind="web", target_card_id=8)
    conn.execute("UPDATE content_items SET card_id=9 WHERE content_id='target'")
    conn.commit()
    assert list_document_links(root, "A", 7)[0]["target_card_id"] == 9


def test_link_limit_still_applies_after_the_source_card_is_rebound(tmp_path):
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    conn.execute("INSERT INTO content_items VALUES ('source', 'pdf', 7, 70, 'source.pdf', 0, 0)")
    conn.commit()
    for page in range(1, 201):
        add_document_link(root, 'A', source_card_id=7, source_kind='pdf', target_card_id=8, target_page=page)
    conn.execute("UPDATE content_items SET card_id=9 WHERE content_id='source'")
    conn.commit()
    with pytest.raises(ValueError):
        add_document_link(root, 'A', source_card_id=9, source_kind='pdf', target_card_id=8)


def test_canonical_source_rebinding_cannot_expose_links_to_a_different_document(tmp_path):
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    conn.execute("INSERT INTO content_items VALUES ('source', 'pdf', 7, 70, 'source.pdf', 0, 0)")
    conn.commit()
    link = add_document_link(root, 'A', source_card_id=7, source_kind='pdf', target_card_id=8)
    conn.execute("UPDATE content_items SET card_id=9 WHERE content_id='source'")
    conn.execute("INSERT INTO content_items VALUES ('other', 'pdf', 7, 71, 'other.pdf', 0, 0)")
    conn.commit()
    assert list_document_links(root, 'A', 7) == []
    assert not remove_document_link(root, 'A', link, source_card_id=7)
    assert list_document_links(root, 'A', 9)[0]['id'] == link


def test_repair_link_keeps_source_and_rejects_other_source_owner(tmp_path):
    root = str(tmp_path)
    link = add_document_link(root, "A", source_card_id=7, source_kind="pdf", source_page=3,
                             quote="Footnote", target_card_id=8)
    assert not replace_document_target(root, "A", link, source_card_id=99, target_card_id=9, target_page=4)
    assert replace_document_target(root, "A", link, source_card_id=7, target_card_id=9, target_page=4)
    row = list_document_links(root, "A", 7)[0]
    assert (row["id"], row["source_page"], row["quote"], row["target_card_id"], row["target_page"]) == (link, 3, "Footnote", 9, 4)


@pytest.mark.parametrize("changes", [
    {"source_card_id": 0}, {"source_kind": "script"}, {"target_card_id": True},
    {"target_page": -1}, {"target_scroll": float("nan")}, {"quote": "x" * 2001},
])
def test_bad_links_do_not_write_rows(tmp_path, changes):
    values = dict(source_card_id=7, source_kind="pdf", target_card_id=8)
    with pytest.raises(ValueError):
        add_document_link(str(tmp_path), "A", **{**values, **changes})
    assert list_document_links(str(tmp_path), "A", 7) == []


def test_link_migration_rolls_back_with_its_ledger():
    from db_schema import initialize_schema
    conn = sqlite3.connect(":memory:")
    initialize_schema(conn, bootstrap=lambda c: None, migrations=())
    def failing(c):
        db._migration_14_document_links(c)
        raise RuntimeError("interrupted")
    with pytest.raises(RuntimeError):
        initialize_schema(conn, bootstrap=lambda c: None, migrations=((2, "links", failing),))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='document_links'").fetchall() == []
