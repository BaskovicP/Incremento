import os
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import db
import pytest

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
                <item id="cover" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>
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
        zf.writestr("OEBPS/images/cover.jpg", b"fake jpg")


class TestEnsureEpubExtracted:
    def test_extracts_metadata_and_sections(self, tmp_path):
        src = tmp_path / "sample.epub"
        _write_test_epub(src)
        extract_root = tmp_path / "extracted"

        with patch("epub_manager.get_epub_extract_root", return_value=str(extract_root)):
            meta = epub_manager.ensure_epub_extracted(str(src), stored_filename="sample.epub")

        assert meta["title"] == "Sample EPUB"
        assert meta["cover_href"] == "OEBPS/images/cover.jpg"
        assert [section["title"] for section in meta["sections"]] == ["Chapter 1", "Chapter 2"]
        assert "Hello from the first chapter." in meta["sections"][0]["text"]
        assert os.path.isfile(extract_root / "sample.epub" / "metadata.json")

    def test_rejects_rootfile_outside_extract_root(self, tmp_path):
        src = tmp_path / "malicious.epub"
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr(
                "META-INF/container.xml",
                """<?xml version="1.0"?>
                <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
                  <rootfiles>
                    <rootfile full-path="../../outside.opf" media-type="application/oebps-package+xml"/>
                  </rootfiles>
                </container>""",
            )

        extract_root = tmp_path / "extracted"
        with patch("epub_manager.get_epub_extract_root", return_value=str(extract_root)):
            with pytest.raises(RuntimeError, match="escapes extraction root"):
                epub_manager.ensure_epub_extracted(str(src), stored_filename="malicious.epub")

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


class TestCopyToEpubDir:
    def test_long_filename_stem_is_truncated_before_uuid_suffix(self, tmp_path):
        src = tmp_path / f'{"b" * 140}.epub'
        src.write_bytes(b"epub")
        epub_dir = tmp_path / "epubs"
        epub_dir.mkdir()

        with patch("epub_manager.get_epub_dir", return_value=str(epub_dir)):
            stored = epub_manager._copy_to_epub_dir(str(src))

        stem = Path(stored).stem
        base, _, suffix = stem.rpartition("-")
        assert len(base) <= 80
        assert len(suffix) == 32


class TestEpubStorageAbspath:
    def test_rejects_parent_traversal(self, tmp_path):
        epub_dir = tmp_path / "epubs"
        epub_dir.mkdir()

        with patch("epub_manager.get_epub_dir", return_value=str(epub_dir)):
            assert epub_manager.epub_storage_abspath("../../../etc/passwd") == ""


class TestEpubProgressAndIndex:
    def test_progress_round_trip(self, tmp_path):
        addon_dir = str(tmp_path)
        assert epub_manager.get_epub_progress(addon_dir, "TestProfile", 10) == (0, 0.0, False)
        assert epub_manager.get_read_section_index(addon_dir, "TestProfile", 10) == 0
        assert epub_manager.get_read_anchor(addon_dir, "TestProfile", 10) is None
        assert epub_manager.get_epub_font_scale(addon_dir, "TestProfile", 10) == 1.0

        epub_manager.set_epub_progress(
            addon_dir, "TestProfile", 10,
            section_index=3,
            scroll_ratio=0.45,
            is_finished=True,
        )
        epub_manager.set_read_section_index(
            addon_dir,
            "TestProfile",
            10,
            2,
            {"sectionIndex": 2, "offset": 123, "text": "Last sentence here"},
        )
        epub_manager.set_epub_font_scale(addon_dir, "TestProfile", 10, 1.35)

        assert epub_manager.get_epub_progress(addon_dir, "TestProfile", 10) == (3, 0.45, True)
        assert epub_manager.get_read_section_index(addon_dir, "TestProfile", 10) == 2
        assert epub_manager.get_read_anchor(addon_dir, "TestProfile", 10) == {
            "sectionIndex": 2,
            "offset": 123,
            "text": "Last sentence here",
        }
        assert epub_manager.get_epub_font_scale(addon_dir, "TestProfile", 10) == 1.35

        epub_manager.set_read_section_index(addon_dir, "TestProfile", 10, 2, None)
        assert epub_manager.get_read_anchor(addon_dir, "TestProfile", 10) is None

    def test_replace_and_search_epub_text_index(self, tmp_path):
        db.replace_epub_text_index(
            str(tmp_path), "TestProfile", 42,
            [("Intro", "Alpha beta gamma"), ("Deep Dive", "Second chapter text")],
        )

        hits = db.search_epub_text_index(str(tmp_path), "TestProfile", "second cha", limit=10)
        assert hits == [(42, 1, "Deep Dive", "Second chapter text")]


