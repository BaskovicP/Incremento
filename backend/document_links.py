"""Bounded per-profile associations; Anki remains the owner of document cards."""
import math

try:
    from .db import get_connection
except ImportError:
    from db import get_connection


_SOURCE_MATCH = '(source_content_id=? OR (source_content_id IS NULL AND source_card_id=?))'


def _validate_position(scroll, point):
    if (type(scroll) not in (int, float) or not math.isfinite(scroll) or not 0 <= scroll <= 1
            or (point is not None and (type(point) not in (int, float)
                or not math.isfinite(point) or not 0 <= point <= 1))):
        raise ValueError('Invalid document position')


def _identity(conn, card_id):
    row = conn.execute("SELECT content_id FROM content_items WHERE card_id=? LIMIT 1", (card_id,)).fetchone()
    return row[0] if row else None


def add_document_link(addon_dir, profile, *, source_card_id, source_kind, target_card_id,
                      source_page=0, quote="", target_page=1, target_scroll=0, source_y=None, target_y=None):
    _validate_position(target_scroll, target_y)
    _validate_position(0, source_y)
    for number, minimum in ((source_card_id, 1), (target_card_id, 1), (source_page, 0), (target_page, 1)):
        if type(number) is not int or not minimum <= number <= 2**63 - 1:
            raise ValueError("Invalid document location")
    if (source_kind not in ("pdf", "web", "card") or not isinstance(quote, str)
            or len(quote) > 2000 or "\x00" in quote
            or type(target_scroll) not in (int, float) or not math.isfinite(target_scroll)
            or not 0 <= target_scroll <= 1):
        raise ValueError("Invalid document link")
    conn = get_connection(addon_dir, profile)
    with conn:
        source_identity = _identity(conn, source_card_id)
        count = conn.execute('SELECT count(*) FROM document_links WHERE ' + _SOURCE_MATCH,
                             (source_identity, source_card_id)).fetchone()[0]
        if count >= 200:
            raise ValueError("Document link limit reached")
        cursor = conn.execute(
            "INSERT INTO document_links(source_card_id, source_content_id, source_kind, source_page, quote, "
            "target_card_id, target_content_id, target_page, target_scroll, source_y, target_y) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (source_card_id, source_identity, source_kind, source_page, quote,
             target_card_id, _identity(conn, target_card_id), target_page, target_scroll, source_y, target_y))
    return cursor.lastrowid


def list_document_links(addon_dir, profile, source_card_id, *, source_page=None):
    conn = get_connection(addon_dir, profile)
    identity = _identity(conn, source_card_id)
    params = [identity, source_card_id]
    where = _SOURCE_MATCH
    if source_page is not None:
        where += " AND l.source_page=?"
        params.append(source_page)
    rows = conn.execute(
        "SELECT l.id, l.source_kind, l.source_page, l.quote, "
        "CASE WHEN l.target_content_id IS NULL THEN l.target_card_id ELSE coalesce(c.card_id,0) END, "
        "l.target_page, l.target_scroll, l.target_y FROM document_links l LEFT JOIN content_items c "
        "ON c.content_id=l.target_content_id WHERE " + where + " ORDER BY l.id LIMIT 200", params).fetchall()
    keys = ("id", "source_kind", "source_page", "quote", "target_card_id", "target_page", "target_scroll", "target_y")
    return [dict(zip(keys, row)) for row in rows]


def list_pdf_page_links(addon_dir, profile, card_id, page):
    """Show a saved PDF page connection at either end without duplicating it.

    Each indexed endpoint lookup is bounded before combining the results. A
    canonical identity supersedes its old card id in both directions.
    """
    if (type(card_id) is not int or not 1 <= card_id <= 2**63 - 1
            or type(page) is not int or not 1 <= page <= 1_000_000):
        raise ValueError('Invalid PDF page')
    conn = get_connection(addon_dir, profile)
    identity = _identity(conn, card_id)
    keys = ('id', 'direction', 'target_card_id', 'target_page', 'target_scroll', 'quote', 'target_y')
    rows = []
    for side, opposite, direction, scroll in (
        ('source', 'target', 'outgoing', 'l.target_scroll'),
        ('target', 'source', 'incoming', '0'),
    ):
        matches = [(f'l.{side}_content_id IS NULL AND l.{side}_card_id=?', card_id)]
        if identity is not None:
            matches.append((f'l.{side}_content_id=?', identity))
        # Separate indexed branches avoid sorting every incoming connection
        # before LIMIT when a popular document has many references.
        for predicate, value in matches:
            results = conn.execute(
                f"SELECT l.id, '{direction}', CASE WHEN l.{opposite}_content_id IS NULL "
                f"THEN l.{opposite}_card_id ELSE coalesce(c.card_id,0) END, "
                f"l.{opposite}_page, {scroll}, l.quote, l.{opposite}_y FROM document_links l "
                f"LEFT JOIN content_items c ON c.content_id=l.{opposite}_content_id "
                f"WHERE {predicate} AND l.{side}_page=? AND l.source_kind='pdf' AND l.source_page>0 "
                "ORDER BY l.id LIMIT 200", (value, page)).fetchall()
            rows.extend(dict(zip(keys, row)) for row in results)
    # A link from a page to itself needs only one visible button.
    seen = set()
    connections = []
    for row in sorted(rows, key=lambda row: (row['id'], row['direction'])):
        if row['id'] not in seen:
            seen.add(row['id'])
            connections.append(row)
    return connections[:200]


