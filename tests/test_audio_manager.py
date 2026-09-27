import importlib.util
import os
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", relpath)),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


audio = _load("_incremento_audio_manager", "backend/audio_manager.py")


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


class _DeckResult:
    def __init__(self, deck_id):
        self.id = deck_id


class _FakeDecks:
    def __init__(self):
        self.decks = {}
        self._next_id = 100

    def by_name(self, name):
        deck_id = self.decks.get(name)
        return {"id": deck_id} if deck_id is not None else None

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


class _FakeMedia:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True)
        self.added = []
        self.trashed = []

    def add_file(self, source_path):
        source = Path(source_path)
        target = self.root / source.name
        shutil.copyfile(source, target)
        self.added.append(target.name)
        return target.name

    def trash_files(self, filenames):
        self.trashed.extend(filenames)
        for filename in filenames:
            (self.root / filename).unlink(missing_ok=True)


class _FakeCol:
    def __init__(self, media_root, *, reject_notes=False):
        self.models = _FakeModels()
        self.decks = _FakeDecks()
        self.media = _FakeMedia(media_root)
        self.reject_notes = reject_notes
        self._next_note_id = 1
        self._next_card_id = 1000
        self._cards_by_note = {}
        self.last_note = None

    def new_note(self, model):
        note = _FakeNote(model, self._next_note_id)
        self._next_note_id += 1
        return note

    def add_note(self, note, _deck_id):
        if self.reject_notes:
            return 0
        card_id = self._next_card_id
        self._next_card_id += 1
        self._cards_by_note[note.id] = [card_id]
        self.last_note = note
        return 1

    def find_cards(self, query):
        prefix, _, value = query.partition(":")
        return self._cards_by_note.get(int(value), []) if prefix == "nid" else []


def test_audio_note_type_uses_synced_media_and_device_local_resume_player():
    spec = audio.audio_note_type_spec()

    assert spec.name == "Incremento Audio"
    assert spec.fields[:5] == (
        "Title",
        "Audio",
        "Audio_Filename",
        "Progress_Key",
        "Notes",
    )
    assert "<audio" in spec.question_template
    assert 'src="{{text:Audio_Filename}}"' in spec.question_template
    assert "localStorage.getItem" in spec.question_template
    assert "localStorage.setItem" in spec.question_template
    assert "loadedmetadata" in spec.question_template
    assert "timeupdate" in spec.question_template
    assert "pagehide" in spec.question_template
    assert spec.answer_template == spec.question_template


def test_add_audio_card_copies_media_and_creates_portable_topic(tmp_path):
    source = tmp_path / "NotebookLM overview.MP3"
    source.write_bytes(b"ID3\x04\x00\x00test audio")
    col = _FakeCol(tmp_path / "collection.media")

    card_id = audio.add_audio_card(
        str(tmp_path / "addon"),
        "TestProfile",
        col,
        source_path=str(source),
        title="My <Audio>",
        deck_name="Topics",
        tags=["topic", "lecture"],
        notes="Line one\nLine two",
    )

    note = col.last_note
    assert card_id == 1000
    assert col.decks.decks["Topics"] == 100
    assert note["Title"] == "My &lt;Audio&gt;"
    assert note["Audio"].startswith("[sound:incremento-audio-")
    assert note["Audio"].endswith(".mp3]")
    assert note["Audio_Filename"] in col.media.added
    assert (tmp_path / "collection.media" / note["Audio_Filename"]).read_bytes() == source.read_bytes()
    assert len(note["Progress_Key"]) == 32
    assert note["Notes"] == "Line one<br>Line two"
    assert note.tags == ["Incremento", "topic", "lecture"]
    assert note["Incremento_Source_Type"] == "Audio"
    assert note["Incremento_Source_Title"] == "My <Audio>"
    assert note["Incremento_Source_Link"] == note["Audio_Filename"]
    assert "Source:" not in note["Notes"]
    db_path = tmp_path / "addon" / "user_files" / "TestProfile" / "incremento.db"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT state, operation_kind FROM import_journal"
        ).fetchall() == [("committed", "audio")]
        assert conn.execute(
            "SELECT kind, card_id, storage_key FROM content_items"
        ).fetchall() == [("audio", 1000, note["Audio_Filename"])]


