"""Card-level batches are atomic, profile scoped, and preserve original content."""
import pytest

import db
from document_links import list_document_links
from recording_links import list_recording_links
from tests.test_study_resources import Collection, Note


def setup_resources(tmp_path, monkeypatch):
    import card_resource_links as links
    col = Collection({1: Note('Basic', Front='A question'),
                      7: Note('Incremento PDF', Title='Book'),
                      8: Note('Incremento Video', Title='Lecture')})
    pdf = tmp_path / 'book.pdf'
    video = tmp_path / 'lecture.mp4'
    pdf.write_bytes(b'synthetic PDF')
    video.write_bytes(b'synthetic video')
    monkeypatch.setattr(links, 'resolve_document', lambda *a: dict(path=str(pdf), title='Book', max_page=10))
    monkeypatch.setattr(links, 'resolve_recording', lambda *a: dict(path=str(video), title='Lecture', kind='video'))
    monkeypatch.setattr(links, 'pdf_page_count', lambda p: 10)
    return links, col


def test_mixed_batch_attaches_to_card_and_retry_does_not_duplicate_links(tmp_path, monkeypatch):
    links, col = setup_resources(tmp_path, monkeypatch)
    selection = [dict(kind='pdf', card_id=7, page=3, label='Proof'),
                 dict(kind='video', card_id=8, start=12.5, end=18., label='Example')]
    links.save_card_resource_links(str(tmp_path), 'A', col, 1, selection)
    links.save_card_resource_links(str(tmp_path), 'A', col, 1, selection)
    books = list_document_links(str(tmp_path), 'A', 1)
    recordings = list_recording_links(str(tmp_path), 'A', source=dict(kind='card', card_id=1))
    assert len(books) == len(recordings) == 1
    assert (books[0]['target_page'], books[0]['quote']) == (3, 'Proof')
    assert recordings[0]['source']['kind'] == 'card'
    assert (recordings[0]['start'], recordings[0]['end']) == (12.5, 18.)
    assert list_document_links(str(tmp_path), 'B', 1) == []
    assert col.notes[1]['Front'] == 'A question'


