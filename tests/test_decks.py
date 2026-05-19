"""Tests for backend/decks.py"""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import decks


class TestCreateTopicsDeck:
    def test_calls_add_normal_deck_with_topics(self):
        with patch("decks.mw") as mock_mw:
            mock_mw.col.decks.by_name.return_value = None
            assert decks.create_topics_deck() is True
        mock_mw.col.decks.by_name.assert_called_once_with("Topics")
        mock_mw.col.decks.add_normal_deck_with_name.assert_called_once_with("Topics")

    def test_skips_creation_when_topics_exists(self):
        with patch("decks.mw") as mock_mw:
            mock_mw.col.decks.by_name.return_value = {"id": 9}
            assert decks.create_topics_deck() is False
        mock_mw.col.decks.add_normal_deck_with_name.assert_not_called()

    def test_skips_creation_when_topics_exists_with_different_case(self):
        with patch("decks.mw") as mock_mw:
            mock_mw.col.decks.by_name.return_value = None
            mock_mw.col.decks.all_names_and_ids.return_value = [SimpleNamespace(name="topics")]
            assert decks.create_topics_deck() is False
        mock_mw.col.decks.add_normal_deck_with_name.assert_not_called()

    def test_skips_creation_without_collection(self):
        with patch("decks.mw", MagicMock(col=None)):
            assert decks.create_topics_deck() is False
