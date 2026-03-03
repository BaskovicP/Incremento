"""
This module defines the main functionality for the Incremental Learning Anki addon.
It includes the AddonManager class for managing addon-specific data and the learnFunction
for initiating the learning process.
"""

import json
from aqt import mw
from aqt.utils import showInfo
from aqt.qt import *

from .utils.statistics import load_stats, save_stats
from .utils.cards import add_topic_type_to_custom_data

class AddonManager:
    def __init__(self):
        self.addon_dir = os.path.dirname(__file__)
        self.stats = None

    def get_stats(self):
        if self.stats is None:
            self.stats = load_stats(self.addon_dir)
        return self.stats


addon_manager = AddonManager()


def learnFunction() -> None:
    # cids = mw.col.find_cards("is:due")
    # cid = random.choice(cids)
    # card = mw.col.get_card(cid)


    add_topic_type_to_custom_data("topics")

    test_card = mw.col.get_card(mw.col.find_cards("deck:topics")[0])

    showInfo(json.loads(test_card.custom_data))

    config = mw.addonManager.getConfig(__name__)
    if config:
        showInfo(config['my_var'])
    else:
        showInfo("Learn button clicked! Replace this with your test code.")

learnAction = QAction("Start Incremental Learning", mw)
qconnect(learnAction.triggered, learnFunction)
mw.form.menuTools.addAction(learnAction)
