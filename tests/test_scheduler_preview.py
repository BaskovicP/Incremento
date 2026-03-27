import scheduler_preview


def test_equal_slider_example_shares():
    mix = scheduler_preview.compute_expected_mix(
        session_card_count=40,
        topics_slider=50,
        pdf_slider=50,
        random_slider=50,
    )

    assert mix["content_shares"]["pdf"] == 0.5
    assert mix["content_shares"]["topics"] == 0.25
    assert mix["content_shares"]["items"] == 0.25
    assert mix["mode_shares"]["random"] == 0.5
    assert mix["mode_shares"]["priority"] == 0.5

    assert mix["content_counts"] == {"pdf": 20, "topics": 10, "items": 10}
    assert mix["mode_counts"] == {"random": 20, "priority": 20}


def test_topics_slider_applies_inside_non_pdf_pool():
    mix = scheduler_preview.compute_expected_mix(
        session_card_count=20,
        topics_slider=0,   # 100% topics
        pdf_slider=50,     # 50% pdf
        random_slider=100,
    )

    assert mix["content_shares"]["pdf"] == 0.5
    assert mix["content_shares"]["topics"] == 0.5
    assert mix["content_shares"]["items"] == 0.0
    assert sum(mix["content_counts"].values()) == 20
    assert mix["mode_counts"] == {"random": 20, "priority": 0}


def test_count_apportionment_preserves_total():
    mix = scheduler_preview.compute_expected_mix(
        session_card_count=7,
        topics_slider=50,
        pdf_slider=50,
        random_slider=50,
    )

    assert sum(mix["content_counts"].values()) == 7
    assert sum(mix["mode_counts"].values()) == 7
