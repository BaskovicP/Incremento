from extract_batch_dialog import can_create_batch_preview, validate_batch_preview_row


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
