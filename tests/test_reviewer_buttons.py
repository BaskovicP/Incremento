import reviewer_buttons as buttons


def test_configured_use_fail_pass_on_items_reads_config():
    assert buttons.configured_use_fail_pass_on_items({}) is True
    assert buttons.configured_use_fail_pass_on_items(
        {"use_fail_pass_on_items": True}
    ) is True
    assert buttons.configured_use_fail_pass_on_items(
        {"use_fail_pass_on_items": False}
    ) is False


def test_item_pass_ease_for_button_count_is_always_good():
    assert buttons.item_pass_ease_for_button_count(2) == 3
    assert buttons.item_pass_ease_for_button_count(3) == 3
    assert buttons.item_pass_ease_for_button_count(4) == 3


def test_item_fail_pass_buttons_use_positional_shortcuts():
    assert buttons.item_fail_pass_buttons(4) == ((1, "Fail"), (2, "Pass"))
    assert buttons.item_fail_pass_buttons(3) == ((1, "Fail"), (2, "Pass"))
    assert buttons.item_fail_pass_buttons(2) == ((1, "Fail"), (2, "Pass"))


def test_item_pass_remaps_to_graduating_good_for_new_cards():
    class _Card:
        type = 0
        queue = 0

    card = _Card()
    assert buttons.item_pass_ease_for_card(card, 2) == 3
    assert buttons.remap_item_fail_pass_ease(card, 2) == 3
    assert buttons.item_fail_pass_buttons(2, card) == ((1, "Fail"), (2, "Pass"))


def test_item_pass_remaps_to_graduating_good_for_learning_cards():
    class _Card:
        type = 1
        queue = 1

    card = _Card()
    assert buttons.item_pass_ease_for_card(card, 2) == 3
    assert buttons.remap_item_fail_pass_ease(card, 2) == 3
    assert buttons.item_fail_pass_buttons(2, card) == ((1, "Fail"), (2, "Pass"))


def test_item_pass_remaps_to_good_for_review_cards():
    class _Card:
        type = 2
        queue = 2

    card = _Card()
    assert buttons.item_pass_ease_for_card(card, 4) == 3
    assert buttons.remap_item_fail_pass_ease(card, 2) == 3
    assert buttons.item_fail_pass_buttons(4, card) == ((1, "Fail"), (2, "Pass"))


def test_item_fail_always_remains_again():
    for card_type, queue in ((0, 0), (1, 1), (3, 3), (2, 2)):
        card = type("_Card", (), {"type": card_type, "queue": queue})()
        assert buttons.remap_item_fail_pass_ease(card, 1) == 1


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
