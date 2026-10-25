"""Measure completed empty-PDF preparation without Anki or a GUI.

Uses real PyMuPDF/Poppler extraction and synthetic PDFs in a temporary folder.
The manager's prepared-text decision is compiled verbatim from its AST. Note
creation, cover rendering, storage, and actual Qt extraction are excluded; the
Qt fallback is an empty boundary fake. This is not end-to-end import latency.
"""
from __future__ import annotations

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter
import types

import pymupdf as fitz


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "6125c2ca3f4e21cdd52a861c765d3916bb838d28"
PATH_KEY = "_prepared_pdf_path"
TEXT_KEY = "_prepared_pdf_page_texts"


class EmptyQtDocument:
    def __init__(self, *_args):
        pass

    def load(self, _path):
        pass

    def pageCount(self):
        return 0

    def close(self):
        pass


def definitions(source, names, namespace):
    selected = [node for node in ast.parse(source).body
                if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected} == set(names)
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<production-definitions>", "exec"), namespace)


def load_pipeline(label, source):
    package_name = f"_incremento_pdf_benchmark_{label}"
    package = types.ModuleType(package_name)
    package.__path__ = []
    sys.modules[package_name] = package
    manager = types.ModuleType(f"{package_name}.pdf_manager")
    sys.modules[manager.__name__] = manager
    manager.__dict__.update({"os": os, "shutil": shutil, "subprocess": subprocess,
                            "QPdfDocument": EmptyQtDocument})
    definitions(source["backend/pdf_manager.py"], {"extract_pdf_pages_text"}, manager.__dict__)
    calls = []
    extractor = manager.extract_pdf_pages_text

    def count_extract(path, **kwargs):
        calls.append({"allow_qt": kwargs.get("allow_qt", True)})
        return extractor(path, **kwargs)

    manager.extract_pdf_pages_text = count_extract
    bridge = {"__package__": package_name, "os": os, "tempfile": tempfile,
              "b64decode": base64.b64decode, "_PREPARED_PDF_PATH_KEY": PATH_KEY,
              "_PREPARED_PDF_PAGE_TEXTS_KEY": TEXT_KEY, "_MAX_PDF_UPLOAD_BYTES": 48 * 1024 * 1024}
    definitions(source["backend/browser_bridge.py"], {
        "_make_temp_pdf_path", "_extract_pdf_pages_text_off_main", "_prepare_pdf_item_off_main",
    }, bridge)
    # Reuse the exact manager branch rather than approximating its None/[] rule.
    manager_tree = ast.parse(source["backend/pdf_manager.py"])
    owner = next(node for node in manager_tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "_create_new_pdf_card")
    assignment = next(node for node in owner.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "page_texts"
                              for target in node.targets))
    decision = compile(ast.Module(body=[assignment], type_ignores=[]), "<manager-text-decision>", "exec")

    def run(pdf_bytes):
        calls.clear()
        item = {"kind": "pdf", "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii")}
        try:
            bridge["_prepare_pdf_item_off_main"](item)
            context = {"precomputed_page_texts": item.get(TEXT_KEY), "dest_path": item[PATH_KEY],
                       "extract_pdf_pages_text": count_extract}
            exec(decision, context)
            assert not any(context["page_texts"])
            return len(calls), sum(call["allow_qt"] for call in calls)
        finally:
            if item.get(PATH_KEY):
                os.remove(item[PATH_KEY])

    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = ("backend/pdf_manager.py", "backend/browser_bridge.py")
    sources = {
        "before": {path: subprocess.check_output(["git", "show", f"{BASELINE}:{path}"],
                                                  cwd=ROOT, text=True) for path in paths},
        "after": {path: (ROOT / path).read_text() for path in paths},
    }
    pipelines = {label: load_pipeline(label, source) for label, source in sources.items()}
    measurements = []
    with tempfile.TemporaryDirectory(prefix="incremento-empty-pdf-benchmark-") as folder:
        for pages in (1, 100, 500):
            path = Path(folder) / "synthetic.pdf"
            with fitz.open() as document:
                for _ in range(pages):
                    document.new_page()
                document.save(path)
            pdf_bytes = path.read_bytes()
            for label, pipeline in pipelines.items():
                samples, counts, qt_passes = [], [], []
                for _ in range(5):
                    started = perf_counter()
                    extractions, qt = pipeline(pdf_bytes)
                    samples.append(round((perf_counter() - started) * 1000, 3))
                    counts.append(extractions)
                    qt_passes.append(qt)
                measurements.append({"version": label, "pages": pages, "bytes": len(pdf_bytes),
                    "median_ms": round(statistics.median(samples), 3), "samples_ms": samples,
                    "extraction_passes_per_import": counts, "allow_qt_passes_per_import": qt_passes})
    args.output.write_text(json.dumps({"baseline_commit": BASELINE,
        "environment": {"python": platform.python_version(), "machine": platform.machine(),
                        "pymupdf": fitz.VersionBind, "poppler_available": bool(shutil.which("pdftotext"))},
        "scope": __doc__.strip(),
        "source_sha256": {label: {path: hashlib.sha256(text.encode()).hexdigest()
                                  for path, text in source.items()} for label, source in sources.items()},
        "results": measurements}, indent=2) + "\n")


if __name__ == "__main__":
    main()
