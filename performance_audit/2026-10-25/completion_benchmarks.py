"""Measure remaining fixes against commit 6a371c7 using synthetic temporary data.

Production definitions are compiled from their AST to omit GUI imports. EPUB
metadata uses real JSON reads with a synthetic contained-path resolver; highlight
and tree cases use real temporary SQLite. These are component measurements.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "6a371c732fc6c7d65bb4468fdb5853a2926ec097"
sys.path.insert(0, str(ROOT))
db = importlib.import_module("backend.db")


def source(path, stage):
    if stage == "before":
        return subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, text=True)
    return (ROOT / path).read_text()


def definitions(path, stage, names, namespace):
    tree = ast.parse(source(path, stage))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), path, "exec",
                 flags=__import__("__future__").annotations.compiler_flag), namespace)


def samples(operation, repeats=3):
    times = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        times.append(round((time.perf_counter() - started) * 1000, 3))
    return {"median_ms": statistics.median(times), "samples_ms": times}


def epub_metadata(folder):
    path = folder / "metadata.json"
    path.write_text(json.dumps({"sections": [{"href": f"chapter-{index}.xhtml", "text": "alpha " * 8333}
                                             for index in range(200)]}))
    results = []
    for stage in ("before", "after"):
        reads = []

        def load(*_args, **_kwargs):
            reads.append(True)
            return json.loads(path.read_text())

        namespace = {"os": os, "_ADDON_DIR": str(folder), "_current_epub_filename": "book.epub",
            "_active_profile": lambda: "Synthetic", "load_epub_metadata": load,
            "epub_metadata_identity": lambda *_args, **_kwargs: path.stat().st_mtime_ns,
            "_epub_metadata_cache_key": None, "_epub_metadata_cache": {},
            "_epub_section_path_cache": None, "_epub_reverse_path_cache": {},
            "_extract_epub_path": lambda _filename, href, **_kwargs: str(folder / href)}
        definitions("backend/epub_manager.py", stage, {"get_epub_section_path"}, namespace)
        definitions("frontend/epub_dock.py", stage, {"_current_metadata", "_current_sections",
                    "_current_section_path", "_current_section_paths", "_section_index_from_path"}, namespace)
        target = str(folder / "chapter-199.xhtml")

        def lookup():
            assert namespace["_section_index_from_path"](target) == 199

        cold = samples(lookup, repeats=1)
        cold_reads = len(reads)
        reads.clear()
        warm = samples(lookup)
        results.append({"stage": stage, "sections": 200, "metadata_bytes": path.stat().st_size,
                        "cold": cold, "cold_json_reads": cold_reads, "warm": warm,
                        "warm_json_reads_per_lookup": len(reads) // 3})
    return results


def epub_highlights(folder):
    connection = db.get_connection(str(folder), "highlights")
    with connection:
        connection.executemany(
            "INSERT INTO epub_highlights(id,card_id,section_index,color,text,note,start_offset,end_offset) "
            "VALUES (?,7,?,'yellow',?,'',0,10)",
            [(str(index), index // 100, "Synthetic text " * 35) for index in range(20000)],
        )
    results = []
    for stage in ("before", "after"):
        namespace = {"get_connection": lambda *_args: connection}
        definitions("backend/epub_highlights.py", stage, {"load_highlights"}, namespace)
        row_counts = []

        def read():
            if stage == "before":
                rows = namespace["load_highlights"](str(folder), "highlights", 7)
                row_counts.append(len(rows))
                result = [row for row in rows if row["sectionIndex"] == 199]
            else:
                result = namespace["load_highlights"](str(folder), "highlights", 7, section_index=199)
                row_counts.append(len(result))
            assert len(result) == 100 and result[0]["id"] == "19900"

        results.append({"stage": stage, "total_highlights": 20000, "section_highlights": 100,
                        **samples(read), "materialized_rows_per_read": row_counts[0]})
    return results


def tree_writes(folder):
    results = []
    for stage in ("before", "after"):
        namespace = {"time": time, "get_connection": db.get_connection,
                     "get_knowledge_tree_nodes": db.get_knowledge_tree_nodes,
                     "_iter_sql_chunks": db._iter_sql_chunks}
        definitions("backend/db.py", stage, {"_validate_knowledge_tree_parents", "set_knowledge_tree_structure"}, namespace)
        profile = f"tree-{stage}"
        rows = [{"card_id": index, "parent_card_id": None if index == 1 else 1,
                 "sort_order": index} for index in range(1,4001)]
        save = namespace["set_knowledge_tree_structure"]
        save(str(folder), profile, rows)
        connection = db.get_connection(str(folder), profile)
        counts = []

        def write():
            changes = connection.total_changes
            save(str(folder), profile, rows)
            counts.append(connection.total_changes - changes)

        noop = samples(write)
        noop_counts = counts[:]
        counts.clear()

        def move():
            rows[-1]["parent_card_id"] = 3999 if rows[-1]["parent_card_id"] == 1 else 1
            write()

        results.append({"stage": stage, "nodes": 4000, "unchanged_save": noop,
                        "unchanged_save_changed_rows": noop_counts, "move_one_leaf": samples(move),
                        "move_one_leaf_changed_rows": counts})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = ("backend/db.py", "backend/epub_manager.py", "backend/epub_highlights.py", "frontend/epub_dock.py")
    results = {"baseline_commit": BASELINE, "scope": __doc__.strip(),
               "environment": {"python": platform.python_version(), "sqlite": db.sqlite3.sqlite_version},
               "source_sha256": {stage: {path: hashlib.sha256(source(path,stage).encode()).hexdigest()
                                          for path in paths} for stage in ("before", "after")}}
    with tempfile.TemporaryDirectory(prefix="incremento-completion-benchmark-") as temporary:
        folder = Path(temporary)
        try:
            results["F02_epub_metadata"] = epub_metadata(folder)
            results["F13_epub_highlights"] = epub_highlights(folder)
            results["F06_tree_writes"] = tree_writes(folder)
        finally:
            db.close_connection()
    args.output.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
