"""Lifetime of a reference visit. Returning never redraws or grades the card."""
from dataclasses import dataclass


@dataclass
class StudyVisit:
    profile: str
    collection: object
    card_id: int
    side: str
    stage: str = "card"
    closed: bool = False

    def current(self, profile, collection, card_id, side):
        return (not self.closed and profile == self.profile and collection is self.collection
                and card_id == self.card_id and side == self.side)

    def navigate(self, stage):
        if self.closed or stage not in ("card", "book", "video"):
            raise ValueError("Unavailable study visit")
        self.stage = stage

    def finish(self, profile, collection, card_id, side):
        valid = self.current(profile, collection, card_id, side)
        self.closed = True
        return valid
