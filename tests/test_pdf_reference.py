from pathlib import Path
from types import SimpleNamespace

import pytest

from pdf_reference import resolve_pdf_reference


def collection(filename):
    return SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=cid),
                           get_note=lambda nid: {"PDF_Filename": filename, "Title": "Document"})


def test_reference_resolution_uses_live_note_and_managed_profile_path(tmp_path):
    path = tmp_path / "user_files" / "A" / "pdfs" / "actual.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"%PDF-1.7\n")
    resolved = resolve_pdf_reference(str(tmp_path), "A", collection("actual.pdf"), 7)
    assert resolved["path"] == str(path)
    assert resolved["filename"] == "actual.pdf"
    assert resolved["card_id"] == 7
    with pytest.raises(ValueError):
        resolve_pdf_reference(str(tmp_path), "B", collection("actual.pdf"), 7)


@pytest.mark.parametrize("name", ["../secret.pdf", "/etc/passwd", "missing.pdf"])
def test_reference_cannot_load_arbitrary_or_missing_files(tmp_path, name):
    with pytest.raises(ValueError):
        resolve_pdf_reference(str(tmp_path), "A", collection(name), 7)


def test_reference_rejects_symlink_escape(tmp_path):
    root = tmp_path / "user_files" / "A" / "pdfs"
    root.mkdir(parents=True)
    secret = tmp_path / "private.pdf"
    secret.write_bytes(b"%PDF-1.7")
    (root / "link.pdf").symlink_to(secret)
    with pytest.raises(ValueError):
        resolve_pdf_reference(str(tmp_path), "A", collection("link.pdf"), 7)
