from extract_batch_dialog import (
    can_create_batch_preview,
    normalize_batch_preview_row,
    normalize_batch_tags,
    validate_batch_preview_row,
)


def test_validate_batch_preview_row_flags_empty_question_and_answer():
    assert validate_batch_preview_row("", "Answer") == {
        "question": "",
        "answer": "Answer",
        "valid": False,
        "error": "Question is empty.",
    }
    assert validate_batch_preview_row("Question", "") == {
        "question": "Question",
        "answer": "",
        "valid": False,
        "error": "Answer is empty.",
    }


def test_can_create_batch_preview_requires_valid_rows_and_distinct_fields():
    rows = [{"question": "Q1", "answer": "A1"}]

    assert can_create_batch_preview(rows, "Front", "Back") is True
    assert can_create_batch_preview(rows, "Front", "Front") is False
    assert can_create_batch_preview([{"question": "Q1", "answer": ""}], "Front", "Back") is False


def test_normalize_batch_tags_accepts_spaces_commas_and_semicolons():
    assert normalize_batch_tags("alpha beta, Gamma;alpha") == ["alpha", "beta", "Gamma"]


def test_normalize_batch_preview_row_keeps_per_card_settings():
    row = normalize_batch_preview_row(
        {
            "question": "Question",
            "answer": "Answer",
            "priority": 12.75,
            "classification": "topic",
            "tags": "alpha, beta",
        },
        default_priority=50,
        default_classification="other",
        default_tags=["fallback"],
    )

    assert row == {
        "question": "Question",
        "answer": "Answer",
        "valid": True,
        "error": "",
        "priority": 12.75,
        "classification": "topic",
        "tags": ["alpha", "beta"],
    }


def test_normalize_batch_preview_row_uses_bounded_defaults_for_new_rows():
    row = normalize_batch_preview_row(
        {"question": "Question", "answer": "Answer"},
        default_priority=125,
        default_classification="unexpected",
        default_tags="one two",
    )

    assert row["priority"] == 100.0
    assert row["classification"] == "other"
    assert row["tags"] == ["one", "two"]
