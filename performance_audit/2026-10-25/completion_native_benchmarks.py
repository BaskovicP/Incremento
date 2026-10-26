"""Offscreen native measurements with disposable PDFs, Anki collections and DBs.

Run with QT_QPA_PLATFORM=offscreen .venv/bin/python and --output. Timings are
component results, not claims about total Anki startup or every real document.
"""

from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import CancelledError, ThreadPoolExecutor
from datetime import date
import importlib
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import threading
import time
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from completion_cpu_benchmarks import ROOT, BASELINE, definitions, samples, source
from PyQt6.QtWidgets import QApplication, QTextBrowser, QTableWidget, QTableWidgetItem
from anki.collection import Collection
import fitz
import aqt

app = QApplication.instance() or QApplication([])
db = importlib.import_module("incremento_bench.backend.db")


def writing_preview():
    preview = QTextBrowser()
    text = "# Synthetic heading\n\nA **markdown** paragraph with a [link](https://example.test).\n\n" * 1250
    parsed = []

    def parse():
        preview.setMarkdown(text)
        parsed.append(True)

    before = samples(lambda: [parse() for _ in range(20)])
    after = samples(parse)
    preview.deleteLater()
    return {
        "characters": len(text),
        "keystrokes_per_burst": 20,
        "before": {**before, "markdown_parses": 20},
        "after_visible": {**after, "markdown_parses": 1},
        "after_hidden": {"markdown_parses": 0},
        "scope": "Qt markdown parsing only; writing handler debounce/ordered saves verified separately",
    }


def qt_rows():
    batches = importlib.import_module("incremento_bench.frontend.render_batches")
    result = {}
    for stage in ("before", "after"):
        table = QTableWidget(5000, 8)
        callbacks, durations = deque(), []

        def row(index):
            for column in range(8):
                table.setItem(index, column, QTableWidgetItem(f"Synthetic {index}, {column}"))

        def step(callback):
            started = time.perf_counter()
            callback()
            durations.append((time.perf_counter() - started) * 1000)

        started = time.perf_counter()
        if stage == "before":
            step(lambda: [row(i) for i in range(5000)])
        else:
            step(
                lambda: batches.build_in_batches(
                    range(5000), row, valid=lambda: True, done=lambda: None, schedule=callbacks.append
                )
            )
            while callbacks:
                app.processEvents()
                step(callbacks.popleft())
        result[stage] = {
            "total_ms": round((time.perf_counter() - started) * 1000, 3),
            "max_construction_callback_ms": round(max(durations), 3),
            "callbacks": len(durations),
            "rows": table.rowCount(),
            "cells": 40000,
        }
        assert table.item(4999, 7).text() == "Synthetic 4999, 7"
        table.deleteLater()
        app.processEvents()
    result["scope"] = "actual Qt item construction; excludes DB reads, layout/paint and upfront empty table allocation"
    return result


def thumbnails(folder):
    from PyQt6.QtCore import QSize, Qt
    from PyQt6.QtGui import QImage, QImageReader

    cache_module = importlib.import_module("incremento_bench.frontend.bounded_cache")
    path = folder / "cover.png"
    image = QImage(320, 480, QImage.Format.Format_RGB32)
    image.fill(0xFF224466)
    image.save(str(path))
    result = {"library_tiles": 2000, "viewport_columns": 3, "visible_rows": 2}
    for stage in ("before", "after"):
        ids = (
            range(2000)
            if stage == "before"
            else cache_module.thumbnail_window(2000, columns=3, first_row=0, visible_rows=2)
        )
        cache = {} if stage == "before" else cache_module.ByteLRU(24 * 1024 * 1024)

        def decode():
            for cid in ids:
                reader = QImageReader(str(path))
                reader.setScaledSize(reader.size().scaled(QSize(160, 320), Qt.AspectRatioMode.KeepAspectRatio))
                value = reader.read()
                assert not value.isNull()
                if stage == "before":
                    cache[cid] = value
                else:
                    cache.put(cid, value, 160 * 320 * 4)

        timing = samples(decode)
        result[stage] = {
            **timing,
            "images_decoded": len(ids),
            "accounted_raster_budget_bytes": len(cache) * 160 * 320 * 4 if stage == "before" else cache.bytes_used,
        }
    result["scope"] = (
        "same native Qt decoder and warm filesystem; work before idling at the first viewport; all later tiles remain reachable by scrolling; byte values are conservative raster accounting, not process RSS"
    )
    return result


