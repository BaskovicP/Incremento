import os
import subprocess
import sys
import threading
from pathlib import Path
from textwrap import dedent


# Some older dialog tests replace the shared aqt.qt test double during
# collection. Supply only the names needed to import this dialog module so the
# pure loader/path regressions remain order-independent.
_qt_module = sys.modules.get("aqt.qt")
if _qt_module is not None:
    for _name in (
        "QAbstractItemView",
        "QCheckBox",
        "QColor",
        "QComboBox",
        "QCompleter",
        "QDialog",
        "QEvent",
        "QHBoxLayout",
        "QIcon",
        "QLabel",
        "QLineEdit",
        "QListView",
        "QListWidget",
        "QListWidgetItem",
        "QMenu",
        "QPalette",
        "QPainter",
        "QPen",
        "QPixmap",
        "QPushButton",
        "QSize",
        "QStyle",
        "QStyleOptionViewItem",
        "QStyledItemDelegate",
        "QTimer",
        "QVBoxLayout",
    ):
        if not hasattr(_qt_module, _name):
            setattr(_qt_module, _name, type(_name, (), {}))
    if not hasattr(_qt_module, "qconnect"):
        _qt_module.qconnect = lambda *_args, **_kwargs: None

import pdf_bookshelf


ROOT = Path(__file__).resolve().parents[1]


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
            note_id=1,
        ),
        pdf_bookshelf._BookshelfEntry(
            title="Beta EPUB",
            card_id=22,
            kind="EPUB",
            cover_filename="beta-cover.jpg",
            source_filename="beta.epub",
            priority=75,
            tags=("reading", "machine_learning"),
            note_id=2,
        ),
    ]


def test_bookshelf_snapshot_preloads_attachment_counts_for_title_duplicates(
    monkeypatch,
):
    entries = [
        pdf_bookshelf._BookshelfEntry("Worked Copy", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("worked copy", 2, "PDF"),
        pdf_bookshelf._BookshelfEntry("Unrelated", 3, "PDF"),
    ]
    collection = object()
    calls = []

    def load_entries(addon_dir, *, collection=None, profile=None):
        calls.append(("load", addon_dir, collection, profile))
        return entries

    def attachment_counts(addon_dir, profile, candidates, *, col):
        calls.append(("counts", addon_dir, profile, candidates, col))
        return {1: 4, 2: 0}

    monkeypatch.setattr(pdf_bookshelf, "_load_bookshelf_entries", load_entries)
    monkeypatch.setattr(
        pdf_bookshelf,
        "_bookshelf_attachment_counts",
        attachment_counts,
    )

    snapshot = pdf_bookshelf._load_bookshelf_snapshot(
        "/addon",
        "Captured",
        collection=collection,
    )

    assert snapshot == (entries, {1: 4, 2: 0})
    assert calls == [
        ("load", "/addon", collection, "Captured"),
        ("counts", "/addon", "Captured", entries[:2], collection),
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
            note_id=7,
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


def test_bookshelf_possible_duplicates_match_original_filename_within_kind():
    uuid_a = "a" * 32
    uuid_b = "b" * 32
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            1,
            "PDF",
            source_filename=f"Guide-{uuid_a}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide [2]",
            2,
            "PDF",
            source_filename=f"guide-{uuid_b}.PDF",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            3,
            "EPUB",
            source_filename=f"Guide-{uuid_a}.epub",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            4,
            "PDF",
            source_filename=f"other-{uuid_a}.pdf",
        ),
    ]

    groups = pdf_bookshelf._bookshelf_duplicate_groups(entries)

    assert groups == ((entries[0], entries[1]),)
    assert pdf_bookshelf._bookshelf_duplicate_entries(entries) == entries[:2]


