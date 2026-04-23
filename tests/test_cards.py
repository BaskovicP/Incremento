"""Tests for backend/cards.py"""
import sys
from unittest.mock import MagicMock, patch

import cards


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_mw(find_cards_return=None, db_rows=None):
    """Build a minimal mw mock.

    db.all() is the SQL path used by _sort_by_due.
    """
    mock_mw = MagicMock()
    mock_mw.col.find_cards.return_value = find_cards_return or []
    mock_mw.col.db.all.return_value = db_rows or []
    return mock_mw


# ---------------------------------------------------------------------------
# _sort_by_due
# ---------------------------------------------------------------------------


class TestSortByDue:
    def test_empty_input_returns_empty_list(self):
        with patch("cards.mw") as mock_mw:
            result = cards._sort_by_due([])
        assert result == []
        mock_mw.col.db.all.assert_not_called()

    def test_sorts_ascending_by_due(self):
        """Cards with lower due values (most overdue) should come first."""
        card_ids = [101, 102, 103]
        db_rows = [(101, 30), (102, 10), (103, 20)]
        with patch("cards.mw") as mock_mw:
            mock_mw.col.db.all.return_value = db_rows
            result = cards._sort_by_due(card_ids)
        assert result == [102, 103, 101]

    def test_single_card_returns_single_element_list(self):
        with patch("cards.mw") as mock_mw:
            mock_mw.col.db.all.return_value = [(42, 99)]
            result = cards._sort_by_due([42])
        assert result == [42]

    def test_cards_with_equal_due_preserved(self):
        """Cards with identical due values should all appear in the result."""
        card_ids = [1, 2, 3]
        db_rows = [(1, 5), (2, 5), (3, 5)]
        with patch("cards.mw") as mock_mw:
            mock_mw.col.db.all.return_value = db_rows
            result = cards._sort_by_due(card_ids)
        assert sorted(result) == [1, 2, 3]

    def test_missing_card_in_db_defaults_to_zero(self):
        """If a card_id isn't in the DB result, due defaults to 0 (sorts first)."""
        card_ids = [10, 20]
        # Only card 20 in DB rows; card 10 gets default due=0
        db_rows = [(20, 50)]
        with patch("cards.mw") as mock_mw:
            mock_mw.col.db.all.return_value = db_rows
            result = cards._sort_by_due(card_ids)
        assert result[0] == 10
        assert result[1] == 20

    def test_query_uses_correct_placeholders(self):
        """db.all() should be called with one placeholder per card id."""
        card_ids = [7, 8, 9]
        with patch("cards.mw") as mock_mw:
            mock_mw.col.db.all.return_value = [(7, 1), (8, 2), (9, 3)]
            cards._sort_by_due(card_ids)
            sql_arg = mock_mw.col.db.all.call_args[0][0]
        assert sql_arg.count("?") == 3


class TestSortCardsForPriorityMode:
    def test_lower_priority_more_important_sorts_by_priority_then_due(self):
        card_ids = [101, 102, 103]
        db_rows = [(101, 30), (102, 10), (103, 20)]
        with patch("cards.mw") as mock_mw, patch(
            "cards.get_all_priorities",
            return_value={101: 70.0, 102: 20.0, 103: 20.0},
        ):
            mock_mw.col.db.all.return_value = db_rows
            result = cards.sort_cards_for_priority_mode(
                card_ids,
                addon_dir="/tmp/unused",
                lower_is_more_important=True,
            )
        assert result == [102, 103, 101]

    def test_higher_priority_more_important_sorts_by_priority_then_due(self):
        card_ids = [101, 102, 103]
        db_rows = [(101, 30), (102, 10), (103, 20)]
        with patch("cards.mw") as mock_mw, patch(
            "cards.get_all_priorities",
            return_value={101: 70.0, 102: 20.0, 103: 70.0},
        ):
            mock_mw.col.db.all.return_value = db_rows
            result = cards.sort_cards_for_priority_mode(
                card_ids,
                addon_dir="/tmp/unused",
                lower_is_more_important=False,
            )
        assert result == [103, 101, 102]

    def test_without_addon_dir_falls_back_to_due_order(self):
        card_ids = [101, 102, 103]
        db_rows = [(101, 30), (102, 10), (103, 20)]
        with patch("cards.mw") as mock_mw, patch(
            "cards.get_all_priorities"
        ) as mock_get_all_priorities:
            mock_mw.col.db.all.return_value = db_rows
            result = cards.sort_cards_for_priority_mode(card_ids, addon_dir=None)
        mock_get_all_priorities.assert_not_called()
        assert result == [102, 103, 101]


# ---------------------------------------------------------------------------
# get_all_topic_cards
# ---------------------------------------------------------------------------


