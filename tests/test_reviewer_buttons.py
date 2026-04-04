import reviewer_buttons as buttons


def test_configured_use_fail_pass_on_items_reads_config():
    assert buttons.configured_use_fail_pass_on_items({}) is False
    assert buttons.configured_use_fail_pass_on_items(
        {"use_fail_pass_on_items": True}
    ) is True


def test_item_pass_ease_for_button_count_matches_good_button():
    assert buttons.item_pass_ease_for_button_count(2) == 2
    assert buttons.item_pass_ease_for_button_count(3) == 2
    assert buttons.item_pass_ease_for_button_count(4) == 3


def test_item_fail_pass_buttons_use_fail_and_good():
    assert buttons.item_fail_pass_buttons(4) == ((1, "Fail"), (3, "Pass"))
    assert buttons.item_fail_pass_buttons(2) == ((1, "Fail"), (2, "Pass"))


def test_reviewer_button_mode_prefers_topic_cards():
    class _Card:
        pass

    card = _Card()
    original = buttons.is_topic_card
    try:
        buttons.is_topic_card = lambda _card: True
        assert buttons.reviewer_button_mode(card, use_fail_pass_on_items=True) == "topic"
    finally:
        buttons.is_topic_card = original


def test_reviewer_button_mode_enables_items_fail_pass_for_non_topics():
    class _Card:
        pass

    card = _Card()
    original = buttons.is_topic_card
    try:
        buttons.is_topic_card = lambda _card: False
        assert (
            buttons.reviewer_button_mode(card, use_fail_pass_on_items=True)
            == "items_fail_pass"
        )
        assert (
            buttons.reviewer_button_mode(card, use_fail_pass_on_items=False)
            == "standard"
        )
    finally:
        buttons.is_topic_card = original