class _FakeEpubCard:
    def __init__(self, card_id: int, nid: int, queue: int, due: int):
        self.id = int(card_id)
        self.nid = int(nid)
        self.queue = int(queue)
        self.due = int(due)


class _FakeEpubNote:
    def __init__(self, title: str):
        self.fields = [title]


class _FakeEpubCol:
    def __init__(self):
        self.searches: list[str] = []
        self._cards = {
            101: _FakeEpubCard(101, 1001, queue=2, due=10),
            102: _FakeEpubCard(102, 1002, queue=1, due=3),
        }
        self._notes = {
            1001: _FakeEpubNote("Section One Card"),
            1002: _FakeEpubNote("Section Two Card"),
        }

    def find_cards(self, query: str):
        self.searches.append(str(query))
        return [101, 102]

    def get_card(self, card_id: int):
        return self._cards[int(card_id)]

    def get_note(self, note_id: int):
        return self._notes[int(note_id)]


class _FakeEpubCoverNote:
    def __init__(self, note_id: int, **fields):
        self.id = note_id
        self.mid = 123
        self.fields = dict(fields)

    def __getitem__(self, name: str):
        return self.fields.get(name, "")

    def __setitem__(self, name: str, value):
        self.fields[name] = value


class TestEpubCoverMedia:
    def test_render_epub_cover_media_uses_declared_cover_image(self, tmp_path):
        src = tmp_path / "sample.epub"
        _write_test_epub(src)
        extract_root = tmp_path / "extracted"
        media = MagicMock()
        media.add_file.return_value = "stored-cover.jpg"
        col = MagicMock(media=media)

        with patch("epub_manager.get_epub_extract_root", return_value=str(extract_root)):
            result = epub_manager.render_epub_cover_media(
                col,
                str(src),
                title="Sample EPUB",
                source_filename="sample.epub",
            )

        assert result == "stored-cover.jpg"
        saved_path = media.add_file.call_args.args[0]
        assert os.path.basename(saved_path).startswith("Sample_EPUB-cover-")
        assert os.path.basename(saved_path).endswith(".jpg")

    def test_regenerate_epub_card_cover_updates_note(self, tmp_path):
        epub_dir = tmp_path / "epubs"
        epub_dir.mkdir()
        stored_epub = epub_dir / "stored.epub"
        _write_test_epub(stored_epub)

        note = _FakeEpubCoverNote(
            321,
            Title="Linked EPUB",
            EPUB_Filename="stored.epub",
            EPUB_Cover_Image="",
        )
        card = _FakeEpubCard(77, 321, queue=2, due=10)
        col = MagicMock()
        col.get_card.return_value = card
        col.get_note.return_value = note

        with patch("epub_manager.ensure_epub_note_type", return_value=None), \
             patch("epub_manager.render_epub_cover_media", return_value="fresh-cover.jpg") as cover_mock, \
             patch("epub_manager._paths.get_active_profile", return_value="TestProfile"), \
             patch("epub_manager._paths.get_epub_dir", return_value=epub_dir):
            result = epub_manager.regenerate_epub_card_cover(str(tmp_path), col, 77)

        assert result == "fresh-cover.jpg"
        cover_mock.assert_called_once_with(
            col,
            str(stored_epub),
            title="Linked EPUB",
            source_filename="stored.epub",
        )
        assert note[epub_manager.EPUB_COVER_FIELD] == "fresh-cover.jpg"
        col.update_note.assert_called_once_with(note)

    def test_missing_stored_epub_does_not_update_note(self, tmp_path):
        note = _FakeEpubCoverNote(
            321,
            Title="Linked EPUB",
            EPUB_Filename="missing.epub",
            EPUB_Cover_Image="keep.jpg",
        )
        card = _FakeEpubCard(77, 321, queue=2, due=10)
        col = MagicMock()
        col.get_card.return_value = card
        col.get_note.return_value = note

        with patch("epub_manager._paths.get_active_profile", return_value="TestProfile"), \
             patch("epub_manager._paths.get_epub_dir", return_value=tmp_path / "epubs"):
            try:
                epub_manager.regenerate_epub_card_cover(str(tmp_path), col, 77)
            except FileNotFoundError:
                pass
            else:
                raise AssertionError("Expected FileNotFoundError")

        assert note[epub_manager.EPUB_COVER_FIELD] == "keep.jpg"
        col.update_note.assert_not_called()


