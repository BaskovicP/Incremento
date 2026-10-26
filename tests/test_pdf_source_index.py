from types import SimpleNamespace
import sqlite3
from pdf_source_index import PdfSourceIndex
from pdf_manager import PDF_COVER_FIELD


def test_reviewer_cover_reuses_both_sides_and_discards_profile_switch(monkeypatch):
    import ast
    from pathlib import Path
    import sys

    queued, shown, reads = [], [], []

    class Query:
        def __init__(self, *, parent, op, success):
            self.op, self.success = op, success

        def failure(self, callback):
            return self

        def run_in_background(self):
            queued.append(self)

    monkeypatch.setitem(sys.modules, "aqt.operations", SimpleNamespace(QueryOp=Query))
    tree = ast.parse((Path(__file__).resolve().parents[1] / "__init__.py").read_text())
    nodes = [
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
        and n.name in {"_sync_reviewer_source_cover", "_invalidate_reviewer_source_cover"}
    ]
    for node in nodes:
        for item in ast.walk(node):
            if isinstance(item, ast.ImportFrom) and item.level:
                item.module, item.level = item.module.rsplit(".", 1)[-1], 0
    profile = ["A"]
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(id=cid))
    mw = SimpleNamespace(col=col, reviewer=SimpleNamespace(card=SimpleNamespace(id=7), web=object()))

    def payload(card, **kwargs):
        reads.append(card.id)
        assert kwargs["col"] is col
        return {"title": str(card.id)}

    ns = dict(
        mw=mw,
        _active_profile=lambda: profile[0],
        _render_reviewer_source_cover=shown.append,
        _reviewer_pdf_source_cover_payload=payload,
        _source_cover_generation=0,
        _source_cover_index=None,
        _source_cover_index_key=None,
        _source_cover_payload_key=None,
        _source_cover_payload=None,
        _source_cover_queries=None,
    )
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<source-cover>", "exec"), ns)
    ns["_sync_reviewer_source_cover"]()
    assert reads == [] and len(queued) == 1
    queued[0].success(queued[0].op(col))
    ns["_sync_reviewer_source_cover"]()
    assert reads == [7] and shown[-2:] == [{"title": "7"}, {"title": "7"}]
    mw.reviewer.card = SimpleNamespace(id=8)
    ns["_sync_reviewer_source_cover"]()
    old = queued[-1].op(col)
    profile[0] = "B"
    queued[-1].success(old)
    assert shown[-1] is None
    assert ns["_source_cover_payload_key"][2] == 7


def test_source_lookup_batches_notes_and_preserves_exact_and_unique_fuzzy_matches():
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE cards(id INTEGER,nid INTEGER); CREATE TABLE notes(id INTEGER,mid INTEGER,flds TEXT);"
    )
    filenames = ["paper-" + "a" * 32 + ".pdf", "paper-" + "b" * 32 + ".pdf", "unique-" + "c" * 32 + ".pdf"]
    for i, filename in enumerate(filenames, 1):
        conn.execute("INSERT INTO notes VALUES(?,?,?)", (i, 10, f"Title {i}\x1f{filename}\x1fcover-{i}.png"))
        conn.execute("INSERT INTO cards VALUES(?,?)", (i, i))
    calls = []

    def all_rows(query, *args):
        calls.append(query)
        return conn.execute(query, args).fetchall()

    col = SimpleNamespace(
        find_cards=lambda query: [1, 2, 3],
        db=SimpleNamespace(all=all_rows),
        models=SimpleNamespace(
            get=lambda mid: {"flds": [{"name": name} for name in ("Title", "PDF_Filename", PDF_COVER_FIELD)]}
        ),
        get_note=lambda *_: (_ for _ in ()).throw(AssertionError("per-note lookup")),
    )
    index = PdfSourceIndex.build(col)
    assert index.get(filenames[1]) == (2, "Title 2", "cover-2.png")
    assert index.get("paper.pdf") is None
    assert index.get("unique.pdf")[0] == 3
    assert index.get("missing.pdf") is None
    for _ in range(1000):
        index.get(filenames[0])
    assert len(calls) == 1
