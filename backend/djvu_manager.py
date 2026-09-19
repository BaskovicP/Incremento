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
_SAMPLE_PAGES = 8
_SAMPLE_PDF_BYTES = 128 * 1024 * 1024
_RISKY_EXPANSION_RATIO = 10
_RISKY_PDF_BYTES = 250 * 1024 * 1024
COMPRESSION_PRESETS = (
    "mrc",
    "compact_color",
    "balanced",
    "small",
    "black_white",
    "original",
)
_COMPRESSION_ARGS = {
    "mrc": (),
    "compact_color": ("-scale=200", "-quality=80"),
    "original": (),
    "balanced": ("-scale=300", "-quality=85"),
    "small": ("-scale=200", "-quality=80"),
    "black_white": ("-mode=black",),
}
_KINDS = ("page", "column", "region", "para", "line", "word", "char")
_TOKEN = re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)', re.DOTALL)


class DjvuImportError(RuntimeError):
    """A safe, actionable import failure (including cancellation)."""


class _MrcUnavailable(DjvuImportError):
    """The document cannot expose the three image layers required by MRC."""


def is_djvu(path: str) -> bool:
    return Path(path).suffix.casefold() in {".djvu", ".djv"}


def _check_cancel(cancel_cb) -> None:
    if cancel_cb and cancel_cb():
        raise DjvuImportError(t("backend_djvu_cancelled"))


def _validate_snapshot(path: Path, cancel_cb=None) -> int:
    """Reject indirect directories and standalone external component includes."""
    with path.open("rb") as handle:
        header = handle.read(16)
        if header[:8] != b"AT&TFORM" or header[12:16] not in (b"DJVU", b"DJVM"):
            raise DjvuImportError(t("backend_djvu_invalid"))
        end = 12 + int.from_bytes(header[8:12], "big")
        if not 16 <= end <= path.stat().st_size:
            raise DjvuImportError(t("backend_djvu_invalid"))
        offset, directory_count, chunks = 16, 0, 0
        pages = int(header[12:16] == b"DJVU")
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
            if header[12:16] == b"DJVM" and chunk[:4] == b"FORM" and size >= 4:
                pages += handle.read(4) == b"DJVU"
            offset += 8 + size + (size & 1)
        if header[12:16] == b"DJVM" and directory_count != 1:
            raise DjvuImportError(t("backend_djvu_invalid"))
        if not 0 < pages <= _MAX_PAGES:
            raise DjvuImportError(t("backend_djvu_budget"))
        return pages


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
    stack: list[list] = []
    root: list | None = None
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
            node: list = []
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

    def validate(node, page_box=None):
        if len(node) < 5 or node[0] not in _KINDS:
            raise ValueError("invalid zone")
        box = tuple(int(value) for value in node[1:5])
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= 1_000_000 and 0 <= y0 < y1 <= 1_000_000):
            raise ValueError("invalid coordinates")
        if page_box and not (page_box[0] <= x0 < x1 <= page_box[2] and page_box[1] <= y0 < y1 <= page_box[3]):
            raise ValueError("zone outside page")
        children = node[5:]
        if len(children) == 1 and isinstance(children[0], str):
            return box, [(box, children[0])]
        leaves = []
        for child in children:
            if not isinstance(child, list) or _KINDS.index(child[0]) <= _KINDS.index(node[0]):
                raise ValueError("invalid hierarchy")
            # OCR words can extend beyond their line/paragraph boxes. Preserve
            # their absolute positions, enforcing the document page boundary.
            _, child_leaves = validate(child, page_box if page_box is not None else box)
            leaves.extend(child_leaves)
        return box, leaves

    return validate(root)


