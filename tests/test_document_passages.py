"""Passage payloads are bounded data, including when pasted from the clipboard."""
import json

import pytest

from backend.document_passages import normalize_passage, parse_epub_reference


@pytest.mark.parametrize('anchor', [dict(quote='x'*2001),dict(quote='a\0b'),dict(rects=[[0,0,float('nan'),.1]]),
    dict(rects=[[.9,0,.2,.1]]),dict(rects=[[0,0,.1,.1]]*65),dict(start=True,end=10),dict(script='alert(1)')])
def test_hostile_passages_are_rejected(anchor):
    with pytest.raises(ValueError):
        normalize_passage(anchor)


def test_json_epub_reference_retains_a_bounded_range_and_legacy_commands_remain_readable():
    passage=dict(quote='Explanation',start=100,end=111,prefix='Before ',suffix=' after')
    value=dict(card_id=7,section_index=2,focus_offset=100,scroll_ratio=.4,passage=passage)
    assert parse_epub_reference('incremento_open_epub:'+json.dumps(value)) == value
    assert parse_epub_reference('incremento_open_epub:7:2:100:.4')['focus_offset'] == 100
    assert parse_epub_reference('incremento_open_epub:'+json.dumps({**value,'card_id':True})) is None
    assert parse_epub_reference('incremento_open_epub:'+json.dumps({**value,'filename':'../../escape'})) is None
