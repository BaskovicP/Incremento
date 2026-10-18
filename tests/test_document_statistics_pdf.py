"""Count PDF pages with Anki's bundled Qt reader in its owning worker thread."""

import os
from pathlib import Path
import subprocess
import sys
from textwrap import dedent


def test_pdf_count_includes_blank_pages_without_optional_pdf_dependencies(tmp_path):
    # A tiny three-page PDF, including blank pages: text indexes cannot infer this total.
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >>"]
    objects += [b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Resources << >> >>"] * 3
    data = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(data)
    data += b"xref\n0 6\n0000000000 65535 f \n"
    data += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    (tmp_path / "blank.pdf").write_bytes(data)
    script = dedent(r'''
        import sys
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        from aqt.qt import QApplication
        from frontend.learning_stats import _document_pdf_pages
        app = QApplication([])
        sys.modules["fitz"] = sys.modules["pymupdf"] = None
        with ThreadPoolExecutor(max_workers=1) as worker:
            assert worker.submit(_document_pdf_pages, Path(sys.argv[1]) / "blank.pdf").result() == 3
            assert worker.submit(_document_pdf_pages, Path(sys.argv[1]) / "missing.pdf").result() is None
        ''')
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                            cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