def _overlay_text(page, parsed, font, fitz) -> None:
    if parsed is None:
        return
    (px0, py0, px1, py1), leaves = parsed
    sx, sy = page.rect.width / (px1 - px0), page.rect.height / (py1 - py0)
    page.insert_font(fontname="djvutext", fontbuffer=font.buffer)
    # Batch ordinary words so final PDF deduplication scales with pages,
    # rather than hundreds of thousands of individual OCR text streams.
    shape = page.new_shape()
    for (x0, y0, x1, y1), text in leaves:
        lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines() or [text]
        height = (y1 - y0) * sy / len(lines)
        size = height / (font.ascender - font.descender)
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            needs_fallback = any(not font.has_glyph(ord(char)) for char in line)
            if any(ord(char) < 32 for char in line) or (
                needs_fallback and any(not font.has_glyph(ord(char), fallback=True) for char in line)
            ):
                raise ValueError("unsupported text")
            width = font.text_length(line, fontsize=size)
            scale = (x1 - x0) * sx / width
            if not math.isfinite(scale) or scale <= 0:
                raise ValueError("invalid text width")
            origin = fitz.Point((x0 - px0) * sx, (py1 - y1) * sy + index * height + font.ascender * size)
            if needs_fallback:
                shape.commit()
                # TextWriter embeds MuPDF's bundled fallback fonts; insert_text
                # alone would silently replace missing symbols with .notdef.
                # Measure the mixed fonts before fitting their invisible text
                # to the source box: fallback ascenders/descenders can differ.
                with fitz.open() as text_doc:
                    text_page = text_doc.new_page(width=width + 4 * size, height=10 * size)
                    writer = fitz.TextWriter(text_page.rect)
                    writer.append((size, 5 * size), line, font=font, fontsize=size)
                    writer.write_text(text_page, render_mode=3)
                    bounds = fitz.Rect()
                    for block in text_page.get_text("blocks"):
                        bounds |= fitz.Rect(block[:4])
                    target = fitz.Rect((x0 - px0) * sx, (py1 - y1) * sy + index * height,
                                       (x1 - px0) * sx, (py1 - y1) * sy + (index + 1) * height)
                    page.show_pdf_page(target, text_doc, clip=bounds, keep_proportion=False)
                shape = page.new_shape()
            else:
                shape.insert_text(origin, line, fontsize=size, fontname="djvutext", render_mode=3,
                                  morph=(origin, fitz.Matrix(scale, 1)))
    shape.commit()


def _compression_args(compression):
    if not isinstance(compression, str) or compression not in _COMPRESSION_ARGS:
        raise DjvuImportError(t("backend_djvu_invalid"))
    return _COMPRESSION_ARGS[compression]


def is_risky_pdf_expansion(source_bytes: int, expected_bytes: int) -> bool:
    """Return whether a projected PDF deserves an explicit size warning."""
    try:
        source = int(source_bytes)
        expected = int(expected_bytes)
    except (TypeError, ValueError):
        return False
    if source <= 0 or expected <= 0:
        return False
    return expected >= _RISKY_PDF_BYTES or expected >= source * _RISKY_EXPANSION_RATIO


def _dependencies():
    tools = djvu_tools()
    if len(tools) != 2:
        raise DjvuImportError(t("backend_djvu_dependency", instructions=djvulibre_instructions()))
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise DjvuImportError(t("backend_djvu_pymupdf", instructions=pymupdf_instructions())) from exc
    return tools, fitz


def _snapshot_source(source, snapshot, cancel_cb):
    _check_cancel(cancel_cb)
    with source.open("rb") as handle, snapshot.open("xb") as target:
        if not source.is_file() or os.fstat(handle.fileno()).st_size > _MAX_SOURCE_BYTES:
            raise DjvuImportError(t("backend_djvu_budget"))
        copied = 0
        while chunk := handle.read(1024 * 1024):
            _check_cancel(cancel_cb)
            copied += len(chunk)
            if copied > _MAX_SOURCE_BYTES:
                raise DjvuImportError(t("backend_djvu_budget"))
            target.write(chunk)
    return _validate_snapshot(snapshot, cancel_cb)


def _grayscale_images(page, fitz):
    # Bilevel scans already have efficient lossless encoding.
    for image in page.get_images():
        xref, _, width, height, bits = image[:5]
        if bits == 1:
            continue
        if width * height > 64_000_000:
            raise DjvuImportError(t("backend_djvu_budget"))
        pixmap = fitz.Pixmap(page.parent, xref)
        gray = fitz.Pixmap(fitz.csGRAY, pixmap)
        # Replace the stream in place. replace_image creates an extra image
        # resource whose differing Name key defeats PDF stream deduplication.
        page.parent.update_object(xref, f"<< /Type /XObject /Subtype /Image /Width {width} "
                                  f"/Height {height} /BitsPerComponent 8 /ColorSpace /DeviceGray >>")
        page.parent.update_stream(xref, gray.tobytes("jpeg", jpg_quality=80), compress=False)
        page.parent.xref_set_key(xref, "Filter", "/DCTDecode")