def remove_document_link(addon_dir, profile, link_id, *, source_card_id):
    conn = get_connection(addon_dir, profile)
    with conn:
        cursor = conn.execute(
            'DELETE FROM document_links WHERE id=? AND ' + _SOURCE_MATCH,
            (link_id, _identity(conn, source_card_id), source_card_id))
    return cursor.rowcount > 0


def _pdf_endpoint(conn, card_id, page, side):
    if (type(card_id) is not int or not 1 <= card_id <= 2**63 - 1
            or type(page) is not int or not 1 <= page <= 1_000_000):
        raise ValueError('Invalid PDF page')
    return (f"((l.{side}_content_id=? OR (l.{side}_content_id IS NULL AND l.{side}_card_id=?)) "
            f"AND l.{side}_page=?)", (_identity(conn, card_id), card_id, page))


def remove_pdf_page_link(addon_dir, profile, card_id, page, link_id):
    """Either endpoint can remove the one shared page connection."""
    if type(link_id) is not int or not 1 <= link_id <= 2**63 - 1:
        raise ValueError('Invalid connection')
    conn = get_connection(addon_dir, profile)
    source, source_params = _pdf_endpoint(conn, card_id, page, 'source')
    target, target_params = _pdf_endpoint(conn, card_id, page, 'target')
    with conn:
        cursor = conn.execute(
            "DELETE FROM document_links AS l WHERE id=? AND source_kind='pdf' AND source_page>0 "
            f"AND ({source} OR {target})", (link_id, *source_params, *target_params))
    return cursor.rowcount > 0


def replace_pdf_page_link(addon_dir, profile, card_id, page, link_id, *, direction, target_card_id, target_page,
                         target_scroll=0, target_y=None):
    """Change the opposite endpoint, keeping the page the user is managing fixed."""
    _validate_position(target_scroll, target_y)
    if (type(link_id) is not int or not 1 <= link_id <= 2**63 - 1
            or direction not in ('outgoing', 'incoming') or type(target_card_id) is not int
            or not 1 <= target_card_id <= 2**63 - 1 or type(target_page) is not int
            or not 1 <= target_page <= 1_000_000):
        raise ValueError('Invalid PDF target')
    conn = get_connection(addon_dir, profile)
    fixed, other = ('source', 'target') if direction == 'outgoing' else ('target', 'source')
    endpoint, params = _pdf_endpoint(conn, card_id, page, fixed)
    reset_scroll = ', target_scroll=?' if other == 'target' else ''
    scroll_params = (target_scroll,) if other == 'target' else ()
    with conn:
        cursor = conn.execute(
            f"UPDATE document_links AS l SET {other}_card_id=?, {other}_content_id=?, {other}_page=?, {other}_y=?{reset_scroll} "
            f"WHERE id=? AND source_kind='pdf' AND source_page>0 AND {endpoint}",
            (target_card_id, _identity(conn, target_card_id), target_page, target_y, *scroll_params, link_id, *params))
    return cursor.rowcount > 0


def replace_document_target(addon_dir, profile, link_id, *, source_card_id, target_card_id, target_page,
                            target_scroll=0, target_y=None):
    _validate_position(target_scroll, target_y)
    if type(target_card_id) is not int or target_card_id <= 0 or type(target_page) is not int or not 1 <= target_page <= 1_000_000:
        raise ValueError("Invalid document target")
    conn = get_connection(addon_dir, profile)
    with conn:
        cursor = conn.execute(
            "UPDATE document_links SET target_card_id=?, target_content_id=?, target_page=?, target_scroll=?, target_y=? "
            'WHERE id=? AND ' + _SOURCE_MATCH,
            (target_card_id, _identity(conn, target_card_id), target_page, target_scroll, target_y, link_id,
             _identity(conn, source_card_id), source_card_id))
    return cursor.rowcount > 0