def extraction(folder):
    manager = importlib.import_module("incremento_bench.backend.pdf_manager")
    path = folder / "extraction.pdf"
    with fitz.open() as document:
        for i in range(1000):
            document.new_page().insert_text((72, 72), f"Synthetic searchable page {i}")
        document.save(path)
    real_open = fitz.open
    result = {}
    for stage in ("before", "after"):
        loaded, closed = [], []

        class Document:
            def __init__(self):
                self.document = real_open(path)

            def __len__(self):
                return len(self.document)

            def load_page(self, index):
                loaded.append(index)
                return self.document.load_page(index)

            def close(self):
                closed.append(True)
                self.document.close()

        ns = dict(vars(manager))
        definitions("backend/pdf_manager.py", stage, {"extract_pdf_pages_text"}, ns)
        original = sys.modules["fitz"]
        sys.modules["fitz"] = types.SimpleNamespace(open=lambda *_args: Document())

        def run():
            loaded.clear()
            closed.clear()
            try:
                ns["extract_pdf_pages_text"](
                    str(path), allow_qt=False, **({"cancelled": lambda: len(loaded) >= 2} if stage == "after" else {})
                )
            except CancelledError:
                pass

        try:
            result[stage] = {**samples(run), "loaded_pages": len(loaded), "document_closed": bool(closed)}
        finally:
            sys.modules["fitz"] = original
    result["scope"] = "cancellation requested after two pages; baseline could only finish the whole file"
    return result


def supermemo(folder):
    module = importlib.import_module("incremento_bench.backend.supermemo_import")
    formats = importlib.import_module("incremento_bench.backend.supermemo_format")
    result = {}
    for stage in ("before", "after"):
        identifier_reads = []

        class Element(formats.SuperMemoElement):
            def __getattribute__(self, name):
                if name == "element_id":
                    identifier_reads.append(True)
                return super().__getattribute__(name)

        size = 256
        elements = tuple(
            Element(
                element_id=i,
                element_type=0,
                status=2,
                parent_id=i - 1 if i > 1 else None,
                sort_order=i,
                priority_rank=i,
                a_factor=2.5,
                forgetting_index=10,
                current_interval=7,
                due_date=None,
                repetition_count=0,
                lapse_count=0,
                title=f"Topic {i}",
                question="",
                answer="",
                body="Synthetic",
                history=(),
            )
            for i in range(1, size + 1)
        )
        source_collection = formats.SuperMemoCollection(
            name="Synthetic",
            kno_path=folder / "source.Kno",
            collection_dir=folder,
            fingerprint="b" * 64,
            structure_version=22,
            first_day=date(2024, 1, 1),
            last_day=date(2024, 1, 1),
            default_forgetting_index=10,
            elements=elements,
            optimization_files=(),
        )
        profile = "SuperMemo" + stage
        collection = Collection(str(folder / f"supermemo-{stage}.anki2"))
        conn = db.get_connection(str(folder), profile)
        queries = []
        ns = dict(vars(module), set_topic_schedule=db.set_topic_schedule)
        definitions("backend/supermemo_import.py", stage, {"import_supermemo_collection"}, ns)
        conn.set_trace_callback(queries.append)
        started = time.perf_counter()
        imported = ns["import_supermemo_collection"](
            str(folder), profile, collection, source_collection, deck_name="Synthetic"
        )
        elapsed = (time.perf_counter() - started) * 1000
        conn.set_trace_callback(None)
        topic_pending = False
        commits = 0
        for statement in queries:
            if "INTO topic_schedule" in statement:
                topic_pending = True
            if statement == "COMMIT" and topic_pending:
                commits += 1
                topic_pending = False
        assert imported.created == size
        result[stage] = {
            "elapsed_ms": round(elapsed, 3),
            "element_id_reads": len(identifier_reads),
            "topic_commits": commits,
            "created": size,
        }
        collection.close()
    result["scope"] = "one native Anki import per stage; journals retain their per-item durability boundaries"
    return result


def pdf_import(folder):
    import aqt

    manager = importlib.import_module("incremento_bench.backend.pdf_manager")
    bridge = importlib.import_module("incremento_bench.backend.browser_bridge")
    path = folder / "import.pdf"
    with fitz.open() as document:
        for i in range(200):
            document.new_page().insert_text((72, 72), f"Synthetic import page {i}")
        document.save(path)
    bridge._addon_dir = str(folder)
    original_dir = manager.get_pdf_dir

    def directory(profile=None):
        target = folder / "user_files" / str(profile) / "pdfs"
        target.mkdir(parents=True, exist_ok=True)
        return str(target)

    manager.get_pdf_dir = directory
    result = {}
    try:
        for stage in ("before", "after"):
            col = Collection(str(folder / f"pdf-{stage}.anki2"))
            aqt.mw = types.SimpleNamespace(col=col, addonManager=types.SimpleNamespace(getConfig=lambda name: {}))
            item = bridge.normalize_add_content_payload(
                {"kind": "pdf", "url": "https://example.test/import.pdf", "title": "Synthetic"}
            )
            item[bridge._PREPARED_PDF_PATH_KEY] = str(path)

            def operation():
                return bridge.import_prepared_pdf_item(item, col=col, profile="PDF" + stage)

            started = time.perf_counter()
            ui_ticks = 0
            longest_gap = 0.0
            previous = started
            if stage == "before":
                imported = operation()
                longest_gap = (time.perf_counter() - previous) * 1000
            else:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(operation)
                    while not future.done():
                        app.processEvents()
                        now = time.perf_counter()
                        longest_gap = max(longest_gap, (now - previous) * 1000)
                        previous = now
                        ui_ticks += 1
                        threading.Event().wait(0.001)
                    imported = future.result()
            elapsed = (time.perf_counter() - started) * 1000
            assert col.get_card(imported["cardId"]).note()["PDF_Filename"]
            result[stage] = {
                "elapsed_ms": round(elapsed, 3),
                "ui_event_pumps": ui_ticks,
                "max_ui_pump_gap_ms": round(longest_gap, 3),
            }
            col.close()
    finally:
        manager.get_pdf_dir = original_dir
    result["scope"] = (
        "same 200-page import on UI thread versus worker; throughput is not the optimization; QWebEngine webpage rendering remains asynchronous UI-owned"
    )
    return result


