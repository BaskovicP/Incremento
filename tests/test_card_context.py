"""Extraction context is read-only, bounded, and scoped to the current profile."""
from types import SimpleNamespace

import pytest

import db
from card_context import load_parent_context


class Note(dict):
    @property
    def fields(self):
        return list(self.values())


class Collection:
    def __init__(self, notes):
        self.notes = notes

    def get_card(self, cid):
        return SimpleNamespace(id=cid, note=lambda: self.notes[cid]) if cid in self.notes else self.missing(cid)

    def missing(self, cid):
        raise KeyError(cid)


@pytest.mark.parametrize('tags', [['topic'], ['item'], []])
def test_saved_extraction_parent_opens_its_visible_content_without_changing_notes(tmp_path, tags):
    parent = Note(Front='<b>Capillary exchange</b>', Back='Hydrostatic pressure<br>Osmosis',
                  Incremento_Source_Link='private metadata', Incremento_OCR_Text='hidden OCR')
    parent.tags = tags
    child = Note(Front='What drives filtration?', Incremento_Parent_Card_ID='1')
    col = Collection({1: parent, 2: child})
    before = dict(parent), dict(child)

    result = load_parent_context(str(tmp_path), 'A', col, 2)

    assert result['card_id'] == 1 and result['available']
    assert result['title'] == 'Capillary exchange'
    assert result['fields'] == [('Front', '<b>Capillary exchange</b>'),
                                ('Back', 'Hydrostatic pressure<br>Osmosis')]
    assert (parent, child) == before


def test_tree_parent_is_a_profile_scoped_fallback_and_saved_origin_takes_precedence(tmp_path):
    root = str(tmp_path)
    db.set_knowledge_tree_structure(root, 'A', [
        dict(card_id=1, parent_card_id=None, node_kind='topic', sort_order=0),
        dict(card_id=2, parent_card_id=1, node_kind='item', sort_order=0)])
    child = Note(Front='Child')
    col = Collection({1: Note(Title='Tree parent'), 2: child, 3: Note(Front='Original source')})

    assert load_parent_context(root, 'A', col, 2)['title'] == 'Tree parent'
    assert load_parent_context(root, 'B', col, 2) is None
    child['Incremento_Parent_Card_ID'] = '3'
    assert load_parent_context(root, 'A', col, 2)['title'] == 'Original source'


def test_deleted_parent_retains_its_saved_label_without_guessing_a_replacement(tmp_path):
    col = Collection({2: Note(Front='Child', Incremento_Parent_Card_ID='1', Incremento_Parent='Original topic')})
    result = load_parent_context(str(tmp_path), 'A', col, 2)
    assert result == dict(card_id=1, title='Original topic', available=False, fields=[])


@pytest.mark.parametrize('value', ['', '0', '-1', '2', '1e3', '١', '9'*1000, '<script>1</script>'])
def test_invalid_and_self_parent_ids_do_not_open_arbitrary_cards(tmp_path, value):
    col = Collection({2: Note(Front='Child', Incremento_Parent_Card_ID=value)})
    assert load_parent_context(str(tmp_path), 'A', col, 2) is None


def test_parent_preview_bounds_content_and_removes_active_markup_and_resource_urls(tmp_path):
    parent = Note(Front='<b>Safe</b><script>pycmd("delete")</script><img src="file:///secret">',
                  Back='<a href="javascript:alert(1)">Answer</a><iframe src="https://remote">bad</iframe>',
                  Long='x'*300_000)
    col = Collection({1: parent, 2: Note(Incremento_Parent_Card_ID='1')})
    result = load_parent_context(str(tmp_path), 'A', col, 2)
    markup = ''.join(value for _name, value in result['fields'])
    assert result['title'] == 'Safe'
    assert '<b>Safe</b>' in markup and 'Answer' in markup
    assert all(value not in markup for value in ('script', 'pycmd', 'file:', 'javascript:', 'iframe', 'https:'))
    assert len(markup) <= 262_144


def test_parent_preview_budget_also_bounds_html_entity_expansion(tmp_path):
    col = Collection({1: Note(Front='&'*300_000), 2: Note(Incremento_Parent_Card_ID='1')})
    result = load_parent_context(str(tmp_path), 'A', col, 2)
    assert sum(len(value) for _name, value in result['fields']) <= 262_144


def test_source_title_preserves_literal_angle_brackets_and_entities(tmp_path):
    col = Collection({1: Note(Title='Relations &lt; and &gt; &amp; meaning'),
                      2: Note(Incremento_Parent_Card_ID='1')})
    assert load_parent_context(str(tmp_path), 'A', col, 2)['title'] == 'Relations < and > & meaning'
