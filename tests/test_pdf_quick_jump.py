import pdf_quick_jump


class _FakeNote:
    def __init__(self, fields=None, named_fields=None):
        self.fields = list(fields or [])
        self._named_fields = dict(named_fields or {})

    def __getitem__(self, key):
        return self._named_fields[key]


class _FakeCollection:
    def __init__(self, note_ids_by_query, notes, card_ids_by_nid):
        self._note_ids_by_query = dict(note_ids_by_query)
        self._notes = dict(notes)
        self._card_ids_by_nid = dict(card_ids_by_nid)

    def find_notes(self, query):
        return list(self._note_ids_by_query.get(query, []))

    def get_note(self, nid):
        return self._notes[nid]

    def find_cards(self, query):
        if not str(query).startswith("nid:"):
            return []
        nid = int(str(query).split(":", 1)[1])
        return list(self._card_ids_by_nid.get(nid, []))


def test_load_doc_quick_open_entries_returns_pdf_and_epub_rows(monkeypatch):
    monkeypatch.setattr(pdf_quick_jump, "get_all_priorities", lambda *_args: {11: 30, 22: 80})
    monkeypatch.setattr(pdf_quick_jump, "_active_profile", lambda: "TestProfile")
    fake_col = _FakeCollection(
        note_ids_by_query={
            f'note:"{pdf_quick_jump.PDF_NOTE_TYPE}" -is:suspended': [1],
            f'note:"{pdf_quick_jump.EPUB_NOTE_TYPE}" -is:suspended': [2],
        },
        notes={
            1: _FakeNote(fields=["Beta PDF"]),
            2: _FakeNote(fields=["Alpha EPUB"]),
        },
        card_ids_by_nid={
            1: [11],
            2: [22],
        },
    )

    entries = pdf_quick_jump._load_doc_quick_open_entries("/tmp/addon", collection=fake_col)

    assert [(entry.title, entry.card_id, entry.kind, entry.priority) for entry in entries] == [
        ("Alpha EPUB", 22, "EPUB", 80),
        ("Beta PDF", 11, "PDF", 30),
    ]


def test_load_writing_quick_open_entries_returns_relpath(monkeypatch):
    monkeypatch.setattr(pdf_quick_jump, "get_all_priorities", lambda *_args: {33: 12})
    monkeypatch.setattr(pdf_quick_jump, "_active_profile", lambda: "TestProfile")
    fake_col = _FakeCollection(
        note_ids_by_query={
            f'note:"{pdf_quick_jump.WRITING_NOTE_TYPE}" -is:suspended': [3],
        },
        notes={
            3: _FakeNote(
                fields=["Ignored fallback"],
                named_fields={
                    "Title": "Writing Note",
                    pdf_quick_jump.WRITING_FILE_FIELD: "writing/note.md",
                },
            ),
        },
        card_ids_by_nid={
            3: [33],
        },
    )

    entries = pdf_quick_jump._load_writing_quick_open_entries("/tmp/addon", collection=fake_col)

    assert entries == [
        pdf_quick_jump._QuickOpenEntry(
            title="Writing Note",
            card_id=33,
            kind="WRITING",
            priority=12,
            relpath="writing/note.md",
        )
    ]


def test_filter_quick_open_entries_applies_substring_search():
    entries = [
        pdf_quick_jump._QuickOpenEntry("Alpha PDF", 1, "PDF", 20),
        pdf_quick_jump._QuickOpenEntry("Beta Writing", 2, "WRITING", 10),
        pdf_quick_jump._QuickOpenEntry("Gamma EPUB", 3, "EPUB", None),
    ]

    filtered = pdf_quick_jump._filter_quick_open_entries(entries, "writ")

    assert filtered == [pdf_quick_jump._QuickOpenEntry("Beta Writing", 2, "WRITING", 10)]


def test_best_quick_open_entry_prefers_lowest_priority_and_defaults_none_to_mid():
    entries = [
        pdf_quick_jump._QuickOpenEntry("Unset", 1, "PDF", None),
        pdf_quick_jump._QuickOpenEntry("High", 2, "PDF", 70),
        pdf_quick_jump._QuickOpenEntry("Best", 3, "WRITING", 10),
    ]

    best = pdf_quick_jump._best_quick_open_entry(entries)

    assert best == pdf_quick_jump._QuickOpenEntry("Best", 3, "WRITING", 10)
