"""Non-linear coverage is durable document state, independent of daily activity."""
import sqlite3

import pytest

from backend import db
from backend.db_schema import initialize_schema
from backend import reader_coverage as coverage


def test_pdf_rereads_merge_across_sessions_without_filling_unvisited_pages(tmp_path):
    args = (str(tmp_path), 'A', 'pdf', 7, 'book.pdf')
    coverage.record_coverage(*args, position=0, start=0, end=10)
    coverage.record_coverage(*args, position=0, start=90, end=100)
    coverage.record_coverage(*args, position=0, start=0, end=10)
    db.close_connection(str(tmp_path), 'A')
    result = coverage.coverage_summary(*args, total=100)
    assert (result['viewed'], result['viewed_percent'], result['marked']) == (20, 20, 0)
    assert coverage.coverage_summary(str(tmp_path), 'B', 'pdf', 7, 'book.pdf', total=100)['viewed'] == 0
    assert coverage.coverage_summary(str(tmp_path), 'A', 'pdf', 7, 'replacement.pdf', total=100)['viewed'] == 0


def test_confirmed_ranges_union_with_legacy_prefix_and_can_be_corrected(tmp_path):
    args = (str(tmp_path), 'A', 'pdf', 7, 'book.pdf')
    coverage.record_coverage(*args, position=0, start=5, end=15, marked=True)
    coverage.record_coverage(*args, position=0, start=90, end=100, marked=True)
    result = coverage.coverage_summary(*args, total=100, legacy_read=10)
    assert result['marked'] == result['viewed'] == 25
    coverage.record_coverage(*args, position=0, start=92, end=98, marked=False, remove=True)
    assert coverage.coverage_summary(*args, total=100, legacy_read=10)['marked'] == 19


def test_epub_coverage_uses_text_offsets_and_never_counts_a_whole_chapter_from_a_visit(tmp_path):
    args = (str(tmp_path), 'A', 'epub', 8, 'book.epub')
    coverage.record_coverage(*args, position=0, start=0, end=1500)
    coverage.record_coverage(*args, position=1, start=3000, end=4500, marked=True)
    result = coverage.coverage_summary(*args, lengths=(3000, 6000))
    assert (result['total'], result['viewed'], result['marked']) == (6, 2, 1)
    assert result['viewed_percent'] == pytest.approx(100 / 3)
    assert coverage.coverage_summary(*args, lengths=(3000, 6000)) == result
    assert coverage.coverage_summary(*args, lengths=(1500,)*5001)['viewed_percent'] is None


def test_unmarking_a_legacy_prefix_page_does_not_unread_the_rest_or_erase_views(tmp_path):
    args = (str(tmp_path), 'A', 'pdf', 7, 'book.pdf')
    coverage.record_coverage(*args, position=0, start=4, end=5, remove=True)
    result = coverage.coverage_summary(*args, total=100, legacy_read=10)
    assert (result['viewed'], result['marked']) == (10, 9)
    coverage.record_coverage(*args, position=0, start=4, end=5, marked=True)
    assert coverage.coverage_summary(*args, total=100, legacy_read=10)['marked'] == 10


def test_coverage_follows_canonical_rebinding_and_survives_statistics_reset(tmp_path):
    root = str(tmp_path)
    conn = db.get_connection(root, 'A')
    conn.execute("INSERT INTO content_items VALUES('book','pdf',7,70,'book.pdf',0,0)")
    conn.commit()
    coverage.record_coverage(root, 'A', 'pdf', 7, 'book.pdf', position=0, start=90, end=100, marked=True)
    conn.execute("UPDATE content_items SET card_id=9 WHERE content_id='book'")
    conn.commit()
    from backend.statistics import delete_all_stats
    delete_all_stats(root, 'A')
    assert coverage.coverage_summary(root, 'A', 'pdf', 9, 'book.pdf', total=100)['marked'] == 10
    assert coverage.coverage_summary(root, 'A', 'pdf', 7, 'book.pdf', total=100)['marked'] == 0


def test_concurrent_page_observations_never_overwrite_each_other(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    root = str(tmp_path)
    def record(page):
        try:
            coverage.record_coverage(root, 'A', 'pdf', 7, 'book.pdf', position=0, start=page, end=page+1)
        finally:
            db.close_current_connection(root, 'A')
    # Initialize the schema before deliberately racing the range transactions.
    db.get_connection(root, 'A')
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(record, range(20)))
    assert coverage.coverage_summary(root, 'A', 'pdf', 7, 'book.pdf', total=100)['viewed'] == 20


@pytest.mark.parametrize('change', [dict(kind='video'), dict(card_id=True), dict(filename='../book.pdf'),
    dict(start=-1), dict(end=float('nan')), dict(end=0), dict(position=True), dict(marked='yes')])
def test_invalid_coverage_cannot_write(tmp_path, change):
    values = dict(kind='pdf', card_id=7, filename='book.pdf', position=0, start=0, end=1)
    values.update(change)
    with pytest.raises(ValueError):
        coverage.record_coverage(str(tmp_path), 'A', **values)
    assert coverage.coverage_summary(str(tmp_path), 'A', 'pdf', 7, 'book.pdf', total=100)['viewed'] == 0


def test_new_reader_schema_rolls_back_every_change_with_its_ledger():
    conn = sqlite3.connect(':memory:')
    previous = db._SCHEMA_MIGRATIONS[:-1]
    initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)
    version = conn.execute('PRAGMA user_version').fetchone()[0]
    migration = db._SCHEMA_MIGRATIONS[-1]
    def interrupted(c):
        migration[2](c)
        raise RuntimeError('interrupted')
    with pytest.raises(RuntimeError):
        initialize_schema(conn, bootstrap=db._create_tables,
                          migrations=(*previous, (migration[0], migration[1], interrupted)))
    assert conn.execute('PRAGMA user_version').fetchone()[0] == version
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='document_coverage'").fetchall() == []
    assert 'source_passage' not in {r[1] for r in conn.execute('PRAGMA table_info(document_links)')}
    initialize_schema(conn, bootstrap=db._create_tables, migrations=db._SCHEMA_MIGRATIONS)
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='document_coverage'").fetchall()
    conn.close()
