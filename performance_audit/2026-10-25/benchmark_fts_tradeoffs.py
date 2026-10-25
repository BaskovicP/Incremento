"""Compare schema 18/19 fresh PDF indexing, size, and one-time migration cost.

Uses isolated temporary SQLite files with Incremento's WAL/NORMAL settings.
Source indexes and text are synthetic. No live profiles or Anki are accessed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import tempfile
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
db = importlib.import_module("backend.db")


def initialize(connection, version):
    db.initialize_schema(connection, bootstrap=db._create_tables,
                         migrations=tuple(m for m in db._SCHEMA_MIGRATIONS if m[0] <= version))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = []
    corpus_results = []
    with tempfile.TemporaryDirectory(prefix="incremento-fts-tradeoffs-") as folder:
        for pages in (1000, 4000):
            rows = [(7, page + 1, "alpha beta gamma delta") for page in range(pages)]
            for version in (18, 19):
                samples, sizes, migration_samples = [], [], []
                for repeat in range(5):
                    path = Path(folder) / f"index-{pages}-{version}-{repeat}.db"
                    with sqlite3.connect(path) as connection:
                        connection.execute("PRAGMA journal_mode=WAL")
                        connection.execute("PRAGMA synchronous=NORMAL")
                        initialize(connection, version)
                        started = perf_counter()
                        connection.executemany("INSERT INTO pdf_text_index VALUES (?,?,?)", rows)
                        connection.commit()
                        samples.append(round((perf_counter() - started) * 1000, 3))
                        sizes.append(connection.execute("PRAGMA page_count").fetchone()[0]
                                     * connection.execute("PRAGMA page_size").fetchone()[0])
                        if version == 18:
                            started = perf_counter()
                            initialize(connection, 19)
                            migration_samples.append(round((perf_counter() - started) * 1000, 3))
                        assert connection.execute("SELECT count(*) FROM pdf_text_fts").fetchone() == (pages,)
                        assert connection.execute("SELECT count(*) FROM pdf_text_fts_keys").fetchone() == (pages,)
                results.append({"schema": version, "pages": pages,
                    "fresh_insert_median_ms": round(statistics.median(samples), 3),
                    "fresh_insert_samples_ms": samples,
                    "database_allocated_bytes_before_migration": sizes,
                    "upgrade_to_19_samples_ms": migration_samples,
                    "upgrade_to_19_median_ms": round(statistics.median(migration_samples), 3)
                    if migration_samples else None})
        for unrelated_pages in (0, 2000, 8000):
            for version in (18, 19):
                path = Path(folder) / f"corpus-{unrelated_pages}-{version}.db"
                with sqlite3.connect(path) as connection:
                    connection.execute("PRAGMA journal_mode=WAL")
                    connection.execute("PRAGMA synchronous=NORMAL")
                    initialize(connection, version)
                    connection.executemany("INSERT INTO pdf_text_index VALUES (?,?,?)",
                        [(8, page + 1, "alpha unrelated") for page in range(unrelated_pages)])
                    connection.commit()
                    samples = []
                    for _ in range(5):
                        connection.executemany("INSERT INTO pdf_text_index VALUES (?,?,?)",
                            [(7, page + 1, "beta target") for page in range(50)])
                        connection.commit()
                        started = perf_counter()
                        connection.execute("DELETE FROM pdf_text_index WHERE card_id=7")
                        connection.commit()
                        samples.append(round((perf_counter() - started) * 1000, 3))
                        assert connection.execute("SELECT count(*) FROM pdf_text_fts").fetchone() == (unrelated_pages,)
                    corpus_results.append({"schema": version, "unrelated_pages": unrelated_pages,
                        "deleted_document_pages": 50, "median_ms": round(statistics.median(samples), 3),
                        "samples_ms": samples})
    args.output.write_text(json.dumps({"scope": __doc__.strip(),
        "environment": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                        "machine": platform.machine()},
        "source_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
                          for path in ("backend/db.py", "backend/db_schema.py")},
        "results": results, "delete_document_with_unrelated_corpus": corpus_results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
