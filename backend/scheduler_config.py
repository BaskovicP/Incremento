from __future__ import annotations

from dataclasses import dataclass, field

try:
    from .config_service import load_addon_config
except ImportError:
    from config_service import load_addon_config  # type: ignore

NO_TAGS_KEY = "__no_tags__"
READY_NEW_CLAUSE = "is:new"
READY_LEARNING_CLAUSE = "(is:learn is:due)"
READY_REVIEW_CLAUSE = "(is:review is:due)"
DEFAULT_DAY_END_TIME = "04:00"
MAX_SESSION_CARD_COUNT = 9999
_VALID_SCOPES = {"session", "daily", "lifetime"}
_VALID_PHASE_IDS = ("content_types", "tags", "type", "mode")


def _bounded_number(value, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = float(default)
    if number != number:  # NaN
        number = float(default)
    return min(float(maximum), max(float(minimum), number))


def _bounded_int(value, default: int, minimum: int, maximum: int) -> int:
    return int(_bounded_number(value, default, minimum, maximum))


def _config_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0", ""}:
            return False
    return bool(default)


def _normalized_day_end_time(value) -> str:
    text = str(value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except Exception:
        return DEFAULT_DAY_END_TIME
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return DEFAULT_DAY_END_TIME
    return f"{hour:02d}:{minute:02d}"


def _normalized_phase_order(value) -> list[str]:
    raw = value if isinstance(value, (list, tuple)) else []
    normalized: list[str] = []
    for phase_id in raw:
        phase = str(phase_id or "").strip()
        if phase in _VALID_PHASE_IDS and phase not in normalized:
            normalized.append(phase)
    for phase in _VALID_PHASE_IDS:
        if phase not in normalized:
            normalized.append(phase)
    return normalized


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
        return "cid:0 -is:suspended"
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
    allow_content_tag_fallback: bool = False  # document/media tag misses may fall back to the full content pool
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
    config = load_addon_config(mw.addonManager, _ADDON_PKG)
    cfg = _config_from_dialog_dict(config.get("dialog", {}))
    cfg.priority_lower_is_more_important = _config_bool(
        config.get(
            "priority_lower_is_more_important",
            cfg.priority_lower_is_more_important,
        ),
        cfg.priority_lower_is_more_important,
    )
    return cfg


def _config_from_dialog_dict(d: dict) -> SchedulerConfig:
    """Build a SchedulerConfig from the raw ``dialog`` config sub-dict."""
    d = d if isinstance(d, dict) else {}
    session_card_count = _bounded_int(
        d.get("session_card_count", 50),
        50,
        1,
        MAX_SESSION_CARD_COUNT,
    )
    topics_slider = _bounded_number(d.get("topics_slider", 10), 10, 0, 100)
    random_slider = _bounded_number(d.get("random_slider", 99), 99, 0, 100)
    topics_rate = 1.0 - topics_slider / 100.0
    random_rate = random_slider / 100.0

    raw_tag_rows = d.get("tag_rows")
    tag_rows = [row for row in raw_tag_rows if isinstance(row, dict)] if isinstance(raw_tag_rows, list) else []
    no_tags_checked = _config_bool(d.get("no_tags_checked", True), True)

    other_rows = [r for r in tag_rows if r.get("tag") == NO_TAGS_KEY]
    real_rows = [
        r
        for r in tag_rows
        if str(r.get("tag") or "").strip()
        and r.get("tag") != NO_TAGS_KEY
    ]
    # Each slider value is an absolute % of the session (0–100).
    # Do NOT normalise across tags — the remainder goes to "other cards".
    tag_weights = {
        str(row.get("tag") or "").strip(): weight / 100.0
        for row in real_rows
        if (weight := _bounded_number(row.get("weight", 0), 0, 0, 100)) > 0
    }
    include_rest = no_tags_checked
    if other_rows:
        include_rest = _bounded_number(
            other_rows[0].get("weight", 0), 0, 0, 100
        ) > 0.0

    priority_order = d.get("priority_order", ["tags", "type", "mode"])
    if not isinstance(priority_order, list):
        priority_order = ["tags", "type", "mode"]
    enforce_priority = _config_bool(d.get("enforce_priority", True), True)

    scheduler_scope = str(d.get("scheduler_scope") or "session").strip().lower()
    if scheduler_scope not in _VALID_SCOPES:
        scheduler_scope = "session"
    day_end_time = _normalized_day_end_time(
        d.get("day_end_time", DEFAULT_DAY_END_TIME)
    )
    topics_filter = str(d.get("topics_filter", "") or "").strip()
    items_filter = str(d.get("items_filter", "") or "").strip()
    # Migrate old deck/tag defaults to the new classifier-based empty filters.
    if topics_filter in {"deck:Topics", "deck:Topics OR tag:Incremento"}:
        topics_filter = ""
    if items_filter in {"-deck:Topics", "-deck:Topics -tag:Incremento"}:
        items_filter = ""
    include_new = _config_bool(d.get("include_new", True), True)
    include_learning = _config_bool(d.get("include_learning", True), True)
    include_due = _config_bool(d.get("include_due", True), True)
    preserve_order = _config_bool(d.get("preserve_order", True), True)
    show_debug = _config_bool(d.get("show_debug", False), False)
    auto_refill_session = _config_bool(d.get("auto_refill_session", False), False)
    # The UI slider runs from Docs on the left to Other on the right.
    pdf_slider = _bounded_number(d.get("pdf_slider", 100), 100, 0, 100)
    pdf_rate = 1.0 - pdf_slider / 100.0
    priority_lower_is_more_important = _config_bool(
        d.get("priority_lower_is_more_important", True), True
    )

    raw_content_type_rows = d.get("content_type_rows")
    content_type_rows = (
        [row for row in raw_content_type_rows if isinstance(row, dict)]
        if isinstance(raw_content_type_rows, list)
        else []
    )
    content_type_weights = {
        str(r.get("type") or "").strip().lower(): weight / 100.0
        for r in content_type_rows
        if _config_bool(r.get("enabled", False), False)
        and str(r.get("type") or "").strip().lower()
        in {"pdf", "youtube", "webpage"}
        and (weight := _bounded_number(r.get("weight", 0), 0, 0, 100)) > 0
    }
    allow_content_tag_fallback = _config_bool(
        d.get("allow_content_tag_fallback", False), False
    )
    prioritized_tags_first: list[str] = []
    raw_prioritized_tags = d.get("prioritized_tags_first", [])
    if isinstance(raw_prioritized_tags, str):
        raw_prioritized_tags = raw_prioritized_tags.replace(",", "\n").splitlines()
    elif not isinstance(raw_prioritized_tags, (list, tuple, set)):
        raw_prioritized_tags = []
    for raw_tag in raw_prioritized_tags:
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
    priority_order_enabled = _config_bool(
        d.get("priority_order_enabled", False), False
    )
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
        auto_refill_session=auto_refill_session,
        topics_rate=topics_rate,
        random_rate=random_rate,
        use_tags=bool(tag_weights),
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
        allow_content_tag_fallback=allow_content_tag_fallback,
        priority_lower_is_more_important=priority_lower_is_more_important,
        priority_order_enabled=priority_order_enabled,
        priority_order_entries=priority_order_entries,
        prioritized_tags_first=prioritized_tags_first,
        prioritized_tags_mode=prioritized_tags_mode,
        phase_order=_normalized_phase_order(d.get("phase_order")),
        phases_enabled={
            str(phase): _config_bool(enabled, True)
            for phase, enabled in (
                d.get("phases_enabled", {}).items()
                if isinstance(d.get("phases_enabled"), dict)
                else []
            )
            if str(phase) in _VALID_PHASE_IDS
        },
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
