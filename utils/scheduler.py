import random
import cards as card_utils

def get_card_from_scheduler(topics_rate=0.5, random_rate=0.5):
    card_type = 'item'
    probability = 'priority'

    if random.random() > topics_rate:
        card_type = 'topic'

    if random.random() > random_rate:
        probability = 'random'

    if card_type == 'topic':
        cards = card_utils.get_all_topic_cards()
    else:
        cards = card_utils.get_all_item_cards()

    if not cards:
        return None

    if probability == 'random':
        return random.choice(cards)
    else:
        # Sort by priority and get the first priority one
        return cards[0]

    # Daj mi po prioritetu ili random
    # Daj mi po tagu ili ne