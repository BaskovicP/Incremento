"""Conservative wall-clock accounting for observed video playback."""

from __future__ import annotations

import math
from collections.abc import Callable


class VideoWatchMeter:
    """Accumulate short active samples and flush them under their captured scope."""

    def __init__(
        self,
        persist: Callable[[str, int, str, float], None],
        *,
        flush_after: float = 5.0,
    ) -> None:
        self._persist = persist
        self._flush_after = max(1.0, float(flush_after))
        self._key: tuple[str, int, str] | None = None
        self._previous: tuple[float, float, bool] | None = None
        self._pending = 0.0

    def observe(
        self,
        profile: str,
        card_id: int,
        logical_date: str,
        position: float,
        monotonic_time: float,
        *,
        paused: bool | None,
        has_video: bool = True,
    ) -> None:
        key = (str(profile), int(card_id), str(logical_date))
        if key != self._key:
            self.flush()
            self._key = key
            self._previous = None
        try:
            current = float(position)
            now = float(monotonic_time)
        except (TypeError, ValueError):
            self._previous = None
            return
        if not math.isfinite(current) or not math.isfinite(now) or current < 0:
            self._previous = None
            return
        active = bool(has_video) and paused is not True
        previous = self._previous
        if previous is not None and previous[2] and active:
            old_position, old_time, _old_active = previous
            elapsed = now - old_time
            progress = current - old_position
            if 0 < elapsed <= 5 and 0 < progress <= max(2.0, elapsed * 4.0 + 1.0):
                self._pending += elapsed
        self._previous = (current, now, active)
        if self._pending >= self._flush_after:
            self.flush()

    def flush(self) -> None:
        if self._key is None or self._pending <= 0:
            return
        profile, card_id, logical_date = self._key
        seconds = round(self._pending, 3)
        try:
            self._persist(profile, card_id, logical_date, seconds)
        except Exception:
            return
        self._pending = 0.0

    def reset(self) -> None:
        self.flush()
        self._key = None
        self._previous = None
        self._pending = 0.0
