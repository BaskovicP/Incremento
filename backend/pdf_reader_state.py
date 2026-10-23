"""Instance-owned navigation and lifetime for supplemental PDF readers.

Reference navigation is deliberately transient: no collection, progress, timer,
or scheduling writes belong to this controller.
"""
from dataclasses import dataclass, field
import math
import secrets


def maximum_reference_page(status):
    limit = status.get('allowed_max_page')
    locked = (status.get('enabled') and status.get('enforcement_mode') in ('soft_lock', 'hard_stop')
              and not status.get('override_enabled'))
    return max(1, int(limit)) if locked and limit is not None else 1_000_000


@dataclass
class PdfReaderState:
    profile: str
    card_id: int
    filename: str
    page: int = 1
    scroll_ratio: float = 0
    zoom: float = 1
    max_page: int = 1_000_000
    nonce: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    closed: bool = False

    def is_current(self, profile: str, nonce: str) -> bool:
        return not self.closed and self.profile == profile and secrets.compare_digest(self.nonce, nonce)

    def receive(self, payload: object, *, profile: str, nonce: str) -> bool:
        if not self.is_current(profile, nonce) or not isinstance(payload, dict):
            return False
        page = payload.get("page", self.page)
        scroll = payload.get("scroll_ratio", self.scroll_ratio)
        zoom = payload.get("zoom", self.zoom)
        if (type(page) is not int or not 1 <= page <= self.max_page
                or type(scroll) not in (int, float) or not math.isfinite(scroll) or not 0 <= scroll <= 1
                or type(zoom) not in (int, float) or not math.isfinite(zoom) or not .25 <= zoom <= 4):
            return False
        self.page, self.scroll_ratio, self.zoom = page, scroll, zoom
        return True

    def close(self) -> None:
        self.closed = True
        self.nonce = secrets.token_urlsafe(24)
