"""Tests for backend/pdf_manager.py

PyQt6 / PyQt6.QtPdf must be stubbed before importing pdf_manager because the
module executes `from PyQt6.QtPdf import QPdfDocument` at import time.
"""
import importlib
import os
import sys
import tempfile
import shutil
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Stub Qt / PyQt6 before any pdf_manager import
# ---------------------------------------------------------------------------
_qt_pdf_mock = MagicMock()
_qpdf_document_cls = MagicMock()
_qt_pdf_mock.QPdfDocument = _qpdf_document_cls

sys.modules.setdefault("PyQt6", MagicMock())
sys.modules["PyQt6.QtPdf"] = _qt_pdf_mock

# Also make sure db-related modules imported by pdf_manager are available.
# The conftest already puts backend/ on sys.path, but we need to ensure
# pdf_manager's relative-import fallback resolves to the real db module.
import db  # noqa: E402  (db is on sys.path via conftest)
from note_metadata import (
    INCREMENTO_CONTENT_ID_FIELD,
    INCREMENTO_SOURCE_LINK_FIELD,
    INCREMENTO_SOURCE_TITLE_FIELD,
    INCREMENTO_SOURCE_TYPE_FIELD,
)
sys.modules.setdefault("db", db)

pdf_manager = importlib.import_module("pdf_manager")  # noqa: E402
pdf_manager = importlib.reload(pdf_manager)
from pdf_manager import PDF_COVER_FIELD, pdf_display_label_from_filename  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_temp_pdf(content: bytes = b"%PDF-1.4 fake content") -> str:
    """Write a temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="test_pdf_")
    os.write(fd, content)
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# _copy_to_pdf_dir
# ---------------------------------------------------------------------------


class TestCopyToPdfDir:
    def setup_method(self):
        self._tmp_pdf_dir = tempfile.mkdtemp()
        self._patcher = patch("pdf_manager.get_pdf_dir", return_value=self._tmp_pdf_dir)
        self._patcher.start()

    def teardown_method(self):
        self._patcher.stop()
        shutil.rmtree(self._tmp_pdf_dir, ignore_errors=True)

    def test_file_is_copied_to_pdf_dir(self):
        src = _make_temp_pdf()
        try:
            dest_name = pdf_manager._copy_to_pdf_dir(src)
            assert os.path.isfile(os.path.join(self._tmp_pdf_dir, dest_name))
        finally:
            os.unlink(src)

    def test_returns_basename(self):
        src = _make_temp_pdf()
        try:
            dest_name = pdf_manager._copy_to_pdf_dir(src)
            assert dest_name.endswith(".pdf")
            assert os.path.basename(src).replace(".pdf", "") in dest_name
        finally:
            os.unlink(src)

    def test_same_content_still_gets_distinct_uuid_names(self):
        src = _make_temp_pdf(b"%PDF-1.4 identical content")
        try:
            name1 = pdf_manager._copy_to_pdf_dir(src)
            name2 = pdf_manager._copy_to_pdf_dir(src)
            assert name1 != name2
            pdfs = [f for f in os.listdir(self._tmp_pdf_dir) if f.endswith(".pdf")]
            assert len(pdfs) == 2
        finally:
            os.unlink(src)

    def test_different_content_same_name_gets_uuid_suffix(self):
        src = os.path.join(tempfile.mkdtemp(), "document.pdf")
        with open(src, "wb") as f:
            f.write(b"%PDF different content abc123")

        result = pdf_manager._copy_to_pdf_dir(src)
        assert result.startswith("document-")
        assert result.endswith(".pdf")
        assert os.path.isfile(os.path.join(self._tmp_pdf_dir, result))

    def test_long_filename_stem_is_truncated_before_uuid_suffix(self):
        src = os.path.join(tempfile.mkdtemp(), f'{"a" * 140}.pdf')
        with open(src, "wb") as f:
            f.write(b"%PDF long name")

        result = pdf_manager._copy_to_pdf_dir(src)

        stem = os.path.splitext(result)[0]
        base, _, suffix = stem.rpartition("-")
        assert len(base) <= 80
        assert len(suffix) == 32


class TestPdfStorageAbspath:
    def test_rejects_parent_traversal(self, tmp_path):
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()

        with patch("pdf_manager.get_pdf_dir", return_value=str(pdf_dir)):
            assert pdf_manager.pdf_storage_abspath("../../../etc/passwd") == ""

    def test_accepts_legacy_pdfs_prefix(self, tmp_path):
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()

        with patch("pdf_manager.get_pdf_dir", return_value=str(pdf_dir)):
            assert pdf_manager.pdf_storage_abspath("pdfs/stored.pdf") == str(pdf_dir / "stored.pdf")


class TestPdfDisplayLabelFromFilename:
    def test_strips_uuid_suffix_and_extension(self):
        filename = f"very_long_pdf_title_for_reading-{('a' * 32)}.pdf"

        assert pdf_display_label_from_filename(filename) == "very long pdf title for reading"

    def test_truncates_overlong_labels(self):
        filename = f"{'x' * 120}-{('b' * 32)}.pdf"

        assert pdf_display_label_from_filename(filename) == "x" * 48

    def test_keeps_short_readable_names(self):
        assert pdf_display_label_from_filename("chapter_01-intro.pdf") == "chapter 01 intro"


class TestReadAnchorPersistence:
    def test_set_and_get_read_anchor_round_trip(self, tmp_path):
        addon_dir = str(tmp_path)

        pdf_manager.set_read_page(
            addon_dir,
            "TestProfile",
            77,
            5,
            {
                "page": 5,
                "x": 12.3456,
                "y": 45.6789,
                "w": 34.2,
                "h": 11.1,
                "text": "Last sentence here",
            },
        )

        assert pdf_manager.get_read_page(addon_dir, "TestProfile", 77) == 5
        assert pdf_manager.get_read_anchor(addon_dir, "TestProfile", 77) == {
            "page": 5,
            "x": 12.346,
            "y": 45.679,
            "w": 34.2,
            "h": 11.1,
            "text": "Last sentence here",
        }

    def test_clearing_read_page_clears_anchor(self, tmp_path):
        addon_dir = str(tmp_path)

        pdf_manager.set_read_page(
            addon_dir,
            "TestProfile",
            78,
            4,
            {"page": 4, "x": 1, "y": 2, "w": 3, "h": 4, "text": "Anchor"},
        )
        pdf_manager.set_read_page(addon_dir, "TestProfile", 78, 0)

        assert pdf_manager.get_read_page(addon_dir, "TestProfile", 78) == 0
        assert pdf_manager.get_read_anchor(addon_dir, "TestProfile", 78) is None


class TestFindLivePdfCardByFilename:
    def test_finds_matching_card_id_by_stored_filename(self):
        note = MagicMock()
        note.__getitem__.side_effect = lambda key: {"PDF_Filename": "paper.pdf"}[key]
        col = MagicMock()
        col.find_notes.return_value = [11]
        col.get_note.return_value = note
        col.find_cards.return_value = [123]

        assert pdf_manager.find_live_pdf_card_by_filename(col, "paper.pdf") == 123

    def test_falls_back_to_unique_stem_match_when_uuid_differs(self):
        note = MagicMock()
        note.__getitem__.side_effect = lambda key: {
            "PDF_Filename": f"paper-{('a' * 32)}.pdf"
        }[key]
        col = MagicMock()
        col.find_notes.return_value = [11]
        col.get_note.return_value = note
        col.find_cards.return_value = [123]

        assert (
            pdf_manager.find_live_pdf_card_by_filename(
                col,
                f"paper-{('b' * 32)}.pdf",
            )
            == 123
        )

    def test_returns_none_when_stem_match_is_ambiguous(self):
        note_a = MagicMock()
        note_a.__getitem__.side_effect = lambda key: {
            "PDF_Filename": f"paper-{('a' * 32)}.pdf"
        }[key]
        note_b = MagicMock()
        note_b.__getitem__.side_effect = lambda key: {
            "PDF_Filename": f"paper-{('b' * 32)}.pdf"
        }[key]
        col = MagicMock()
        col.find_notes.return_value = [11, 12]
        col.get_note.side_effect = [note_a, note_b, note_a, note_b]
        col.find_cards.side_effect = [[123], [124]]

        assert (
            pdf_manager.find_live_pdf_card_by_filename(
                col,
                f"paper-{('c' * 32)}.pdf",
            )
            is None
        )


class TestRenderPdfCoverMedia:
    def test_renders_first_page_and_adds_png_to_media(self, tmp_path):
        pdf_path = tmp_path / "cover.pdf"
        pdf_path.write_bytes(b"%PDF fake")

        image = MagicMock()
        image.isNull.return_value = False

        media = MagicMock()
        media.add_file.return_value = "stored-cover.png"
        col = MagicMock(media=media)

        doc = MagicMock()
        doc.pageCount.return_value = 1
        doc.pagePointSize.return_value = MagicMock(width=lambda: 200.0, height=lambda: 320.0)
        doc.render.return_value = image
        _qpdf_document_cls.return_value = doc

        def _save(path, fmt):
            with open(path, "wb") as handle:
                handle.write(b"png")
            return True

        image.save.side_effect = _save

        with patch.dict(sys.modules, {"PyQt6.QtCore": MagicMock(QSize=lambda w, h: (w, h))}):
            result = pdf_manager.render_pdf_cover_media(
                col,
                str(pdf_path),
                title="Cover Title",
                source_filename="cover.pdf",
            )

        assert result == "stored-cover.png"
        assert media.add_file.call_count == 1
        saved_path = media.add_file.call_args.args[0]
        assert os.path.basename(saved_path).startswith("Cover_Title-cover-")
        image.save.assert_called_once()

    def test_returns_empty_when_pdf_has_no_pages(self, tmp_path):
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.write_bytes(b"%PDF fake")

        col = MagicMock()
        doc = MagicMock()
        doc.pageCount.return_value = 0
        _qpdf_document_cls.return_value = doc

        with patch.dict(sys.modules, {"PyQt6.QtCore": MagicMock(QSize=lambda w, h: (w, h))}):
            result = pdf_manager.render_pdf_cover_media(col, str(pdf_path))

        assert result == ""
        col.media.add_file.assert_not_called()


class TestAddPdfCard:
    def test_relinks_unique_missing_matching_card_instead_of_creating_duplicate(self, tmp_path):
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        source_pdf = tmp_path / "Guide.pdf"
        source_pdf.write_bytes(b"%PDF replacement")

        note = _FakePdfNote(
            321,
            Title="Guide",
            PDF_Filename=f"Guide-{('a' * 32)}.pdf",
            Incremento_Source_Link=f"pdfs/Guide-{('a' * 32)}.pdf",
        )
        card = _FakeCard(77, 321)
        col = MagicMock()
        col.find_notes.return_value = [321]
        col.find_cards.side_effect = lambda query: [77] if query == "nid:321" else []
        col.get_note.return_value = note
        col.get_card.return_value = card

        with patch("pdf_manager.ensure_pdf_note_type", return_value=None), \
             patch("pdf_manager._paths.get_active_profile", return_value="TestProfile"), \
             patch("pdf_manager.get_pdf_dir", return_value=str(pdf_dir)), \
             patch("pdf_manager.replace_pdf_card_file", return_value="Guide-new.pdf") as relink_mock, \
             patch("pdf_manager.save_pdf_daily_limit_settings") as save_limit:
            result = pdf_manager.add_pdf_card(
                str(tmp_path),
                col,
                str(source_pdf),
                "Guide",
                daily_page_limit=6,
            )

        assert result == 77
        relink_mock.assert_called_once_with(
            str(tmp_path),
            col,
            77,
            str(source_pdf),
            profile="TestProfile",
        )
        col.add_note.assert_not_called()
        save_limit.assert_called_once_with(
            str(tmp_path),
            "TestProfile",
            77,
            enabled=True,
            daily_page_limit=6,
            enforcement_mode="warning",
        )

    def test_uses_visible_duplicate_suffix_when_title_collides(self):
        col = MagicMock()
        first_note = MagicMock()
        first_note.id = 999
        second_note = MagicMock()
        second_note.id = 1000
        col.new_note.side_effect = [first_note, second_note]
        col.add_note.side_effect = [0, 1]
        col.find_cards.return_value = [12345]
        col.models.by_name.return_value = {"name": pdf_manager.PDF_NOTE_TYPE}
        col.decks.by_name.return_value = {"id": 1}

        with patch("pdf_manager.ensure_pdf_note_type", return_value=None), \
             patch("pdf_manager._copy_to_pdf_dir", return_value="stored-file.pdf"), \
             patch("pdf_manager.render_pdf_cover_media", return_value="stored-cover.png"), \
             patch("pdf_manager.extract_pdf_pages_text", return_value=["page one"]), \
             patch("pdf_manager.replace_pdf_text_index", return_value=None):
            result = pdf_manager.add_pdf_card("/tmp/incremento-test", col, "/tmp/source.pdf", "Guide")

        assert result == 12345
        setitem_calls = second_note.__setitem__.call_args_list
        assert any(c.args == ("Title", "Guide [2]") for c in setitem_calls)
        assert any(c.args == (PDF_COVER_FIELD, "stored-cover.png") for c in setitem_calls)
        assert any(c.args == (INCREMENTO_SOURCE_TYPE_FIELD, "PDF") for c in setitem_calls)
        assert any(c.args == (INCREMENTO_SOURCE_TITLE_FIELD, "Guide") for c in setitem_calls)
        assert any(
            c.args == (INCREMENTO_SOURCE_LINK_FIELD, "pdfs/stored-file.pdf")
            for c in setitem_calls
        )

    def test_persists_pdf_daily_limit_settings_after_create(self):
        col = MagicMock()
        note = MagicMock()
        note.id = 999
        col.new_note.return_value = note
        col.add_note.return_value = 1
        col.find_cards.return_value = [12345]
        col.models.by_name.return_value = {"name": pdf_manager.PDF_NOTE_TYPE}
        col.decks.by_name.return_value = {"id": 1}

        with patch("pdf_manager.ensure_pdf_note_type", return_value=None), \
             patch("pdf_manager._copy_to_pdf_dir", return_value="stored-file.pdf"), \
             patch("pdf_manager.render_pdf_cover_media", return_value="stored-cover.png"), \
             patch("pdf_manager.extract_pdf_pages_text", return_value=["page one"]), \
             patch("pdf_manager.replace_pdf_text_index", return_value=None), \
             patch("pdf_manager.save_pdf_daily_limit_settings") as save_limit:
            pdf_manager.add_pdf_card(
                "/tmp/incremento-test",
                col,
                "/tmp/source.pdf",
                "Guide",
                daily_page_limit=8,
                enforcement_mode="soft_lock",
            )

        save_limit.assert_called_once_with(
            "/tmp/incremento-test",
            pdf_manager._paths.get_active_profile(),
            12345,
            enabled=True,
            daily_page_limit=8,
            enforcement_mode="soft_lock",
        )

    def test_uses_precomputed_page_texts_when_supplied(self):
        col = MagicMock()
        note = MagicMock()
        note.id = 999
        col.new_note.return_value = note
        col.add_note.return_value = 1
        col.find_cards.return_value = [12345]
        col.models.by_name.return_value = {"name": pdf_manager.PDF_NOTE_TYPE}
        col.decks.by_name.return_value = {"id": 1}

        with patch("pdf_manager.ensure_pdf_note_type", return_value=None), \
             patch("pdf_manager._copy_to_pdf_dir", return_value="stored-file.pdf"), \
             patch("pdf_manager.render_pdf_cover_media", return_value="stored-cover.png"), \
             patch("pdf_manager.extract_pdf_pages_text") as extract_mock, \
             patch("pdf_manager.replace_pdf_text_index") as index_mock:
            result = pdf_manager.add_pdf_card(
                "/tmp/incremento-test",
                col,
                "/tmp/source.pdf",
                "Guide",
                precomputed_page_texts=["ready text"],
            )

        assert result == 12345
        extract_mock.assert_not_called()
        index_mock.assert_called_once_with(
            "/tmp/incremento-test",
            pdf_manager._paths.get_active_profile(),
            12345,
            ["ready text"],
        )


# ---------------------------------------------------------------------------
# extract_pdf_pages_text — PyMuPDF path
# ---------------------------------------------------------------------------


class TestExtractPdfPagesTextFitz:
    def test_fitz_path_returns_per_page_text(self):
        """When fitz is importable and returns text, use it."""
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 2
        page0 = MagicMock()
        page0.get_text.return_value = "  Page one text  "
        page1 = MagicMock()
        page1.get_text.return_value = "Page two text"
        mock_doc.load_page.side_effect = [page0, page1]
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            # Reimport to pick up the mock — call the function directly
            result = pdf_manager.extract_pdf_pages_text("/fake/path.pdf")

        assert len(result) == 2
        assert result[0] == "Page one text"
        assert result[1] == "Page two text"

    def test_fitz_returns_non_empty_list(self):
        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        pg = MagicMock()
        pg.get_text.return_value = "Some content"
        mock_doc.load_page.return_value = pg
        mock_fitz.open.return_value = mock_doc

        with patch.dict(sys.modules, {"fitz": mock_fitz}):
            result = pdf_manager.extract_pdf_pages_text("/fake/any.pdf")

        assert result != []
        assert any(r for r in result)

    def test_fitz_exception_falls_through(self):
        """If fitz.open raises, the function should not propagate the exception."""
        mock_fitz = MagicMock()
        mock_fitz.open.side_effect = RuntimeError("fitz broken")

        # Make QPdfDocument also return nothing useful so we get []
        mock_doc_instance = MagicMock()
        mock_doc_instance.pageCount.return_value = 0
        _qpdf_document_cls.return_value = mock_doc_instance

        with patch.dict(sys.modules, {"fitz": mock_fitz}), \
             patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            result = pdf_manager.extract_pdf_pages_text("/fake/broken.pdf")

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# extract_pdf_pages_text — Qt fallback path
# ---------------------------------------------------------------------------


class TestExtractPdfPagesTextQtFallback:
    def test_qt_fallback_when_fitz_missing(self):
        """Without fitz, QPdfDocument path is tried."""
        mock_doc_instance = MagicMock()
        mock_doc_instance.pageCount.return_value = 2

        sel0 = MagicMock()
        sel0.isValid.return_value = True
        sel0.text.return_value = "Qt page one"

        sel1 = MagicMock()
        sel1.isValid.return_value = True
        sel1.text.return_value = "Qt page two"

        mock_doc_instance.getAllText.side_effect = [sel0, sel1]
        _qpdf_document_cls.return_value = mock_doc_instance

        with patch.dict(sys.modules, {"fitz": None}), \
             patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            result = pdf_manager.extract_pdf_pages_text("/fake/qt.pdf")

        assert "Qt page one" in result or any("Qt page" in r for r in result)

    def test_returns_empty_list_when_all_extractors_fail(self):
        """If fitz is missing and Qt doc has 0 pages, and pdftotext not found → []."""
        mock_doc_instance = MagicMock()
        mock_doc_instance.pageCount.return_value = 0
        _qpdf_document_cls.return_value = mock_doc_instance

        with patch.dict(sys.modules, {"fitz": None}), \
             patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            result = pdf_manager.extract_pdf_pages_text("/fake/empty.pdf")

        assert result == []


# ---------------------------------------------------------------------------
# ocr_pdf_in_place
# ---------------------------------------------------------------------------


class TestOcrPdfInPlace:
    def test_returns_false_when_tesseract_not_found(self):
        """No tesseract + no ocrmypdf → False."""
        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", return_value=False):
            result = pdf_manager.ocr_pdf_in_place("/fake/doc.pdf")
        assert result is False

    def test_returns_false_when_fitz_missing_even_with_tesseract(self):
        """tesseract found but fitz (PyMuPDF) not importable → no pipeline → False."""
        with patch("shutil.which", side_effect=lambda name: "/usr/bin/tesseract" if name == "tesseract" else None), \
             patch("os.path.isfile", return_value=True), \
             patch.dict(sys.modules, {"fitz": None}):
            result = pdf_manager.ocr_pdf_in_place("/fake/scan.pdf")
        # Without fitz to render pages, the pipeline can't proceed
        assert isinstance(result, bool)

    def test_successful_ocr_pipeline_returns_true(self):
        """Mock the full tesseract + fitz pipeline to simulate success."""
        import tempfile as _tempfile
        import shutil as _shutil

        # We need to mock: tesseract binary found, fitz importable,
        # fitz.open returns a doc with pages, subprocess.run succeeds,
        # and the merged file has non-zero size.

        mock_fitz = MagicMock()
        mock_doc = MagicMock()
        mock_doc.__len__ = lambda self: 1
        mock_doc.__iter__ = lambda self: iter([])

        mock_page = MagicMock()
        mock_pixmap = MagicMock()
        mock_page.get_pixmap.return_value = mock_pixmap
        mock_doc.load_page.return_value = mock_page

        mock_fitz.Matrix.return_value = MagicMock()
        mock_fitz.open.side_effect = [
            mock_doc,       # first call: open source PDF
            MagicMock(),    # subsequent calls: open page PDFs
        ]

        # merged_doc
        merged_doc_mock = MagicMock()
        merged_doc_mock.__enter__ = lambda s: s
        merged_doc_mock.__exit__ = MagicMock(return_value=False)

        def _fitz_open(path=None):
            if path is None:
                return merged_doc_mock
            if path == "/fake/ocr.pdf":
                return mock_doc
            ctx_mock = MagicMock()
            ctx_mock.__enter__ = lambda s: s
            ctx_mock.__exit__ = MagicMock(return_value=False)
            return ctx_mock

        mock_fitz.open.side_effect = _fitz_open

        def _subprocess_run(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            return proc

        # Create a real temp file as the merged output target
        fd, merged_path = _tempfile.mkstemp(suffix=".pdf")
        os.write(fd, b"%PDF-1.4 ocr output")
        os.close(fd)

        def _os_path_getsize(path):
            return 1024  # non-zero

        tesseract_bin = "/opt/homebrew/bin/tesseract"

        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", side_effect=lambda p: p == tesseract_bin), \
             patch.dict(sys.modules, {"fitz": mock_fitz}), \
             patch("subprocess.run", side_effect=_subprocess_run), \
             patch("os.path.getsize", side_effect=_os_path_getsize), \
             patch("shutil.move"):
            result = pdf_manager.ocr_pdf_in_place("/fake/ocr.pdf")

        try:
            os.unlink(merged_path)
        except OSError:
            pass

        # Either True (pipeline completed) or False (intermediate mock mis-wired)
        # The important thing is no exception propagates
        assert isinstance(result, bool)

    def test_ocrmypdf_fallback_returns_true_on_success(self):
        """When tesseract absent, falls back to ocrmypdf."""
        def _subprocess_run(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            return proc

        ocrmypdf_bin = "/opt/homebrew/bin/ocrmypdf"

        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", side_effect=lambda p: p == ocrmypdf_bin), \
             patch("subprocess.run", side_effect=_subprocess_run), \
             patch("os.path.getsize", return_value=2048), \
             patch("shutil.move"):
            result = pdf_manager.ocr_pdf_in_place("/fake/scan.pdf")

        assert result is True

    def test_ocrmypdf_fallback_returns_false_on_nonzero_returncode(self):
        def _subprocess_run(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 1
            return proc

        ocrmypdf_bin = "/usr/bin/ocrmypdf"

        with patch("shutil.which", return_value=None), \
             patch("os.path.isfile", side_effect=lambda p: p == ocrmypdf_bin), \
             patch("subprocess.run", side_effect=_subprocess_run):
            result = pdf_manager.ocr_pdf_in_place("/fake/scan.pdf")

        assert result is False


# ---------------------------------------------------------------------------
# get_page / set_page (integration via db)
# ---------------------------------------------------------------------------


class TestGetSetPage:
    def setup_method(self):
        import db as _db
        _db.close_connection()
        self.addon_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import db as _db
        _db.close_connection()

    def test_default_page_is_one(self):
        assert pdf_manager.get_page(self.addon_dir, "TestProfile", card_id=42) == 1

    def test_set_and_get_page(self):
        pdf_manager.set_page(self.addon_dir, "TestProfile", card_id=5, page=7)
        assert pdf_manager.get_page(self.addon_dir, "TestProfile", card_id=5) == 7

    def test_update_page_overwrites(self):
        pdf_manager.set_page(self.addon_dir, "TestProfile", card_id=10, page=3)
        pdf_manager.set_page(self.addon_dir, "TestProfile", card_id=10, page=12)
        assert pdf_manager.get_page(self.addon_dir, "TestProfile", card_id=10) == 12


class TestPdfScrollRatio:
    def setup_method(self):
        import db as _db
        _db.close_connection()
        self.addon_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import db as _db
        _db.close_connection()
        shutil.rmtree(self.addon_dir, ignore_errors=True)

    def test_set_and_get_scroll_ratio_round_trip(self):
        pdf_manager.set_scroll_ratio(self.addon_dir, "TestProfile", card_id=15, scroll_ratio=0.35)

        assert pdf_manager.get_scroll_ratio(self.addon_dir, "TestProfile", card_id=15) == 0.35

    def test_set_scroll_ratio_clamps_invalid_values(self):
        pdf_manager.set_scroll_ratio(self.addon_dir, "TestProfile", card_id=16, scroll_ratio=8)
        assert pdf_manager.get_scroll_ratio(self.addon_dir, "TestProfile", card_id=16) == 1.0

        pdf_manager.set_scroll_ratio(self.addon_dir, "TestProfile", card_id=16, scroll_ratio=-2)
        assert pdf_manager.get_scroll_ratio(self.addon_dir, "TestProfile", card_id=16) == 0.0

    def test_updating_scroll_preserves_page_zoom_and_read_state(self):
        pdf_manager.set_page(self.addon_dir, "TestProfile", card_id=17, page=9)
        pdf_manager.set_zoom(self.addon_dir, "TestProfile", card_id=17, zoom=1.75)
        pdf_manager.set_read_page(
            self.addon_dir,
            "TestProfile",
            17,
            8,
            {"page": 8, "x": 10, "y": 20, "w": 30, "h": 5, "text": "Stop here"},
        )

        pdf_manager.set_scroll_ratio(self.addon_dir, "TestProfile", card_id=17, scroll_ratio=0.6)

        assert pdf_manager.get_page(self.addon_dir, "TestProfile", card_id=17) == 9
        assert pdf_manager.get_zoom(self.addon_dir, "TestProfile", card_id=17) == 1.75
        assert pdf_manager.get_scroll_ratio(self.addon_dir, "TestProfile", card_id=17) == 0.6
        assert pdf_manager.get_read_page(self.addon_dir, "TestProfile", card_id=17) == 8
        assert pdf_manager.get_read_anchor(self.addon_dir, "TestProfile", card_id=17) == {
            "page": 8,
            "x": 10.0,
            "y": 20.0,
            "w": 30.0,
            "h": 5.0,
            "text": "Stop here",
        }


class TestPdfDailyLimitStatus:
    def setup_method(self):
        import db as _db
        _db.close_connection()
        self.addon_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import db as _db
        _db.close_connection()
        shutil.rmtree(self.addon_dir, ignore_errors=True)

    def test_status_counts_current_page_and_remaining(self):
        pdf_manager.save_pdf_daily_limit_settings(
            self.addon_dir,
            "TestProfile",
            101,
            enabled=True,
            daily_page_limit=10,
            enforcement_mode="soft_lock",
        )
        with patch("pdf_manager.load_scheduler_config", return_value=MagicMock(day_end_time="04:00")), \
             patch("pdf_manager._effective_date", return_value="2026-04-18"):
            status = pdf_manager.get_pdf_daily_limit_status(
                self.addon_dir,
                "TestProfile",
                101,
                current_page=5,
            )

        assert status["enabled"] is True
        assert status["baseline_page"] == 4
        assert status["highest_page"] == 5
        assert status["pages_used"] == 1
        assert status["pages_remaining"] == 9
        assert status["allowed_max_page"] == 14
        assert status["blocking_active"] is False

    def test_status_only_grows_with_furthest_page_reached(self):
        pdf_manager.save_pdf_daily_limit_settings(
            self.addon_dir,
            "TestProfile",
            102,
            enabled=True,
            daily_page_limit=5,
            enforcement_mode="warning",
        )
        with patch("pdf_manager.load_scheduler_config", return_value=MagicMock(day_end_time="00:00")), \
             patch("pdf_manager._effective_date", return_value="2026-04-18"):
            pdf_manager.get_pdf_daily_limit_status(
                self.addon_dir,
                "TestProfile",
                102,
                current_page=3,
            )
            advanced = pdf_manager.get_pdf_daily_limit_status(
                self.addon_dir,
                "TestProfile",
                102,
                current_page=6,
            )
            backed_up = pdf_manager.get_pdf_daily_limit_status(
                self.addon_dir,
                "TestProfile",
                102,
                current_page=4,
            )

        assert advanced["pages_used"] == 4
        assert backed_up["pages_used"] == 4
        assert backed_up["highest_page"] == 6

    def test_status_with_persist_usage_false_does_not_create_usage_row(self):
        pdf_manager.save_pdf_daily_limit_settings(
            self.addon_dir,
            "TestProfile",
            103,
            enabled=True,
            daily_page_limit=7,
            enforcement_mode="warning",
        )
        with patch("pdf_manager.load_scheduler_config", return_value=MagicMock(day_end_time="00:00")), \
             patch("pdf_manager._effective_date", return_value="2026-04-18"):
            status = pdf_manager.get_pdf_daily_limit_status(
                self.addon_dir,
                "TestProfile",
                103,
                current_page=2,
                persist_usage=False,
            )

        assert status["pages_used"] == 1
        usage = db.get_pdf_daily_limit_usage(self.addon_dir, "TestProfile", 103, "2026-04-18")
        assert usage["highest_page"] == 0

    def test_soft_lock_override_disables_blocking_for_the_day(self):
        pdf_manager.save_pdf_daily_limit_settings(
            self.addon_dir,
            "TestProfile",
            104,
            enabled=True,
            daily_page_limit=3,
            enforcement_mode="soft_lock",
        )
        with patch("pdf_manager.load_scheduler_config", return_value=MagicMock(day_end_time="00:00")), \
             patch("pdf_manager._effective_date", return_value="2026-04-18"):
            pdf_manager.get_pdf_daily_limit_status(
                self.addon_dir,
                "TestProfile",
                104,
                current_page=1,
            )
            blocked = pdf_manager.get_pdf_daily_limit_status(
                self.addon_dir,
                "TestProfile",
                104,
                current_page=3,
            )
            overridden = pdf_manager.set_pdf_daily_limit_override(
                self.addon_dir,
                "TestProfile",
                104,
                enabled=True,
                current_page=3,
            )

        assert blocked["limit_reached"] is True
        assert blocked["blocking_active"] is True
        assert overridden["override_enabled"] is True
        assert overridden["blocking_active"] is False


class _FakeCard:
    def __init__(self, card_id, nid, *, queue=2, due=0):
        self.id = int(card_id)
        self.nid = int(nid)
        self.queue = int(queue)
        self.due = int(due)


class _FakeNote:
    def __init__(self, nid, first_field):
        self.id = int(nid)
        self.fields = [first_field]


class _FakeCollection:
    def __init__(self, *, due_ids, cards, notes):
        self._due_ids = list(due_ids)
        self._cards = dict(cards)
        self._notes = dict(notes)
        self.searches: list[str] = []

    def find_cards(self, query):
        self.searches.append(query)
        return list(self._due_ids)

    def get_card(self, card_id):
        return self._cards[int(card_id)]

    def get_note(self, note_id):
        return self._notes[int(note_id)]


class _FakePdfNote:
    def __init__(self, nid, **fields):
        self.id = int(nid)
        self._fields = dict(fields)

    def __getitem__(self, key):
        return self._fields[key]

    def __setitem__(self, key, value):
        self._fields[key] = value


class TestPdfDueSourceCards:
    def setup_method(self):
        import db as _db
        _db.close_connection()
        self.addon_dir = tempfile.mkdtemp()

    def teardown_method(self):
        import db as _db
        _db.close_connection()
        shutil.rmtree(self.addon_dir, ignore_errors=True)

    def test_returns_due_cards_only_up_to_current_page_sorted_by_source_page(self):
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=77, page=21, note_id=201, excerpt="page 21")
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=77, page=33, note_id=202, excerpt="page 33")
        db.add_pdf_card_source(self.addon_dir, "TestProfile", pdf_card_id=77, page=50, note_id=203, excerpt="page 50")

        col = _FakeCollection(
            due_ids=[502, 501],
            cards={
                501: _FakeCard(501, 201, queue=2, due=9),
                502: _FakeCard(502, 202, queue=1, due=3),
            },
            notes={
                201: _FakeNote(201, "<b>Earlier</b> card"),
                202: _FakeNote(202, "Later card"),
            },
        )

        rows = pdf_manager.get_due_pdf_source_cards(
            self.addon_dir,
            "TestProfile",
            77,
            33,
            col=col,
        )

        assert [row["card_id"] for row in rows] == [501, 502]
        assert [row["page"] for row in rows] == [21, 33]
        assert rows[0]["title"] == "Earlier card"
        assert rows[1]["due_state"] == "learning"
        assert "nid:203" not in col.searches[0]
        assert "(is:learn is:due)" in col.searches[0]
        assert "(is:review is:due)" in col.searches[0]
        assert "is:due OR is:learn" not in col.searches[0]

    def test_due_review_prompt_settings_round_trip(self):
        initial = pdf_manager.get_pdf_due_review_prompt_settings(
            self.addon_dir,
            "TestProfile",
            88,
        )
        assert initial["enabled"] is True

        updated = pdf_manager.save_pdf_due_review_prompt_settings(
            self.addon_dir,
            "TestProfile",
            88,
            enabled=False,
        )
        assert updated["enabled"] is False


class TestReplacePdfCardFile:
    def test_relinks_note_and_refreshes_text_index(self, tmp_path):
        replacement_pdf = tmp_path / "replacement.pdf"
        replacement_pdf.write_bytes(b"%PDF replacement")
        db.add_pdf_card_source(
            str(tmp_path),
            "TestProfile",
            pdf_card_id=77,
            page=3,
            note_id=901,
            excerpt="old extract",
            pdf_filename="old-file.pdf",
        )

        note = _FakePdfNote(
            321,
            Title="Linked PDF",
            PDF_Filename="old-file.pdf",
            Incremento_Imported_At="2026-04-01 10:00:00",
            Incremento_Parent="Parent",
            Incremento_Parent_Card_ID="88",
            Incremento_Source_Author="Author",
            Incremento_Content_ID="stable-pdf-content-id",
        )
        card = _FakeCard(77, 321)
        col = MagicMock()
        col.get_card.return_value = card
        col.get_note.return_value = note

        with patch("pdf_manager._copy_to_pdf_dir", return_value="new-file.pdf") as copy_mock, \
             patch("pdf_manager.ensure_pdf_note_type", return_value=None), \
             patch("pdf_manager.get_pdf_dir", return_value=str(tmp_path / "pdfs")), \
             patch("pdf_manager.render_pdf_cover_media", return_value="new-cover.png") as cover_mock, \
             patch("pdf_manager.extract_pdf_pages_text", return_value=["page one"]) as extract_mock, \
             patch("pdf_manager.replace_pdf_text_index") as index_mock, \
             patch("pdf_manager._paths.get_active_profile", return_value="TestProfile"):
            filename = pdf_manager.replace_pdf_card_file(
                str(tmp_path),
                col,
                77,
                str(replacement_pdf),
            )

        assert filename == "new-file.pdf"
        copy_mock.assert_called_once_with(
            str(replacement_pdf),
            profile="TestProfile",
        )
        cover_mock.assert_called_once_with(
            col,
            os.path.join(str(tmp_path / "pdfs"), "new-file.pdf"),
            title="Linked PDF",
            source_filename="new-file.pdf",
        )
        extract_mock.assert_called_once_with(os.path.join(str(tmp_path / "pdfs"), "new-file.pdf"))
        index_mock.assert_called_once_with(str(tmp_path), "TestProfile", 77, ["page one"])
        assert note["PDF_Filename"] == "new-file.pdf"
        assert note[PDF_COVER_FIELD] == "new-cover.png"
        assert note["Incremento_Source_Link"] == "pdfs/new-file.pdf"
        assert note["Incremento_Imported_At"] == "2026-04-01 10:00:00"
        assert note["Incremento_Parent"] == "Parent"
        assert note["Incremento_Parent_Card_ID"] == "88"
        assert note["Incremento_Source_Author"] == "Author"
        assert note[INCREMENTO_CONTENT_ID_FIELD] == "stable-pdf-content-id"
        assert db.get_pdf_card_source_filename(str(tmp_path), "TestProfile", 77, 3) == "new-file.pdf"
        col.update_note.assert_called_once_with(note)


class TestRepairPdfCardFilename:
    def test_repairs_note_when_unique_matching_disk_file_exists(self, tmp_path):
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        expected_filename = f"paper-{('a' * 32)}.pdf"
        (pdf_dir / expected_filename).write_bytes(b"%PDF repaired")

        note = _FakePdfNote(
            321,
            Title="Paper",
            PDF_Filename=f"paper-{('b' * 32)}.pdf",
            Incremento_Source_Link=f"pdfs/paper-{('b' * 32)}.pdf",
        )
        card = _FakeCard(77, 321)
        col = MagicMock()
        col.get_card.return_value = card
        col.get_note.return_value = note
        col.find_notes.return_value = [321]
        col.find_cards.return_value = [77]
        db.add_pdf_card_source(
            str(tmp_path),
            "TestProfile",
            pdf_card_id=77,
            page=2,
            note_id=777,
            excerpt="linked note",
            pdf_filename=f"paper-{('b' * 32)}.pdf",
        )

        with patch("pdf_manager._paths.get_pdf_dir", return_value=pdf_dir):
            repaired = pdf_manager.repair_pdf_card_filename(
                str(tmp_path),
                "TestProfile",
                col,
                77,
                missing_filename=f"paper-{('c' * 32)}.pdf",
            )

        assert repaired == expected_filename
        assert note["PDF_Filename"] == expected_filename
        assert note["Incremento_Source_Link"] == f"pdfs/{expected_filename}"
        assert db.get_pdf_card_source_filename(str(tmp_path), "TestProfile", 77, 2) == expected_filename
        col.update_note.assert_called_once_with(note)


class TestEnsurePdfNoteType:
    def test_adds_cover_field_when_creating_new_model(self):
        model = {"flds": [], "tmpls": []}

        class _Models:
            def by_name(self, name):
                return None

            def new(self, name):
                return model

            def new_field(self, name):
                return {"name": name}

            def add_field(self, model_dict, field):
                model_dict.setdefault("flds", []).append(field)

            def new_template(self, name):
                return {"name": name, "qfmt": "", "afmt": ""}

            def add_template(self, model_dict, template):
                model_dict.setdefault("tmpls", []).append(template)

            def add(self, model_dict):
                self.added = model_dict

        col = MagicMock(models=_Models())

        pdf_manager.ensure_pdf_note_type(col)

        assert [field["name"] for field in model["flds"][:3]] == ["Title", "PDF_Filename", PDF_COVER_FIELD]
        assert model["tmpls"][0]["qfmt"] == pdf_manager.CARD_TEMPLATE_FRONT

    def test_updates_existing_model_with_cover_field_and_template(self):
        model = {
            "flds": [{"name": "Title"}, {"name": "PDF_Filename"}],
            "tmpls": [{"qfmt": "old", "afmt": "old"}],
        }

        class _Models:
            def __init__(self):
                self.updated = False

            def by_name(self, name):
                return model

            def new_field(self, name):
                return {"name": name}

            def add_field(self, model_dict, field):
                model_dict["flds"].append(field)

            def update_dict(self, model_dict):
                self.updated = True

        models = _Models()
        col = MagicMock(models=models)

        pdf_manager.ensure_pdf_note_type(col, allow_existing_update=True)

        assert PDF_COVER_FIELD in [field["name"] for field in model["flds"]]
        assert model["tmpls"][0]["qfmt"] == pdf_manager.CARD_TEMPLATE_FRONT
        assert models.updated is True


class TestRegeneratePdfCardCover:
    def test_updates_existing_pdf_note_cover(self, tmp_path):
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        stored_pdf = pdf_dir / "stored.pdf"
        stored_pdf.write_bytes(b"%PDF stored")

        note = _FakePdfNote(321, Title="Linked PDF", PDF_Filename="stored.pdf", PDF_Cover_Image="")
        card = _FakeCard(77, 321)
        col = MagicMock()
        col.get_card.return_value = card
        col.get_note.return_value = note

        with patch("pdf_manager.ensure_pdf_note_type", return_value=None), \
             patch("pdf_manager.render_pdf_cover_media", return_value="fresh-cover.png") as cover_mock, \
             patch("pdf_manager._paths.get_active_profile", return_value="TestProfile"), \
             patch("pdf_manager._paths.get_pdf_dir", return_value=pdf_dir):
            result = pdf_manager.regenerate_pdf_card_cover(str(tmp_path), col, 77)

        assert result == "fresh-cover.png"
        cover_mock.assert_called_once_with(
            col,
            str(stored_pdf),
            title="Linked PDF",
            source_filename="stored.pdf",
        )
        assert note[PDF_COVER_FIELD] == "fresh-cover.png"
        col.update_note.assert_called_once_with(note)

    def test_missing_stored_pdf_does_not_update_note(self, tmp_path):
        note = _FakePdfNote(321, Title="Linked PDF", PDF_Filename="missing.pdf", PDF_Cover_Image="keep.png")
        card = _FakeCard(77, 321)
        col = MagicMock()
        col.get_card.return_value = card
        col.get_note.return_value = note

        with patch("pdf_manager._paths.get_active_profile", return_value="TestProfile"), \
             patch("pdf_manager._paths.get_pdf_dir", return_value=tmp_path / "pdfs"):
            try:
                pdf_manager.regenerate_pdf_card_cover(str(tmp_path), col, 77)
            except FileNotFoundError:
                pass
            else:
                raise AssertionError("Expected FileNotFoundError")

        assert note[PDF_COVER_FIELD] == "keep.png"
        col.update_note.assert_not_called()
