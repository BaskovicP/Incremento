"""Reproduce isolated audit measurements without importing Anki or using a profile.

Run with the repository's .venv/bin/python. All runtime fixtures are created
inside TemporaryDirectory. Results describe these synthetic inputs, not live UI
latency. No network, GUI, installs, or production data are used.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import html
import importlib
import inspect
from itertools import combinations
import json
import math
import os
from pathlib import Path
import platform
import re
import sqlite3
import statistics as timing_statistics
import sys
import tempfile
from time import perf_counter
import types
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

db = importlib.import_module("backend.db")
stats = importlib.import_module("backend.statistics")
normalize_config = importlib.import_module("backend.config_service").normalize_config
get_priority = importlib.import_module("backend.priority_manager").get_priority


def timed(operation, repeats=3):
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        operation()
        samples.append((perf_counter() - started) * 1000)
    return {"median_ms": round(timing_statistics.median(samples), 3),
            "samples_ms": [round(value, 3) for value in samples]}


def pure_source(path, names, *, assignments=(), extra=None):
    """Compile selected original definitions verbatim, omitting GUI imports."""
    tree = ast.parse((ROOT / path).read_text())
    selected = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in assignments
            for target in node.targets
        ):
            selected.append(node)
    found = {node.name for node in selected if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    if found != set(names):
        raise RuntimeError(f"Source definitions changed: {set(names) - found}")
    module = types.ModuleType("_incremento_audit_" + path.replace("/", "_").replace(".", "_"))
    module.__dict__.update({"Counter": Counter, "defaultdict": defaultdict,
        "deque": deque, "dataclass": dataclass, "html": html, "os": os,
        "re": re, "sys": sys, "math": math, "unicodedata": unicodedata,
        "combinations": combinations, "json": json})
    module.__dict__.update(extra or {})
    sys.modules[module.__name__] = module
    compiled = compile(ast.Module(body=selected, type_ignores=[]), path, "exec",
                       flags=__import__("__future__").annotations.compiler_flag)
    exec(compiled, module.__dict__)
    return module


def tree_measurements(addon_dir):
    results = []
    for shape in ("star", "chain"):
        for size in (1000, 2000, 4000):
            rows = [{"card_id": index, "parent_card_id": (
                None if index == 1 else index - 1 if shape == "chain" else 1),
                "node_kind": "topic", "sort_order": index}
                for index in range(1, size + 1)]
            db.set_knowledge_tree_structure(addon_dir, "tree", rows)
            result = timed(lambda: db.set_knowledge_tree_structure(addon_dir, "tree", rows))
            results.append({"shape": shape, "nodes": size, **result})
    return results


def priority_measurements(addon_dir):
    conn = db.get_connection(addon_dir, "priorities")
    size = 4000
    with conn:
        conn.executemany("INSERT INTO priorities(card_id,priority) VALUES (?,?)",
                         [(index, float(index % 100)) for index in range(1, size + 1)])
    ids = list(range(1, size + 1))
    def helpers():
        return [get_priority(addon_dir, "priorities", cid) for cid in ids]
    def connection_queries():
        return [conn.execute("SELECT priority FROM priorities WHERE card_id=?", (cid,)).fetchone()[0]
                for cid in ids]
    def batched():
        result = {}
        for start in range(0, size, 900):
            chunk = ids[start:start + 900]
            result.update(conn.execute("SELECT card_id,priority FROM priorities WHERE card_id IN ("
                + ",".join("?" for _ in chunk) + ")", chunk).fetchall())
        return [result[cid] for cid in ids]
    assert helpers() == connection_queries() == batched()
    return {"rows": size, "public_helper": timed(helpers),
            "same_connection_per_row": timed(connection_queries), "batched_900": timed(batched)}


def stats_measurements(addon_dir):
    results = []
    combined_events = "study_kind" in inspect.signature(stats.StatsManager.record).parameters
    for tag_count in (1, 128, 512):
        profile = f"stats_{tag_count}"
        tags = {f"tag_{index}": 1 for index in range(tag_count)}
        daily = {"date": stats._effective_date(), "counts": {"type": {"items": 1}, "tags": tags, "mode": {"random": 1}}}
        seed = {"daily": daily, "lifetime": daily["counts"],
            "time": {"daily": {"date": daily["date"], "seconds": {"type": {"items": 1}, "tags": tags}},
                     "lifetime": {"type": {"items": 1}, "tags": tags}},
            "tag_breakdown": {"daily": {"date": daily["date"],
                "counts": {"topics": tags, "items": tags}, "seconds": {"topics": tags, "items": tags}},
                "lifetime": {"counts": {"topics": tags, "items": tags}, "seconds": {"topics": tags, "items": tags}}}}
        stats.save_stats(addon_dir, profile, seed)
        result = types.SimpleNamespace(card=1, card_type="items", tag="tag_0", mode="random", review_seconds=0.0)
        writes = 0
        original = stats._write_stats_file_atomic
        def count_write(*args):
            nonlocal writes
            writes += 1
            return original(*args)
        def free_review_cycle():
            # Mirrors separate tracker time and answer callbacks; no Anki imports.
            manager = stats.StatsManager(addon_dir, profile)
            if combined_events:
                manager.record_time_only(result, 10, study_kind="items")
            else:
                manager.record_time_only(result, 10)
                stats.record_tag_breakdown(addon_dir, profile, study_kind="items", tag="tag_0",
                    include_count=False, seconds=10)
            manager = stats.StatsManager(addon_dir, profile)
            if combined_events:
                manager.record(result, "daily", study_kind="items")
            else:
                manager.record(result, "daily")
                stats.record_tag_breakdown(addon_dir, profile, study_kind="items", tag="tag_0",
                    include_count=True, seconds=0)
        stats._write_stats_file_atomic = count_write
        try:
            measurement = timed(free_review_cycle, repeats=5)
        finally:
            stats._write_stats_file_atomic = original
        results.append({"tags_per_populated_group": tag_count, "atomic_file_writes_per_cycle": writes // 5,
            "combined_event_api": combined_events,
            "fixture_bytes": stats._get_stats_path(addon_dir, profile).stat().st_size, **measurement})
    return results


def search_measurements(addon_dir):
    conn = db.get_connection(addon_dir, "search")
    pages = 12000
    text = "alpha beta gamma delta " * 60
    db.replace_pdf_text_index(addon_dir, "search", 1, [text + f" page{index}" for index in range(pages)])
    fts = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='pdf_text_fts'").fetchone())
    results = []
    for limit in (120, 1200):
        hits = db.search_pdf_text_index(addon_dir, "search", "alpha beta", limit=limit)
        assert len(hits) == limit
        results.append({"requested_results": limit, "candidate_limit": max(500, limit * 25),
            **timed(lambda: db.search_pdf_text_index(addon_dir, "search", "alpha beta", limit=limit))})
    with conn:
        conn.executemany("INSERT INTO pdf_highlights(id,card_id,page,color,text,note,rects) VALUES (?,?,?,'yellow',?,'','[]')",
            [(f"h{index}", 1, index, text) for index in range(pages)])
    plan = conn.execute("EXPLAIN QUERY PLAN SELECT card_id,page,text FROM pdf_highlights "
        "WHERE lower(text) LIKE lower(?) ORDER BY card_id,page LIMIT ?", ("%alpha%", 30000)).fetchall()
    return {"pages": pages, "page_chars": len(text), "fts5_active": fts, "search": results,
            "highlight_like_plan": [list(row) for row in plan]}


def fts_replacement_measurements(addon_dir):
    results = []
    for size in (500, 1000, 2000, 4000):
        profile = f"fts_replace_{size}"
        pages = ["alpha beta gamma delta"] * size
        db.replace_pdf_text_index(addon_dir, profile, 1, pages)
        conn = db.get_connection(addon_dir, profile)
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='pdf_text_fts'").fetchone():
            return {"available": False}
        lookup_keys = bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='pdf_text_fts_keys'").fetchone())
        delete_sql = (
            "DELETE FROM pdf_text_fts WHERE rowid=(SELECT id FROM pdf_text_fts_keys WHERE card_id=? AND page=?)"
            if lookup_keys else "DELETE FROM pdf_text_fts WHERE card_id=? AND page=?"
        )
        plan = conn.execute("EXPLAIN QUERY PLAN " + delete_sql, (1, 1)).fetchall()
        results.append({"pages": size,
            "indexed_fts_key_lookup": lookup_keys,
            "fts_delete_plan": [list(row) for row in plan],
            **timed(lambda: db.replace_pdf_text_index(addon_dir, profile, 1, pages))})
    return {"available": True, "replace_existing": results}


def database_text_measurements():
    module = pure_source("frontend/database_entries_dialog.py", {"text_index_to_qt_position"})
    results = []
    for matches in (2000, 4000, 8000):
        text = ("needle " + "x" * 56 + "\n") * matches
        def offsets():
            return [(module.text_index_to_qt_position(text, index * 64),
                     module.text_index_to_qt_position(text, index * 64 + 6)) for index in range(matches)]
        results.append({"chars": len(text), "matches": matches, **timed(offsets)})
    return results


def bookshelf_measurements():
    names = {"_BookshelfEntry", "_DuplicateFingerprint", "_DuplicateMatches", "_normalized_bookshelf_duplicate_label",
        "_bookshelf_origin_label", "_bookshelf_metadata_title_label", "_duplicate_tokens",
        "_duplicate_trigrams", "_duplicate_fingerprint", "_duplicate_feature_weights",
        "_weighted_duplicate_scores", "_duplicate_channel_matches", "_bookshelf_duplicate_matches"}
    assignments = {"_MANAGED_FILENAME_UUID_RE", "_VISIBLE_DUPLICATE_SUFFIX_RE", "_DUPLICATE_NOISE_TOKENS",
        "_MAX_DUPLICATE_FEATURE_BUCKET", "_MAX_EXACT_TITLE_BUCKET", "_GENERIC_PDF_METADATA_TITLES", "_KIND_PDF"}
    module = pure_source("frontend/pdf_bookshelf.py", names, assignments=assignments, extra={"Mapping": Mapping})
    results = []
    for size in (200, 400, 800):
        entries = [module._BookshelfEntry(title=f"Distinct title {index}", card_id=index + 1, kind="PDF",
            source_filename=f"shared-chapter-{index:032x}.pdf") for index in range(size)]
        result = module._bookshelf_duplicate_matches(entries)
        edges = sum(len(peers) for peers in result.values())
        assert edges == size * (size - 1)
        results.append({"documents_with_same_normalized_origin": size,
            "expanded_peer_references": edges,
            "stored_peer_references": getattr(result, "stored_reference_count", edges),
            **timed(lambda: module._bookshelf_duplicate_matches(entries))})
    return results


def config_measurements():
    default = json.loads((ROOT / "config.json").read_text())
    results = []
    for presets in (1, 25, 100):
        fixture = {**default, "scheduler_presets": {f"Preset {index}": default.get("dialog", {}) for index in range(presets)}}
        fixture = normalize_config(fixture)
        results.append({"presets": presets, **timed(lambda: [normalize_config(fixture) for _ in range(50)]),
                        "normalizations_per_sample": 50})
    return results


def undo_tracker_measurements():
    # Isolate Python set work; the revlog lookup is a deterministic boundary fake.
    from dataclasses import field
    current = set()
    module = pure_source("backend/answer_schedule.py", {"_TrackedCard", "ReviewRevlogTracker"}, extra={
        "field": field, "_existing_revlog_ids": lambda ids, **kwargs: frozenset(current)})
    results = []
    for size in (1000, 2000, 4000):
        samples = []
        for _ in range(3):
            tracker = module.ReviewRevlogTracker()
            for index in range(1, size + 1):
                tracker.track("synthetic", index, index)
            current.clear()
            current.update(range(1, size))
            assert len(list(tracker.transitions(types.SimpleNamespace(can_redo=True)))) == 1
            started = perf_counter()
            assert list(tracker.transitions(types.SimpleNamespace(can_redo=False))) == []
            samples.append((perf_counter() - started) * 1000)
        results.append({"tracked_cards": size, "case": "Undo one answer then clear Redo without a revlog delta",
            "revlog_lookup": "boundary fake; SQL cost excluded",
            "median_ms": round(timing_statistics.median(samples), 3),
            "samples_ms": [round(value, 3) for value in samples]})
    return results


def epub_metadata_measurements(folder):
    results = []
    for sections, chars in ((50, 20000), (200, 50000)):
        path = folder / "metadata.json"
        path.write_text(json.dumps({"sanitizer_version": 999, "sections": [
            {"href": f"section{index}.xhtml", "text": "alpha " * (chars // 6)} for index in range(sections)]}))
        module = pure_source("backend/epub_manager.py", {"load_epub_metadata"}, extra={
            "_metadata_path": lambda *args, **kwargs: str(path), "_EPUB_SANITIZER_VERSION": 999})
        results.append({"sections": sections, "bytes": path.stat().st_size,
            **timed(lambda: module.load_epub_metadata("unused", "synthetic.epub"), repeats=5)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source_paths = ["backend/db.py", "backend/statistics.py", "backend/config_service.py",
        "backend/priority_manager.py", "backend/db_connection.py", "frontend/pdf_bookshelf.py",
        "frontend/database_entries_dialog.py", "backend/epub_manager.py", "backend/answer_schedule.py"]
    results = {"environment": {"python": platform.python_version(), "platform": platform.system(),
        "machine": platform.machine(), "sqlite": sqlite3.sqlite_version},
        "scope": "Synthetic local inputs; medians of three samples unless a measurement lists five; no live Anki or GUI latency measured",
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in source_paths}}
    with tempfile.TemporaryDirectory(prefix="incremento-performance-") as temporary:
        folder = Path(temporary)
        try:
            for name, operation in (("tree_structure", lambda: tree_measurements(temporary)),
                    ("priority_reads", lambda: priority_measurements(temporary)),
                    ("statistics", lambda: stats_measurements(temporary)),
                    ("search", lambda: search_measurements(temporary)),
                    ("fts_replacement", lambda: fts_replacement_measurements(temporary)),
                    ("database_text_offsets", database_text_measurements),
                    ("bookshelf_duplicates", bookshelf_measurements),
                    ("config", config_measurements),
                    ("undo_tracker", undo_tracker_measurements),
                    ("epub_metadata", lambda: epub_metadata_measurements(folder))):
                print(f"Measuring {name}", file=sys.stderr, flush=True)
                results[name] = operation()
        finally:
            db.close_connection()
    rendered = json.dumps(results, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
