import database_entries_dialog


def test_find_text_matches_empty_query_returns_no_matches():
    assert database_entries_dialog.find_text_matches("Alpha beta", "") == []


def test_find_text_matches_case_insensitive_finds_all_occurrences():
    matches = database_entries_dialog.find_text_matches("Alpha alpha ALPHA", "alpha")
    assert matches == [
        database_entries_dialog.TextMatch(0, 5),
        database_entries_dialog.TextMatch(6, 11),
        database_entries_dialog.TextMatch(12, 17),
    ]


def test_find_text_matches_reports_start_and_end_offsets():
    matches = database_entries_dialog.find_text_matches("abc test xyz test", "test")
    assert matches == [
        database_entries_dialog.TextMatch(4, 8),
        database_entries_dialog.TextMatch(13, 17),
    ]


def test_find_text_matches_keeps_offsets_when_casefold_expands_prior_text():
    matches = database_entries_dialog.find_text_matches("ﬁ alpha egos", "egos")
    assert matches == [database_entries_dialog.TextMatch(8, 12)]


def test_find_text_matches_can_match_expanded_ligature_as_original_character():
    matches = database_entries_dialog.find_text_matches("office ﬁle", "file")
    assert matches == [database_entries_dialog.TextMatch(7, 10)]


def test_normalize_plain_text_for_qt_collapses_crlf_to_single_newline():
    assert database_entries_dialog.normalize_plain_text_for_qt("a\r\nb\rc") == "a\nb\nc"


def test_text_index_to_qt_position_counts_non_bmp_characters_as_two_code_units():
    text = "a😀egos"
    assert database_entries_dialog.text_index_to_qt_position(text, 2) == 3
    assert database_entries_dialog.text_index_to_qt_position(text, 6) == 7


def test_advance_match_index_wraps_forward_from_last_to_first():
    assert database_entries_dialog.advance_match_index(2, 3, 1) == 0


def test_advance_match_index_wraps_backward_from_first_to_last():
    assert database_entries_dialog.advance_match_index(0, 3, -1) == 2
