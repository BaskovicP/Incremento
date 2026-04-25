import importlib.util
import os
import sys


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


lfm = _load("_incremento_local_file_manager", "backend/local_file_manager.py")
nm = _load("_incremento_note_metadata_local_file", "backend/note_metadata.py")


class _FakeModels:
    def __init__(self):
        self.models = {}
        self._next_mid = 1

    def by_name(self, name):
        return self.models.get(name)

    def new(self, name):
        model = {"name": name, "flds": [], "tmpls": [], "id": self._next_mid}
        self._next_mid += 1
        return model

    def new_field(self, name):
        return {"name": name}

    def add_field(self, model, field):
        model["flds"].append(field)

    def new_template(self, name):
        return {"name": name, "qfmt": "", "afmt": ""}

    def add_template(self, model, template):
        model["tmpls"].append(template)

    def add(self, model):
        self.models[model["name"]] = model

    def update_dict(self, model):
        self.models[model["name"]] = model

    def get(self, mid):
        for model in self.models.values():
            if model["id"] == mid:
                return model
        return None


class _DeckResult:
    def __init__(self, deck_id):
        self.id = deck_id


class _FakeDecks:
    def __init__(self):
        self.decks = {}
        self._next_id = 100

    def by_name(self, name):
        deck = self.decks.get(name)
        if deck is None:
            return None
        return {"id": deck}

    def add_normal_deck_with_name(self, name):
        deck_id = self._next_id
        self._next_id += 1
        self.decks[name] = deck_id
        return _DeckResult(deck_id)


class _FakeNote(dict):
    def __init__(self, model, note_id):
        super().__init__()
        self._model = model
        self.id = note_id
        self.mid = model["id"]
        self.tags = []

    def note_type(self):
        return self._model

    def add_tag(self, tag):
        self.tags.append(tag)


class _FakeCol:
    def __init__(self):
        self.models = _FakeModels()
        self.decks = _FakeDecks()
        self._next_note_id = 1
        self._next_card_id = 1000
        self._cards_by_note = {}
        self.last_note = None

    def new_note(self, model):
        note = _FakeNote(model, self._next_note_id)
        self._next_note_id += 1
        return note

    def add_note(self, note, deck_id):
        card_id = self._next_card_id
        self._next_card_id += 1
        self._cards_by_note[note.id] = [card_id]
        self.last_note = note
        return deck_id

    def find_cards(self, query):
        prefix, _, value = query.partition(":")
        if prefix != "nid":
            return []
        return self._cards_by_note.get(int(value), [])


def test_prepare_local_file_storage_reference_mode_uses_absolute_path(tmp_path):
    source = tmp_path / "notes" / "example.txt"
    source.parent.mkdir(parents=True)
    source.write_text("hello", encoding="utf-8")

    stored_path, filename = lfm.prepare_local_file_storage(
        str(tmp_path),
        "TestProfile",
        str(source),
        lfm.LOCAL_FILE_MODE_REFERENCE,
    )

    assert stored_path == os.path.abspath(str(source))
    assert filename == "example.txt"
    assert lfm.resolve_local_file_abspath(
        str(tmp_path),
        "TestProfile",
        stored_path,
        lfm.LOCAL_FILE_MODE_REFERENCE,
    ) == os.path.abspath(str(source))


def test_prepare_local_file_storage_managed_copy_copies_into_profile_files_dir(tmp_path):
    source = tmp_path / "source" / "project.plan"
    source.parent.mkdir(parents=True)
    source.write_text("plan", encoding="utf-8")

    stored_path, filename = lfm.prepare_local_file_storage(
        str(tmp_path),
        "TestProfile",
        str(source),
        lfm.LOCAL_FILE_MODE_MANAGED_COPY,
    )

    assert stored_path.startswith("files/")
    assert filename == "project.plan"
    resolved = lfm.resolve_local_file_abspath(
        str(tmp_path),
        "TestProfile",
        stored_path,
        lfm.LOCAL_FILE_MODE_MANAGED_COPY,
    )
    assert os.path.isfile(resolved)
    with open(resolved, "r", encoding="utf-8") as handle:
        assert handle.read() == "plan"