class TestGetAllTopicCards:
    def test_returns_sorted_list(self):
        card_map = {3: object(), 1: object(), 2: object()}
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card",
            side_effect=lambda card: card is not card_map[2],
        ):
            mock_mw.col.find_cards.return_value = [3, 1, 2]
            mock_mw.col.db.all.return_value = [(3, 30), (1, 10), (2, 20)]
            mock_mw.col.get_card.side_effect = lambda cid: card_map[cid]
            cards.clear_topic_item_cache()
            result = cards.get_all_topic_cards()
        assert result == [1, 3]

    def test_passes_topics_filter_in_query(self):
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card", return_value=False
        ):
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.clear_topic_item_cache()
            cards.get_all_topic_cards(topics_filter="deck:MyTopics")
            call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert "deck:MyTopics" in call_arg

    def test_empty_result_returns_empty_list(self):
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card", return_value=False
        ):
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.clear_topic_item_cache()
            result = cards.get_all_topic_cards()
        assert result == []

    def test_passes_ready_filter_in_query(self):
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card", return_value=False
        ):
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.clear_topic_item_cache()
            cards.get_all_topic_cards(ready_filter="is:due")
            call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert "is:due" in call_arg


# ---------------------------------------------------------------------------
# get_all_item_cards
# ---------------------------------------------------------------------------


class TestGetAllItemCards:
    def test_returns_sorted_list(self):
        card_map = {200: object(), 100: object()}
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card",
            side_effect=lambda card: card is card_map[200],
        ):
            mock_mw.col.find_cards.return_value = [200, 100]
            mock_mw.col.db.all.return_value = [(200, 100), (100, 50)]
            mock_mw.col.get_card.side_effect = lambda cid: card_map[cid]
            cards.clear_topic_item_cache()
            result = cards.get_all_item_cards()
        assert result == [100]

    def test_passes_items_filter_in_query(self):
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card", return_value=False
        ):
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.clear_topic_item_cache()
            cards.get_all_item_cards(items_filter="-deck:Topics")
            call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert "-deck:Topics" in call_arg

    def test_empty_collection_returns_empty_list(self):
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card", return_value=False
        ):
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.clear_topic_item_cache()
            result = cards.get_all_item_cards()
        assert result == []


# ---------------------------------------------------------------------------
# get_topic_cards_by_tag / get_item_cards_by_tag
# ---------------------------------------------------------------------------


class TestGetCardsByTag:
    def test_topic_tag_filter_includes_tag_in_query(self):
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card", return_value=False
        ):
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.clear_topic_item_cache()
            cards.get_topic_cards_by_tag("physics")
            call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert "tag:physics" in call_arg

    def test_item_tag_filter_includes_tag_in_query(self):
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card", return_value=False
        ):
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.clear_topic_item_cache()
            cards.get_item_cards_by_tag("history")
            call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert "tag:history" in call_arg

    def test_topic_tag_returns_sorted_result(self):
        card_map = {5: object(), 3: object(), 4: object()}
        with patch("cards.mw") as mock_mw, patch(
            "cards.is_topic_card",
            side_effect=lambda card: card is not card_map[4],
        ):
            mock_mw.col.find_cards.return_value = [5, 3, 4]
            mock_mw.col.db.all.return_value = [(5, 50), (3, 10), (4, 30)]
            mock_mw.col.get_card.side_effect = lambda cid: card_map[cid]
            cards.clear_topic_item_cache()
            result = cards.get_topic_cards_by_tag("science")
        assert result == [3, 5]


# ---------------------------------------------------------------------------
# get_all_ready_card_ids (line 29)
# ---------------------------------------------------------------------------


class TestGetAllReadyCardIds:
    def test_calls_find_cards_with_filter(self):
        with patch("cards.mw") as mock_mw:
            mock_mw.col.find_cards.return_value = [1, 2, 3]
            result = cards.get_all_ready_card_ids()
        assert result == [1, 2, 3]
        call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert "is:due" in call_arg or "is:new" in call_arg or "is:learn" in call_arg


# ---------------------------------------------------------------------------
# get_all_pdf_cards (line 105)
# ---------------------------------------------------------------------------


class TestGetAllPdfCards:
    def test_returns_pdf_cards_sorted(self):
        with patch("cards.mw") as mock_mw:
            mock_mw.col.find_cards.return_value = [200, 100]
            mock_mw.col.db.all.return_value = [(200, 50), (100, 10)]
            result = cards.get_all_pdf_cards()
        assert result == [100, 200]

    def test_excludes_suspended_from_query(self):
        with patch("cards.mw") as mock_mw:
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.get_all_pdf_cards()
            call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert "-is:suspended" in call_arg

    def test_custom_pdf_filter(self):
        with patch("cards.mw") as mock_mw:
            mock_mw.col.find_cards.return_value = []
            mock_mw.col.db.all.return_value = []
            cards.get_all_pdf_cards(pdf_filter='note:"My PDF"')
            call_arg = mock_mw.col.find_cards.call_args[0][0]
        assert 'note:"My PDF"' in call_arg
