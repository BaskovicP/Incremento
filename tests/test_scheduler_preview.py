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


def test_summarize_selected_mix_uses_actual_preview_counts():
    summary = scheduler_preview.summarize_selected_mix(
        selected_ids=[11, 22, 33, 44],
        picked_meta={
            11: {"card_type": "pdf", "mode": "priority", "tag": "writing"},
            22: {"card_type": "items", "mode": "random", "tag": "writing"},
            33: {"card_type": "topics", "mode": "priority", "tag": "__no_tags__"},
            44: {"card_type": "webpage", "mode": "priority", "tag": "psychology"},
        },
    )

    assert summary["selected_total"] == 4
    assert summary["content_counts"] == {"pdf": 1, "topics": 1, "items": 1}
    assert summary["mode_counts"] == {"priority": 3, "random": 1}
    assert summary["tag_content_counts"] == {
        "writing": {"PDF": 1, "Topics": 0, "Items": 1, "Total": 2},
        "Other": {"PDF": 0, "Topics": 1, "Items": 0, "Total": 1},
        "psychology": {"PDF": 0, "Topics": 0, "Items": 0, "Total": 0},
    }
    assert summary["other_type_counts"] == {"webpage": 1}
