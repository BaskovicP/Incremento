"""DjVu import must preserve text and geometry without changing source images.

Native DjVuLibre processes are the boundary fake; PDFs and their text/rendering
are real PyMuPDF documents. All artifacts live in this test's temporary root.
"""
import importlib
from pathlib import Path
import sys
import shutil

import pytest

# conftest exposes backend/statistics.py as a top-level module. PyMuPDF needs
# the standard library module instead; restore the harness immediately.
_original_statistics = sys.modules.pop("statistics", None)
_original_path = sys.path[:]
try:
    sys.path[:] = [p for p in sys.path if Path(p).resolve().name != "backend"]
    import pymupdf as fitz
finally:
    sys.path[:] = _original_path
    sys.modules.pop("statistics", None)
    if _original_statistics is not None:
        sys.modules["statistics"] = _original_statistics


TEXT = '(page 0 0 600 800 (line 30 700 450 730 (word 30 700 120 730 "Hello") (word 150 700 330 730 "κόσμος中文")))'


def manager():
    return importlib.import_module("djvu_manager")


def fake_decoder(monkeypatch, tmp_path, texts):
    source = tmp_path / 'book with "quotes".djvu'
    source.write_bytes(b"AT&TFORM\x00\x00\x00\x04DJVU")
    raster = tmp_path / "raster.pdf"
    with fitz.open() as doc:
        for _ in texts:
            page = doc.new_page(width=300, height=400)
            page.draw_rect(fitz.Rect(10, 10, 290, 390), color=(0, 0, 1))
        doc.save(raster)
    calls = []

    def run(args, *, output_path, max_bytes, cancel_cb=None, capture_stdout=True):
        calls.append(args)
        if args[0] == "ddjvu":
            Path(output_path).write_bytes(raster.read_bytes())
        else:
            number = int(next(arg for arg in args if arg.startswith("--page=")).split("=")[1])
            Path(output_path).write_text(texts[number - 1], encoding="utf-8")

    monkeypatch.setattr(manager(), "_run_tool", run)
    monkeypatch.setattr(manager(), "djvu_tools", lambda: {"ddjvu": "ddjvu", "djvutxt": "djvutxt"})
    return source, raster, calls


def test_conversion_keeps_unicode_text_at_source_word_positions_and_images_unchanged(monkeypatch, tmp_path):
    source, raster, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    before = source.read_bytes()
    output = tmp_path / "converted.pdf"

    manager().convert_djvu_to_pdf(str(source), str(output))

    with fitz.open(output) as doc, fitz.open(raster) as original:
        assert doc[0].get_text().split() == ["Hello", "κόσμος中文"]
        box = doc[0].search_for("Hello")[0]
        assert tuple(box) == pytest.approx((15, 35, 60, 50), abs=0.2)
        assert doc[0].get_pixmap().samples == original[0].get_pixmap().samples
    assert source.read_bytes() == before
    assert all(str(source) not in call for call in calls)


def test_blank_page_does_not_shift_later_pages_text(monkeypatch, tmp_path):
    source, _, _ = fake_decoder(monkeypatch, tmp_path, ["", TEXT, "()"])
    output = tmp_path / "converted.pdf"
    manager().convert_djvu_to_pdf(str(source), str(output))
    with fitz.open(output) as doc:
        assert [page.get_text().split() for page in doc] == [[], ["Hello", "κόσμος中文"], []]


@pytest.mark.parametrize("enclosing_kind", ["line", "para"])
def test_word_outside_enclosing_ocr_zone_keeps_its_position_within_page(monkeypatch, tmp_path, enclosing_kind):
    text = f'(page 0 0 600 800 ({enclosing_kind} 30 700 450 730 (word 10 680 25 720 "x")))'
    source, raster, _ = fake_decoder(monkeypatch, tmp_path, [text])
    before = source.read_bytes()
    output = tmp_path / "converted.pdf"

    manager().convert_djvu_to_pdf(str(source), str(output))

    with fitz.open(output) as doc, fitz.open(raster) as original:
        assert doc[0].get_text().strip() == "x"
        assert tuple(doc[0].search_for("x")[0]) == pytest.approx((5, 40, 12.5, 60), abs=0.2)
        assert doc[0].get_pixmap().samples == original[0].get_pixmap().samples
    assert source.read_bytes() == before


