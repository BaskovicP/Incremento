"""Reproducible component benchmarks; synthetic data only, never live profiles.

Uses baseline definitions from Git and current definitions against identical
temporary SQLite/synthetic collection boundaries. Timings are not end-to-end
Anki latency. Native UI/import measurements are in completion_native_benchmarks.py.
"""

from __future__ import annotations

import argparse
import ast
from array import array
import hashlib
import importlib
import json
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
import types
import threading
from collections import defaultdict, deque

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "6a371c732fc6c7d65bb4468fdb5853a2926ec097"
sys.path.insert(0, str(ROOT))
package = types.ModuleType("incremento_bench")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
db = importlib.import_module("incremento_bench.backend.db")


def source(path, stage):
    return (
        subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, text=True)
        if stage == "before"
        else (ROOT / path).read_text()
    )


def definitions(path, stage, names, namespace, *, cls=None):
    tree = ast.parse(source(path, stage))
    body = (
        tree.body if cls is None else next(n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    )
    nodes = [node for node in body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(
        compile(
            ast.Module(body=nodes, type_ignores=[]),
            path,
            "exec",
            flags=__import__("__future__").annotations.compiler_flag,
        ),
        namespace,
    )


def samples(operation, repeats=3):
    values = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        values.append(round((time.perf_counter() - started) * 1000, 3))
    return {"median_ms": statistics.median(values), "samples_ms": values}


def peak(operation):
    tracemalloc.start()
    try:
        operation()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def source_covers():
    manager = importlib.import_module("incremento_bench.backend.pdf_manager")
    model = importlib.import_module("incremento_bench.backend.pdf_source_index")
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        "CREATE TABLE cards(id INTEGER,nid INTEGER); CREATE TABLE notes(id INTEGER,mid INTEGER,flds TEXT)"
    )
    count, calls = 4000, defaultdict(int)
    filenames = [f"document-{i}.pdf" for i in range(count)]
    notes = {}
    for i, name in enumerate(filenames, 1):
        notes[i] = {"PDF_Filename": name}
        connection.execute("INSERT INTO notes VALUES (?,?,?)", (i, 10, f"Document {i}\x1f{name}\x1fcover.png"))
        connection.execute("INSERT INTO cards VALUES (?,?)", (i, i))

    def note(nid):
        calls["note_loads"] += 1
        return notes[nid]

    def cards(query):
        calls["card_searches"] += 1
        return [int(query[4:])] if query.startswith("nid:") else list(range(1, count + 1))

    def all_rows(query, *args):
        calls["metadata_batches"] += 1
        return connection.execute(query, args).fetchall()

    col = types.SimpleNamespace(
        find_notes=lambda query: range(1, count + 1),
        get_note=note,
        find_cards=cards,
        db=types.SimpleNamespace(all=all_rows),
        models=types.SimpleNamespace(
            get=lambda mid: {"flds": [{"name": name} for name in ("Title", "PDF_Filename", manager.PDF_COVER_FIELD)]}
        ),
    )

    def old():
        for _ in range(20):
            assert manager.find_live_pdf_card_by_filename(col, filenames[-1]) == count

    before = samples(old)
    calls.clear()
    old()
    before["operations"] = dict(calls)
    calls.clear()
    cold = samples(lambda: model.PdfSourceIndex.build(col))
    index = model.PdfSourceIndex.build(col)

    def new():
        for _ in range(20):
            assert index.get(filenames[-1])[0] == count

    after = samples(new)
    calls.clear()
    new()
    after["operations"] = dict(calls)
    connection.close()
    return {
        "pdf_notes": count,
        "lookups": 20,
        "before": before,
        "after_warm": after,
        "after_cold_index": cold,
        "boundary": "real SQLite batches; synthetic note API, no Anki RPC timing",
    }


def session_counts():
    cards = importlib.import_module("incremento_bench.backend.cards")
    topic = importlib.import_module("incremento_bench.backend.topic_scheduler")
    module = importlib.import_module("incremento_bench.frontend.learn_dialog")
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE cards(id INTEGER,nid INTEGER,did INTEGER,odid INTEGER,due INTEGER);"
        "CREATE TABLE notes(id INTEGER,mid INTEGER,tags TEXT)"
    )
    size = 10000
    tags = [f"tag{i}" for i in range(20)]
    conn.executemany("INSERT INTO cards VALUES (?,?,1,0,?)", [(i, i, i) for i in range(1, size + 1)])
    conn.executemany(
        "INSERT INTO notes VALUES (?,1,?)",
        [(i, " ".join(tags) + (" topic" if i % 2 else "")) for i in range(1, size + 1)],
    )
    calls = defaultdict(int)

    def all_rows(query, *args):
        calls["sql_queries"] += 1
        return conn.execute(query, args).fetchall()

    def find(query):
        calls["card_searches"] += 1
        return list(range(1, size + 1))

    collection_type = type("Collection", (), {"__module__": "anki.collection"})
    col = collection_type()
    col.db = types.SimpleNamespace(all=all_rows)
    col.find_cards = find
    col.models = types.SimpleNamespace(get=lambda _: {"name": "Basic"})
    col.decks = types.SimpleNamespace(get=lambda _: {"name": "Default"})
    classifier = topic.TopicCardClassifier(frozenset(), frozenset({"topic"}), frozenset(), "Topics")

    def resolve():
        calls["classifier_resolutions"] += 1
        return classifier

    saved_mw, saved_resolve = cards.mw, cards.resolve_topic_card_classifier
    cards.mw, cards.resolve_topic_card_classifier = types.SimpleNamespace(col=col), resolve
    try:
        label = types.SimpleNamespace(setText=lambda value: None)
        ns = dict(vars(module), _card_utils=cards, t=lambda *args, **kwargs: "")
        definitions(
            "frontend/learn_dialog.py",
            "before",
            {"_refresh_counts", "_refresh_tag_count"},
            ns,
            cls="SchedulerConfigDialog",
        )
        dialog = types.SimpleNamespace(
            _ready_filter_from_checks=lambda: "",
            _apply_branch_scope_query=lambda value: value,
            _topics_filter_edit=types.SimpleNamespace(text=lambda: ""),
            _items_filter_edit=types.SimpleNamespace(text=lambda: ""),
            _branch_scope=None,
            _counts_lbl=label,
            _linked_rows=[{"tag": tag, "name_label": label} for tag in tags],
        )
        dialog._refresh_tag_count = lambda row: ns["_refresh_tag_count"](dialog, row)

        def before():
            ns["_refresh_counts"](dialog)

        def after():
            output = module._session_count_snapshot(
                col,
                topics_filter="",
                items_filter="",
                ready="",
                tags=tags,
                content_queries={},
                classifier=resolve(),
                cancel=threading.Event(),
            )
            assert output["topics"] == 5000 and output["items"] == 5000
            assert all(value == (5000, 5000) for value in output["tags"].values())

        result = {
            "cards": size,
            "tag_rows": len(tags),
            "boundary": "real SQLite; synthetic Anki search returning the same tagged pool; classifier config parsing excluded",
        }
        for stage, work in (("before", before), ("after", after)):
            timing = samples(work)
            calls.clear()
            work()
            result[stage] = {**timing, **calls}
        return result
    finally:
        cards.mw, cards.resolve_topic_card_classifier = saved_mw, saved_resolve
        cards.clear_topic_item_cache()
        conn.close()