def test_second_write_failure_rolls_back_the_entire_mixed_batch(tmp_path, monkeypatch):
    links, col = setup_resources(tmp_path, monkeypatch)
    conn = db.get_connection(str(tmp_path), 'A')
    conn.execute("CREATE TRIGGER reject_recording BEFORE INSERT ON recording_links BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(Exception, match='test'):
        links.save_card_resource_links(str(tmp_path), 'A', col, 1,
            [dict(kind='pdf', card_id=7, page=3), dict(kind='video', card_id=8, start=1)])
    assert list_document_links(str(tmp_path), 'A', 1) == []
    assert list_recording_links(str(tmp_path), 'A', source=dict(kind='card', card_id=1)) == []


@pytest.mark.parametrize('selection', [[], [dict(kind='pdf', card_id=7, page=11)],
    [dict(kind='video', card_id=8, start=20, end=12)], [dict(kind='pdf', card_id=7, page=True)],
    [dict(kind='video', card_id=8, start=1, label='x'*241)]])
def test_invalid_batches_leave_no_associations(tmp_path, monkeypatch, selection):
    links, col = setup_resources(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        links.save_card_resource_links(str(tmp_path), 'A', col, 1, selection)
    assert list_document_links(str(tmp_path), 'A', 1) == []


def test_cancelled_batch_does_not_save(tmp_path, monkeypatch):
    links, col = setup_resources(tmp_path, monkeypatch)
    assert links.save_card_resource_links(str(tmp_path), 'A', col, 1,
        [dict(kind='pdf', card_id=7, page=3)], is_cancelled=lambda: True) == []
    assert list_document_links(str(tmp_path), 'A', 1) == []


def test_document_link_metadata_keeps_multiple_locations_manageable(tmp_path, monkeypatch):
    import study_resources
    links, col = setup_resources(tmp_path, monkeypatch)
    monkeypatch.setattr(study_resources, 'resolve_document', links.resolve_document)
    links.save_card_resource_links(str(tmp_path), 'A', col, 1,
        [dict(kind='pdf', card_id=7, page=3, label='First'),
         dict(kind='pdf', card_id=7, page=4, label='Second')])
    docs = study_resources.load_card_resources(str(tmp_path), 'A', col, 1)['documents']
    assert [d['label'] for d in docs] == ['First', 'Second']
    assert all(d['link_id'] > 0 and d['owner_card_id'] == 1 for d in docs)


def test_counts_describe_distinct_files_instead_of_saved_locations():
    from frontend.study_availability import resource_availability
    from backend.i18n import t
    docs = [dict(available=True, location=dict(card_id=7)), dict(available=True, location=dict(card_id=7)),
            dict(available=True, location=dict(card_id=8))]
    assert resource_availability(docs)['status'] == t('study_linked_count', count=2)


def test_edit_and_unlink_are_scoped_to_the_direct_card_owner(tmp_path, monkeypatch):
    links, col = setup_resources(tmp_path, monkeypatch)
    link_id = links.save_card_resource_links(str(tmp_path), 'A', col, 1, [dict(kind='pdf', card_id=7, page=3)])[0]
    with pytest.raises(ValueError, match='Link no longer'):
        links.save_card_resource_links(str(tmp_path), 'A', col, 8,
            [dict(kind='pdf', card_id=7, page=4, link_id=link_id)])
    links.save_card_resource_links(str(tmp_path), 'A', col, 1,
        [dict(kind='pdf', card_id=7, page=4, label='Updated', link_id=link_id)])
    row = list_document_links(str(tmp_path), 'A', 1)[0]
    assert (row['target_page'], row['quote']) == (4, 'Updated')
    managed = dict(location=dict(kind='pdf', card_id=7, page=4), link_id=link_id, owner_card_id=1)
    assert not links.unlink_card_resource(str(tmp_path), 'A', 8, managed)
    assert links.unlink_card_resource(str(tmp_path), 'A', 1, managed)
    assert list_document_links(str(tmp_path), 'A', 1) == []


def test_all_saved_locations_remain_visible_after_multiple_batches(tmp_path, monkeypatch):
    import study_resources
    from document_links import add_document_link
    links, col = setup_resources(tmp_path, monkeypatch)
    monkeypatch.setattr(study_resources, 'resolve_document', links.resolve_document)
    for page in range(1, 35):
        add_document_link(str(tmp_path), 'A', source_card_id=1, source_kind='card', target_card_id=7, target_page=page)
    assert len(study_resources.load_card_resources(str(tmp_path), 'A', col, 1)['documents']) == 34


def test_unlink_undo_restores_a_missing_resource_without_reading_its_file(tmp_path, monkeypatch):
    links, col = setup_resources(tmp_path, monkeypatch)
    link_id = links.save_card_resource_links(str(tmp_path), 'A', col, 1, [dict(kind='pdf', card_id=7, page=3)])[0]
    token = links.unlink_card_resource(str(tmp_path), 'A', 1,
        dict(location=dict(kind='pdf', card_id=7, page=3), owner_card_id=1, link_id=link_id))
    (tmp_path / 'book.pdf').unlink()
    with pytest.raises(ValueError):
        links.restore_card_resource_link(str(tmp_path), 'B', col, 1, token)
    assert links.restore_card_resource_link(str(tmp_path), 'A', col, 1, token)
    assert list_document_links(str(tmp_path), 'A', 1)[0]['target_page'] == 3


@pytest.mark.parametrize('kind', ['pdf', 'video'])
def test_edit_cannot_hide_an_existing_link_by_duplicating_its_location(tmp_path, monkeypatch, kind):
    links, col = setup_resources(tmp_path, monkeypatch)
    first = dict(kind=kind, card_id=7, page=3) if kind == 'pdf' else dict(kind=kind, card_id=8, start=3)
    second = dict(first, page=4) if kind == 'pdf' else dict(first, start=4)
    ids = links.save_card_resource_links(str(tmp_path), 'A', col, 1, [first, second])
    with pytest.raises(ValueError, match='already linked'):
        links.save_card_resource_links(str(tmp_path), 'A', col, 1, [dict(first, link_id=ids[1])])


def test_editing_a_legacy_card_reference_preserves_its_existing_long_excerpt(tmp_path, monkeypatch):
    from document_links import add_document_link
    links, col = setup_resources(tmp_path, monkeypatch)
    excerpt = 'A saved passage. ' * 40
    link_id = add_document_link(str(tmp_path), 'A', source_card_id=1, source_kind='card',
                               target_card_id=7, target_page=3, quote=excerpt)
    links.save_card_resource_links(str(tmp_path), 'A', col, 1,
        [dict(kind='pdf', card_id=7, page=4, label=excerpt.strip(), link_id=link_id)])
    assert list_document_links(str(tmp_path), 'A', 1)[0]['quote'] == excerpt.strip()