@pytest.mark.parametrize("label, bottom, top", [("Next►", 700, 730), ("►", 0, 30)])
def test_unicode_symbol_uses_fallback_font_and_remains_selectable_and_invisible(monkeypatch, tmp_path, label, bottom, top):
    text = f'(page 0 0 600 800 (word 30 {bottom} 330 {top} "{label}"))'
    source, raster, _ = fake_decoder(monkeypatch, tmp_path, [text])
    output = tmp_path / "converted.pdf"

    manager().convert_djvu_to_pdf(str(source), str(output))

    with fitz.open(output) as doc, fitz.open(raster) as original:
        assert doc[0].get_text().strip() == label
        # Mixed fonts may return adjacent search rectangles for the same word.
        box = fitz.Rect()
        for match in doc[0].search_for(label):
            box |= match
        assert tuple(box) == pytest.approx((15, (800 - top) / 2, 165, (800 - bottom) / 2), abs=0.2)
        assert doc[0].get_pixmap().samples == original[0].get_pixmap().samples


@pytest.mark.parametrize("text", [
    '(page 0 0 0 800 "bad")',
    '(page 0 0 600 800 (word -1 0 20 30 "bad"))',
    '(page 0 0 600 800 (line 30 700 450 730 (word 590 700 610 730 "bad")))',
    '(page 0 0 600 800 (line 30 700 450 730 (word 30 790 50 810 "bad")))',
    '(page 0 0 600 800 (word 30 700 50 730 "\U0010ffff"))',
    '(page 0 0 600 800 (word 10 20 30 40 "unfinished))',
    '(page 0 0 600 800 (word 10 20 30 40 "ok")) unexpected',
])
def test_invalid_text_layer_fails_without_partial_pdf_or_changed_source(monkeypatch, tmp_path, text):
    source, _, _ = fake_decoder(monkeypatch, tmp_path, [text])
    before = source.read_bytes()
    output = tmp_path / "converted.pdf"
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(output))
    assert not output.exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("include_symbol", [False, True])
def test_dense_ocr_page_has_bounded_pdf_streams_and_preserves_reading_order(monkeypatch, tmp_path, include_symbol):
    labels = ["►" if include_symbol and index == 100 else f"word{index}" for index in range(200)]
    words = []
    for index, label in enumerate(labels):
        x, y = 10 + index % 10 * 58, 760 - index // 10 * 36
        width = 10 if label == "►" else 50
        words.append(f'(word {x} {y} {x + width} {y + 30} "{label}")')
    source, _, _ = fake_decoder(monkeypatch, tmp_path, [f'(page 0 0 600 800 {" ".join(words)})'])
    output = tmp_path / "converted.pdf"

    manager().convert_djvu_to_pdf(str(source), str(output))

    with fitz.open(output) as doc:
        assert doc[0].get_text().split() == labels
        # Stream deduplication at final save must not compare one object per
        # OCR word across a whole book. A page needs only a few text batches.
        assert len(doc[0].get_contents()) <= 4


def test_existing_output_is_never_overwritten(monkeypatch, tmp_path):
    source, _, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    output = tmp_path / "converted.pdf"
    output.write_bytes(b"keep me")
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(output))
    assert output.read_bytes() == b"keep me"
    assert calls == []


def test_cancellation_leaves_no_output(monkeypatch, tmp_path):
    source, _, _ = fake_decoder(monkeypatch, tmp_path, [TEXT])
    output = tmp_path / "converted.pdf"
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(output), cancel_cb=lambda: True)
    assert not output.exists()