def unicode_offsets():
    module = importlib.import_module("incremento_bench.frontend.database_entries_dialog")
    ns = {}
    definitions("frontend/database_entries_dialog.py", "before", {"text_index_to_qt_position"}, ns)
    text = "Synthetic 😀 Straße target\n" * 12000
    positions = [i * (len(text) // 1000) for i in range(1000)]
    expected = []

    def old():
        values = [ns["text_index_to_qt_position"](text, i) for i in positions]
        expected[:] = values

    old()

    def new():
        offsets = module.utf16_prefix_offsets(text)
        assert [offsets[i] for i in positions] == expected

    offsets = module.utf16_prefix_offsets(text)
    return {
        "characters": len(text),
        "positions": len(positions),
        "before": samples(old),
        "after": samples(new),
        "offset_storage_bytes": len(offsets) * offsets.itemsize,
    }


def duplicates():
    module = importlib.import_module("incremento_bench.frontend.pdf_bookshelf")
    entries = [
        module._BookshelfEntry(f"Distinct title {i}", i + 1, "PDF", source_filename="same-origin.pdf")
        for i in range(800)
    ]
    result = {}
    for stage in ("before", "after"):
        ns = dict(vars(module))
        definitions("frontend/pdf_bookshelf.py", stage, {"_bookshelf_duplicate_matches"}, ns)

        def run():
            matches = ns["_bookshelf_duplicate_matches"](entries)
            assert len(matches) == len(entries) and len(matches[1]) == len(entries) - 1
            return matches

        matches = run()
        references = (
            sum(len(value) for value in matches.values()) if stage == "before" else matches.stored_reference_count
        )
        result[stage] = {**samples(run), "peak_python_bytes": peak(run), "stored_peer_references": references}
    return result


def search(folder):
    db.replace_pdf_text_index(
        str(folder),
        "Search",
        1,
        [
            ("alpha beta gamma delta epsilon " if i % 3 else "alpha filler beta gamma delta epsilon ")
            + "synthetic source words " * 8
            + str(i)
            for i in range(12000)
        ],
    )
    conn = db.get_connection(str(folder), "Search")
    outputs, result = {}, {}
    helpers = {
        "normalize_search_text",
        "split_search_terms",
        "_fts_prefix_query",
        "_fts_table_available",
        "_find_consecutive_prefix_match",
        "_find_ordered_prefix_match",
        "_find_unordered_prefix_match",
        "search_text_match_score",
        "search_pdf_text_index",
    }
    for stage in ("before", "after"):
        ns = dict(vars(db))
        ns["get_connection"] = lambda *args: conn
        if stage == "before":
            definitions("backend/db.py", stage, helpers, ns)
        else:
            definitions("backend/db.py", stage, {"search_pdf_text_index"}, ns)

        def run():
            rows = ns["search_pdf_text_index"](str(folder), "Search", "alpha beta gamma delta epsilon", limit=1200)
            outputs[stage] = rows

        run()
        result[stage] = {**samples(run), "peak_python_bytes": peak(run), "returned_rows": len(outputs[stage])}
    assert outputs["before"] == outputs["after"]
    result["rows"] = 12000
    result["ranking_equal"] = True
    return result


def priorities(folder):
    module = importlib.import_module("incremento_bench.backend.knowledge_tree")
    result = {}
    rows = [
        {"card_id": i, "parent_card_id": None if i == 1 else 1, "node_kind": "topic", "sort_order": i}
        for i in range(1, 4001)
    ]
    for stage in ("before", "after"):
        profile = "Priority" + stage
        db.set_knowledge_tree_structure(str(folder), profile, rows)
        ns = dict(vars(module))
        definitions("backend/knowledge_tree.py", stage, {"shift_subtree_priorities"}, ns)
        conn = db.get_connection(str(folder), profile)
        queries = []

        def run():
            ns["shift_subtree_priorities"](str(folder), profile, 1, 1)

        timing = samples(run)
        conn.set_trace_callback(queries.append)
        run()
        conn.set_trace_callback(None)
        result[stage] = {
            **timing,
            "commits": queries.count("COMMIT"),
            "priority_reads": sum("SELECT" in query and "priorities" in query for query in queries),
        }
    return result


def config_snapshots():
    import aqt

    module = importlib.import_module("incremento_bench.backend.reviewer_buttons")
    calls = []
    config = {
        "use_fail_pass_on_items": False,
        "scheduler_presets": {
            f"Preset {i}": {
                "session_card_count": 100,
                "tag_rows": [{"tag": f"tag{j}", "weight": 10} for j in range(20)],
            }
            for i in range(20)
        },
    }
    original = aqt.mw
    aqt.mw = types.SimpleNamespace(
        addonManager=types.SimpleNamespace(getConfig=lambda name: calls.append(name) or config)
    )
    note = types.SimpleNamespace(tags=[], note_type=lambda: {"name": "Basic"})
    card = types.SimpleNamespace(note=lambda: note, did=2, odid=0)
    result = {}
    try:
        for stage in ("before", "after"):
            ns = dict(vars(module))
            definitions("backend/reviewer_buttons.py", stage, {"reviewer_button_mode"}, ns)

            def run():
                for _ in range(100):
                    assert ns["reviewer_button_mode"](card) == "standard"

            timing = samples(run)
            calls.clear()
            run()
            result[stage] = {**timing, "config_reads_per_100_events": len(calls)}
    finally:
        aqt.mw = original
    return result


def undo_sql():
    ns = {"frozenset": frozenset}
    definitions("backend/answer_schedule.py", "after", {"_existing_revlog_ids"}, ns)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE revlog(id INTEGER PRIMARY KEY)")
    conn.executemany("INSERT INTO revlog VALUES (?)", [(i,) for i in range(1, 10001)])
    queries = []
    col = types.SimpleNamespace(
        db=types.SimpleNamespace(
            list=lambda query, *args: queries.append(query) or [row[0] for row in conn.execute(query, args)]
        )
    )
    # The boundary uses db.all in some Anki versions and db.list in others.
    col.db.all = lambda query, *args: queries.append(query) or conn.execute(query, args).fetchall()
    ids = set(range(1, 10001))
    result = samples(lambda: ns["_existing_revlog_ids"](ids, collection=col))
    queries.clear()
    assert ns["_existing_revlog_ids"](ids, collection=col) == frozenset(ids)
    result.update(
        {
            "tracked_revlogs": len(ids),
            "bounded_sql_queries": len(queries),
            "scope": "SQL boundary only; earlier implementation_results.json measures Python transition work",
        }
    )
    conn.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {
        "baseline_commit": BASELINE,
        "scope": __doc__,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
    }
    with tempfile.TemporaryDirectory(prefix="incremento-cpu-bench-") as temporary:
        folder = Path(temporary)
        try:
            for name, operation in [
                ("F01_session_counts", session_counts),
                ("F04_source_covers", source_covers),
                ("F07_unicode_offsets", unicode_offsets),
                ("F12_search", lambda: search(folder)),
                ("F14_duplicates", duplicates),
                ("F15_priorities", lambda: priorities(folder)),
                ("F24_config", config_snapshots),
                ("F11_sql", undo_sql),
            ]:
                result[name] = operation()
                args.output.write_text(json.dumps(result, indent=2) + "\n")
        finally:
            db.close_connection()
    paths = [
        "backend/db.py",
        "backend/knowledge_tree.py",
        "backend/reviewer_buttons.py",
        "backend/pdf_source_index.py",
        "frontend/database_entries_dialog.py",
        "frontend/pdf_bookshelf.py",
    ]
    result["source_sha256"] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