def test_bookshelf_possible_duplicates_fall_back_to_normalized_legacy_title():
    entries = [
        pdf_bookshelf._BookshelfEntry("Legacy Book", 1, "EPUB"),
        pdf_bookshelf._BookshelfEntry("legacy book\u200b", 2, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Legacy Book [3]", 3, "EPUB"),
        pdf_bookshelf._BookshelfEntry("Legacy Book", 4, "PDF"),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == (
        (entries[0], entries[1], entries[2]),
    )


def test_bookshelf_possible_duplicates_use_word_and_trigram_title_similarity():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Neuroscience: Exploring the Brain",
            1,
            "PDF",
            source_filename=f"source-one-{'a' * 32}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Exploring Brain — Neurosciences",
            2,
            "PDF",
            source_filename=f"source-two-{'b' * 32}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Unrelated",
            3,
            "PDF",
            source_filename=f"source-three-{'c' * 32}.pdf",
        ),
    ]

    matches = pdf_bookshelf._bookshelf_duplicate_matches(entries)

    assert matches[1] == (entries[1],)
    assert matches[2] == (entries[0],)
    assert 3 not in matches


def test_bookshelf_possible_duplicates_use_fuzzy_original_filename():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "First title",
            1,
            "PDF",
            source_filename=f"Sword_and_Scimitar-{'a' * 32}.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Completely different title",
            2,
            "PDF",
            source_filename=f"the-sword-scimitar-scan-{'b' * 32}.pdf",
        ),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == (
        (entries[0], entries[1]),
    )


def test_bookshelf_possible_duplicates_use_pdf_metadata_title():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "First import",
            1,
            "PDF",
            source_filename=f"opaque-one-{'a' * 32}.pdf",
            metadata_title="Neuroscience: Exploring the Brain",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Second import",
            2,
            "PDF",
            source_filename=f"opaque-two-{'b' * 32}.pdf",
            metadata_title="Exploring Brain — Neurosciences",
        ),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == (
        (entries[0], entries[1]),
    )


def test_bookshelf_pdf_metadata_title_ignores_generic_values_and_number_mismatches():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Alpha",
            1,
            "PDF",
            metadata_title="Untitled",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Beta",
            2,
            "PDF",
            metadata_title="untitled",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Gamma",
            3,
            "PDF",
            metadata_title="Collected Essays Volume 1",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Delta",
            4,
            "PDF",
            metadata_title="Collected Essays Volume 2",
        ),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == ()


def test_bookshelf_loads_pdf_metadata_titles_for_captured_profile(
    monkeypatch,
    tmp_path,
):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    first_pdf.write_bytes(b"%PDF-1.7")
    second_pdf.write_bytes(b"%PDF-1.7")
    resolved = {
        "first.pdf": str(first_pdf),
        "second.pdf": str(second_pdf),
    }
    path_calls = []
    title_calls = []
    monkeypatch.setattr(
        pdf_bookshelf,
        "pdf_storage_abspath",
        lambda filename, *, profile=None: (
            path_calls.append((filename, profile)) or resolved.get(filename, "")
        ),
    )
    monkeypatch.setattr(
        pdf_bookshelf,
        "_cached_pdf_metadata_title",
        lambda path: title_calls.append(path) or f"Metadata {Path(path).stem}",
    )
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "First",
            1,
            "PDF",
            source_filename="first.pdf",
        ),
        pdf_bookshelf._BookshelfEntry(
            "EPUB",
            2,
            "EPUB",
            source_filename="book.epub",
        ),
        pdf_bookshelf._BookshelfEntry(
            "Second",
            3,
            "PDF",
            source_filename="second.pdf",
        ),
    ]

    assert pdf_bookshelf._load_pdf_metadata_titles(
        entries,
        profile="Captured",
    ) == {
        1: "Metadata first",
        3: "Metadata second",
    }
    assert path_calls == [
        ("first.pdf", "Captured"),
        ("second.pdf", "Captured"),
    ]
    assert title_calls == [str(first_pdf), str(second_pdf)]


