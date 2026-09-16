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


@pytest.mark.parametrize("text", [
    '(page 0 0 0 800 "bad")',
    '(page 0 0 600 800 (word -1 0 20 30 "bad"))',
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
