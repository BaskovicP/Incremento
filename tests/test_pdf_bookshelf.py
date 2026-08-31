import os
import sys
from pathlib import Path


# Some older dialog tests replace the shared aqt.qt test double during
# collection. Supply only the names needed to import this dialog module so the
# pure loader/path regressions remain order-independent.
_qt_module = sys.modules.get("aqt.qt")
if _qt_module is not None and not hasattr(_qt_module, "QAbstractItemView"):
    for _name in (
        "QAbstractItemView",
        "QCheckBox",
        "QColor",
        "QComboBox",
        "QDialog",
        "QEvent",
        "QHBoxLayout",
        "QIcon",
        "QLabel",
        "QLineEdit",
        "QListView",
        "QListWidget",
        "QListWidgetItem",
        "QPalette",
        "QPixmap",
        "QPushButton",
        "QSize",
        "QStyle",
        "QTimer",
        "QVBoxLayout",
    ):
        if not hasattr(_qt_module, _name):
            setattr(_qt_module, _name, type(_name, (), {}))
    if not hasattr(_qt_module, "qconnect"):
        _qt_module.qconnect = lambda *_args, **_kwargs: None

import pdf_bookshelf


class _FakeNote:
    def __init__(self, fields=None, named_fields=None, tags=None):
        self.fields = list(fields or [])
        self._named_fields = dict(named_fields or {})
        self.tags = list(tags or [])

    def __getitem__(self, key):
        return self._named_fields[key]


class _FakeCollection:
    def __init__(self, note_ids_by_query, notes, card_ids_by_nid):
        self._note_ids_by_query = dict(note_ids_by_query)
        self._notes = dict(notes)
        self._card_ids_by_nid = dict(card_ids_by_nid)
        self.queries = []

    def find_notes(self, query):
        self.queries.append(query)
        return list(self._note_ids_by_query.get(query, []))

    def get_note(self, note_id):
        return self._notes[note_id]

    def find_cards(self, query):
        if not str(query).startswith("nid:"):
            return []
        note_id = int(str(query).split(":", 1)[1])
        return list(self._card_ids_by_nid.get(note_id, []))


def test_bookshelf_loads_pdf_and_epub_notes_with_cover_metadata(monkeypatch):
    monkeypatch.setattr(
        pdf_bookshelf,
        "get_all_priorities",
        lambda *_args: {11: 25, 22: 75},
    )
    monkeypatch.setattr(pdf_bookshelf, "_active_profile", lambda: "TestProfile")
    pdf_query = f'note:"{pdf_bookshelf.PDF_NOTE_TYPE}"'
    epub_query = f'note:"{pdf_bookshelf.EPUB_NOTE_TYPE}"'
    collection = _FakeCollection(
        note_ids_by_query={pdf_query: [1], epub_query: [2]},
        notes={
            1: _FakeNote(
                fields=["Alpha fallback"],
                tags=["reading", "Work"],
                named_fields={
                    "Title": "Alpha PDF",
                    "PDF_Filename": "alpha.pdf",
                    pdf_bookshelf.PDF_COVER_FIELD: "alpha-cover.png",
                },
            ),
            2: _FakeNote(
                fields=["Beta fallback"],
                tags=["reading", "machine_learning"],
                named_fields={
                    "Title": "Beta EPUB",
                    pdf_bookshelf.EPUB_FILE_FIELD: "beta.epub",
                    pdf_bookshelf.EPUB_COVER_FIELD: "beta-cover.jpg",
                },
            ),
        },
        card_ids_by_nid={1: [11], 2: [22]},
    )

    entries = pdf_bookshelf._load_bookshelf_entries(
        "/tmp/addon",
        collection=collection,
    )

    assert collection.queries == [pdf_query, epub_query]
    assert all("-is:suspended" not in query for query in collection.queries)
    assert entries == [
        pdf_bookshelf._BookshelfEntry(
            title="Alpha PDF",
            card_id=11,
            kind="PDF",
            cover_filename="alpha-cover.png",
            source_filename="alpha.pdf",
            priority=25,
            tags=("reading", "Work"),
        ),
        pdf_bookshelf._BookshelfEntry(
            title="Beta EPUB",
            card_id=22,
            kind="EPUB",
            cover_filename="beta-cover.jpg",
            source_filename="beta.epub",
            priority=75,
            tags=("reading", "machine_learning"),
        ),
    ]