def test_final_pdf_budget_is_checked_before_publishing_destination(monkeypatch, tmp_path):
    source, raster, _ = fake_decoder(monkeypatch, tmp_path, [TEXT])
    output = tmp_path / "converted.pdf"
    # The image-only native intermediate fits this budget. Adding text/fonts
    # exceeds it and must prevent the destination being published.
    monkeypatch.setattr(manager(), "_MAX_PDF_BYTES", raster.stat().st_size + 512)
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(output))
    assert not output.exists()
    assert source.exists()


def test_partial_copy_failure_removes_only_new_destination(monkeypatch, tmp_path):
    source, _, _ = fake_decoder(monkeypatch, tmp_path, [TEXT])
    before = source.read_bytes()
    output = tmp_path / "converted.pdf"
    def fail_copy(source_handle, target):
        target.write(b"partial")
        raise OSError("disk full")
    monkeypatch.setattr(manager().shutil, "copyfileobj", fail_copy)
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(output))
    assert not output.exists()
    assert source.read_bytes() == before


def test_native_output_budget_is_enforced(tmp_path):
    output = tmp_path / "out.txt"
    with pytest.raises(manager().DjvuImportError):
        manager()._run_tool([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'12345')"],
                            output_path=output, max_bytes=4)


def test_native_timeout_terminates_and_reaps_process(monkeypatch, tmp_path):
    import subprocess
    original = subprocess.Popen
    children = []
    def launch(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(manager().subprocess, "Popen", launch)
    monkeypatch.setattr(manager(), "_TOOL_TIMEOUT", 0)
    with pytest.raises(manager().DjvuImportError):
        manager()._run_tool([sys.executable, "-c", "pass"], output_path=tmp_path / "out.txt", max_bytes=10)
    assert len(children) == 1 and children[0].poll() is not None


def test_selected_ocr_reuses_existing_djvu_text_instead_of_recognizing_again(monkeypatch, tmp_path):
    from unittest.mock import Mock
    import pdf_manager
    source, _, _ = fake_decoder(monkeypatch, tmp_path, [TEXT])
    ocr = Mock()
    monkeypatch.setattr(pdf_manager, "ocr_pdf_in_place", ocr)
    prepared = manager().prepare_djvu_pdf(str(source), do_ocr=True)
    try:
        assert [text.split() for text in prepared.page_texts] == [["Hello", "κόσμος中文"]]
        assert not prepared.ocr_failed
        ocr.assert_not_called()
        directory = Path(prepared.directory.name)
        assert directory.exists()
    finally:
        prepared.close()
    assert not directory.exists()


def test_image_only_djvu_runs_selected_ocr_before_import(monkeypatch, tmp_path):
    import pdf_manager
    source, _, _ = fake_decoder(monkeypatch, tmp_path, [""])
    calls = []
    def ocr(path, progress_cb=None):
        calls.append(path)
        with fitz.open(path) as doc:
            doc[0].insert_text((30, 30), "Recognized text")
            replacement = Path(path).with_suffix(".ocr.pdf")
            doc.save(replacement)
        replacement.replace(path)
        return True
    monkeypatch.setattr(pdf_manager, "ocr_pdf_in_place", ocr)
    prepared = manager().prepare_djvu_pdf(str(source), do_ocr=True)
    try:
        assert calls == [prepared.path]
        assert prepared.page_texts[0].strip() == "Recognized text"
    finally:
        prepared.close()


def test_missing_decoder_explains_required_dependency(monkeypatch, tmp_path):
    source = tmp_path / "book.djvu"
    source.write_bytes(b"AT&TFORM\x00\x00\x00\x04DJVU")
    monkeypatch.setattr(manager(), "djvu_tools", lambda: {})
    with pytest.raises(manager().DjvuImportError, match="DjVuLibre"):
        manager().convert_djvu_to_pdf(str(source), str(tmp_path / "out.pdf"))


def test_invalid_signature_is_rejected_before_native_decoder(monkeypatch, tmp_path):
    source, _, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    source.write_bytes(b"not a DjVu document")
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(tmp_path / "out.pdf"))
    assert calls == []