def test_bookshelf_reads_and_cleans_standard_pdf_title(monkeypatch, tmp_path):
    pdf_path = tmp_path / "metadata.pdf"
    pdf_path.write_bytes(b"%PDF-1.7")
    instances = []

    class _FakePdfDocument:
        class MetaDataField:
            Title = object()

        def __init__(self, _parent):
            self.loaded = ""
            self.closed = False
            instances.append(self)

        def load(self, path):
            self.loaded = path

        def metaData(self, field):
            assert field is self.MetaDataField.Title
            return "  Brain\x00 Research\nHandbook  "

        def close(self):
            self.closed = True

    monkeypatch.setattr(pdf_bookshelf, "QPdfDocument", _FakePdfDocument)

    assert pdf_bookshelf._read_pdf_metadata_title(str(pdf_path)) == (
        "Brain Research Handbook"
    )
    assert instances[0].loaded == str(pdf_path)
    assert instances[0].closed is True


def test_bookshelf_pdf_metadata_scan_honors_cancellation(monkeypatch):
    cancelled = threading.Event()
    cancelled.set()
    monkeypatch.setattr(
        pdf_bookshelf,
        "pdf_storage_abspath",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cancelled scan must not resolve files")
        ),
    )

    assert pdf_bookshelf._load_pdf_metadata_titles(
        [
            pdf_bookshelf._BookshelfEntry(
                "Cancelled",
                1,
                "PDF",
                source_filename="cancelled.pdf",
            )
        ],
        profile="Captured",
        cancelled=cancelled,
    ) == {}


def test_bookshelf_fuzzy_matching_respects_numbers_and_common_word_frequency():
    entries = [
        pdf_bookshelf._BookshelfEntry("World History Volume 1", 1, "PDF"),
        pdf_bookshelf._BookshelfEntry("World History Volume 2", 2, "PDF"),
        pdf_bookshelf._BookshelfEntry("Common Handbook Biology", 3, "PDF"),
        pdf_bookshelf._BookshelfEntry("Common Handbook Chemistry", 4, "PDF"),
        pdf_bookshelf._BookshelfEntry("Common Handbook Physics", 5, "PDF"),
    ]

    assert pdf_bookshelf._bookshelf_duplicate_groups(entries) == ()


def test_bookshelf_duplicate_filter_combines_with_existing_filters():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Guide",
            1,
            "PDF",
            source_filename=f"guide-{'a' * 32}.pdf",
            tags=("work",),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Guide [2]",
            2,
            "PDF",
            source_filename=f"guide-{'b' * 32}.pdf",
            tags=("archive",),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Unique",
            3,
            "PDF",
            source_filename=f"unique-{'a' * 32}.pdf",
            tags=("work",),
        ),
    ]

    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "guide",
        "PDF",
        tag_query="work",
        duplicates_only=True,
    ) == [entries[0]]
    assert pdf_bookshelf._filter_bookshelf_entries(
        entries,
        "",
        "PDF",
        tag_query="work",
        duplicates_only=False,
    ) == [entries[0], entries[2]]


def test_bookshelf_delete_targets_distinct_live_note_ids_only():
    entries = [
        pdf_bookshelf._BookshelfEntry("One", 1, "PDF", note_id=11),
        pdf_bookshelf._BookshelfEntry("Two", 2, "PDF", note_id=11),
        pdf_bookshelf._BookshelfEntry("Missing", 3, "PDF", note_id=0),
        pdf_bookshelf._BookshelfEntry("Three", 4, "PDF", note_id=22),
    ]

    assert pdf_bookshelf._bookshelf_note_ids(entries) == (11, 22)
    assert pdf_bookshelf._without_bookshelf_notes(entries, (11,)) == entries[2:]


def test_bookshelf_delete_attachment_check_uses_lightweight_media_resolver(monkeypatch):
    calls = []

    def linked_ids(addon_dir, profile, card_id, **kwargs):
        calls.append((addon_dir, profile, card_id, kwargs))
        if card_id == 1:
            return (10, 20)
        return (10, 40)

    monkeypatch.setattr(
        pdf_bookshelf,
        "linked_media_attachment_card_ids",
        linked_ids,
    )
    entries = [
        pdf_bookshelf._BookshelfEntry("PDF", 1, "PDF", note_id=101),
        pdf_bookshelf._BookshelfEntry("EPUB", 2, "EPUB", note_id=102),
    ]
    collection = object()

    assert pdf_bookshelf._bookshelf_attached_card_ids(
        "/addon",
        "Captured",
        entries,
        col=collection,
    ) == (10, 20, 40)
    assert [call[2] for call in calls] == [1, 2]
    assert [call[3]["media_kind"] for call in calls] == ["pdf", "epub"]
    assert all(call[3]["col"] is collection for call in calls)


