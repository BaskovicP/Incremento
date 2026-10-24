import json
from types import SimpleNamespace
import pytest
from epub_manager import _EPUB_SANITIZER_VERSION


def book(tmp_path):
    root = tmp_path / 'user_files' / 'A'
    (root / 'epubs').mkdir(parents=True)
    (root / 'epubs' / 'book.epub').write_bytes(b'fixture')
    extracted = root / 'epub_extracted' / 'book.epub'
    extracted.mkdir(parents=True)
    (extracted / 'chapter.xhtml').write_text('<html><body>test</body></html>')
    (extracted / 'metadata.json').write_text(json.dumps({'sanitizer_version': _EPUB_SANITIZER_VERSION,
        'sections': [{'href': 'chapter.xhtml', 'title': 'Chapter', 'text': 'test'}]}))
    note = {'EPUB_Filename': 'book.epub', 'Title': 'Book'}
    col = SimpleNamespace(get_card=lambda cid: SimpleNamespace(nid=cid), get_note=lambda nid: note)
    return extracted, col


def test_epub_reference_resolves_only_managed_current_profile_document(tmp_path):
    from epub_reference import resolve_epub_reference
    extracted, col = book(tmp_path)
    result = resolve_epub_reference(str(tmp_path), 'A', col, 7)
    assert result['paths'] == [str(extracted / 'chapter.xhtml')]
    assert result['card_id'] == 7
    with pytest.raises(ValueError):
        resolve_epub_reference(str(tmp_path), 'B', col, 7)


@pytest.mark.parametrize('attack', ['../outside.xhtml', '/etc/passwd', 'https://example.com/book'])
def test_epub_reference_rejects_escaping_section_without_writes(tmp_path, attack):
    from epub_reference import resolve_epub_reference
    extracted, col = book(tmp_path)
    meta = extracted / 'metadata.json'
    data = json.loads(meta.read_text())
    data['sections'][0]['href'] = attack
    meta.write_text(json.dumps(data))
    before = meta.read_bytes()
    with pytest.raises(ValueError):
        resolve_epub_reference(str(tmp_path), 'A', col, 7)
    assert meta.read_bytes() == before


def test_epub_reference_rejects_old_sanitizer_and_symlink_escape(tmp_path):
    from epub_reference import resolve_epub_reference
    extracted, col = book(tmp_path)
    chapter = extracted / 'chapter.xhtml'
    chapter.unlink()
    chapter.symlink_to('/etc/passwd')
    with pytest.raises(ValueError):
        resolve_epub_reference(str(tmp_path), 'A', col, 7)
    meta = extracted / 'metadata.json'
    meta.write_text('{"sanitizer_version": 0, "sections": []}')
    with pytest.raises(ValueError):
        resolve_epub_reference(str(tmp_path), 'A', col, 7)