@pytest.mark.parametrize("kind, chunk", [(b"DJVM", b"DIRM\x00\x00\x00\x01\x01\x00"),
                                        (b"DJVU", b"INCL\x00\x00\x00\x04/abs")])
def test_external_component_documents_are_rejected_before_native_decoder(monkeypatch, tmp_path, kind, chunk):
    source, _, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    # Indirect DIRM flag, or an external INCL in a standalone page. Neither
    # may cause DjVuLibre to read an unselected neighboring/absolute file.
    size = 4 + len(chunk)
    source.write_bytes(b"AT&TFORM" + size.to_bytes(4, "big") + kind + chunk)
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(tmp_path / "out.pdf"))
    assert calls == []


def test_coarse_line_text_and_escaped_quotes_are_preserved(monkeypatch, tmp_path):
    text = r'(page 0 0 600 800 (line 30 700 450 730 "A \"quote\" and \\slash"))'
    source, _, _ = fake_decoder(monkeypatch, tmp_path, [text])
    output = tmp_path / "converted.pdf"
    manager().convert_djvu_to_pdf(str(source), str(output))
    with fitz.open(output) as doc:
        assert doc[0].get_text().strip() == 'A "quote" and \\slash'


@pytest.mark.skipif(not shutil.which("ddjvu") or not shutil.which("djvutxt"), reason="DjVuLibre is optional")
def test_real_bundled_djvu_preserves_unicode_text_and_blank_page_order(tmp_path):
    source = Path(__file__).parent / "fixtures/djvu/text_and_blank.djvu"
    before = source.read_bytes()
    output = tmp_path / "book.pdf"
    progress = []
    manager().convert_djvu_to_pdf(str(source), str(output), progress_cb=lambda *args: progress.append(args))
    with fitz.open(output) as doc:
        assert [page.get_text().split() for page in doc] == [[], ["Hello", "κόσμος中文"], []]
        assert tuple(doc[1].search_for("Hello")[0]) == pytest.approx((7.2, 16.8, 28.8, 24), abs=0.2)
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert source.read_bytes() == before


@pytest.mark.parametrize("compression, options", [
    ("original", []),
    ("balanced", ["-scale=300", "-quality=85"]),
    ("compact_color", ["-scale=200", "-quality=80"]),
    ("small", ["-scale=200", "-quality=80"]),
    ("black_white", ["-mode=black"]),
])
def test_compression_choice_reaches_decoder_and_preserves_positioned_text(monkeypatch, tmp_path, compression, options):
    source, _, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    output = tmp_path / "compressed.pdf"
    manager().convert_djvu_to_pdf(str(source), str(output), compression=compression)
    assert calls[0][1:-2] == ["-format=pdf", *options]
    with fitz.open(output) as doc:
        assert doc[0].get_text().split() == ["Hello", "κόσμος中文"]
        assert tuple(doc[0].search_for("Hello")[0]) == pytest.approx((15, 35, 60, 50), abs=0.2)