def test_bookshelf_attachment_counts_are_per_document_and_drive_duplicate_badge(
    monkeypatch,
):
    def linked_ids(_addon_dir, _profile, card_id, **_kwargs):
        if card_id == 1:
            return (10, 10)
        return (20,)

    monkeypatch.setattr(
        pdf_bookshelf,
        "linked_media_attachment_card_ids",
        linked_ids,
    )
    first = pdf_bookshelf._BookshelfEntry("First", 1, "PDF")
    second = pdf_bookshelf._BookshelfEntry("Second", 2, "EPUB")
    counts = pdf_bookshelf._bookshelf_attachment_counts(
        "/addon",
        "Captured",
        [first, second],
        col=object(),
    )

    assert counts == {1: 1, 2: 1}
    assert pdf_bookshelf._bookshelf_entry_has_attachment_badge(
        first,
        duplicates_only=True,
        attachment_counts=counts,
    ) is True
    assert pdf_bookshelf._bookshelf_entry_has_attachment_badge(
        first,
        duplicates_only=False,
        attachment_counts=counts,
    ) is False
    assert pdf_bookshelf._bookshelf_entry_has_attachment_badge(
        pdf_bookshelf._BookshelfEntry("Unworked", 3, "PDF"),
        duplicates_only=True,
        attachment_counts=counts,
    ) is False


def test_bookshelf_delete_confirmation_warns_about_attached_cards():
    without_attachments = pdf_bookshelf._bookshelf_delete_confirmation(
        document_count=1,
        attached_card_count=0,
        keep_one=False,
    )
    with_attachments = pdf_bookshelf._bookshelf_delete_confirmation(
        document_count=1,
        attached_card_count=3,
        keep_one=False,
    )

    assert "attached" not in without_attachments.casefold()
    assert "3 attached cards" in with_attachments
    assert "will remain in Anki" in with_attachments
    assert "may no longer work" in with_attachments


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


