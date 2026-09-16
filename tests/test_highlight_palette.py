"""Custom reader swatches are durable, ordered, and isolated by profile."""

import sqlite3

import db
import pytest


@pytest.fixture
def addon_dir(tmp_path):
    yield str(tmp_path)
    db.close_connection()


def test_custom_swatches_survive_connection_restart_in_their_original_slots(addon_dir):
    colors = ['#ffffff'] * 16
    colors[0], colors[7], colors[15] = '#123ABC', '#000000', '#aabbcc'

    assert db.get_reader_custom_colors(addon_dir, 'Profile A') is None
    db.set_reader_custom_colors(addon_dir, 'Profile A', colors)
    db.close_connection()

    assert db.get_reader_custom_colors(addon_dir, 'Profile A') == [c.lower() for c in colors]
    assert db.get_reader_custom_colors(addon_dir, 'Profile B') is None


@pytest.mark.parametrize('colors', [
    [], ['#ffffff'] * 15, ['#ffffff'] * 17,
    ['yellow'] * 16, ['#12345g'] * 16, [None] * 16,
    '#ffffff', None,
])
def test_invalid_palette_cannot_replace_saved_swatches(addon_dir, colors):
    original = ['#123abc'] * 16
    db.set_reader_custom_colors(addon_dir, 'Profile A', original)

    with pytest.raises(ValueError):
        db.set_reader_custom_colors(addon_dir, 'Profile A', colors)

    assert db.get_reader_custom_colors(addon_dir, 'Profile A') == original


def test_interrupted_palette_write_rolls_back_every_slot(addon_dir):
    original = ['#123abc'] * 16
    db.set_reader_custom_colors(addon_dir, 'Profile A', original)
    conn = db.get_connection(addon_dir, 'Profile A')
    conn.execute("""
        CREATE TRIGGER interrupt_palette BEFORE INSERT ON reader_custom_colors
        WHEN NEW.slot = 8 BEGIN SELECT RAISE(ABORT, 'interrupted palette'); END
    """)
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match='interrupted palette'):
        db.set_reader_custom_colors(addon_dir, 'Profile A', ['#abcdef'] * 16)

    assert not conn.in_transaction
    assert db.get_reader_custom_colors(addon_dir, 'Profile A') == original


@pytest.mark.parametrize(('slot', 'color'), [
    (-1, '#ffffff'), (16, '#ffffff'), (1.5, '#ffffff'),
    (0, 'yellow'), (0, '#12345g'), (0, '#12345678'),
])
def test_palette_schema_rejects_invalid_slot_or_color(addon_dir, slot, color):
    conn = db.get_connection(addon_dir, 'Profile A')
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute('INSERT INTO reader_custom_colors(slot, color) VALUES (?, ?)',
                         (slot, color))


def test_palette_migration_failure_rolls_back_table_ledger_and_version():
    from db_schema import initialize_schema

    conn = sqlite3.connect(':memory:')
    try:
        previous = tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= 9)
        initialize_schema(conn, bootstrap=db._create_tables, migrations=previous)

        def fail(connection):
            db._migration_10_reader_custom_colors(connection)
            raise RuntimeError('palette migration interrupted')

        with pytest.raises(RuntimeError, match='interrupted'):
            initialize_schema(conn, bootstrap=db._create_tables,
                              migrations=previous + ((10, 'reader_custom_colors', fail),))

        assert conn.execute('PRAGMA user_version').fetchone()[0] == 9
        assert conn.execute('SELECT max(version) FROM schema_migrations').fetchone()[0] == 9
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='reader_custom_colors'").fetchone() is None
    finally:
        conn.close()