def test_mrc_uses_jpeg_background_and_compact_black_masked_foreground(monkeypatch, tmp_path):
    source = tmp_path / "layered.djvu"
    source.write_bytes(b"AT&TFORM\x00\x00\x00\x04DJVU")
    calls = []

    def image_pdf(path, *, gray=False):
        with fitz.open() as doc:
            page = doc.new_page(width=300, height=400)
            colorspace = fitz.csGRAY if gray else fitz.csRGB
            pixmap = fitz.Pixmap(colorspace, fitz.IRect(0, 0, 600, 800), False)
            pixmap.clear_with(255)
            if gray:
                for y in range(80, 120):
                    for x in range(60, 260):
                        pixmap.set_pixel(x, y, (0,))
            else:
                for y in range(80, 120):
                    for x in range(60, 260):
                        pixmap.set_pixel(x, y, (15, 45, 180))
            page.insert_image(page.rect, pixmap=pixmap)
            doc.save(path)

    def run(args, *, output_path, max_bytes, cancel_cb=None, capture_stdout=True):
        calls.append(args)
        if args[0] == "djvutxt":
            Path(output_path).write_text(TEXT, encoding="utf-8")
            return
        image_pdf(output_path, gray="-mode=mask" in args)

    monkeypatch.setattr(manager(), "_run_tool", run)
    monkeypatch.setattr(manager(), "djvu_tools", lambda: {"ddjvu": "ddjvu", "djvutxt": "djvutxt"})
    output = tmp_path / "mrc.pdf"

    manager().convert_djvu_to_pdf(str(source), str(output), compression="mrc")

    decoder_calls = [call for call in calls if call[0] == "ddjvu"]
    assert any("-mode=background" in call and "-scale=120" in call for call in decoder_calls)
    assert any("-mode=mask" in call for call in decoder_calls)
    assert not any("-mode=foreground" in call for call in decoder_calls)
    with fitz.open(output) as doc:
        images = doc[0].get_images(full=True)
        assert len(images) == 2
        smasks = [image[1] for image in images if image[1] > 0]
        assert len(smasks) == 1
        # Soft masks must be DeviceGray. Poppler rejects an ICC-based image in
        # /SMask even if MuPDF accepts it.
        assert doc.xref_get_key(smasks[0], "ColorSpace")[1] == "/DeviceGray"
        assert doc[0].get_text().split() == ["Hello", "κόσμος中文"]
        assert tuple(doc[0].search_for("Hello")[0]) == pytest.approx((15, 35, 60, 50), abs=0.2)
        rendered = doc[0].get_pixmap()
        assert max(rendered.pixel(50, 50)[:3]) < 20
        assert min(rendered.pixel(200, 200)[:3]) > 240


def test_mrc_falls_back_to_compact_colour_when_layers_are_unavailable(monkeypatch, tmp_path):
    source, _, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    output = tmp_path / "fallback.pdf"

    manager().convert_djvu_to_pdf(str(source), str(output), compression="mrc")

    decoder_calls = [call for call in calls if call[0] == "ddjvu"]
    assert len(decoder_calls) == 3
    assert decoder_calls[-1][1:-2] == ["-format=pdf", "-scale=200", "-quality=80"]
    with fitz.open(output) as doc:
        assert doc[0].get_text().split() == ["Hello", "κόσμος中文"]


@pytest.mark.parametrize("source, expected, risky", [
    (17 * 2**20, 60 * 2**20, False),
    (17 * 2**20, 170 * 2**20, True),
    (40 * 2**20, 250 * 2**20, True),
])
def test_expansion_warning_uses_ratio_or_absolute_size(source, expected, risky):
    assert manager().is_risky_pdf_expansion(source, expected) is risky


@pytest.mark.parametrize("compression", ["unknown", "-quality=1", None, [], 1])
def test_invalid_compression_is_rejected_before_creating_output(monkeypatch, tmp_path, compression):
    source, _, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    output = tmp_path / "compressed.pdf"
    with pytest.raises(manager().DjvuImportError):
        manager().convert_djvu_to_pdf(str(source), str(output), compression=compression)
    assert not calls
    assert not output.exists()


