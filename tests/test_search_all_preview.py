"""Annotation origins are marked in the original, escaped document context."""

from html import unescape
import re

import pytest


@pytest.mark.parametrize("page,source,marked", [
    ("Before. A saved passage. After.", "A saved passage.", "A saved passage."),
    ("Before. A saved\npassage. After.", "A saved passage.", "A saved\npassage."),
    ("Before. Co-\noperation and eﬃciency matter. After.", "Cooperation and efficiency matter.",
     "Co-\noperation and eﬃciency matter."),
    ("Before. ‘A SAVED passage’. After.", "A saved passage", "A SAVED passage"),
])
def test_annotation_source_is_marked_inside_original_page_context(page, source, marked):
    from search_all_preview import annotation_source_html

    rendered = annotation_source_html(page, source, "green")
    match = re.search(r'<mark\b[^>]*>(.*?)</mark>', rendered, re.DOTALL)

    assert match is not None
    assert unescape(match[1]) == marked
    assert "rgba(0,200,80," in match[0]
    assert 'id="incremento-search-source"' in match[0]
    assert unescape(re.sub(r"<[^>]*>", "", rendered)) == page


@pytest.mark.parametrize("page", ["", "Completely unrelated indexed page."])
def test_missing_or_unmatched_page_uses_saved_passage_without_marking_unrelated_text(page):
    from search_all_preview import annotation_source_html

    rendered = annotation_source_html(page, "The saved source passage.", "green")

    assert "The saved source passage." in rendered
    assert '<mark' in rendered
    assert "Completely unrelated" not in rendered


def test_annotation_context_and_source_are_escaped_before_inserting_color_markup():
    from search_all_preview import annotation_source_html

    rendered = annotation_source_html('Before <script>bad()</script> & after.', '<script>bad()</script>',
                                      'red; background:url(https://invalid)')

    assert "<script>" not in rendered and "&lt;script&gt;bad()&lt;/script&gt;" in rendered
    assert "https://invalid" not in rendered
    assert "rgba(255,220,0," in rendered


def test_empty_source_does_not_highlight_an_arbitrary_part_of_the_page():
    from search_all_preview import annotation_source_html

    assert annotation_source_html("Indexed page.", "", "green") == ""
