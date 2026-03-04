from unittest.mock import patch
import scheduler


TOPIC_CARDS = [101, 102, 103]
ITEM_CARDS = [201, 202, 203]


def _mock_cards(topic_cards=None, item_cards=None):
    """Patch card_utils inside the scheduler module."""
    topic_cards = topic_cards if topic_cards is not None else TOPIC_CARDS
    item_cards = item_cards if item_cards is not None else ITEM_CARDS
    return patch.multiple(
        "scheduler.card_utils",
        get_all_topic_cards=lambda: topic_cards,
        get_all_item_cards=lambda: item_cards,
    )


# ---------------------------------------------------------------------------
# Card type selection (topic vs item)
# ---------------------------------------------------------------------------

class TestCardTypeSelection:
    def test_returns_topic_card_when_random_below_topics_rate(self):
        """random() < topics_rate  →  topic cards are queried."""
        with _mock_cards():
            with patch("scheduler.random.random", return_value=0.0):
                # 0.0 > 0.5 is False → card_type stays 'item'... wait
                # random.random() > topics_rate → topic; 0.0 > 0.5 is False → item
                # To get topic: return_value must be > topics_rate
                pass

        with _mock_cards():
            with patch("scheduler.random.random", side_effect=[0.9, 0.0]):
                # First call (type check): 0.9 > 0.5 → topic
                # Second call (prob check): 0.0 > 0.5 → priority
                result = scheduler.get_card_from_scheduler(topics_rate=0.5, random_rate=0.5)
        assert result in TOPIC_CARDS

    def test_returns_item_card_when_random_below_topics_rate(self):
        """random() < topics_rate  →  item cards are queried."""
        with _mock_cards():
            with patch("scheduler.random.random", side_effect=[0.1, 0.0]):
                # First call: 0.1 > 0.5 is False → item
                # Second call: 0.0 > 0.5 is False → priority
                result = scheduler.get_card_from_scheduler(topics_rate=0.5, random_rate=0.5)
        assert result in ITEM_CARDS

    def test_topics_rate_1_always_gives_topic_card(self):
        """topics_rate=1.0 means random() never exceeds it → always item.
        topics_rate=0.0 means random() always > 0.0 → always topic."""
        with _mock_cards():
            with patch("scheduler.random.random", side_effect=[0.5, 0.0]):
                result = scheduler.get_card_from_scheduler(topics_rate=0.0, random_rate=0.5)
        assert result in TOPIC_CARDS

    def test_topics_rate_1_always_gives_item_card(self):
        """topics_rate=1.0 means random() (0-1) never exceeds 1.0 → always item."""
        with _mock_cards():
            with patch("scheduler.random.random", side_effect=[0.99, 0.0]):
                result = scheduler.get_card_from_scheduler(topics_rate=1.0, random_rate=0.5)
        assert result in ITEM_CARDS


# ---------------------------------------------------------------------------
# Probability selection (priority vs random)
# ---------------------------------------------------------------------------

class TestProbabilitySelection:
    def test_priority_returns_first_card(self):
        """When probability='priority', the first card in the list is returned."""
        with _mock_cards(item_cards=[501, 502, 503]):
            with patch("scheduler.random.random", side_effect=[0.1, 0.1]):
                # type: 0.1 > 0.5 False → item
                # prob: 0.1 > 0.5 False → priority
                result = scheduler.get_card_from_scheduler()
        assert result == 501

    def test_random_probability_calls_random_choice(self):
        """When probability='random', random.choice is called to pick a card."""
        with _mock_cards(item_cards=[601, 602, 603]):
            with patch("scheduler.random.random", side_effect=[0.1, 0.9]):
                # type: 0.1 > 0.5 False → item
                # prob: 0.9 > 0.5 True → random
                with patch("scheduler.random.choice", return_value=602) as mock_choice:
                    result = scheduler.get_card_from_scheduler()
        mock_choice.assert_called_once_with([601, 602, 603])
        assert result == 602

    def test_random_rate_0_always_uses_priority(self):
        """random_rate=1.0 means random() never exceeds it → always priority."""
        with _mock_cards(item_cards=[701, 702]):
            with patch("scheduler.random.random", side_effect=[0.1, 0.99]):
                result = scheduler.get_card_from_scheduler(random_rate=1.0)
        assert result == 701

    def test_random_rate_0_always_uses_random(self):
        """random_rate=0.0 means random() always > 0.0 → always random."""
        with _mock_cards(item_cards=[801, 802]):
            with patch("scheduler.random.random", side_effect=[0.1, 0.5]):
                with patch("scheduler.random.choice", return_value=802) as mock_choice:
                    result = scheduler.get_card_from_scheduler(random_rate=0.0)
        mock_choice.assert_called_once()
        assert result == 802


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_returns_none_when_no_topic_cards(self):
        with _mock_cards(topic_cards=[]):
            with patch("scheduler.random.random", side_effect=[0.9, 0.0]):
                result = scheduler.get_card_from_scheduler()
        assert result is None

    def test_returns_none_when_no_item_cards(self):
        with _mock_cards(item_cards=[]):
            with patch("scheduler.random.random", side_effect=[0.1, 0.0]):
                result = scheduler.get_card_from_scheduler()
        assert result is None

    def test_single_card_list_returns_that_card(self):
        with _mock_cards(item_cards=[999]):
            with patch("scheduler.random.random", side_effect=[0.1, 0.0]):
                result = scheduler.get_card_from_scheduler()
        assert result == 999
