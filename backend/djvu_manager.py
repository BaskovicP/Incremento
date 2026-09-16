"""Bounded, offline DjVu conversion retaining the source's positioned text.

DjVuLibre renders images; PyMuPDF adds invisible Unicode text. Conversion owns
only temporary files and a new caller-provided output. Managed storage and Anki
note creation continue through pdf_manager's ImportOperation boundary.
"""
from __future__ import annotations

import math
from contextlib import nullcontext
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

try:
    from .deps import djvu_tools, djvulibre_instructions, pymupdf_instructions
    from .i18n import t
except ImportError:
    from deps import djvu_tools, djvulibre_instructions, pymupdf_instructions
    from i18n import t

_MAX_SOURCE_BYTES = 256 * 1024 * 1024
_MAX_PDF_BYTES = 1024 * 1024 * 1024
_MAX_TEXT_BYTES = 8 * 1024 * 1024
_MAX_PAGES = 5000
_MAX_ZONES = 100_000
_TOOL_TIMEOUT = 300
_KINDS = ("page", "column", "region", "para", "line", "word", "char")
_TOKEN = re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)', re.DOTALL)


class DjvuImportError(RuntimeError):
    """A safe, actionable import failure (including cancellation)."""


def is_djvu(path: str) -> bool:
    return Path(path).suffix.casefold() in {".djvu", ".djv"}


def _check_cancel(cancel_cb) -> None:
    if cancel_cb and cancel_cb():
        raise DjvuImportError(t("backend_djvu_cancelled"))


def _validate_snapshot(path: Path, cancel_cb=None) -> None:
    """Reject indirect directories and standalone external component includes."""
    with path.open("rb") as handle:
        header = handle.read(16)
        if header[:8] != b"AT&TFORM" or header[12:16] not in (b"DJVU", b"DJVM"):
            raise DjvuImportError(t("backend_djvu_invalid"))
        end = 12 + int.from_bytes(header[8:12], "big")
        if not 16 <= end <= path.stat().st_size:
            raise DjvuImportError(t("backend_djvu_invalid"))
        offset, directory_count, chunks = 16, 0, 0
        while offset < end:
            _check_cancel(cancel_cb)
            handle.seek(offset)
            chunk = handle.read(8)
            chunks += 1
            if len(chunk) != 8 or chunks > _MAX_ZONES:
                raise DjvuImportError(t("backend_djvu_invalid"))
            size = int.from_bytes(chunk[4:], "big")
            if offset + 8 + size > end:
                raise DjvuImportError(t("backend_djvu_invalid"))
            if chunk[:4] == b"INCL":
                raise DjvuImportError(t("backend_djvu_decode_failed"))
            if chunk[:4] == b"DIRM":
                directory_count += 1
                if size < 1 or not handle.read(1)[0] & 0x80:
                    raise DjvuImportError(t("backend_djvu_decode_failed"))
            offset += 8 + size + (size & 1)
        if header[12:16] == b"DJVM" and directory_count != 1:
            raise DjvuImportError(t("backend_djvu_invalid"))


