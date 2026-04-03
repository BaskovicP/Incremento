import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import db

sys.modules.setdefault("db", db)

import epub_manager


def _write_test_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
            <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
              <rootfiles>
                <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
              </rootfiles>
            </container>""",
        )
        zf.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="utf-8"?>
            <package xmlns="http://www.idpf.org/2007/opf" version="3.0">
              <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
                <dc:title>Sample EPUB</dc:title>
              </metadata>
              <manifest>
                <item id="nav" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>
                <item id="chap1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
                <item id="chap2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
              </manifest>
              <spine>
                <itemref idref="chap1"/>
                <itemref idref="chap2"/>
              </spine>
            </package>""",
        )
        zf.writestr(
            "OEBPS/toc.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><body><nav>
            <ol>
              <li><a href="chapter1.xhtml">Chapter One</a></li>
              <li><a href="chapter2.xhtml">Chapter Two</a></li>
            </ol>
            </nav></body></html>""",
        )
        zf.writestr(
            "OEBPS/chapter1.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter 1</title></head>
            <body><h1>Chapter 1</h1><p>Hello from the first chapter.</p></body></html>""",
        )
        zf.writestr(
            "OEBPS/chapter2.xhtml",
            """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter 2</title></head>
            <body><h1>Chapter 2</h1><p>Second chapter text here.</p></body></html>""",
        )


class TestEnsureEpubExtracted:
    def test_extracts_metadata_and_sections(self, tmp_path):
        src = tmp_path / "sample.epub"
        _write_test_epub(src)
        extract_root = tmp_path / "extracted"

        with patch("epub_manager.get_epub_extract_root", return_value=str(extract_root)):
            meta = epub_manager.ensure_epub_extracted(str(src), stored_filename="sample.epub")

        assert meta["title"] == "Sample EPUB"
        assert [section["title"] for section in meta["sections"]] == ["Chapter 1", "Chapter 2"]
        assert "Hello from the first chapter." in meta["sections"][0]["text"]
        assert os.path.isfile(extract_root / "sample.epub" / "metadata.json")

    def test_load_metadata_reuses_cached_extract(self, tmp_path):
        src = tmp_path / "sample.epub"
        _write_test_epub(src)
        epub_dir = tmp_path / "epubs"
        epub_dir.mkdir()
        stored = epub_dir / "stored.epub"
        stored.write_bytes(src.read_bytes())
        extract_root = tmp_path / "extracted"

        with patch("epub_manager.get_epub_extract_root", return_value=str(extract_root)), patch(
            "epub_manager.get_epub_dir", return_value=str(epub_dir)
        ):
            epub_manager.ensure_epub_extracted(str(stored), stored_filename="stored.epub")
            meta = epub_manager.load_epub_metadata(str(tmp_path), "stored.epub")

        assert meta["sections"][1]["href"] == "OEBPS/chapter2.xhtml"


class TestEpubProgressAndIndex:
    def test_progress_round_trip(self, tmp_path):
        addon_dir = str(tmp_path)
        assert epub_manager.get_epub_progress(addon_dir, 10) == (0, 0.0, False)

        epub_manager.set_epub_progress(
            addon_dir,
            10,
            section_index=3,
            scroll_ratio=0.45,
            is_finished=True,
        )

        assert epub_manager.get_epub_progress(addon_dir, 10) == (3, 0.45, True)

    def test_replace_and_search_epub_text_index(self, tmp_path):
        db.replace_epub_text_index(
            str(tmp_path),
            42,
            [("Intro", "Alpha beta gamma"), ("Deep Dive", "Second chapter text")],
        )

        hits = db.search_epub_text_index(str(tmp_path), "second cha", limit=10)
        assert hits == [(42, 1, "Deep Dive", "Second chapter text")]