def test_small_preset_converts_page_image_to_grayscale_without_moving_text(monkeypatch, tmp_path):
    source, raster, _ = fake_decoder(monkeypatch, tmp_path, [TEXT])
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=400)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 600, 800), False)
        pix.clear_with(120)
        image = page.insert_image(page.rect, pixmap=pix)
        # Native ddjvu images carry a Name entry, unlike insert_image output.
        doc.xref_set_key(image, "Name", "/Im1")
        doc.save(raster)
    output = tmp_path / "gray.pdf"
    manager().convert_djvu_to_pdf(str(source), str(output), compression="small")
    with fitz.open(output) as doc:
        assert fitz.Pixmap(doc, doc[0].get_images()[0][0]).colorspace.n == 1
        assert doc[0].get_images()[0][8] == "DCTDecode"
        # One visible scan must not leave a second, unused full-page JPEG
        # embedded in the PDF: that doubles the Small preset's image payload.
        assert len({image[0] for image in doc[0].get_images()}) == 1
        assert tuple(doc[0].search_for("Hello")[0]) == pytest.approx((15, 35, 60, 50), abs=0.2)


@pytest.mark.skipif(not shutil.which("ddjvu") or not shutil.which("djvutxt"), reason="DjVuLibre is optional")
@pytest.mark.parametrize("compression", ["mrc", "balanced", "compact_color", "small", "black_white"])
def test_real_compressed_djvu_keeps_page_dimensions_and_ocr_coordinates(tmp_path, compression):
    source = Path(__file__).parent / "fixtures/djvu/text_and_blank.djvu"
    output = tmp_path / "book.pdf"
    manager().convert_djvu_to_pdf(str(source), str(output), compression=compression)
    with fitz.open(output) as doc:
        assert len(doc) == 3
        assert tuple(doc[1].rect) == pytest.approx((0, 0, 144, 192), abs=.1)
        assert doc[1].get_text().split() == ["Hello", "κόσμος中文"]
        assert tuple(doc[1].search_for("Hello")[0]) == pytest.approx((7.2, 16.8, 28.8, 24), abs=.2)


@pytest.mark.skipif(not shutil.which("ddjvu") or not shutil.which("djvutxt"), reason="DjVuLibre is optional")
def test_estimates_use_all_pages_for_short_document_and_match_actual_conversions(tmp_path):
    source = Path(__file__).parent / "fixtures/djvu/text_and_blank.djvu"
    before = source.read_bytes()
    preview = manager().estimate_djvu_compression(str(source))
    assert preview.page_count == 3
    assert preview.sample_pages == (1, 2, 3)
    assert set(preview.estimates) == {
        "mrc", "compact_color", "balanced", "small", "black_white", "original"
    }
    for compression, estimate in preview.estimates.items():
        output = tmp_path / (compression + ".pdf")
        manager().convert_djvu_to_pdf(str(source), str(output), compression=compression)
        assert estimate.expected_bytes == output.stat().st_size
        assert estimate.low_bytes <= estimate.expected_bytes <= estimate.high_bytes
        assert len(estimate.previews) == 3
        assert all(png.startswith(b"\x89PNG") for png in estimate.previews)
    assert source.read_bytes() == before


def test_sample_projection_weights_cover_pages_once_and_does_not_promise_savings():
    mod = manager()
    pages = mod.compression_sample_pages(100)
    assert len(pages) == 8
    assert pages == tuple(sorted(set(pages)))
    assert pages[0] == 1 and pages[-1] == 100
    # Covers are exceptionally large; multiplying their sample average by
    # all pages would substantially overestimate the whole book.
    result = mod.project_compressed_size([1_000_000, *([10_000] * 6), 1_000_000], 100, 50_000)
    assert result == 3_030_000


def test_estimation_cancellation_does_not_launch_decoder_or_leave_temporary_files(monkeypatch, tmp_path):
    source, _, calls = fake_decoder(monkeypatch, tmp_path, [TEXT])
    monkeypatch.setattr(manager().tempfile, "tempdir", str(tmp_path))
    before = set(tmp_path.iterdir())
    with pytest.raises(manager().DjvuImportError):
        manager().estimate_djvu_compression(str(source), cancel_cb=lambda: True)
    assert calls == []
    assert set(tmp_path.iterdir()) == before
