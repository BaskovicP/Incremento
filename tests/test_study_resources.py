from types import SimpleNamespace
from pathlib import Path
import json

import pytest

import db
from paths import get_pdf_dir, get_videos_dir
from recording_links import add_recording_link
from study_resources import resolve_recording, load_card_resources, source_locations


class Note(dict):
    def __init__(self, kind, **fields):
        super().__init__(fields)
        self.kind = kind
        self.fields = list(fields.values())
    def note_type(self):
        return {"name": self.kind}


class Collection:
    def __init__(self, notes, media=None):
        self.notes = notes
        self.media = SimpleNamespace(dir=lambda: str(media))
    def get_card(self, cid):
        if cid not in self.notes:
            raise KeyError(cid)
        return SimpleNamespace(id=cid, nid=cid * 10, note=lambda: self.notes[cid])
    def get_note(self, nid):
        return self.notes[nid // 10]


def test_card_resource_context_uses_the_note_title_without_rendered_reader_instructions(tmp_path):
    note = Note('Incremento PDF', Title='Statistics textbook', Front='PDF open in sidebar · select text to fill fields')
    result = load_card_resources(str(tmp_path), 'A', Collection({1: note}), 1)
    assert result['card_title'] == 'Statistics textbook'
    assert note['Front'] == 'PDF open in sidebar · select text to fill fields'


def test_card_finds_its_textbook_passage_and_the_passages_recording(tmp_path):
    root = str(tmp_path)
    pdf = get_pdf_dir(root, "A") / "geometry.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF-synthetic")
    video = get_videos_dir(root, "A") / "episode.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"synthetic-media")
    source = dict(kind="pdf", card_id=7, page=3, scroll=.2, quote="Angles")
    link = add_recording_link(root, "A", source, 8, start=490, end=695, label="Angle proof")
    note = Note("Basic", Front='Why?', Back='<a onclick=\'pycmd("incremento_open_pdf_ref:' +
                json.dumps(dict(card_id=7, filename="geometry.pdf", page=3, scroll_ratio=.2)) +
                '")\'>Read</a>')
    col = Collection({1: note, 7: Note("Incremento PDF", Title="Geometry", PDF_Filename="geometry.pdf"),
                      8: Note("Incremento Video", Title="Episode", Local_Video_File="videos/episode.mp4")})
    result = load_card_resources(root, "A", col, 1)
    assert result["documents"][0]["location"]["page"] == 3
    assert result["documents"][0]["title"] == "Geometry"
    assert result["recordings"][0]["id"] == link
    assert result["recordings"][0]["available"]
    assert result["recordings"][0]["start"] == 490
    assert note["Front"] == "Why?"
    assert load_card_resources(root, "B", col, 1)["recordings"] == []


def test_legacy_extraction_sources_are_discovered_without_inline_citations(tmp_path):
    db.add_pdf_card_source(str(tmp_path), "A", 7, 3, 10, excerpt="Angles")
    col = Collection({1: Note("Basic", Front="Why?")})
    sources = source_locations(str(tmp_path), "A", col, 1)
    assert sources[0]["card_id"] == 7
    assert sources[0]["page"] == 3


@pytest.mark.parametrize("name", ["../outside.mp4", "/tmp/outside.mp4", "videos/../../../outside.mp4"])
def test_recording_cannot_escape_its_profiles_video_directory(tmp_path, name):
    col = Collection({8: Note("Incremento Video", Title="Episode", Local_Video_File=name)})
    with pytest.raises(ValueError):
        resolve_recording(str(tmp_path), "A", col, 8)


def test_audio_reference_only_accepts_regular_media_files_inside_collection_media(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    (media / "lecture.mp3").write_bytes(b"synthetic-audio")
    note = Note("Incremento Audio", Title="Lecture", Audio_Filename="lecture.mp3")
    col = Collection({8: note}, media)
    result = resolve_recording(str(tmp_path), "A", col, 8)
    assert result["kind"] == "audio"
    assert Path(result["path"]) == media / "lecture.mp3"
    note["Audio_Filename"] = "../lecture.mp3"
    with pytest.raises(ValueError):
        resolve_recording(str(tmp_path), "A", col, 8)


def test_remote_recording_and_missing_file_have_controlled_unavailable_results(tmp_path):
    col = Collection({8: Note("Incremento Video", Title="Episode", YouTube_URL="https://youtu.be/example")})
    with pytest.raises(ValueError):
        resolve_recording(str(tmp_path), "A", col, 8)


def test_deleted_recording_card_is_an_unavailable_link_not_a_failed_resource_list(tmp_path):
    from study_resources import resolve_link_rows
    class NotFound(Exception):
        pass
    def deleted(_cid):
        raise NotFound('Anki card no longer exists')
    col = SimpleNamespace(get_card=deleted, get_note=lambda nid: None)
    rows = resolve_link_rows(str(tmp_path), 'A', col, [dict(recording_card_id=8)])
    assert rows == [dict(recording_card_id=8, available=False, recording=None)]


def test_epub_link_source_has_a_verifiable_local_passage_file(tmp_path):
    from paths import get_epub_dir, get_epub_extract_root
    from epub_manager import _EPUB_SANITIZER_VERSION
    from study_resources import resolve_document, file_signature
    book = get_epub_dir(str(tmp_path), 'A') / 'geometry.epub'
    book.parent.mkdir(parents=True, exist_ok=True)
    book.write_bytes(b'synthetic')
    extracted = get_epub_extract_root(str(tmp_path), 'A') / book.name
    extracted.mkdir(parents=True)
    chapter = extracted / 'chapter.xhtml'
    chapter.write_text('<html><body>Angles</body></html>')
    (extracted / 'metadata.json').write_text(json.dumps(dict(sanitizer_version=_EPUB_SANITIZER_VERSION,
        sections=[dict(href=chapter.name, title='Angles', text='Angles')])))
    col = Collection({7: Note('Incremento EPUB', Title='Geometry', EPUB_Filename=book.name)})
    result = resolve_document(str(tmp_path), 'A', col, dict(kind='epub', card_id=7, section=0))
    assert Path(result['path']) == chapter
    assert file_signature(result['path'])[2] > 0
