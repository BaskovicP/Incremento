from backend import pdf_context_cards


class _Note:
    def __init__(self, note_id, fields):
        self.id = note_id
        self.fields = list(fields)


class _Db:
    def __init__(self, note_ids):
        self.note_ids = list(note_ids)
        self.calls = []

    def list(self, query, value):
        self.calls.append((query, value))
        return list(self.note_ids)


class _Collection:
    def __init__(self, notes):
        self.notes = {note.id: note for note in notes}
        self.db = _Db(self.notes)
        self.updated = []
        self.update_batches = []
        self.undo_labels = []
        self.merged = []

    def get_note(self, note_id):
        return self.notes[note_id]

    def update_note(self, note):
        self.updated.append(note.id)

    def update_notes(self, notes):
        note_ids = [note.id for note in notes]
        self.update_batches.append(note_ids)
        self.updated.extend(note_ids)

    def add_custom_undo_entry(self, label):
        self.undo_labels.append(label)
        return 42

    def merge_undo_entries(self, step):
        self.merged.append(step)
        return {"notes": True}


def test_rebuild_all_pdf_context_cards_updates_changed_notes_in_one_undo_step():
    collection = _Collection(
        [
            _Note(1, ["plain", "incremento_open_pdf_ref: one"]),
            _Note(2, ["incremento_open_pdf_ref: two"]),
        ]
    )

    def transform(field):
        if "incremento_open_pdf_ref:" not in field:
            return field, 0, 0
        return field + " rebuilt", 1, 0

    result = pdf_context_cards.rebuild_all_pdf_context_cards(
        collection,
        transform,
        undo_label="Rebuild PDF contexts",
    )

    assert collection.db.calls == [
        (
            "SELECT id FROM notes WHERE flds LIKE ? ESCAPE '\\' ORDER BY id",
            "%incremento\\_open\\_pdf\\_ref:%",
        )
    ]
    assert collection.updated == [1, 2]
    assert collection.update_batches == [[1, 2]]
    assert collection.undo_labels == ["Rebuild PDF contexts"]
    assert collection.merged == [42]
    assert result.scanned_notes == 2
    assert result.changed_notes == 2
    assert result.updated_contexts == 2
    assert result.skipped_contexts == 0
    assert result.changes == {"notes": True}


def test_rebuild_all_pdf_context_cards_does_not_create_undo_for_unchanged_notes():
    collection = _Collection([_Note(1, ["incremento_open_pdf_ref: one"])])

    result = pdf_context_cards.rebuild_all_pdf_context_cards(
        collection,
        lambda field: (field, 0, 1),
        undo_label="Rebuild PDF contexts",
    )

    assert collection.updated == []
    assert collection.undo_labels == []
    assert collection.merged == []
    assert result.changed_notes == 0
    assert result.skipped_contexts == 1
    assert result.changes is None


def test_rebuild_bulk_updates_notes_before_merging_the_custom_undo_step():
    class _BoundedUndoCollection(_Collection):
        def __init__(self, notes):
            super().__init__(notes)
            self.undo_steps = []
            self.next_step = 1

        def _push_undo_step(self):
            step = self.next_step
            self.next_step += 1
            self.undo_steps.append(step)
            self.undo_steps = self.undo_steps[-3:]
            return step

        def add_custom_undo_entry(self, label):
            self.undo_labels.append(label)
            return self._push_undo_step()

        def update_note(self, note):
            super().update_note(note)
            self._push_undo_step()

        def update_notes(self, notes):
            super().update_notes(notes)
            self._push_undo_step()

        def merge_undo_entries(self, step):
            if step not in self.undo_steps:
                raise RuntimeError("target undo op not found")
            self.merged.append(step)
            return {"notes": True}

    collection = _BoundedUndoCollection(
        [_Note(note_id, ["incremento_open_pdf_ref: source"]) for note_id in range(10)]
    )

    result = pdf_context_cards.rebuild_all_pdf_context_cards(
        collection,
        lambda field: (field + " rebuilt", 1, 0),
        undo_label="Rebuild PDF contexts",
    )

    assert collection.update_batches == [list(range(10))]
    assert collection.merged == [1]
    assert result.changed_notes == 10


def test_rebuild_reports_progress_for_every_scanned_note():
    collection = _Collection(
        [
            _Note(1, ["incremento_open_pdf_ref: one"]),
            _Note(2, ["incremento_open_pdf_ref: two"]),
            _Note(3, ["plain"]),
        ]
    )
    progress = []

    pdf_context_cards.rebuild_all_pdf_context_cards(
        collection,
        lambda field: (field, 0, 1),
        undo_label="Rebuild PDF contexts",
        progress=lambda completed, total: progress.append((completed, total)),
    )

    assert progress == [(0, 3), (1, 3), (2, 3), (3, 3)]
