import importlib.util
from pathlib import Path
import sys
import sysconfig

_previous_statistics = sys.modules.get("statistics")
_stdlib_spec = importlib.util.spec_from_file_location(
    "_snapshot_stdlib_statistics",
    Path(sysconfig.get_path("stdlib")) / "statistics.py",
)
_stdlib_statistics = importlib.util.module_from_spec(_stdlib_spec)
_stdlib_spec.loader.exec_module(_stdlib_statistics)
try:
    sys.modules["statistics"] = _stdlib_statistics
    import pymupdf as fitz
finally:
    if _previous_statistics is None:
        sys.modules.pop("statistics", None)
    else:
        sys.modules["statistics"] = _previous_statistics

from backend import pdf_context_snapshot


def _make_text_pdf(path: Path) -> None:
    with fitz.open() as document:
        page = document.new_page(width=612, height=792)
        for index in range(15):
            text = f"Context row {index + 1}"
            if index == 7:
                text = "The exact target passage is on this row."
            page.insert_text((54, 72 + (index * 30)), text, fontsize=12)
        document.save(path)


def test_render_pdf_context_snapshot_crops_rows_and_highlights_exact_passage(tmp_path):
    pdf_path = tmp_path / "source.pdf"
    _make_text_pdf(pdf_path)

    image = pdf_context_snapshot.render_pdf_context_snapshot(
        pdf_path,
        page_number=1,
        excerpt="The exact target passage is on this row.",
        context_rows=2,
    )

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    pixmap = fitz.Pixmap(image)
    assert pixmap.width > 300
    assert 100 < pixmap.height < 500
    yellow_pixels = 0
    for offset in range(0, len(pixmap.samples), pixmap.n):
        red, green, blue = pixmap.samples[offset : offset + 3]
        if red > 190 and green > 140 and blue < 150:
            yellow_pixels += 1
    assert yellow_pixels > 500


def test_render_pdf_context_snapshot_spans_selected_rows_with_context_when_saved_rect_is_partial(tmp_path):
    pdf_path = tmp_path / "source.pdf"
    with fitz.open() as document:
        page = document.new_page(width=612, height=792)
        for index in range(16):
            page.insert_text((54, 72 + index * 30), f"Selected passage row {index + 1}", fontsize=12)
        document.save(pdf_path)

    with fitz.open(pdf_path) as document:
        first_selected_word = next(
            word for word in document[0].get_text("words")
            if word[4] == "Selected" and word[6] == 0 and word[5] == 3
        )
    excerpt = " ".join(f"Selected passage row {index}" for index in range(4, 12))

    image = pdf_context_snapshot.render_pdf_context_snapshot(
        pdf_path,
        page_number=1,
        excerpt=excerpt,
        context_rows=2,
        highlight_rects=[first_selected_word[:4]],
    )

    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    pixmap = fitz.Pixmap(image)
    # Eight selected rows plus two rows on each side should be visible.
    assert 650 < pixmap.height < 800


def test_render_pdf_context_snapshot_returns_empty_when_passage_is_not_on_page(tmp_path):
    pdf_path = tmp_path / "source.pdf"
    _make_text_pdf(pdf_path)

    assert pdf_context_snapshot.render_pdf_context_snapshot(
        pdf_path,
        page_number=1,
        excerpt="This sentence does not exist in the PDF.",
        context_rows=5,
    ) == b""


def test_render_pdf_context_snapshot_falls_back_to_words_when_saved_rect_is_stale(tmp_path):
    pdf_path = tmp_path / "source.pdf"
    _make_text_pdf(pdf_path)

    image = pdf_context_snapshot.render_pdf_context_snapshot(
        pdf_path,
        page_number=1,
        excerpt="The exact target passage is on this row.",
        context_rows=2,
        highlight_rects=[{"x": 500, "y": 700, "w": 20, "h": 20}],
    )

    assert image.startswith(b"\x89PNG\r\n\x1a\n")


def test_snapshot_media_filename_is_content_addressed_and_stable():
    first = pdf_context_snapshot.snapshot_media_filename(b"same image")
    second = pdf_context_snapshot.snapshot_media_filename(b"same image")

    assert first == second
    assert first.startswith("incremento-pdf-context-")
    assert first.endswith(".png")


def test_add_snapshot_to_anki_media_uses_the_content_addressed_name(tmp_path):
    calls = []

    class _Media:
        def add_file(self, path):
            candidate = Path(path)
            calls.append((candidate.name, candidate.read_bytes()))
            return candidate.name

    collection = type("Collection", (), {"media": _Media()})()

    stored = pdf_context_snapshot.add_snapshot_to_anki_media(collection, b"png bytes")

    assert stored == pdf_context_snapshot.snapshot_media_filename(b"png bytes")
    assert calls == [(stored, b"png bytes")]
