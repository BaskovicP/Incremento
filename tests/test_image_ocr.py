from pathlib import Path
from unittest.mock import patch

import image_ocr


class _FakeModels:
    def __init__(self):
        self.updated = []

    def new_field(self, name):
        return {"name": name}

    def add_field(self, model, field):
        model["flds"].append(field)

    def update_dict(self, model):
        self.updated.append(model)


class _FakeCard:
    def __init__(self, card_id):
        self.id = card_id


class _FakeNote(dict):
    def __init__(self, note_id=1, model_name="Basic", fields=None):
        super().__init__()
        self.id = note_id
        self.mid = 1
        self.fields = list(fields or [])
        self._model = {"name": model_name, "flds": [{"name": "Front"}, {"name": "Back"}]}
        self.flush_calls = 0

    def note_type(self):
        return self._model

    def flush(self):
        self.flush_calls += 1

    def cards(self):
        return [_FakeCard(10), _FakeCard(11)]


def test_extract_local_image_names_from_field_finds_html_and_markdown_images():
    names = image_ocr.extract_local_image_names_from_field(
        '<img src="diagram.png"> ![](folder/photo.jpg) <img src="https://example.com/x.png">'
    )

    assert names == ["diagram.png", "photo.jpg"]


def test_supported_image_ocr_note_skips_incremento_document_types():
    note = _FakeNote(model_name="Incremento PDF")

    assert image_ocr.supported_image_ocr_note(note) is False


def test_ocr_note_images_updates_hidden_field_and_index(tmp_path):
    media_dir = Path(tmp_path)
    (media_dir / "diagram.png").write_bytes(b"fake")
    note = _FakeNote(fields=['<img src="diagram.png">'])
    fake_models = _FakeModels()

    with patch.object(image_ocr, "mw") as mock_mw, patch(
        "image_ocr._ocr_image_text", return_value="Detected OCR text"
    ), patch(
        "image_ocr.replace_note_ocr_index"
    ) as mock_replace:
        mock_mw.col.models = fake_models
        result = image_ocr.ocr_note_images(
            "/tmp/addon",
            "TestProfile",
            note,
            media_dir=str(media_dir),
        )

    assert result["updated"] is True
    assert "Detected OCR text" in note[image_ocr.INCREMENTO_OCR_TEXT_FIELD]
    assert note.flush_calls == 1
    mock_replace.assert_called_once()


def test_rebuild_note_ocr_index_from_field_uses_hidden_field_text():
    note = _FakeNote(fields=["Front"])
    note[image_ocr.INCREMENTO_OCR_TEXT_FIELD] = "cached OCR text"

    with patch("image_ocr.replace_note_ocr_index") as mock_replace:
        text = image_ocr.rebuild_note_ocr_index_from_field("/tmp/addon", "TestProfile", note)

    assert text == "cached OCR text"
    assert mock_replace.call_args.kwargs["fallback_text"] == "cached OCR text"
