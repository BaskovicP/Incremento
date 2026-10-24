"""Per-document EPUB appearance, independent of navigation and read progress."""
try:
    from .db import get_connection
except ImportError:
    from db import get_connection

MODES = ('original', 'dark', 'night')


def get_appearance(addon_dir, profile, card_id):
    row = get_connection(addon_dir, profile).execute(
        'SELECT appearance_mode FROM epub_progress WHERE card_id=?', (card_id,)).fetchone()
    return row[0] if row and row[0] in MODES else 'original'


def set_appearance(addon_dir, profile, card_id, mode):
    if mode not in MODES or type(card_id) is not int or card_id <= 0:
        raise ValueError('Invalid EPUB appearance')
    conn = get_connection(addon_dir, profile)
    with conn:
        conn.execute('INSERT INTO epub_progress(card_id,appearance_mode) VALUES(?,?) '
                     'ON CONFLICT(card_id) DO UPDATE SET appearance_mode=excluded.appearance_mode',
                     (card_id, mode))
