"""Tests for backend/decks.py"""
from unittest.mock import patch, MagicMock

import decks


class TestCreateTopicsDeck:
    def test_calls_add_normal_deck_with_topics(self):
        with patch("decks.mw") as mock_mw:
            decks.create_topics_deck()
        mock_mw.col.decks.add_normal_deck_with_name.assert_called_once_with("Topics")