@pytest.mark.parametrize("filename", ["overview.exe", "overview.ogg", "overview"])
def test_add_audio_card_rejects_nonportable_extensions_before_side_effects(
    tmp_path, filename
):
    source = tmp_path / filename
    source.write_bytes(b"audio")
    col = _FakeCol(tmp_path / "collection.media")

    with pytest.raises(ValueError, match="MP3, M4A, AAC, or WAV"):
        audio.add_audio_card(
            str(tmp_path / "addon"),
            "TestProfile",
            col,
            source_path=str(source),
            title="Overview",
        )

    assert col.media.added == []
    assert col.models.models == {}


def test_add_audio_card_rejects_files_at_ankiweb_limit_before_side_effects(tmp_path):
    source = tmp_path / "large.mp3"
    source.write_bytes(b"x")
    col = _FakeCol(tmp_path / "collection.media")
    original_getsize = audio.os.path.getsize

    def fake_getsize(path):
        if os.fspath(path) == os.fspath(source):
            return audio.MAX_AUDIO_BYTES + 1
        return original_getsize(path)

    audio.os.path.getsize = fake_getsize
    try:
        with pytest.raises(ValueError, match="100 MB"):
            audio.add_audio_card(
                str(tmp_path / "addon"),
                "TestProfile",
                col,
                source_path=str(source),
                title="Large",
            )
    finally:
        audio.os.path.getsize = original_getsize

    assert col.media.added == []
    assert col.models.models == {}


def test_note_creation_failure_trashes_newly_added_anki_media(tmp_path):
    source = tmp_path / "overview.mp3"
    source.write_bytes(b"ID3test")
    col = _FakeCol(tmp_path / "collection.media", reject_notes=True)

    with pytest.raises(RuntimeError, match="rejected the note"):
        audio.add_audio_card(
            str(tmp_path / "addon"),
            "TestProfile",
            col,
            source_path=str(source),
            title="Overview",
        )

    assert len(col.media.added) == 1
    assert col.media.trashed == col.media.added
    assert list((tmp_path / "collection.media").iterdir()) == []
    db_path = tmp_path / "addon" / "user_files" / "TestProfile" / "incremento.db"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT state, operation_kind FROM import_journal"
        ).fetchall() == [("rolled_back", "audio")]
        assert conn.execute("SELECT COUNT(*) FROM content_items").fetchone() == (0,)


def test_real_anki_export_includes_audio_referenced_by_portable_card(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(
        """
        import json
        import tempfile
        import zipfile
        from pathlib import Path

        from anki.collection import Collection
        from anki.exporting import AnkiPackageExporter
        from backend.audio_manager import add_audio_card

        with tempfile.TemporaryDirectory(prefix="incremento-audio-integration-") as temporary:
            root = Path(temporary)
            collection = Collection(str(root / "collection.anki2"))
            try:
                source = root / "overview.mp3"
                source.write_bytes(b"ID3\\x04\\x00\\x00integration audio")
                card_id = add_audio_card(
                    str(root / "addon"),
                    "TestProfile",
                    collection,
                    source_path=str(source),
                    title="Audio integration",
                    tags=["topic"],
                )
                note = collection.get_card(card_id).note()
                media_name = note["Audio_Filename"]
                assert note["Audio"] == f"[sound:{media_name}]"
                assert (Path(collection.media.dir()) / media_name).is_file()

                package = root / "audio.apkg"
                exporter = AnkiPackageExporter(collection)
                exporter.includeSched = True
                exporter.includeMedia = True
                exporter.did = None
                exporter.cids = None
                exporter.exportInto(str(package))
            finally:
                collection.close()

            with zipfile.ZipFile(package) as archive:
                media_map = json.loads(archive.read("media"))
                assert media_name in media_map.values(), media_map
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
