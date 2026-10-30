"""Bookshelf counts are read-only, deduplicated, and scoped to the captured profile."""

import sqlite3
import threading
from concurrent.futures import CancelledError
from types import SimpleNamespace

import pytest


@pytest.fixture
def stats_boundary(monkeypatch):
    import document_library_stats as stats
    import media_review

    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE cards(id INTEGER PRIMARY KEY, reps INTEGER);
        INSERT INTO cards VALUES (1, 2), (2, 3), (10, 5), (11, 7), (12, 0);
        CREATE TABLE pdf_highlights(card_id INTEGER, id TEXT);
        CREATE TABLE epub_highlights(card_id INTEGER, id TEXT);
        INSERT INTO pdf_highlights VALUES (1, 'a'), (1, 'b'), (2, 'wrong-kind'), (999, 'orphan');
        INSERT INTO epub_highlights VALUES (2, 'a');
    """)
    reads, searches, profiles = [], [], []
    def rows(sql, *params):
        reads.append((sql, params))
        return conn.execute(sql, params).fetchall()
    def search(query):
        searches.append(query)
        ids = {int(value) for value in query.split()[0][4:].split(',')}
        return sorted(ids & {11, 12})
    col = SimpleNamespace(db=SimpleNamespace(all=rows), find_cards=search,
                          find_notes=lambda query: [],
                          get_card=lambda cid: SimpleNamespace(id=cid) if cid in {10, 11, 12} else None)
    monkeypatch.setattr(stats, "get_connection", lambda addon, profile: profiles.append((addon, profile)) or conn)
    monkeypatch.setattr(media_review, "get_knowledge_tree_nodes", lambda addon, profile: [
        {"card_id": 10, "parent_card_id": 1}, {"card_id": 11, "parent_card_id": 10},
        {"card_id": 12, "parent_card_id": 2}, {"card_id": 999, "parent_card_id": 2},
    ])
    monkeypatch.setattr(media_review, "get_pdf_document_source_rows", lambda *args: [])
    monkeypatch.setattr(media_review, "get_epub_document_source_rows", lambda *args: [])
    yield SimpleNamespace(stats=stats, col=col, conn=conn, reads=reads, searches=searches, profiles=profiles)
    conn.close()


def test_annotation_counts_use_only_the_selected_document_kind_and_profile(stats_boundary):
    b = stats_boundary
    result = b.stats.load_document_statistics("/synthetic", "Captured", [(1, "PDF"), (2, "EPUB"), (3, "PDF")],
                                             col=b.col, metric="annotations")
    assert result == {1: 2, 2: 1, 3: 0}
    assert b.profiles == [("/synthetic", "Captured")]
    assert b.searches == []
    assert b.conn.total_changes == 10


@pytest.mark.parametrize("metric,expected", [("due", {1: 1, 2: 1}), ("reviews", {1: 14, 2: 3})])
def test_library_counts_include_live_nested_cards_once_and_reviews_include_document(stats_boundary, metric, expected):
    b = stats_boundary
    result = b.stats.load_document_statistics("/synthetic", "Captured", [(1, "PDF"), (2, "EPUB")],
                                             col=b.col, metric=metric)
    assert result == expected
    assert b.profiles == []
    if metric == "due":
        assert all("is:due" in query and "-is:suspended" in query and "-is:buried" in query
                   for query in b.searches)
    else:
        assert len(b.reads) == 1
    assert b.conn.total_changes == 10


def test_cancelled_statistics_scan_does_not_query_storage_or_return_partial_counts(stats_boundary):
    b = stats_boundary
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(CancelledError):
        b.stats.load_document_statistics("/synthetic", "Captured", [(1, "PDF")], col=b.col,
                                         metric="annotations", cancelled=cancelled)
    assert b.profiles == b.reads == b.searches == []


def test_statistics_cancelled_during_attachment_scan_returns_no_partial_result(stats_boundary, monkeypatch):
    b = stats_boundary
    cancelled = threading.Event()
    def attached(*args, **kwargs):
        cancelled.set()
        return (10, 11)
    monkeypatch.setattr(b.stats, "linked_media_attachment_card_ids", attached)
    with pytest.raises(CancelledError):
        b.stats.load_document_statistics("/synthetic", "Captured", [(1, "PDF"), (2, "EPUB")],
                                         col=b.col, metric="reviews", cancelled=cancelled)
    assert b.reads == b.searches == []


def test_large_annotation_library_uses_bounded_batch_reads(stats_boundary):
    b = stats_boundary
    statements = []
    b.conn.set_trace_callback(statements.append)
    documents = [(cid, "PDF") for cid in range(1, 1204)] + [(2000, "EPUB")]
    result = b.stats.load_document_statistics("/synthetic", "Captured", documents,
                                             col=b.col, metric="annotations")
    assert len(result) == 1204
    assert result[1] == 2
    assert result[1203] == result[2000] == 0
    assert len(statements) == 3
    assert all(sql.count(',') <= 902 for sql in statements)


@pytest.mark.parametrize("metric", ["due", "reviews", "annotations"])
def test_empty_library_does_not_query_storage(stats_boundary, metric):
    b = stats_boundary
    assert b.stats.load_document_statistics("/synthetic", "Captured", [], col=b.col, metric=metric) == {}
    assert b.profiles == b.reads == b.searches == []