def imports():
    # Compile and call the actual lazy factory definitions without opening UI.
    tree = __import__("ast").parse(source("__init__.py", "after"))
    names = {
        "StatsDialog",
        "_PdfQuickJumpDialog",
        "_DocumentBookshelfDialog",
        "_CurrentDocumentSearchDialog",
        "_SearchAllDialog",
        "show_database_entries_dialog",
    }
    functions = [node for node in tree.body if isinstance(node, __import__("ast").FunctionDef) and node.name in names]
    assert len(functions) == 6
    started = time.perf_counter()
    compile(__import__("ast").Module(body=functions, type_ignores=[]), "<lazy factories>", "exec")
    return {
        "optional_dialog_modules_deferred": 6,
        "factory_definition_compile_ms": round((time.perf_counter() - started) * 1000, 3),
        "before_optional_import_group": json.loads(
            (Path(__file__).parent / "completion_imports_before.json").read_text()
        ),
        "scope": "21.7 ms measured optional-module import group moves to first use; no end-to-end Anki startup speed claim",
    }


def database_startup(folder):
    module = importlib.import_module("incremento_bench.backend.db_connection")
    result = {}
    for stage in ("before", "after"):
        namespace = dict(vars(module))
        definitions("backend/db_connection.py", stage, {"get"}, namespace, cls="ProfileConnectionManager")
        manager_type = type("MeasuredManager", (module.ProfileConnectionManager,), {"get": namespace["get"]})
        manager = manager_type()
        path = folder / f"first-use-{stage}.db"
        started = time.perf_counter()
        ready = manager.get(cache_key="ready", db_path=path, initialize=db._initialize_database)
        cold_ms = (time.perf_counter() - started) * 1000

        def warm():
            for _ in range(1000):
                assert manager.get(cache_key="ready", db_path=path, initialize=db._initialize_database) is ready

        warm_timing = samples(warm)
        initializing, release = threading.Event(), threading.Event()

        def initialize(conn):
            initializing.set()
            if not release.wait(5):
                raise RuntimeError("Benchmark initializer timed out")

        errors = []

        def slow():
            try:
                manager.get(cache_key="slow", db_path=folder / f"slow-{stage}.db", initialize=initialize)
            except Exception as error:
                errors.append(str(error))

        worker = threading.Thread(target=slow)
        worker.start()
        assert initializing.wait(5)
        timer = threading.Timer(0.1, release.set)
        timer.start()
        started = time.perf_counter()
        assert manager.get(cache_key="ready", db_path=path, initialize=db._initialize_database) is ready
        blocked_ms = (time.perf_counter() - started) * 1000
        release.set()
        worker.join(5)
        timer.cancel()
        manager.close_all()
        assert not errors
        result[stage] = {
            "first_schema_open_ms": round(cold_ms, 3),
            "warm_1000_lookups": warm_timing,
            "cached_lookup_during_controlled_100ms_initializer_ms": round(blocked_ms, 3),
        }
    result["scope"] = (
        "real temporary SQLite schema; the 100 ms initializer stall is controlled, not measured production migration latency"
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    result = (
        json.loads(args.output.read_text())
        if args.only and args.output.exists()
        else {"baseline_commit": BASELINE, "scope": __doc__}
    )
    with tempfile.TemporaryDirectory(prefix="incremento-native-bench-") as temporary:
        folder = Path(temporary)
        try:
            for name, operation in (
                ("F10_writing_preview", writing_preview),
                ("F18_qt_rows", qt_rows),
                ("F19_thumbnails", lambda: thumbnails(folder)),
                ("F17_extraction", lambda: extraction(folder)),
                ("F22_supermemo", lambda: supermemo(folder)),
                ("F08_pdf_import", lambda: pdf_import(folder)),
                ("F23_imports", imports),
                ("F23_database", lambda: database_startup(folder)),
            ):
                if args.only and name not in args.only:
                    continue
                result[name] = operation()
                args.output.write_text(json.dumps(result, indent=2) + "\n")
        finally:
            db.close_connection()


if __name__ == "__main__":
    main()
