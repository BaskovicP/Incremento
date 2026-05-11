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