def test_bookshelf_keeps_legacy_pdf_without_cover_field(monkeypatch):
    monkeypatch.setattr(pdf_bookshelf, "get_all_priorities", lambda *_args: {})
    query = f'note:"{pdf_bookshelf.PDF_NOTE_TYPE}"'
    collection = _FakeCollection(
        note_ids_by_query={query: [7]},
        notes={
            7: _FakeNote(
                fields=["Legacy PDF"],
                named_fields={"PDF_Filename": "legacy.pdf"},
            )
        },
        card_ids_by_nid={7: [77]},
    )

    entries = pdf_bookshelf._load_bookshelf_entries(
        "/tmp/addon",
        collection=collection,
    )

    assert entries == [
        pdf_bookshelf._BookshelfEntry(
            title="Legacy PDF",
            card_id=77,
            kind="PDF",
            cover_filename="",
            source_filename="legacy.pdf",
            priority=None,
        )
    ]


def test_bookshelf_filter_is_case_insensitive_and_preserves_order():
    entries = [
        pdf_bookshelf._BookshelfEntry("Alpha", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("Deep Work", 2, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Work Notes", 3, "PDF"),
    ]

    assert pdf_bookshelf._filter_bookshelf_entries(entries, "WORK") == entries[1:]
    assert pdf_bookshelf._filter_bookshelf_entries(entries, "  ") == entries
    assert pdf_bookshelf._filter_bookshelf_entries(entries, "", "EPUB") == [
        entries[1]
    ]


def test_bookshelf_tag_query_normalizes_separators_case_and_duplicates():
    assert pdf_bookshelf._parse_bookshelf_tag_query(
        " Work, reading;WORK\nproject::Deep "
    ) == ("work", "reading", "project::deep")
    assert pdf_bookshelf._parse_bookshelf_tag_query("  , ; ") == ()


def test_bookshelf_tag_filter_supports_or_and_combines_with_title_and_kind():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Alpha Work",
            1,
            "PDF",
            tags=("reading", "Work"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Deep Learning",
            2,
            "EPUB",
            tags=("reading", "machine_learning"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Unsorted",
            3,
            "PDF",
            tags=(),
        ),
    ]

    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="WORK, machine_learning",
        tag_mode="OR",
    ) == entries[:2]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="READING work",
        tag_mode="AND",
    ) == [entries[0]]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "deep",
        "EPUB",
        tag_query="reading machine_learning",
        tag_mode="AND",
    ) == [entries[1]]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="missing",
        tag_mode="OR",
    ) == []
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "ALL",
        tag_query="",
        tag_mode="AND",
    ) == entries


def test_bookshelf_dialog_exposes_tag_filter_and_explicit_or_and_modes():
    source = Path(pdf_bookshelf.__file__).read_text(encoding="utf-8")

    assert "Filter by tags" in source
    assert "Any tag (OR)" in source
    assert "All tags (AND)" in source
    assert "self._tag_search.textChanged" in source
    assert "self._tag_mode_combo.currentIndexChanged" in source


def test_bookshelf_count_describes_current_document_filter():
    entries = [
        pdf_bookshelf._BookshelfEntry("Alpha", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("Deep Work", 2, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Work Notes", 3, "PDF"),
    ]

    assert (
        pdf_bookshelf._bookshelf_count_text(entries, entries, "ALL")
        == "3 documents · 2 PDFs · 1 EPUB"
    )
    assert (
        pdf_bookshelf._bookshelf_count_text(entries, [entries[1]], "EPUB")
        == "1 EPUB"
    )
    assert (
        pdf_bookshelf._bookshelf_count_text(entries, [entries[2]], "PDF")
        == "Showing 1 of 2 PDFs"
    )


def test_bookshelf_caption_colors_are_readable_in_dark_and_light_modes():
    dark_caption, dark_muted = pdf_bookshelf._bookshelf_theme_colors(32)
    light_caption, light_muted = pdf_bookshelf._bookshelf_theme_colors(240)

    assert dark_caption == "#f4f4f5"
    assert dark_muted == "#b8bcc4"
    assert light_caption == "#202124"
    assert light_muted == "#5f6368"


def test_media_preview_path_stays_inside_anki_media_directory(tmp_path):
    media_dir = tmp_path / "collection.media"
    media_dir.mkdir()
    cover = media_dir / "cover.png"
    cover.write_bytes(b"png")
    outside = tmp_path / "private.png"
    outside.write_bytes(b"private")

    resolved = pdf_bookshelf._existing_media_preview_path(
        str(media_dir),
        "cover.png",
    )

    assert resolved == os.path.realpath(cover)
    assert (
        pdf_bookshelf._existing_media_preview_path(
            str(media_dir),
            "../private.png",
        )
        == ""
    )