def _source_page_sizes(snapshot):
    """Read bounded INFO metadata from the already validated bundled file."""
    sizes: list[tuple[float, float] | None] = []
    with snapshot.open("rb") as handle:
        header = handle.read(16)
        end = 12 + int.from_bytes(header[8:12], "big")
        starts = [16] if header[12:16] == b"DJVU" else []
        if not starts:
            offset = 16
            while offset < end:
                handle.seek(offset)
                chunk = handle.read(12)
                size = int.from_bytes(chunk[4:8], "big")
                if chunk[:4] == b"FORM" and chunk[8:12] == b"DJVU":
                    starts.append(offset + 12)
                offset += 8 + size + (size & 1)
        for start in starts:
            handle.seek(start)
            chunk = handle.read(18)
            if chunk[:4] != b"INFO" or len(chunk) < 13:
                sizes.append(None)
                continue
            length = min(int.from_bytes(chunk[4:8], "big"), len(chunk) - 8)
            info = chunk[8:8 + length]
            if len(info) < 5:
                sizes.append(None)
                continue
            width, height = int.from_bytes(info[:2], "big"), int.from_bytes(info[2:4], "big")
            dpi = int.from_bytes(info[6:8], "little") if len(info) >= 8 and info[7] != 255 else 300
            if not 25 <= dpi <= 6000:
                dpi = 300
            if len(info) >= 10 and info[9] & 7 in (5, 6):
                width, height = height, width
            sizes.append((width * 72 / dpi, height * 72 / dpi) if width and height else None)
    return sizes


def _restore_page_size(page, size, fitz):
    # ddjvu rounds downsampled pixel sizes before deriving its PDF MediaBox.
    # Restore the source's physical dimensions and scale the image with it.
    if size is None:
        return
    width, height = size
    sx, sy = width / page.rect.width, height / page.rect.height
    if abs(sx - 1) < 1e-7 and abs(sy - 1) < 1e-7:
        return
    for xref in page.get_contents():
        data = page.parent.xref_stream(xref)
        transform = f"q {sx:.10f} 0 0 {sy:.10f} 0 0 cm\n".encode("ascii")
        page.parent.update_stream(xref, transform + data + b"\nQ")
    page.set_mediabox(fitz.Rect(0, 0, width, height))


def _convert_flattened_snapshot(snapshot, directory, tools, fitz, compression, *,
                                sample_pages=None, progress_cb=None, cancel_cb=None):
    raster = directory / "images.pdf"
    budget = _MAX_PDF_BYTES if sample_pages is None else min(_MAX_PDF_BYTES, _SAMPLE_PDF_BYTES)
    args = [tools["ddjvu"], "-format=pdf", *_compression_args(compression)]
    if sample_pages is not None:
        args.append("-page=" + ",".join(map(str, sample_pages)))
    _run_tool([*args, str(snapshot), str(raster)], output_path=raster,
              max_bytes=budget, cancel_cb=cancel_cb, capture_stdout=False)
    staged = directory / "converted.pdf"
    source_sizes = _source_page_sizes(snapshot) if compression != "original" else []
    with fitz.open(raster) as doc:
        if not 0 < len(doc) <= _MAX_PAGES or (sample_pages is not None and len(doc) != len(sample_pages)):
            raise DjvuImportError(t("backend_djvu_budget"))
        font = fitz.Font("cjk")
        for index, page in enumerate(doc):
            _check_cancel(cancel_cb)
            number = index + 1 if sample_pages is None else sample_pages[index]
            if number <= len(source_sizes):
                _restore_page_size(page, source_sizes[number - 1], fitz)
            if compression == "small":
                _grayscale_images(page, fitz)
            text_path = directory / "text.txt"
            _run_tool([tools["djvutxt"], f"--page={number}", "--detail=word", str(snapshot)],
                      output_path=text_path, max_bytes=_MAX_TEXT_BYTES, cancel_cb=cancel_cb)
            _overlay_text(page, _parse_page(text_path.read_text(encoding="utf-8")), font, fitz)
            if progress_cb:
                progress_cb(index + 1, len(doc))
        _check_cancel(cancel_cb)
        doc.subset_fonts()
        doc.save(str(staged), garbage=4, deflate=True)
    if staged.stat().st_size > budget:
        raise DjvuImportError(t("backend_djvu_budget"))
    _check_cancel(cancel_cb)
    return staged


