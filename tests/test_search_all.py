import pytest

import search_all


def test_search_all_search_while_typing_defaults_enabled():
    assert search_all.configured_search_all_search_while_typing({}) is True


def test_search_all_filter_defaults_disable_pdf_content_only():
    assert search_all.configured_search_all_filter_enabled("pdf_highlights", {}) is True
    assert search_all.configured_search_all_filter_enabled("pdf_sources", {}) is True
    assert search_all.configured_search_all_filter_enabled("pdf_content", {}) is False
    assert search_all.configured_search_all_filter_enabled("epub_content", {}) is True
    assert search_all.configured_search_all_filter_enabled("image_ocr", {}) is True
    assert search_all.configured_search_all_filter_enabled("cards", {}) is True
    assert search_all.configured_search_all_filter_enabled("current_profile", {}) is True


def test_search_all_filter_config_values_override_defaults():
    cfg = {
        "search_all_filter_pdf_highlights": False,
        "search_all_filter_pdf_content": True,
        "search_all_filter_cards": False,
        "search_all_filter_current_profile": False,
    }
    assert search_all.configured_search_all_filter_enabled("pdf_highlights", cfg) is False
    assert search_all.configured_search_all_filter_enabled("pdf_content", cfg) is True
    assert search_all.configured_search_all_filter_enabled("cards", cfg) is False
    assert search_all.configured_search_all_filter_enabled("current_profile", cfg) is False


@pytest.mark.parametrize(("media", "position"), [("pdf", 9), ("epub", 0)])
def test_document_highlight_hover_target_uses_the_saved_highlight_text(
    media,
    position,
):
    previews: dict[str, str] = {}
    highlight_text = "Saved <highlight> with faithful wording."

    url = search_all._highlight_result_url(
        previews,
        media=media,
        card_id=17,
        position=position,
        query="faith",
        text=highlight_text,
    )
    target = search_all._document_preview_target(url, previews)

    assert target is not None
    assert target.media == media
    assert target.card_id == 17
    assert target.position == position
    assert target.query == "faith"
    assert target.highlight_text == highlight_text
    assert highlight_text not in url


def test_stale_highlight_hover_target_does_not_fall_back_to_pdf_content():
    previews: dict[str, str] = {}
    url = search_all._highlight_result_url(
        previews,
        media="pdf",
        card_id=17,
        position=9,
        query="faith",
        text="Saved highlight",
    )

    assert search_all._document_preview_target(url, {}) is None
