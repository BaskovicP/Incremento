"""Custom colors remain searchable data, with CSS input rejected before writes."""
import pytest

import epub_highlights
import pdf_highlights
import search_repository


@pytest.mark.parametrize('repository,kind', [(pdf_highlights, 'pdf_highlights'),
                                            (epub_highlights, 'epub_highlights')])
def test_custom_color_persists_with_searchable_text_and_note(tmp_path, repository, kind):
    repository.add_highlight(str(tmp_path), 'Profile', 42, {'id': 'custom', 'color': '#1aB',
        'page': 1, 'sectionIndex': 0, 'startOffset': 0, 'endOffset': 18,
        'text': 'searchable passage', 'note': 'saved explanation', 'rects': []})
    stored = repository.load_highlights(str(tmp_path), 'Profile', 42)[0]
    assert stored['color'] == '#11aabb'
    assert stored['note'] == 'saved explanation'
    assert search_repository.search_excerpt_rows(str(tmp_path), 'Profile', kind, 'searchable', limit=10)


@pytest.mark.parametrize('repository', [pdf_highlights, epub_highlights])
@pytest.mark.parametrize('color', ['#1234', '#123abc00', 'red; background:url(https://example.com)',
                                 'rgb(1,2,3)', '__proto__'])
def test_invalid_colors_do_not_write_highlights(tmp_path, repository, color):
    with pytest.raises(ValueError):
        repository.add_highlight(str(tmp_path), 'Profile', 42, {'id': 'invalid', 'color': color})
    assert repository.load_highlights(str(tmp_path), 'Profile', 42) == []
