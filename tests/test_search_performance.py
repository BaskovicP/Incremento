import db
from threading import Event
from concurrent.futures import CancelledError
import pytest


def test_compiled_search_keeps_phrase_prefix_unicode_and_repeated_term_semantics():
    texts = ["alpha beta", "alpha something beta", "beta alpha", "alphabet betamax", "Straße café", "alpha alpha"]
    for query in ["alpha beta", "strass caf", "alpha alpha", "missing"]:
        expected = [db.search_text_match_score(text, query) for text in texts]
        compiled = db.CompiledSearch(query)
        assert [db.search_text_match_score(text, compiled) for text in texts] == expected
        assert compiled.terms == tuple(db.split_search_terms(query))


def test_search_streams_candidates_and_retains_only_requested_ranking(tmp_path, monkeypatch):
    addon = str(tmp_path)
    db.replace_pdf_text_index(addon, "A", 1, [f"alpha beta word {i}" for i in range(1000)])
    conn = db.get_connection(addon, "A")
    class Cursor:
        def __init__(self, cursor): self.cursor = cursor
        def fetchone(self): return self.cursor.fetchone()
        def fetchall(self): raise AssertionError("eager candidate materialization")
        def fetchmany(self, amount):
            assert amount <= 128
            return self.cursor.fetchmany(amount)
    class Connection:
        def execute(self, *args): return Cursor(conn.execute(*args))
        def set_progress_handler(self, *args): return conn.set_progress_handler(*args)
    monkeypatch.setattr(db, "get_connection", lambda *args: Connection())
    result = db.search_pdf_text_index(addon, "A", "alpha beta", limit=10)
    assert len(result) == 10
    cancel = Event()
    query = db.CompiledSearch("alpha", cancel=cancel)
    cancel.set()
    with pytest.raises(CancelledError):
        db.search_pdf_text_index(addon, "A", query)


def test_bounded_ranking_matches_stable_sort_with_ties_and_repeated_terms():
    values = [(i % 5, i % 3, i) for i in reversed(range(300))]
    ranking = db._BoundedSearchRanking(17, key=lambda value: value[:2])
    for value in values:
        ranking.append(value)
    assert ranking[:] == sorted(values, key=lambda value: value[:2])[:17]


def test_ranking_honors_an_explicit_large_result_limit():
    ranking = db._BoundedSearchRanking(30001, key=lambda value: value)
    for value in range(30002):
        ranking.append(value)
    assert ranking[:] == list(range(30001))


def test_scoring_does_not_normalize_whitespace_twice(monkeypatch):
    # Regex word extraction already ignores whitespace; avoid allocating a
    # second page-sized normalized string during each candidate score.
    query = db.CompiledSearch("ALPH bet")
    original = db.normalize_search_text
    def normalize(text):
        assert len(text) < 100, "candidate text normalized a second time"
        return original(text)
    monkeypatch.setattr(db, "normalize_search_text", normalize)
    assert query.score("alpha\t\nbeta " + "tail "*1000) == (0, 1, 0, 1002)