class TestEpubWorkflowHelpers:
    def test_due_epub_source_cards_collects_due_cards_up_to_section(self, tmp_path):
        addon_dir = str(tmp_path)
        db.add_epub_card_source(addon_dir, "TestProfile", epub_card_id=5, section_index=0, note_id=1001, excerpt="earlier")
        db.add_epub_card_source(addon_dir, "TestProfile", epub_card_id=5, section_index=2, note_id=1002, excerpt="later")

        col = _FakeEpubCol()
        rows = epub_manager.get_due_epub_source_cards(
            addon_dir,
            "TestProfile",
            epub_card_id=5,
            max_section_index=2,
            col=col,
        )

        assert rows == [
            {
                "card_id": 101,
                "note_id": 1001,
                "section_index": 0,
                "title": "Section One Card",
                "excerpt": "earlier",
                "queue": 2,
                "due": 10,
                "due_state": "due",
            },
            {
                "card_id": 102,
                "note_id": 1002,
                "section_index": 2,
                "title": "Section Two Card",
                "excerpt": "later",
                "queue": 1,
                "due": 3,
                "due_state": "learning",
            },
        ]
        assert "(is:learn is:due)" in col.searches[0]
        assert "(is:review is:due)" in col.searches[0]
        assert "is:due OR is:learn" not in col.searches[0]

    def test_epub_daily_limit_status_uses_sections(self, tmp_path):
        addon_dir = str(tmp_path)
        with patch("epub_manager.load_scheduler_config", return_value=type("Cfg", (), {"day_end_time": "00:00"})()), patch(
            "epub_manager._effective_date", return_value="2026-04-23"
        ):
            epub_manager.save_epub_daily_limit_settings(
                addon_dir,
                "TestProfile",
                10,
                enabled=True,
                daily_section_limit=2,
                enforcement_mode="soft_lock",
            )
            status = epub_manager.get_epub_daily_limit_status(
                addon_dir,
                "TestProfile",
                10,
                current_section_index=1,
            )

        assert status["enabled"] is True
        assert status["daily_section_limit"] == 2
        assert status["sections_used"] == 1
        assert status["sections_remaining"] == 1
        assert status["allowed_max_section"] == 2

    def test_epub_daily_limit_status_uses_page_aliases(self, tmp_path):
        addon_dir = str(tmp_path)
        with patch("epub_manager.load_scheduler_config", return_value=type("Cfg", (), {"day_end_time": "00:00"})()), patch(
            "epub_manager._effective_date", return_value="2026-04-24"
        ):
            epub_manager.save_epub_daily_limit_settings(
                addon_dir,
                "TestProfile",
                11,
                enabled=True,
                daily_section_limit=3,
                enforcement_mode="hard_stop",
            )
            status = epub_manager.get_epub_daily_limit_status(
                addon_dir,
                "TestProfile",
                11,
                current_section_index=0,
                current_page_index=4,
            )

        assert status["daily_page_limit"] == 3
        assert status["current_page_index"] == 4
        assert status["baseline_page"] == 3
        assert status["highest_page"] == 4
        assert status["pages_used"] == 1
        assert status["pages_remaining"] == 2
        assert status["allowed_max_page"] == 6

    def test_epub_daily_limit_highest_page_only_grows(self, tmp_path):
        addon_dir = str(tmp_path)
        with patch("epub_manager.load_scheduler_config", return_value=type("Cfg", (), {"day_end_time": "00:00"})()), patch(
            "epub_manager._effective_date", return_value="2026-04-25"
        ):
            epub_manager.save_epub_daily_limit_settings(
                addon_dir,
                "TestProfile",
                12,
                enabled=True,
                daily_section_limit=2,
                enforcement_mode="soft_lock",
            )
            epub_manager.get_epub_daily_limit_status(
                addon_dir,
                "TestProfile",
                12,
                current_page_index=5,
            )
            backed_up = epub_manager.get_epub_daily_limit_status(
                addon_dir,
                "TestProfile",
                12,
                current_page_index=4,
            )

        assert backed_up["baseline_page"] == 4
        assert backed_up["highest_page"] == 5
        assert backed_up["pages_used"] == 1
        assert backed_up["allowed_max_page"] == 6
