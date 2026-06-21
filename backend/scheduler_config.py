from __future__ import annotations

from dataclasses import dataclass, field

NO_TAGS_KEY = "__no_tags__"
READY_NEW_CLAUSE = "is:new"
READY_LEARNING_CLAUSE = "(is:learn is:due)"
READY_REVIEW_CLAUSE = "(is:review is:due)"
DEFAULT_DAY_END_TIME = "04:00"


def build_ready_filter(
    *,
    include_new: bool,
    include_learning: bool,
    include_due: bool,
) -> str:
    """Return an Anki search clause for cards ready to study now."""
    parts = []
    if include_new:
        parts.append(READY_NEW_CLAUSE)
    if include_learning:
        parts.append(READY_LEARNING_CLAUSE)
    if include_due:
        parts.append(READY_REVIEW_CLAUSE)
    if not parts:
        return f"{READY_NEW_CLAUSE} -is:suspended"
    if len(parts) == 1:
        return f"{parts[0]} -is:suspended"
    return "(" + " OR ".join(parts) + ") -is:suspended"

# Derive the addon package name from this module's path so getConfig works
# regardless of which submodule calls it (e.g. "incremento.backend.scheduler_config"
# → "incremento").
_ADDON_PKG = __name__.split(".")[0]


@dataclass
class SchedulerConfig:
    session_card_count: int = 50   # number of cards to schedule per session
    auto_refill_session: bool = False  # keep session deck topped up to session_card_count pending cards
    topics_rate: float = 0.9       # probability of picking a topic card
    random_rate: float = 0.99      # probability of random mode vs priority
    use_tags: bool = False         # True if any real tag rows are active
    tag_weights: dict = field(default_factory=dict)  # {tag: normalised_weight}
    include_rest: bool = True      # fill remaining slots with untagged cards after tag phases
    scheduler_scope: str = "session"   # "session" | "daily" | "lifetime"
    day_end_time: str = DEFAULT_DAY_END_TIME  # HH:MM — logical day boundary for "daily" scope
    priority_order: list = field(default_factory=lambda: ["tags", "type", "mode"])
    enforce_priority: bool = True      # False → soft debt-based ordering, no hard quotas
    topics_filter: str = ""   # Optional Anki search filter that further narrows topic cards
    items_filter: str = ""    # Optional Anki search filter that further narrows item cards
    include_new: bool = True             # include is:new cards
    include_learning: bool = True        # include is:learn cards
    include_due: bool = True             # include is:due (review) cards
    preserve_order: bool = True          # build filtered deck in scheduler-selected order
    show_debug: bool = False             # show card order debug dialog at session start
    pdf_rate: float = 0.0                # fraction of session picks that are PDF cards
    content_type_weights: dict = field(default_factory=dict)  # {"pdf"|"youtube"|"webpage": fraction}
    priority_lower_is_more_important: bool = True
    priority_order_enabled: bool = False
    priority_order_entries: list = field(default_factory=list)  # [{"kind": "tag"|"content_type", "value": str, "order": int}]
    prioritized_tags_first: list[str] = field(default_factory=list)
    prioritized_tags_mode: str = "exhaust"
    # Funnel: ordered list of phase IDs; phases_enabled gates each phase in strict mode
    phase_order: list = field(default_factory=lambda: ["content_types", "tags", "type", "mode"])
    phases_enabled: dict = field(default_factory=dict)  # {phase_id: bool}; True if absent

    @property
    def ready_filter(self) -> str:
        """Anki search clause for the card states to include."""
        return build_ready_filter(
            include_new=self.include_new,
            include_learning=self.include_learning,
            include_due=self.include_due,
        )


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
    day_end_time    = d.get("day_end_time", DEFAULT_DAY_END_TIME)
    topics_filter    = str(d.get("topics_filter", "") or "").strip()
    items_filter     = str(d.get("items_filter", "") or "").strip()
    # Migrate old deck/tag defaults to the new classifier-based empty filters.
    if topics_filter in {"deck:Topics", "deck:Topics OR tag:Incremento"}:
        topics_filter = ""
    if items_filter in {"-deck:Topics", "-deck:Topics -tag:Incremento"}:
        items_filter = ""
    include_new      = d.get("include_new",      True)
    include_learning = d.get("include_learning", True)
    include_due      = d.get("include_due",      True)
    preserve_order   = d.get("preserve_order",   True)
    show_debug       = d.get("show_debug",       False)
    auto_refill_session = d.get("auto_refill_session", False)
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

    has_new_priority_order_config = (
        "priority_order_enabled" in d
        or "priority_order_entries" in d
        or any("order" in r for r in real_rows)
        or any("order" in r for r in content_type_rows)
    )
    priority_order_enabled = bool(d.get("priority_order_enabled", False))
    priority_order_entries = _normalize_priority_order_entries(
        d.get("priority_order_entries"),
        real_rows=real_rows,
        content_type_rows=content_type_rows,
    )
    if not has_new_priority_order_config and prioritized_tags_first:
        priority_order_enabled = True
        priority_order_entries = [
            {"kind": "tag", "value": tag, "order": idx + 1}
            for idx, tag in enumerate(prioritized_tags_first)
        ]

    return SchedulerConfig(
        session_card_count=session_card_count,
        auto_refill_session=bool(auto_refill_session),
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
        priority_order_enabled=priority_order_enabled,
        priority_order_entries=priority_order_entries,
        prioritized_tags_first=prioritized_tags_first,
        prioritized_tags_mode=prioritized_tags_mode,
        phase_order=d.get("phase_order", ["content_types", "tags", "type", "mode"]),
        phases_enabled=d.get("phases_enabled", {}),
    )


def _positive_int(value) -> int | None:
    try:
        order = int(str(value).strip())
    except Exception:
        return None
    if order <= 0:
        return None
    return order


def _normalize_priority_order_entries(
    entries,
    *,
    real_rows: list[dict],
    content_type_rows: list[dict],
) -> list[dict]:
    raw_entries: list[dict] = []
    if isinstance(entries, list):
        raw_entries.extend(entry for entry in entries if isinstance(entry, dict))
    else:
        for row in real_rows:
            if "order" not in row:
                continue
            raw_entries.append(
                {
                    "kind": "tag",
                    "value": row.get("tag"),
                    "order": row.get("order"),
                }
            )
        for row in content_type_rows:
            if "order" not in row:
                continue
            raw_entries.append(
                {
                    "kind": "content_type",
                    "value": row.get("type"),
                    "order": row.get("order"),
                }
            )

    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    valid_content_types = {"pdf", "youtube", "webpage"}
    for entry in raw_entries:
        kind = str(entry.get("kind") or "").strip()
        value = str(entry.get("value") or "").strip()
        order = _positive_int(entry.get("order"))
        if order is None:
            continue
        if kind == "tag":
            if not value or value == NO_TAGS_KEY:
                continue
            key_value = value.casefold()
        elif kind == "content_type":
            value = value.lower()
            if value not in valid_content_types:
                continue
            key_value = value
        else:
            continue
        key = (kind, key_value)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"kind": kind, "value": value, "order": order})
    return normalized