def _render_mrc_layer(snapshot, output, tools, options, *, pages, budget, cancel_cb):
    args = [tools["ddjvu"], "-format=pdf", *options]
    if pages is not None:
        args.append("-page=" + ",".join(map(str, pages)))
    try:
        _run_tool([*args, str(snapshot), str(output)], output_path=output,
                  max_bytes=budget, cancel_cb=cancel_cb, capture_stdout=False)
    except DjvuImportError as exc:
        _check_cancel(cancel_cb)
        raise _MrcUnavailable(str(exc)) from exc


def _single_page_image(document, page_index):
    images = document[page_index].get_images(full=True)
    xrefs = list(dict.fromkeys(int(image[0]) for image in images if int(image[0]) > 0))
    if len(xrefs) != 1:
        raise _MrcUnavailable("DjVu page does not expose one bounded image layer")
    info = document.extract_image(xrefs[0])
    width = int(info.get("width") or 0)
    height = int(info.get("height") or 0)
    image = info.get("image")
    if not image or width <= 0 or height <= 0 or width * height > 64_000_000:
        raise _MrcUnavailable("DjVu page image layer is invalid or too large")
    return bytes(image), width, height


def _convert_mrc_snapshot(snapshot, directory, tools, fitz, *,
                          sample_pages=None, progress_cb=None, cancel_cb=None):
    """Build a mixed-raster PDF from a DjVu background and bilevel mask.

    The background is a small JPEG. A solid black foreground receives the
    native-resolution transparency mask, so text and line art stay sharp while
    avoiding a full-page, full-resolution colour JPEG for every page.
    """
    budget = _MAX_PDF_BYTES if sample_pages is None else min(_MAX_PDF_BYTES, _SAMPLE_PDF_BYTES)
    background_path = directory / "mrc-background.pdf"
    mask_path = directory / "mrc-mask.pdf"
    _render_mrc_layer(
        snapshot,
        background_path,
        tools,
        ("-mode=background", "-scale=120", "-quality=75"),
        pages=sample_pages,
        budget=budget,
        cancel_cb=cancel_cb,
    )
    _render_mrc_layer(
        snapshot,
        mask_path,
        tools,
        ("-mode=mask",),
        pages=sample_pages,
        budget=budget,
        cancel_cb=cancel_cb,
    )

    staged = directory / "converted.pdf"
    source_sizes = _source_page_sizes(snapshot)
    with (
        fitz.open(background_path) as backgrounds,
        fitz.open(mask_path) as masks,
        fitz.open() as output,
    ):
        count = len(backgrounds)
        if not 0 < count <= _MAX_PAGES or len(masks) != count:
            raise _MrcUnavailable("DjVu image layers have different page counts")
        if sample_pages is not None and count != len(sample_pages):
            raise _MrcUnavailable("DjVu image layers omit a sampled page")

        font = fitz.Font("cjk")
        black_layers: dict[tuple[int, int], bytes] = {}
        for index in range(count):
            _check_cancel(cancel_cb)
            number = index + 1 if sample_pages is None else sample_pages[index]
            background, _, _ = _single_page_image(backgrounds, index)
            mask, mask_width, mask_height = _single_page_image(masks, index)

            size = source_sizes[number - 1] if number <= len(source_sizes) else None
            if size is None:
                source_page = masks[index]
                size = (float(source_page.rect.width), float(source_page.rect.height))
            page = output.new_page(width=size[0], height=size[1])
            page.insert_image(page.rect, stream=background, keep_proportion=False, overlay=False)

            layer_size = (mask_width, mask_height)
            foreground = black_layers.get(layer_size)
            if foreground is None:
                black_pixmap = fitz.Pixmap(
                    fitz.csGRAY,
                    fitz.IRect(0, 0, mask_width, mask_height),
                    False,
                )
                black_pixmap.clear_with(0)
                foreground = black_pixmap.tobytes("png")
                black_layers[layer_size] = foreground

            mask_pixmap = fitz.Pixmap(mask)
            try:
                if mask_pixmap.alpha or not mask_pixmap.colorspace or mask_pixmap.colorspace.n != 1:
                    gray = fitz.Pixmap(fitz.csGRAY, mask_pixmap)
                    mask_pixmap = gray
                mask_pixmap.invert_irect(mask_pixmap.irect)
                alpha_mask = mask_pixmap.tobytes("png")
            finally:
                mask_pixmap = None
            foreground_xref = page.insert_image(
                page.rect,
                stream=foreground,
                mask=alpha_mask,
                keep_proportion=False,
                overlay=True,
            )
            mask_kind, mask_reference = output.xref_get_key(foreground_xref, "SMask")
            if mask_kind != "xref":
                raise _MrcUnavailable("DjVu foreground did not create a PDF soft mask")
            output.xref_set_key(int(mask_reference.split()[0]), "ColorSpace", "/DeviceGray")

            text_path = directory / "text.txt"
            _run_tool(
                [tools["djvutxt"], f"--page={number}", "--detail=word", str(snapshot)],
                output_path=text_path,
                max_bytes=_MAX_TEXT_BYTES,
                cancel_cb=cancel_cb,
            )
            _overlay_text(page, _parse_page(text_path.read_text(encoding="utf-8")), font, fitz)
            if progress_cb:
                progress_cb(index + 1, count)

        _check_cancel(cancel_cb)
        output.subset_fonts()
        output.save(str(staged), garbage=4, deflate=True)
    if staged.stat().st_size > budget:
        raise DjvuImportError(t("backend_djvu_budget"))
    _check_cancel(cancel_cb)
    return staged


