from __future__ import annotations

from dataclasses import dataclass, field

NO_TAGS_KEY = "__no_tags__"

# Derive the addon package name from this module's path so getConfig works
# regardless of which submodule calls it (e.g. "incremento.utils.scheduler_config"
# → "incremento").
_ADDON_PKG = __name__.split(".")[0]


@dataclass
class SchedulerConfig:
    topics_rate: float = 0.9       # probability of picking a topic card
    random_rate: float = 0.99      # probability of random mode vs priority
    use_tags: bool = False         # True if any real tag rows are active
    tag_weights: dict = field(default_factory=dict)  # {tag: normalised_weight}
    include_rest: bool = True      # fill remaining slots with untagged cards after tag phases
    scheduler_scope: str = "session"   # "session" | "daily" | "lifetime"
    day_end_time: str = "00:00"        # HH:MM — logical day boundary for "daily" scope
    priority_order: list = field(default_factory=lambda: ["tags", "type", "mode"])
    enforce_priority: bool = True      # False → soft debt-based ordering, no hard quotas


def load_scheduler_config() -> SchedulerConfig:
    """Return the current scheduler settings from saved config.

    Can be called from any part of the addon (PDF reader, stats view, etc.)
    without opening the dialog.
    """
    from aqt import mw
    config = mw.addonManager.getConfig(_ADDON_PKG) or {}
    return _config_from_dialog_dict(config.get("dialog", {}))


def _config_from_dialog_dict(d: dict) -> SchedulerConfig:
    """Build a SchedulerConfig from the raw ``dialog`` config sub-dict."""
    topics_rate = 1.0 - d.get("topics_slider", 10) / 100.0
    random_rate = d.get("random_slider", 99) / 100.0

    tag_rows = d.get("tag_rows", [])
    no_tags_checked = d.get("no_tags_checked", True)

    real_rows = [r for r in tag_rows if r["tag"] != NO_TAGS_KEY]
    raw = {r["tag"]: r["weight"] for r in real_rows}
    total = sum(raw.values()) or 1
    tag_weights = {tag: v / total for tag, v in raw.items()}

    priority_order    = d.get("priority_order", ["tags", "type", "mode"])
    enforce_priority  = d.get("enforce_priority", True)

    scheduler_scope = d.get("scheduler_scope", "session")
    day_end_time    = d.get("day_end_time", "00:00")

    return SchedulerConfig(
        topics_rate=topics_rate,
        random_rate=random_rate,
        use_tags=bool(real_rows),
        tag_weights=tag_weights,
        include_rest=no_tags_checked,
        scheduler_scope=scheduler_scope,
        day_end_time=day_end_time,
        priority_order=priority_order,
        enforce_priority=enforce_priority,
    )