def test_bookshelf_tag_suggestions_rank_frequency_and_dedupe_case():
    entries = [
        pdf_bookshelf._BookshelfEntry(
            "Alpha",
            1,
            "PDF",
            tags=("Work", "reading"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Beta",
            2,
            "EPUB",
            tags=("reading", "work", "machine_learning"),
        ),
        pdf_bookshelf._BookshelfEntry(
            "Gamma",
            3,
            "PDF",
            tags=("Reading", "project::Deep"),
        ),
    ]

    assert pdf_bookshelf._bookshelf_tag_suggestions(entries) == (
        "reading",
        "Work",
        "machine_learning",
        "project::Deep",
    )


def test_bookshelf_tag_completion_replaces_only_the_active_token():
    completed, cursor = pdf_bookshelf._complete_bookshelf_tag_query(
        "work, mach",
        "machine_learning",
        len("work, mach"),
    )
    assert completed == "work, machine_learning"
    assert cursor == len(completed)

    source = "work; mach reading"
    completed, cursor = pdf_bookshelf._complete_bookshelf_tag_query(
        source,
        "machine_learning",
        len("work; mach"),
    )
    assert completed == "work; machine_learning reading"
    assert cursor == len("work; machine_learning")

    assert pdf_bookshelf._complete_bookshelf_tag_query(
        "",
        "project::Deep",
        0,
    ) == ("project::Deep", len("project::Deep"))
    assert pdf_bookshelf._complete_bookshelf_tag_query(
        "work",
        "invalid tag",
        4,
    ) == ("work", 4)


def test_bookshelf_dialog_exposes_tag_filter_and_explicit_or_and_modes():
    source = Path(pdf_bookshelf.__file__).read_text(encoding="utf-8")

    assert 't("reader_bookshelf_filter_tags_placeholder")' in source
    assert 't("reader_bookshelf_any_tag")' in source
    assert 't("reader_bookshelf_all_tags")' in source
    assert 't("reader_bookshelf_browse_tags")' in source
    assert "QCompleter" in source
    assert "Qt.MatchFlag.MatchContains" in source
    assert "self._tag_search.textChanged" in source
    assert "self._tag_mode_combo.currentIndexChanged" in source


def test_bookshelf_dialog_exposes_duplicate_filter_and_safe_delete_context_menu():
    source = Path(pdf_bookshelf.__file__).read_text(encoding="utf-8")

    assert 't("reader_bookshelf_duplicates_only")' in source
    assert "Qt.ContextMenuPolicy.CustomContextMenu" in source
    assert "self._list.customContextMenuRequested" in source
    assert "def _show_context_menu" in source
    assert "remove_notes(" in source
    assert "askUser(" in source
    assert "_load_pdf_metadata_titles(" in source
    assert "uses_collection=False" in source
    assert '"reader_bookshelf_pdf_metadata_title"' in source
    assert "_bookshelf_attached_card_ids(" in source
    assert "QueryOp(" in source
    assert 't("reader_bookshelf_attachment_check_failed")' in source
    assert "class _BookshelfItemDelegate" in source
    assert "_ATTACHMENT_BADGE_ROLE" in source
    assert "self._list.setItemDelegate(" in source
    assert "_ATTACHMENT_BADGE_ROLE," in source
    assert "attachment_counts: dict[int, int] | None = None" in source
    assert "def _duplicates_filter_changed" in source
    assert "self._start_duplicate_attachment_scan()" in source
    assert '"reader_bookshelf_attached_badge_tooltip"' in source
    assert "self._list.itemClicked" not in source


def test_bookshelf_attachment_badge_renders_above_normal_and_selected_cover():
    script = dedent("""
        import os
        import sys
        import types
        from aqt.qt import (
            QApplication,
            QColor,
            QIcon,
            QListView,
            QListWidget,
            QListWidgetItem,
            QPixmap,
            QSize,
        )

        package = types.ModuleType("incremento")
        package.__path__ = [os.getcwd()]
        sys.modules["incremento"] = package
        from incremento.frontend import pdf_bookshelf

        app = QApplication([])
        view = QListWidget()
        view.resize(220, 380)
        view.setViewMode(QListView.ViewMode.IconMode)
        view.setIconSize(QSize(160, 220))
        view.setGridSize(QSize(196, 350))
        delegate = pdf_bookshelf._BookshelfItemDelegate(view)
        view.setItemDelegate(delegate)

        cover = QPixmap(160, 220)
        cover.fill(QColor("#ececec"))
        item = QListWidgetItem("Worked document")
        item.setIcon(QIcon(cover))
        item.setData(pdf_bookshelf._ATTACHMENT_BADGE_ROLE, 18)
        item.setSizeHint(QSize(196, 350))
        view.addItem(item)
        view.show()

        def badge_pixels():
            app.processEvents()
            image = view.viewport().grab().toImage()
            target = QColor("#188038")
            points = []
            for y in range(image.height()):
                for x in range(image.width()):
                    color = image.pixelColor(x, y)
                    if (
                        abs(color.red() - target.red()) <= 2
                        and abs(color.green() - target.green()) <= 2
                        and abs(color.blue() - target.blue()) <= 2
                    ):
                        points.append((x, y))
            assert len(points) > 300, len(points)
            assert max(x for x, _y in points) > 130
            assert min(y for _x, y in points) < 60

        badge_pixels()
        view.setCurrentItem(item)
        item.setSelected(True)
        badge_pixels()
        view.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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


def test_bookshelf_count_uses_locale_without_changing_kind_codes(monkeypatch):
    monkeypatch.setattr(pdf_bookshelf, "tn", lambda key, count, **values: f"{key}:{count}", raising=False)
    monkeypatch.setattr(pdf_bookshelf, "t", lambda key, **values: f"{key}:{values}", raising=False)
    entry = pdf_bookshelf._BookshelfEntry("原文", 1, "PDF")
    assert "reader_bookshelf_pdf_count:1" in pdf_bookshelf._bookshelf_count_text([entry], [entry], "PDF")


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