def _run_tool(args, *, output_path, max_bytes, cancel_cb=None, capture_stdout=True) -> None:
    """Capture native output on disk; bound runtime and growth, reap on failure."""
    deadline = time.monotonic() + _TOOL_TIMEOUT
    with (open(output_path, "wb") if capture_stdout else nullcontext()) as output:
        process = subprocess.Popen(args, stdout=output if capture_stdout else subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        def output_size():
            path = Path(output_path)
            return path.stat().st_size if path.exists() else 0
        try:
            while True:
                _check_cancel(cancel_cb)
                if time.monotonic() >= deadline or output_size() > max_bytes:
                    raise DjvuImportError(t("backend_djvu_budget"))
                try:
                    result = process.wait(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if output_size() > max_bytes:
                raise DjvuImportError(t("backend_djvu_budget"))
            if result:
                raise DjvuImportError(t("backend_djvu_decode_failed"))
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def _quoted_text(token: str) -> str:
    # DjVu's C-style escapes encode bytes, including octal UTF-8 sequences.
    raw = bytearray()
    index = 1
    while index < len(token) - 1:
        char = token[index]
        index += 1
        if char != "\\":
            raw.extend(char.encode("utf-8"))
            continue
        char = token[index]
        index += 1
        if char in "01234567":
            digits = char
            while len(digits) < 3 and index < len(token) - 1 and token[index] in "01234567":
                digits += token[index]
                index += 1
            value = int(digits, 8)
            if value > 255:
                raise ValueError("invalid escape")
            raw.append(value)
        else:
            raw.extend({"n": b"\n", "r": b"\r", "t": b"\t", "b": b"\b", "f": b"\f"}.get(char, char.encode("utf-8")))
    return raw.decode("utf-8")


def _parse_page(data: str):
    """Parse data as bounded structural lists, never executable expressions."""
    if not data.strip() or data.strip() == "()":
        return None
    stack = []
    root = None
    position = 0
    count = 0
    while position < len(data):
        match = _TOKEN.match(data, position)
        if not match:
            if not data[position:].strip():
                break
            raise ValueError("invalid syntax")
        position = match.end()
        token = match[1]
        if token == "(":
            count += 1
            if len(stack) >= 8 or count > _MAX_ZONES:
                raise ValueError("too many zones")
            node = []
            if stack:
                stack[-1].append(node)
            elif root is not None:
                raise ValueError("multiple roots")
            else:
                root = node
            stack.append(node)
        elif token == ")":
            if not stack:
                raise ValueError("unbalanced list")
            stack.pop()
        elif not stack:
            raise ValueError("trailing token")
        else:
            stack[-1].append(_quoted_text(token) if token.startswith('"') else token)
    if stack or not root or root[0] != "page":
        raise ValueError("invalid page")

    def validate(node, parent=None):
        if len(node) < 5 or node[0] not in _KINDS:
            raise ValueError("invalid zone")
        box = tuple(int(value) for value in node[1:5])
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= 1_000_000 and 0 <= y0 < y1 <= 1_000_000):
            raise ValueError("invalid coordinates")
        if parent and not (parent[0] <= x0 < x1 <= parent[2] and parent[1] <= y0 < y1 <= parent[3]):
            raise ValueError("zone outside page")
        children = node[5:]
        if len(children) == 1 and isinstance(children[0], str):
            return box, [(box, children[0])]
        leaves = []
        for child in children:
            if not isinstance(child, list) or _KINDS.index(child[0]) <= _KINDS.index(node[0]):
                raise ValueError("invalid hierarchy")
            _, child_leaves = validate(child, box)
            leaves.extend(child_leaves)
        return box, leaves

    return validate(root)


def _overlay_text(page, parsed, font, fitz) -> None:
    if parsed is None:
        return
    (px0, py0, px1, py1), leaves = parsed
    sx, sy = page.rect.width / (px1 - px0), page.rect.height / (py1 - py0)
    page.insert_font(fontname="djvutext", fontbuffer=font.buffer)
    for (x0, y0, x1, y1), text in leaves:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines() or [text]
        height = (y1 - y0) * sy / len(lines)
        size = height / (font.ascender - font.descender)
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            if any(ord(char) < 32 for char in line) or any(not font.has_glyph(ord(char)) for char in line):
                raise ValueError("unsupported text")
            width = font.text_length(line, fontsize=size)
            scale = (x1 - x0) * sx / width
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError("invalid text width")
            origin = fitz.Point((x0 - px0) * sx, (py1 - y1) * sy + index * height + font.ascender * size)
            page.insert_text(origin, line, fontsize=size, fontname="djvutext", render_mode=3,
                             morph=(origin, fitz.Matrix(scale, 1)))


def convert_djvu_to_pdf(source_path: str, output_path: str, *, progress_cb=None, cancel_cb=None) -> None:
    """Create a PDF with the original image pages and selectable positioned text.

    Single-page and bundled DjVu are supported. Snapshotting only the selected
    file keeps indirect documents from loading neighboring files or URLs.
    """
    source, output = Path(source_path), Path(output_path)
    if output.exists() or output.is_symlink():
        raise DjvuImportError(t("backend_djvu_output_exists"))
    created_output = False
    succeeded = False
    try:
        _check_cancel(cancel_cb)
        with source.open("rb") as handle:
            if not source.is_file() or os.fstat(handle.fileno()).st_size > _MAX_SOURCE_BYTES:
                raise DjvuImportError(t("backend_djvu_budget"))
            header = handle.read(16)
            if len(header) != 16 or header[:8] != b"AT&TFORM" or header[12:16] not in (b"DJVU", b"DJVM"):
                raise DjvuImportError(t("backend_djvu_invalid"))
        tools = djvu_tools()
        if len(tools) != 2:
            raise DjvuImportError(t("backend_djvu_dependency", instructions=djvulibre_instructions()))
        try:
            import pymupdf as fitz
        except ImportError as exc:
            raise DjvuImportError(t("backend_djvu_pymupdf", instructions=pymupdf_instructions())) from exc
        with tempfile.TemporaryDirectory(prefix="incremento-djvu-") as directory:
            snapshot = Path(directory) / "source.djvu"
            with source.open("rb") as handle, snapshot.open("xb") as target:
                copied = 0
                while chunk := handle.read(1024 * 1024):
                    _check_cancel(cancel_cb)
                    copied += len(chunk)
                    if copied > _MAX_SOURCE_BYTES:
                        raise DjvuImportError(t("backend_djvu_budget"))
                    target.write(chunk)
            _validate_snapshot(snapshot, cancel_cb)
            raster = Path(directory) / "images.pdf"
            _run_tool([tools["ddjvu"], "-format=pdf", str(snapshot), str(raster)], output_path=raster,
                      max_bytes=_MAX_PDF_BYTES, cancel_cb=cancel_cb, capture_stdout=False)
            with fitz.open(raster) as doc:
                if not 0 < len(doc) <= _MAX_PAGES:
                    raise DjvuImportError(t("backend_djvu_budget"))
                font = fitz.Font("cjk")
                for index, page in enumerate(doc):
                    _check_cancel(cancel_cb)
                    text_path = Path(directory) / "text.txt"
                    _run_tool([tools["djvutxt"], f"--page={index + 1}", "--detail=word", str(snapshot)],
                              output_path=text_path, max_bytes=_MAX_TEXT_BYTES, cancel_cb=cancel_cb)
                    _overlay_text(page, _parse_page(text_path.read_text(encoding="utf-8")), font, fitz)
                    if progress_cb:
                        progress_cb(index + 1, len(doc))
                _check_cancel(cancel_cb)
                doc.subset_fonts()
                staged = Path(directory) / "converted.pdf"
                doc.save(str(staged), garbage=4, deflate=True)
                if staged.stat().st_size > _MAX_PDF_BYTES:
                    raise DjvuImportError(t("backend_djvu_budget"))
                _check_cancel(cancel_cb)
                with output.open("xb") as handle:
                    created_output = True
                    with staged.open("rb") as source_handle:
                        shutil.copyfileobj(source_handle, handle)
                succeeded = True
    except DjvuImportError:
        raise
    except Exception as exc:
        raise DjvuImportError(t("backend_djvu_invalid")) from exc
    finally:
        if created_output and not succeeded:
            output.unlink(missing_ok=True)


@dataclass
class PreparedDjvuPdf:
    directory: tempfile.TemporaryDirectory
    path: str
    page_texts: list[str]
    ocr_failed: bool = False

    def close(self) -> None:
        self.directory.cleanup()


def prepare_djvu_pdf(source_path: str, *, do_ocr=False, progress_cb=None, cancel_cb=None) -> PreparedDjvuPdf:
    """Run expensive conversion/OCR without holding Anki's collection queue."""
    try:
        from . import pdf_manager
    except ImportError:
        import pdf_manager
    directory = tempfile.TemporaryDirectory(prefix="incremento-djvu-import-")
    try:
        # Keep the original stem so missing-file relinking still works.
        path = str(Path(directory.name) / (Path(source_path).stem + ".pdf"))
        convert_djvu_to_pdf(source_path, path, progress_cb=progress_cb, cancel_cb=cancel_cb)
        texts = pdf_manager.extract_pdf_pages_text(path)
        ocr_failed = False
        if do_ocr and not any(text.strip() for text in texts):
            _check_cancel(cancel_cb)
            succeeded = pdf_manager.ocr_pdf_in_place(path, progress_cb=progress_cb)
            texts = pdf_manager.extract_pdf_pages_text(path) if succeeded else texts
            ocr_failed = not any(text.strip() for text in texts)
        _check_cancel(cancel_cb)
        return PreparedDjvuPdf(directory, path, texts, ocr_failed)
    except BaseException:
        directory.cleanup()
        raise