def test_relink_local_file_preserves_managed_mode_and_updates_fields(tmp_path):
    first = tmp_path / "source" / "first.docx"
    second = tmp_path / "source" / "second.docx"
    first.parent.mkdir(parents=True)
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")

    stored_path, filename = lfm.prepare_local_file_storage(
        str(tmp_path),
        "TestProfile",
        str(first),
        lfm.LOCAL_FILE_MODE_MANAGED_COPY,
    )
    note = {
        lfm.LOCAL_FILE_MODE_FIELD: lfm.LOCAL_FILE_MODE_MANAGED_COPY,
        lfm.LOCAL_FILE_PATH_FIELD: stored_path,
        lfm.LOCAL_FILE_NAME_FIELD: filename,
    }

    new_stored_path, new_filename = lfm.relink_local_file(
        str(tmp_path),
        "TestProfile",
        note,
        new_source_path=str(second),
    )

    assert new_filename == "second.docx"
    assert new_stored_path.startswith("files/")
    assert note[lfm.LOCAL_FILE_PATH_FIELD] == new_stored_path
    assert note[lfm.LOCAL_FILE_NAME_FIELD] == "second.docx"
    resolved = lfm.resolve_local_file_abspath(
        str(tmp_path),
        "TestProfile",
        new_stored_path,
        lfm.LOCAL_FILE_MODE_MANAGED_COPY,
    )
    with open(resolved, "r", encoding="utf-8") as handle:
        assert handle.read() == "second"


def test_ensure_local_file_note_type_creates_expected_fields():
    col = _FakeCol()

    lfm.ensure_local_file_note_type(col)

    model = col.models.by_name(lfm.LOCAL_FILE_NOTE_TYPE)
    field_names = [field["name"] for field in model["flds"]]
    assert field_names[:5] == [
        "Title",
        lfm.LOCAL_FILE_NAME_FIELD,
        lfm.LOCAL_FILE_PATH_FIELD,
        lfm.LOCAL_FILE_MODE_FIELD,
        lfm.LOCAL_FILE_NOTE_FIELD,
    ]
    assert nm.INCREMENTO_SOURCE_LINK_FIELD in field_names
    assert model["tmpls"][0]["qfmt"] == lfm.CARD_TEMPLATE_FRONT


def test_add_local_file_card_populates_note_fields_and_metadata(tmp_path):
    source = tmp_path / "refs" / "brief.md"
    source.parent.mkdir(parents=True)
    source.write_text("# brief", encoding="utf-8")
    col = _FakeCol()

    card_id = lfm.add_local_file_card(
        str(tmp_path),
        "TestProfile",
        col,
        source_path=str(source),
        title="Client Brief",
        deck_name="Topics",
        tags=["project"],
        mode=lfm.LOCAL_FILE_MODE_REFERENCE,
        note_text="Open in native editor",
    )

    assert card_id == 1000
    assert col.last_note["Title"] == "Client Brief"
    assert col.last_note[lfm.LOCAL_FILE_NAME_FIELD] == "brief.md"
    assert col.last_note[lfm.LOCAL_FILE_MODE_FIELD] == lfm.LOCAL_FILE_MODE_REFERENCE
    assert col.last_note[lfm.LOCAL_FILE_NOTE_FIELD] == "Open in native editor"
    assert col.last_note[nm.INCREMENTO_SOURCE_TYPE_FIELD] == "Local File"
    assert col.last_note[nm.INCREMENTO_SOURCE_LINK_FIELD] == os.path.abspath(str(source))
    assert "Incremento" in col.last_note.tags
    assert "project" in col.last_note.tags
