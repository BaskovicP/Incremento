from __future__ import annotations

from dataclasses import dataclass, field

NO_TAGS_KEY = "__no_tags__"

# Derive the addon package name from this module's path so getConfig works
# regardless of which submodule calls it (e.g. "incremento.backend.scheduler_config"
# → "incremento").
_ADDON_PKG = __name__.split(".")[0]


@dataclass
class SchedulerConfig:
    session_card_count: int = 50   # number of cards to schedule per session
    topics_rate: float = 0.9       # probability of picking a topic card
    random_rate: float = 0.99      # probability of random mode vs priority
    use_tags: bool = False         # True if any real tag rows are active
    tag_weights: dict = field(default_factory=dict)  # {tag: normalised_weight}
    include_rest: bool = True      # fill remaining slots with untagged cards after tag phases
    scheduler_scope: str = "session"   # "session" | "daily" | "lifetime"
    day_end_time: str = "00:00"        # HH:MM — logical day boundary for "daily" scope
    priority_order: list = field(default_factory=lambda: ["tags", "type", "mode"])
    enforce_priority: bool = True      # False → soft debt-based ordering, no hard quotas
    topics_filter: str = "deck:Topics OR tag:Incremento"   # Anki search filter for topic cards
    items_filter: str = "-deck:Topics -tag:Incremento"     # Anki search filter for item cards
    include_new: bool = True             # include is:new cards
    include_learning: bool = True        # include is:learn cards
    include_due: bool = True             # include is:due (review) cards
    preserve_order: bool = True          # build filtered deck in scheduler-selected order
    show_debug: bool = False             # show card order debug dialog at session start
    pdf_rate: float = 0.0                # fraction of session picks that are PDF cards
    content_type_weights: dict = field(default_factory=dict)  # {"pdf"|"youtube"|"webpage": fraction}
    priority_lower_is_more_important: bool = True
    prioritized_tags_first: list[str] = field(default_factory=list)
    prioritized_tags_mode: str = "exhaust"
    # Funnel: ordered list of phase IDs; phases_enabled gates each phase in strict mode
    phase_order: list = field(default_factory=lambda: ["content_types", "tags", "type", "mode"])
    phases_enabled: dict = field(default_factory=dict)  # {phase_id: bool}; True if absent

    @property
    def ready_filter(self) -> str:
        """Anki search clause for the card states to include."""
        parts = []
        if self.include_new:
            parts.append("is:new")
        if self.include_learning:
            parts.append("is:learn")
        if self.include_due:
            parts.append("is:due")
        if not parts:
            return "is:new"   # safety fallback — never emit an empty filter
        if len(parts) == 1:
            return parts[0]
        return "(" + " OR ".join(parts) + ")"


def load_scheduler_config() -> SchedulerConfig:
    """Return the current scheduler settings from saved config.

    Can be called from any part of the addon (PDF reader, stats view, etc.)
    without opening the dialog.
    """
    from aqt import mw
    config = mw.addonManager.getConfig(_ADDON_PKG) or {}
    cfg = _config_from_dialog_dict(config.get("dialog", {}))
    cfg.priority_lower_is_more_important = bool(
        config.get(
            "priority_lower_is_more_important",
            cfg.priority_lower_is_more_important,
        )
    )
    return cfg


def _config_from_dialog_dict(d: dict) -> SchedulerConfig:
    """Build a SchedulerConfig from the raw ``dialog`` config sub-dict."""
    session_card_count = int(d.get("session_card_count", 50))
    topics_rate = 1.0 - d.get("topics_slider", 10) / 100.0
    random_rate = d.get("random_slider", 99) / 100.0

    tag_rows = d.get("tag_rows", [])
    no_tags_checked = d.get("no_tags_checked", True)

    other_rows = [r for r in tag_rows if r.get("tag") == NO_TAGS_KEY]
    real_rows = [r for r in tag_rows if r.get("tag") != NO_TAGS_KEY]
    raw = {r["tag"]: r["weight"] for r in real_rows}
    # Each slider value is an absolute % of the session (0–100).
    # Do NOT normalise across tags — the remainder goes to "other cards".
    tag_weights = {tag: v / 100.0 for tag, v in raw.items()}
    include_rest = no_tags_checked
    if other_rows:
        include_rest = float(other_rows[0].get("weight", 0) or 0) > 0.0

    priority_order    = d.get("priority_order", ["tags", "type", "mode"])
    enforce_priority  = d.get("enforce_priority", True)

    scheduler_scope = d.get("scheduler_scope", "session")
    day_end_time    = d.get("day_end_time", "00:00")
    topics_filter    = d.get("topics_filter",    "deck:Topics OR tag:Incremento")
    items_filter     = d.get("items_filter",     "-deck:Topics -tag:Incremento")
    # Migrate old deck-only defaults to tag-aware defaults
    if topics_filter == "deck:Topics":
        topics_filter = "deck:Topics OR tag:Incremento"
    if items_filter == "-deck:Topics":
        items_filter = "-deck:Topics -tag:Incremento"
    include_new      = d.get("include_new",      True)
    include_learning = d.get("include_learning", True)
    include_due      = d.get("include_due",      True)
    preserve_order   = d.get("preserve_order",   True)
    show_debug       = d.get("show_debug",       False)
    pdf_rate         = d.get("pdf_slider",        0) / 100.0
    priority_lower_is_more_important = d.get("priority_lower_is_more_important", True)

    content_type_rows = d.get("content_type_rows", [])
    content_type_weights = {
        r["type"]: r["weight"] / 100.0
        for r in content_type_rows
        if r.get("enabled") and r.get("weight", 0) > 0
    }
    prioritized_tags_first = []
    for raw_tag in d.get("prioritized_tags_first", []):
        tag = str(raw_tag or "").strip()
        if not tag or tag.casefold() in {t.casefold() for t in prioritized_tags_first}:
            continue
        prioritized_tags_first.append(tag)
    prioritized_tags_mode = str(d.get("prioritized_tags_mode") or "exhaust").strip().lower()
    if prioritized_tags_mode != "exhaust":
        prioritized_tags_mode = "exhaust"

    return SchedulerConfig(
        session_card_count=session_card_count,
        topics_rate=topics_rate,
        random_rate=random_rate,
        use_tags=bool(real_rows),
        tag_weights=tag_weights,
        include_rest=include_rest,
        scheduler_scope=scheduler_scope,
        day_end_time=day_end_time,
        priority_order=priority_order,
        enforce_priority=enforce_priority,
        topics_filter=topics_filter,
        items_filter=items_filter,
        include_new=include_new,
        include_learning=include_learning,
        include_due=include_due,
        preserve_order=preserve_order,
        show_debug=show_debug,
        pdf_rate=pdf_rate,
        content_type_weights=content_type_weights,
        priority_lower_is_more_important=priority_lower_is_more_important,
        prioritized_tags_first=prioritized_tags_first,
        prioritized_tags_mode=prioritized_tags_mode,
        phase_order=d.get("phase_order", ["content_types", "tags", "type", "mode"]),
        phases_enabled=d.get("phases_enabled", {}),
    )