def _convert_snapshot(snapshot, directory, tools, fitz, compression, *,
                      sample_pages=None, progress_cb=None, cancel_cb=None):
    if compression == "mrc":
        try:
            return _convert_mrc_snapshot(
                snapshot,
                directory,
                tools,
                fitz,
                sample_pages=sample_pages,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
        except _MrcUnavailable:
            _check_cancel(cancel_cb)
            for name in ("mrc-background.pdf", "mrc-mask.pdf", "converted.pdf"):
                (directory / name).unlink(missing_ok=True)
            return _convert_flattened_snapshot(
                snapshot,
                directory,
                tools,
                fitz,
                "compact_color",
                sample_pages=sample_pages,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
    return _convert_flattened_snapshot(
        snapshot,
        directory,
        tools,
        fitz,
        compression,
        sample_pages=sample_pages,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
    )


def convert_djvu_to_pdf(source_path: str, output_path: str, *, compression="original",
                        progress_cb=None, cancel_cb=None) -> None:
    """Create a compressed PDF retaining the source's positioned text.

    Single-page and bundled DjVu are supported. Snapshotting only the selected
    file keeps indirect documents from loading neighboring files or URLs.
    """
    source, output = Path(source_path), Path(output_path)
    _compression_args(compression)
    if output.exists() or output.is_symlink():
        raise DjvuImportError(t("backend_djvu_output_exists"))
    created_output = False
    succeeded = False
    try:
        _check_cancel(cancel_cb)
        tools, fitz = _dependencies()
        with tempfile.TemporaryDirectory(prefix="incremento-djvu-") as directory:
            snapshot = Path(directory) / "source.djvu"
            _snapshot_source(source, snapshot, cancel_cb)
            staged = _convert_snapshot(snapshot, Path(directory), tools, fitz, compression,
                                       progress_cb=progress_cb, cancel_cb=cancel_cb)
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


@dataclass(frozen=True)
class CompressionEstimate:
    expected_bytes: int
    low_bytes: int
    high_bytes: int
    previews: tuple[bytes, ...]


@dataclass(frozen=True)
class DjvuCompressionPreview:
    source_bytes: int
    page_count: int
    sample_pages: tuple[int, ...]
    estimates: dict[str, CompressionEstimate]


def compression_sample_pages(page_count):
    if not 0 < page_count <= _MAX_PAGES:
        raise DjvuImportError(t("backend_djvu_budget"))
    if page_count <= _SAMPLE_PAGES:
        return tuple(range(1, page_count + 1))
    interior = _SAMPLE_PAGES - 2
    return (1, *(2 + int((i + .5) * (page_count - 2) / interior) for i in range(interior)), page_count)


def project_compressed_size(page_bytes, page_count, shared_bytes):
    if page_count == len(page_bytes):
        return sum(page_bytes) + shared_bytes
    # Covers are measured once; only the evenly spread interior sample is
    # extrapolated. Otherwise large colour covers dominate a small sample.
    interior_mean = sum(page_bytes[1:-1]) / (len(page_bytes) - 2)
    return round(page_bytes[0] + page_bytes[-1] + interior_mean * (page_count - 2) + shared_bytes)


def estimate_djvu_compression(source_path: str, *, progress_cb=None, cancel_cb=None):
    """Measure the actual encoder on at most eight pages; never run new OCR.

    The six modes share one immutable snapshot. All files are temporary;
    returned PNG bytes and size estimates are bounded plain worker data.
    """
    deadline = time.monotonic() + 120

    def cancelled():
        if time.monotonic() > deadline:
            raise DjvuImportError(t("backend_djvu_budget"))
        return bool(cancel_cb and cancel_cb())

    try:
        _check_cancel(cancelled)
        tools, fitz = _dependencies()
        with tempfile.TemporaryDirectory(prefix="incremento-djvu-estimate-") as directory:
            snapshot = Path(directory) / "source.djvu"
            count = _snapshot_source(Path(source_path), snapshot, cancelled)
            pages = compression_sample_pages(count)
            estimates = {}
            for mode_index, mode in enumerate(COMPRESSION_PRESETS):
                mode_dir = Path(directory) / mode
                mode_dir.mkdir()
                def progress(current, total):
                    if progress_cb:
                        progress_cb(mode_index * len(pages) + current, len(COMPRESSION_PRESETS) * len(pages))
                pdf = _convert_snapshot(snapshot, mode_dir, tools, fitz, mode, sample_pages=pages,
                                        progress_cb=progress, cancel_cb=cancelled)
                size = pdf.stat().st_size
                with fitz.open(pdf) as doc:
                    page_sizes, previews = [], []
                    for page in doc:
                        _check_cancel(cancelled)
                        images = page.get_images()
                        if any(image[2] * image[3] > 64_000_000 for image in images):
                            raise DjvuImportError(t("backend_djvu_budget"))
                        xrefs = {image[0] for image in images} | set(page.get_contents())
                        page_sizes.append(sum(len(doc.xref_stream_raw(xref) or b"") for xref in xrefs))
                        scale = min(900 / page.rect.width, 1200 / page.rect.height)
                        previews.append(page.get_pixmap(matrix=fitz.Matrix(scale, scale)).tobytes("png"))
                    shared = max(0, size - sum(page_sizes))
                    expected = size if count == len(pages) else project_compressed_size(page_sizes, count, shared)
                    # Sampling and font/structure overhead are uncertain. This
                    # is a practical range, not a statistical confidence bound.
                    margin = 0 if count == len(pages) else max(1024 * 1024, round(expected * .3))
                    estimates[mode] = CompressionEstimate(expected, max(1, expected - margin),
                                                         expected + margin, tuple(previews))
                shutil.rmtree(mode_dir)
            return DjvuCompressionPreview(snapshot.stat().st_size, count, pages, estimates)
    except DjvuImportError:
        raise
    except Exception as exc:
        raise DjvuImportError(t("backend_djvu_invalid")) from exc


@dataclass
class PreparedDjvuPdf:
    directory: tempfile.TemporaryDirectory
    path: str
    page_texts: list[str]
    ocr_failed: bool = False

    def close(self) -> None:
        self.directory.cleanup()


def prepare_djvu_pdf(source_path: str, *, do_ocr=False, compression="original", progress_cb=None, cancel_cb=None) -> PreparedDjvuPdf:
    """Run expensive conversion/OCR without holding Anki's collection queue."""
    try:
        from . import pdf_manager
    except ImportError:
        import pdf_manager
    directory = tempfile.TemporaryDirectory(prefix="incremento-djvu-import-")
    try:
        # Keep the original stem so missing-file relinking still works.
        path = str(Path(directory.name) / (Path(source_path).stem + ".pdf"))
        convert_djvu_to_pdf(source_path, path, compression=compression, progress_cb=progress_cb, cancel_cb=cancel_cb)
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
