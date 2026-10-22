"""Copy the embedded bitmap, independent of PDF page rendering and overlays."""

import importlib.util
from pathlib import Path
import sys
import sysconfig

import pytest

from backend import pdf_embedded_images as images

# The shared harness exposes backend/statistics.py under the stdlib name.
_previous_statistics = sys.modules.get("statistics")
_spec = importlib.util.spec_from_file_location(
    "_image_stdlib_statistics", Path(sysconfig.get_path("stdlib")) / "statistics.py",
)
_stdlib_statistics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_stdlib_statistics)
try:
    sys.modules["statistics"] = _stdlib_statistics
    import pymupdf as fitz
finally:
    if _previous_statistics is None:
        sys.modules.pop("statistics", None)
    else:
        sys.modules["statistics"] = _previous_statistics


def _image(alpha=False):
    pixmap = fitz.Pixmap(fitz.csRGB, (0, 0, 32, 16), alpha)
    pixmap.clear_with(0)
    for y in range(16):
        for x in range(32):
            pixmap.set_pixel(x, y, (x * 7, y * 13, 80, 128) if alpha else (x * 7, y * 13, 80))
    return pixmap


def _pdf(tmp_path, *, rotation=0, alpha=False, crop=False):
    path = tmp_path / "images.pdf"
    original = _image(alpha)
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=400)
        page.insert_image(fitz.Rect(100, 100, 300, 200), stream=original.tobytes("png"))
        page.insert_text((110, 150), "Page text over image")
        page.draw_rect(fitz.Rect(120, 110, 130, 120), fill=(1, 0, 0))
        if crop:
            page.set_cropbox(fitz.Rect(50, 50, 350, 300))
        page.set_rotation(rotation)
        doc.save(path)
    return path, original


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("crop", [False, True])
def test_copy_embedded_image_preserves_native_pixels_without_page_overlays(tmp_path, rotation, crop):
    path, original = _pdf(tmp_path, rotation=rotation, crop=crop)
    with fitz.open(path) as doc:
        page = doc[0]
        center = fitz.Rect(page.get_image_info()[0]["bbox"]).tl + (100, 50)
        point = center * page.rotation_matrix
        x, y = point.x / page.rect.width, point.y / page.rect.height

    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=x, y_ratio=y)

    assert result.status == "ready"
    copied = fitz.Pixmap(result.png)
    assert (copied.width, copied.height) == (32, 16)
    assert copied.samples == original.samples


def test_copy_restores_embedded_soft_mask_transparency(tmp_path):
    path, original = _pdf(tmp_path, alpha=True)
    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.5, y_ratio=.375)
    copied = fitz.Pixmap(result.png)
    assert copied.alpha == 1
    # PDF stores straight RGB separately from the mask; alpha survives reconstruction.
    assert copied.pixel(0, 0)[3] == original.pixel(0, 0)[3]
    assert (copied.width, copied.height) == (32, 16)


@pytest.mark.parametrize("x,y", [(.1, .1), (.9, .9)])
def test_clicking_page_background_does_not_copy_a_page_snapshot(tmp_path, x, y):
    path, _ = _pdf(tmp_path)
    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=x, y_ratio=y)
    assert result.status == "not_found"
    assert result.png == b""


@pytest.mark.parametrize("overrides", [
    {"page_number": 0}, {"page_number": 2}, {"page_number": True},
    {"x_ratio": -0.1}, {"y_ratio": 1.1}, {"x_ratio": float("nan")},
    {"x_ratio": "0.5"}, {"y_ratio": None}, {"x_ratio": 10 ** 1000},
])
def test_invalid_image_requests_fail_closed(tmp_path, overrides):
    path, _ = _pdf(tmp_path)
    options = {"page_number": 1, "x_ratio": .5, "y_ratio": .375, **overrides}
    result = images.extract_pdf_image_at_point(path, **options)
    assert result.status == "not_found"
    assert result.png == b""


def test_oversized_image_is_rejected_before_pixel_decoding(tmp_path, monkeypatch):
    path, _ = _pdf(tmp_path)
    monkeypatch.setattr(images, "MAX_IMAGE_PIXELS", 511)
    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.5, y_ratio=.375)
    assert result.status == "too_large"
    assert result.png == b""


def test_damaged_pdf_does_not_escape_as_an_exception(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF broken")
    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.5, y_ratio=.5)
    assert result.status == "failed"
    assert result.png == b""


def test_overlapping_images_copy_the_last_painted_bitmap(tmp_path):
    path, _ = _pdf(tmp_path)
    top = fitz.Pixmap(fitz.csRGB, (0, 0, 8, 8), False)
    top.clear_with(200)
    with fitz.open(path) as doc:
        doc[0].insert_image(fitz.Rect(150, 125, 200, 175), stream=top.tobytes("png"))
        doc.saveIncr()
    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.4375, y_ratio=.375)
    assert fitz.Pixmap(result.png).samples == top.samples


def test_inline_image_without_xref_copies_its_native_bitmap(tmp_path):
    path = tmp_path / "inline.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=400)
        content = doc.get_new_xref()
        doc.update_object(content, "<<>>")
        doc.update_stream(content, b"q 100 0 0 50 100 200 cm BI /W 2 /H 1 /BPC 8 /CS /RGB /F /AHx ID FF000000FF00> EI Q")
        page.set_contents(content)
        doc.save(path)
    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.375, y_ratio=.4375)
    assert result.status == "ready"
    copied = fitz.Pixmap(result.png)
    assert (copied.width, copied.height) == (2, 1)
    assert copied.samples == bytes([255, 0, 0, 0, 255, 0])


def test_vector_figure_does_not_turn_into_a_rendered_screenshot(tmp_path):
    path = tmp_path / "vector.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=400, height=400)
        page.draw_circle((200, 200), 100, fill=(1, 0, 0))
        doc.save(path)
    assert images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.5, y_ratio=.5).status == "not_found"


def test_missing_optional_pymupdf_returns_installation_status(tmp_path, monkeypatch):
    path, _ = _pdf(tmp_path)
    monkeypatch.setitem(sys.modules, "pymupdf", None)
    assert images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.5, y_ratio=.375).status == "unavailable"


@pytest.mark.parametrize("limit", ["MAX_PDF_BYTES", "MAX_IMAGE_BYTES", "MAX_PAGE_IMAGE_PIXELS", "MAX_PAGE_IMAGES"])
def test_document_and_output_limits_leave_no_partial_image(tmp_path, monkeypatch, limit):
    path, _ = _pdf(tmp_path)
    monkeypatch.setattr(images, limit, 0)
    result = images.extract_pdf_image_at_point(path, page_number=1, x_ratio=.5, y_ratio=.375)
    assert result.status == "too_large"
    assert result.png == b""
