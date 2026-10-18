import csv
import io
import json
import math
import os
import tempfile
import threading
import time
from datetime import date, datetime, timedelta

try:
    from .db import get_connection
    from .paths import get_stats_path as _get_stats_path
except ImportError:
    from db import get_connection  # test environment (backend/ on sys.path)
    from paths import get_stats_path as _get_stats_path


_STATS_LOCKS_GUARD = threading.Lock()
_STATS_LOCKS: dict[str, threading.RLock] = {}
_MAX_STAT_KEY_LENGTH = 128
_MAX_STAT_KEYS_PER_GROUP = 512
_MAX_STAT_VALUE = 1_000_000_000_000.0
_MAX_HISTORY_DAYS = 3660
_MAX_DAILY_REVIEW_ROWS = 10_000
_DOCUMENT_TYPES = frozenset({"pdf", "epub"})
_STATISTICS_GOAL_KEYS = ("cards", "pages", "minutes")
_MAX_DAILY_GOAL = 1_000_000.0
_TAG_BREAKDOWN_KINDS = ("topics", "items")
UNTAGGED_STATS_TAG = "(untagged)"


def _stats_lock(addon_dir: str, profile: str) -> threading.RLock:
    key = str(_get_stats_path(addon_dir, profile).resolve())
    with _STATS_LOCKS_GUARD:
        lock = _STATS_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _STATS_LOCKS[key] = lock
        return lock


def _empty() -> dict:
    return {"type": {}, "tags": {}, "mode": {}}


def _empty_time() -> dict:
    return {"type": {}, "tags": {}}


def _empty_tag_breakdown() -> dict:
    return {
        "counts": {kind: {} for kind in _TAG_BREAKDOWN_KINDS},
        "seconds": {kind: {} for kind in _TAG_BREAKDOWN_KINDS},
    }


def normalize_statistics_goals(raw) -> dict[str, float]:
    values = dict(raw or {}) if isinstance(raw, dict) else {}
    result: dict[str, float] = {}
    for key in _STATISTICS_GOAL_KEYS:
        value = values.get(key, 0)
        if isinstance(value, bool):
            number = 0.0
        else:
            try:
                number = float(value)
            except Exception:
                number = 0.0
        if not math.isfinite(number):
            number = 0.0
        result[key] = max(0.0, min(_MAX_DAILY_GOAL, number))
    return result


def get_statistics_goals(addon_dir: str, profile: str) -> dict[str, float]:
    result = normalize_statistics_goals({})
    try:
        conn = get_connection(addon_dir, profile)
        rows = conn.execute(
            "SELECT metric, daily_target FROM statistics_goals "
            "ORDER BY metric"
        ).fetchall()
    except Exception:
        return result
    return normalize_statistics_goals(
        {str(metric): target for metric, target in rows}
    )


def set_statistics_goals(
    addon_dir: str,
    profile: str,
    goals,
    *,
    now: float | None = None,
) -> dict[str, float]:
    normalized = normalize_statistics_goals(goals)
    try:
        timestamp = int(time.time() if now is None else float(now))
    except Exception:
        timestamp = int(time.time())
    timestamp = max(0, timestamp)
    conn = get_connection(addon_dir, profile)
    try:
        with conn:
            for metric in _STATISTICS_GOAL_KEYS:
                conn.execute(
                    "INSERT INTO statistics_goals(metric, daily_target, updated_at) "
                    "VALUES (?, ?, ?) ON CONFLICT(metric) DO UPDATE SET "
                    "daily_target = excluded.daily_target, "
                    "updated_at = excluded.updated_at",
                    (metric, normalized[metric], timestamp),
                )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    return normalized


def _clean_stat_key(key) -> str | None:
    try:
        text = str(key).strip()
    except Exception:
        return None
    if (
        not text
        or text.startswith("__")
        or len(text) > _MAX_STAT_KEY_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in text)
    ):
        return None
    return text


def _coerce_nonnegative_number(value, *, integer: bool):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number) or number < 0 or number > _MAX_STAT_VALUE:
        return None
    if integer:
        return int(number)
    return float(number)


def _normalize_number_map(raw, *, integer: bool) -> dict:
    if not isinstance(raw, dict):
        return {}
    clean: dict = {}
    for key, value in raw.items():
        if len(clean) >= _MAX_STAT_KEYS_PER_GROUP:
            break
        clean_key = _clean_stat_key(key)
        if clean_key is None:
            continue
        clean_value = _coerce_nonnegative_number(value, integer=integer)
        if clean_value is None:
            continue
        combined = clean.get(clean_key, 0) + clean_value
        if combined <= _MAX_STAT_VALUE:
            clean[clean_key] = combined
    return clean


def _normalize_logical_date(value) -> str | None:
    try:
        text = str(value or "").strip()
    except Exception:
        return None
    if len(text) != 10:
        return None
    try:
        parsed = date.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return text if parsed.isoformat() == text else None


def _normalize_counts_block(raw) -> dict:
    if not isinstance(raw, dict):
        return _empty()
    return {
        "type": _normalize_number_map(raw.get("type"), integer=True),
        "tags": _normalize_number_map(raw.get("tags"), integer=True),
        "mode": _normalize_number_map(raw.get("mode"), integer=True),
    }


def _normalize_time_block(raw) -> dict:
    if not isinstance(raw, dict):
        return _empty_time()
    return {
        "type": _normalize_number_map(raw.get("type"), integer=False),
        "tags": _normalize_number_map(raw.get("tags"), integer=False),
    }


def _normalize_tag_breakdown_block(raw) -> dict:
    if not isinstance(raw, dict):
        return _empty_tag_breakdown()
    counts: dict = raw.get("counts") if isinstance(raw.get("counts"), dict) else {}
    seconds: dict = raw.get("seconds") if isinstance(raw.get("seconds"), dict) else {}
    return {
        "counts": {
            kind: _normalize_number_map(counts.get(kind), integer=True)
            for kind in _TAG_BREAKDOWN_KINDS
        },
        "seconds": {
            kind: _normalize_number_map(seconds.get(kind), integer=False)
            for kind in _TAG_BREAKDOWN_KINDS
        },
    }


def _normalize_stats(raw) -> dict:
    if not isinstance(raw, dict):
        return {}

    result: dict = {}

    if "daily" in raw:
        daily_raw = raw.get("daily")
        if isinstance(daily_raw, dict):
            result["daily"] = {
                "date": _normalize_logical_date(daily_raw.get("date")) or "",
                "counts": _normalize_counts_block(daily_raw.get("counts")),
            }
        else:
            result["daily"] = {"date": "", "counts": _empty()}

    if "lifetime" in raw:
        result["lifetime"] = _normalize_counts_block(raw.get("lifetime"))

    if "time" in raw:
        time_raw = raw.get("time")
        time_result: dict = {}
        if isinstance(time_raw, dict):
            if "daily" in time_raw:
                daily_time_raw = time_raw.get("daily")
                if isinstance(daily_time_raw, dict):
                    time_result["daily"] = {
                        "date": _normalize_logical_date(daily_time_raw.get("date")) or "",
                        "seconds": _normalize_time_block(
                            daily_time_raw.get("seconds")
                        ),
                    }
                else:
                    time_result["daily"] = {"date": "", "seconds": _empty_time()}
            if "lifetime" in time_raw:
                time_result["lifetime"] = _normalize_time_block(
                    time_raw.get("lifetime")
                )
        if time_result:
            result["time"] = time_result

    if "tag_breakdown" in raw:
        breakdown_raw = raw.get("tag_breakdown")
        breakdown_result: dict = {}
        if isinstance(breakdown_raw, dict):
            if "daily" in breakdown_raw:
                daily_breakdown = breakdown_raw.get("daily")
                if isinstance(daily_breakdown, dict):
                    normalized_daily = _normalize_tag_breakdown_block(daily_breakdown)
                    normalized_daily["date"] = (
                        _normalize_logical_date(daily_breakdown.get("date")) or ""
                    )
                    breakdown_result["daily"] = normalized_daily
                else:
                    breakdown_result["daily"] = {
                        "date": "",
                        **_empty_tag_breakdown(),
                    }
            if "lifetime" in breakdown_raw:
                breakdown_result["lifetime"] = _normalize_tag_breakdown_block(
                    breakdown_raw.get("lifetime")
                )
        if breakdown_result:
            result["tag_breakdown"] = breakdown_result

    return result


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _effective_date(day_end: str = "04:00") -> str:
    """Return the logical date string, honouring a non-midnight day boundary.

    If day_end is "04:00" and the current time is 03:30, the logical date is
    yesterday — the user's 'day' hasn't ended yet.
    """
    now = datetime.now()
    h, m = map(int, day_end.split(":"))
    boundary_minutes = h * 60 + m
    current_minutes = now.hour * 60 + now.minute
    if current_minutes < boundary_minutes:
        return (now.date() - timedelta(days=1)).isoformat()
    return now.date().isoformat()


def _logical_day_bounds_ms(day_end: str = "04:00") -> tuple[int, int]:
    logical_date = date.fromisoformat(_effective_date(day_end))
    return _logical_date_bounds_ms(logical_date, day_end)


def _logical_date_bounds_ms(logical_date: date, day_end: str) -> tuple[int, int]:
    """Use local calendar boundaries, including 23/25-hour daylight-saving days."""
    hour, minute = map(int, day_end.split(":"))
    start = datetime.combine(logical_date, datetime.min.time()).replace(
        hour=hour,
        minute=minute,
    )
    end = start + timedelta(days=1)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _daily_breakdown_tag(note, classifier) -> str:
    excluded = {
        str(tag or "").strip().casefold()
        for tag in (
            *(getattr(classifier, "topic_tags", ()) or ()),
            *(getattr(classifier, "item_tags", ()) or ()),
        )
        if str(tag or "").strip()
    }
    for raw_tag in getattr(note, "tags", None) or ():
        tag = str(raw_tag or "").strip()
        if tag and not tag.startswith("__") and tag.casefold() not in excluded:
            return tag
    return UNTAGGED_STATS_TAG


def learning_card_states_from_collection(collection, *, classifier=None, should_cancel=None):
    """Current memory-card types, including suspended/buried cards in their stage.

    These are Anki types, not queue numbers (day-learning queue 3 is still
    learning). Relearning stays separate; Review never means permanently done.
    Read in bounded batches through a background collection operation.
    """
    if collection is None:
        return None
    try:
        try:
            from .cards import _bulk_classify_candidate_ids
            from .topic_scheduler import resolve_topic_card_classifier
        except ImportError:
            from cards import _bulk_classify_candidate_ids
            from topic_scheduler import resolve_topic_card_classifier
        classifier = classifier if classifier is not None else resolve_topic_card_classifier()
        result = dict.fromkeys(("new", "learning", "review", "relearning", "total", "suspended", "buried"), 0)
        reader_names = {"Incremento PDF", "Incremento EPUB", "Incremento Video",
                        "Incremento Web", "Incremento Writing", "Incremento Local File"}
        reader_models = {int(model["id"]) for name in reader_names if (model := collection.models.by_name(name))}
        last_id = 0
        while True:
            if should_cancel is not None and should_cancel():
                return None
            rows = collection.db.all(
                "SELECT c.id, c.type, c.queue, n.mid FROM cards c JOIN notes n ON n.id=c.nid "
                "WHERE c.id > ? ORDER BY c.id LIMIT 500", last_id,
            )
            if not rows:
                return result
            partition = _bulk_classify_candidate_ids(
                [row[0] for row in rows], collection=collection, classifier=classifier,
            )
            if partition is None:
                return None
            memory_ids = set(partition[1])
            for cid, stage, queue, mid in rows:
                if cid not in memory_ids or mid in reader_models or stage not in range(4):
                    continue
                result[("new", "learning", "review", "relearning")[stage]] += 1
                result["total"] += 1
                result["suspended"] += int(queue == -1)
                result["buried"] += int(queue in (-2, -3))
            last_id = int(rows[-1][0])
    except Exception:
        return None


def daily_learning_outcomes_from_collection(
    collection,
    day_end_time: str = "04:00",
    *,
    classifier=None,
    topic_predicate=None,
    should_cancel=None,
) -> dict | None:
    """Read today's canonical memory grades off the UI thread; None = unknown."""
    try:
        ranges = [(_effective_date(day_end_time), *_logical_day_bounds_ms(day_end_time))]
    except (ValueError, TypeError, OverflowError):
        return None
    history = _learning_outcomes_for_ranges(
        collection, ranges, classifier=classifier,
        topic_predicate=topic_predicate, should_cancel=should_cancel,
    )
    return history[0] if history is not None else None


def learning_outcome_history_from_collection(
    collection, day_end_time: str = "04:00", *, days: int = 60,
    classifier=None, topic_predicate=None, should_cancel=None,
) -> list[dict] | None:
    """Read up to 60 zero-filled logical days, including today.

    The extra 30 days support comparison with the previous equal-size period.
    Read off the UI thread. No second persisted ledger is created: Undo/Redo
    and historical backfill follow Anki's revlog and current Topic/Item rules.
    """
    try:
        count = max(1, min(60, int(days)))
        end_date = date.fromisoformat(_effective_date(day_end_time))
        dates = [end_date - timedelta(days=offset) for offset in reversed(range(count))]
        ranges = [(day.isoformat(), *_logical_date_bounds_ms(day, day_end_time)) for day in dates]
    except (ValueError, TypeError, OverflowError):
        return None
    return _learning_outcomes_for_ranges(
        collection, ranges, classifier=classifier,
        topic_predicate=topic_predicate, should_cancel=should_cancel,
    )


def _learning_outcomes_for_ranges(collection, ranges, *, classifier, topic_predicate, should_cancel):
    """Bound grouped rows with a (card, day) cursor without truncating totals."""
    if collection is None:
        return None
    try:
        try:
            from .topic_scheduler import is_topic_card, resolve_topic_card_classifier
            from .cards import _bulk_classify_candidate_ids, _supports_bulk_topic_classification
        except ImportError:
            from topic_scheduler import is_topic_card, resolve_topic_card_classifier  # type: ignore
            from cards import _bulk_classify_candidate_ids, _supports_bulk_topic_classification  # type: ignore

        classifier = classifier if classifier is not None else resolve_topic_card_classifier()
        use_bulk = topic_predicate is None and _supports_bulk_topic_classification(collection, classifier)
        topic_predicate = topic_predicate or is_topic_card
        stages = ("learning", "review", "relearning")
        ratings = ("again", "hard", "good", "easy")
        result = [{
            "date": logical_date,
            "cards": 0,
            "failed_cards": 0,
            "stages": {stage: dict.fromkeys(ratings, 0) for stage in stages},
        } for logical_date, _start, _end in ranges]
        # Explicit timestamp boundaries avoid SQLite/host timezone differences.
        day_case = "CASE " + " ".join(
            f"WHEN id < ? THEN {index}" for index in range(len(ranges))
        ) + " END"
        day_ends = [end for _day, _start, end in ranges]
        sums = ", ".join(
            f"SUM(CASE WHEN type = {stage} AND ease = {ease} THEN 1 ELSE 0 END)"
            for stage in range(3) for ease in range(1, 5)
        )
        last_card_id = 0
        last_day_index = -1
        while True:
            if should_cancel is not None and should_cancel():
                return None
            rows = collection.db.all(
                f"SELECT cid, {day_case} AS day_index, {sums} FROM revlog "
                "WHERE id >= ? AND id < ? AND cid >= ? "
                "AND type IN (0, 1, 2) AND ease BETWEEN 1 AND 4 "
                "GROUP BY cid, day_index HAVING cid > ? OR day_index > ? "
                "ORDER BY cid, day_index LIMIT 500",
                *day_ends, ranges[0][1], ranges[-1][2], last_card_id,
                last_card_id, last_day_index,
            )
            if not rows:
                break
            item_ids = None
            if use_bulk:
                partition = _bulk_classify_candidate_ids(
                    sorted({row[0] for row in rows}), collection=collection, classifier=classifier,
                )
                if partition is not None:
                    item_ids = set(partition[1])
            for row in rows:
                if should_cancel is not None and should_cancel():
                    return None
                card_id = int(row[0])
                if item_ids is not None:
                    if card_id not in item_ids:
                        continue
                elif topic_predicate(
                    collection.get_card(card_id), classifier=classifier, col=collection,
                ):
                    continue
                day = result[int(row[1])]
                day["cards"] += 1
                day["failed_cards"] += int(any(row[index] for index in (2, 6, 10)))
                for stage_index, stage in enumerate(stages):
                    for rating_index, rating in enumerate(ratings):
                        day["stages"][stage][rating] += int(row[2 + stage_index * 4 + rating_index])
            last_card_id = int(rows[-1][0])
            last_day_index = int(rows[-1][1])
        return result
    except Exception:
        return None


def daily_tag_breakdown_from_collection(
    collection,
    day_end_time: str = "04:00",
    *,
    classifier=None,
    topic_predicate=None,
) -> dict | None:
    """Rebuild today's card-count pies from Anki's canonical review log.

    ``None`` means the collection could not be read. A successful day with no
    reviews returns an empty normalized breakdown.
    """
    if collection is None:
        return None
    try:
        if classifier is None or topic_predicate is None:
            try:
                from .topic_scheduler import (
                    is_topic_card,
                    resolve_topic_card_classifier,
                )
            except ImportError:
                from topic_scheduler import (  # type: ignore
                    is_topic_card,
                    resolve_topic_card_classifier,
                )
            if classifier is None:
                classifier = resolve_topic_card_classifier()
            if topic_predicate is None:
                topic_predicate = is_topic_card

        start_ms, end_ms = _logical_day_bounds_ms(day_end_time)
        review_rows = collection.db.all(
            "SELECT cid, COUNT(*) FROM revlog WHERE id >= ? AND id < ? "
            "GROUP BY cid ORDER BY MIN(id) LIMIT ?",
            start_ms,
            end_ms,
            _MAX_DAILY_REVIEW_ROWS,
        )
    except Exception:
        return None

    result = _empty_tag_breakdown()
    context_by_card: dict[int, tuple[str, str] | None] = {}
    for row in review_rows:
        try:
            raw_card_id, raw_review_count = row
            card_id = int(raw_card_id)
            review_count = int(raw_review_count)
            if review_count <= 0:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        if card_id not in context_by_card:
            try:
                card = collection.get_card(card_id)
                try:
                    note = card.note()
                except Exception:
                    note = collection.get_note(card.nid)
                kind = (
                    "topics"
                    if topic_predicate(
                        card,
                        classifier=classifier,
                        col=collection,
                    )
                    else "items"
                )
                context_by_card[card_id] = (
                    kind,
                    _daily_breakdown_tag(note, classifier),
                )
            except Exception:
                context_by_card[card_id] = None
        context = context_by_card[card_id]
        if context is None:
            continue
        kind, tag = context
        counts = result["counts"][kind]
        counts[tag] = counts.get(tag, 0) + review_count
    return result


def _is_valid_counts_block(d) -> bool:
    return (
        isinstance(d, dict)
        and isinstance(d.get("type"), dict)
        and isinstance(d.get("tags"), dict)
        and isinstance(d.get("mode"), dict)
    )


def _is_valid_time_block(d) -> bool:
    return (
        isinstance(d, dict)
        and isinstance(d.get("type"), dict)
        and isinstance(d.get("tags"), dict)
    )


def load_stats(addon_dir: str, profile: str) -> dict:
    with _stats_lock(addon_dir, profile):
        return _load_stats_unlocked(addon_dir, profile)


def _load_stats_unlocked(addon_dir: str, profile: str) -> dict:
    path = str(_get_stats_path(addon_dir, profile))
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return _normalize_stats(data)
        except Exception:
            # The file is canonical when healthy. A malformed/truncated file
            # falls through to the last committed SQLite mirror so one failed
            # filesystem write does not erase every visible statistic.
            pass

    return _load_stats_from_db(addon_dir, profile)


def _load_stats_from_db(addon_dir: str, profile: str) -> dict:
    """Load the backward-compatible aggregate mirror from SQLite."""

    try:
        rows = (
            get_connection(addon_dir, profile)
            .execute("SELECT scope, date, data FROM stats")
            .fetchall()
        )
    except Exception:
        return {}

    result: dict = {}
    for scope, date, data in rows:
        try:
            parsed = json.loads(data)
        except Exception:
            parsed = {}
        if scope == "daily":
            result["daily"] = {"date": date, "counts": parsed}
        elif scope == "time":
            result["time"] = parsed if isinstance(parsed, dict) else {}
        elif scope == "tag_breakdown":
            result["tag_breakdown"] = parsed if isinstance(parsed, dict) else {}
        else:
            result[scope] = parsed
    return _normalize_stats(result)


def save_stats(addon_dir: str, profile: str, stats: dict) -> None:
    with _stats_lock(addon_dir, profile):
        _save_stats_unlocked(addon_dir, profile, stats)


def _save_stats_unlocked(addon_dir: str, profile: str, stats: dict) -> None:
    stats = _normalize_stats(stats)
    _write_stats_file_atomic(addon_dir, profile, stats)
    _mirror_stats_to_db(addon_dir, profile, stats)


def _write_stats_file_atomic(addon_dir: str, profile: str, stats: dict) -> None:
    path = _get_stats_path(addon_dir, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                stats,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        except OSError:
            pass


def _json_payload(value: dict) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _mirror_stats_to_db(addon_dir: str, profile: str, stats: dict) -> bool:
    """Transactionally mirror aggregates and the current daily trend row."""
    try:
        conn = get_connection(addon_dir, profile)
        with conn:
            if "daily" in stats:
                daily = stats["daily"]
                conn.execute(
                    "INSERT INTO stats (scope, date, data) VALUES (?, ?, ?) "
                    "ON CONFLICT(scope) DO UPDATE SET "
                    "date = excluded.date, data = excluded.data",
                    (
                        "daily",
                        daily.get("date"),
                        _json_payload(daily.get("counts", _empty())),
                    ),
                )
            else:
                conn.execute("DELETE FROM stats WHERE scope = 'daily'")

            if "lifetime" in stats:
                conn.execute(
                    "INSERT INTO stats (scope, date, data) VALUES (?, ?, ?) "
                    "ON CONFLICT(scope) DO UPDATE SET "
                    "date = excluded.date, data = excluded.data",
                    ("lifetime", None, _json_payload(stats["lifetime"])),
                )
            else:
                conn.execute("DELETE FROM stats WHERE scope = 'lifetime'")

            if "time" in stats:
                conn.execute(
                    "INSERT INTO stats (scope, date, data) VALUES (?, ?, ?) "
                    "ON CONFLICT(scope) DO UPDATE SET "
                    "date = excluded.date, data = excluded.data",
                    ("time", None, _json_payload(stats["time"])),
                )
            else:
                conn.execute("DELETE FROM stats WHERE scope = 'time'")

            if "tag_breakdown" in stats:
                conn.execute(
                    "INSERT INTO stats (scope, date, data) VALUES (?, ?, ?) "
                    "ON CONFLICT(scope) DO UPDATE SET "
                    "date = excluded.date, data = excluded.data",
                    (
                        "tag_breakdown",
                        None,
                        _json_payload(stats["tag_breakdown"]),
                    ),
                )
            else:
                conn.execute("DELETE FROM stats WHERE scope = 'tag_breakdown'")

            daily = stats.get("daily")
            daily_date = (
                _normalize_logical_date(daily.get("date"))
                if isinstance(daily, dict)
                else None
            )
            if daily_date:
                time_stats = stats.get("time")
                daily_time = (
                    time_stats.get("daily")
                    if isinstance(time_stats, dict)
                    and isinstance(time_stats.get("daily"), dict)
                    else {}
                )
                seconds = (
                    _normalize_time_block(daily_time.get("seconds"))
                    if _normalize_logical_date(daily_time.get("date")) == daily_date
                    else _empty_time()
                )
                conn.execute(
                    "INSERT INTO stats_daily_history "
                    "(logical_date, counts_json, seconds_json, updated_at) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(logical_date) DO UPDATE SET "
                    "counts_json = excluded.counts_json, "
                    "seconds_json = excluded.seconds_json, "
                    "updated_at = excluded.updated_at",
                    (
                        daily_date,
                        _json_payload(_normalize_counts_block(daily.get("counts"))),
                        _json_payload(seconds),
                        int(time.time()),
                    ),
                )
        return True
    except Exception:
        # JSON remains canonical. Explicit rollback also repairs connections
        # left in a transaction by driver- or trigger-level failures.
        try:
            conn.rollback()
        except Exception:
            pass
        return False


def mutate_stats(addon_dir: str, profile: str, mutator) -> dict:
    """Atomically read, mutate and persist one profile's aggregate stats."""
    with _stats_lock(addon_dir, profile):
        current = _load_stats_unlocked(addon_dir, profile)
        updated = mutator(_normalize_stats(current))
        normalized = _normalize_stats(updated)
        _save_stats_unlocked(addon_dir, profile, normalized)
        return normalized


def _bounded_history_days(value) -> int:
    if isinstance(value, bool):
        raise ValueError("history days must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("history days must be an integer") from exc
    if parsed < 1 or parsed > _MAX_HISTORY_DAYS:
        raise ValueError(
            f"history days must be between 1 and {_MAX_HISTORY_DAYS}"
        )
    return parsed


def _positive_identifier(value, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a positive integer") from exc
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{label} must be a positive integer")
    if parsed <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return parsed


def record_reading_page(
    addon_dir: str,
    profile: str,
    document_type: str,
    card_id,
    page_number,
    *,
    day_end_time: str = "04:00",
) -> bool:
    """Persist one unique PDF/EPUB page for the current logical day.

    The primary key makes this idempotent across repeated progress messages,
    add-on reloads, and Anki restarts. ``True`` means a new daily page was
    inserted; ``False`` means that exact page was already recorded.
    """
    kind = str(document_type or "").strip().casefold()
    if kind not in _DOCUMENT_TYPES:
        raise ValueError("document_type must be 'pdf' or 'epub'")
    cid = _positive_identifier(card_id, "card_id")
    page = _positive_identifier(page_number, "page_number")
    logical_date = _normalize_logical_date(_effective_date(day_end_time))
    if logical_date is None:
        raise ValueError("logical date is invalid")

    with _stats_lock(addon_dir, profile):
        conn = get_connection(addon_dir, profile)
        try:
            with conn:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO reading_page_history "
                    "(logical_date, document_type, card_id, page_number, recorded_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (logical_date, kind, cid, page, int(time.time())),
                )
            return int(getattr(cursor, "rowcount", 0) or 0) == 1
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise


def record_video_watch(
    addon_dir: str,
    profile: str,
    card_id,
    seconds,
    *,
    day_end_time: str = "04:00",
    logical_date: str | None = None,
) -> None:
    """Add a bounded sample of observed playback to one profile's logical day."""
    cid = _positive_identifier(card_id, "card_id")
    if isinstance(seconds, bool):
        raise ValueError("watch seconds must be positive and at most 300")
    try:
        elapsed = float(seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("watch seconds must be positive and at most 300") from exc
    if not math.isfinite(elapsed) or not 0 < elapsed <= 300:
        raise ValueError("watch seconds must be positive and at most 300")
    resolved_date = _normalize_logical_date(
        logical_date if logical_date is not None else _effective_date(day_end_time)
    )
    if resolved_date is None:
        raise ValueError("logical date is invalid")

    with _stats_lock(addon_dir, profile):
        conn = get_connection(addon_dir, profile)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO video_watch_history "
                    "(logical_date, card_id, watched_seconds) VALUES (?, ?, ?) "
                    "ON CONFLICT(logical_date, card_id) DO UPDATE SET "
                    "watched_seconds = MIN(86400, watched_seconds + excluded.watched_seconds)",
                    (resolved_date, cid, elapsed),
                )
        except Exception:
            conn.rollback()
            raise


def load_media_activity(
    addon_dir: str,
    profile: str,
    *,
    days: int | None = None,
    day_end_time: str = "04:00",
) -> dict:
    """Count recorded document pages and observed video playback by period."""
    result = {
        "pdf_pages": 0,
        "epub_pages": 0,
        "pages": 0,
        "videos_watched": 0,
        "video_watch_seconds": 0.0,
    }
    params: tuple[str, ...] = ()
    where = ""
    if days is not None:
        day_count = _bounded_history_days(days)
        end = date.fromisoformat(_effective_date(day_end_time))
        start = (end - timedelta(days=day_count - 1)).isoformat()
        where = " WHERE logical_date BETWEEN ? AND ?"
        params = (start, end.isoformat())

    with _stats_lock(addon_dir, profile):
        conn = get_connection(addon_dir, profile)
        page_rows = conn.execute(
            "SELECT document_type, COUNT(*) FROM reading_page_history"
            + where + " GROUP BY document_type", params,
        ).fetchall()
        for kind, count in page_rows:
            if kind in {"pdf", "epub"}:
                result[f"{kind}_pages"] = max(0, int(count or 0))
        result["pages"] = result["pdf_pages"] + result["epub_pages"]
        videos, seconds = conn.execute(
            "SELECT COUNT(DISTINCT card_id), COALESCE(SUM(watched_seconds), 0) "
            "FROM video_watch_history" + where, params,
        ).fetchone()
        result["videos_watched"] = max(0, int(videos or 0))
        value = float(seconds or 0.0)
        result["video_watch_seconds"] = round(value, 1) if math.isfinite(value) and value > 0 else 0.0
    return result


def _history_json(value, *, counts: bool) -> dict:
    try:
        parsed = json.loads(str(value or "{}"))
    except Exception:
        parsed = {}
    if counts:
        return _normalize_counts_block(parsed)
    return _normalize_time_block(parsed)


def _empty_history_row(logical_date: str) -> dict:
    return {
        "date": logical_date,
        "counts": _empty(),
        "seconds": _empty_time(),
        "reading": {"pdf_pages": 0, "epub_pages": 0, "pages": 0},
    }


def load_daily_history(
    addon_dir: str,
    profile: str,
    *,
    days: int = 30,
    end_date: str | None = None,
    day_end_time: str = "04:00",
) -> list[dict]:
    """Return a chronological, zero-filled and bounded daily trend model."""
    day_count = _bounded_history_days(days)
    resolved_end = _normalize_logical_date(
        end_date if end_date is not None else _effective_date(day_end_time)
    )
    if resolved_end is None:
        raise ValueError("end_date must be an ISO calendar date")
    end = date.fromisoformat(resolved_end)
    start = end - timedelta(days=day_count - 1)
    start_text = start.isoformat()

    rows_by_date: dict[str, dict] = {}
    with _stats_lock(addon_dir, profile):
        try:
            conn = get_connection(addon_dir, profile)
            rows = conn.execute(
                "SELECT logical_date, counts_json, seconds_json "
                "FROM stats_daily_history "
                "WHERE logical_date BETWEEN ? AND ? ORDER BY logical_date",
                (start_text, resolved_end),
            ).fetchall()
            for logical_date, counts_json, seconds_json in rows:
                clean_date = _normalize_logical_date(logical_date)
                if clean_date is None:
                    continue
                item = _empty_history_row(clean_date)
                item["counts"] = _history_json(counts_json, counts=True)
                item["seconds"] = _history_json(seconds_json, counts=False)
                rows_by_date[clean_date] = item

            page_rows = conn.execute(
                "SELECT logical_date, document_type, COUNT(*) "
                "FROM reading_page_history "
                "WHERE logical_date BETWEEN ? AND ? "
                "GROUP BY logical_date, document_type "
                "ORDER BY logical_date, document_type",
                (start_text, resolved_end),
            ).fetchall()
            for logical_date, kind, raw_count in page_rows:
                clean_date = _normalize_logical_date(logical_date)
                if clean_date is None or kind not in _DOCUMENT_TYPES:
                    continue
                item = rows_by_date.setdefault(
                    clean_date, _empty_history_row(clean_date)
                )
                count = max(0, int(raw_count or 0))
                item["reading"][f"{kind}_pages"] = count
        except Exception:
            # A healthy canonical aggregate can still provide today's row if
            # a history query is unavailable during recovery.
            rows_by_date = {}

        current = _load_stats_unlocked(addon_dir, profile)
        daily = current.get("daily")
        if isinstance(daily, dict):
            logical_date = _normalize_logical_date(daily.get("date"))
            if logical_date and start_text <= logical_date <= resolved_end:
                item = rows_by_date.setdefault(
                    logical_date, _empty_history_row(logical_date)
                )
                item["counts"] = _normalize_counts_block(daily.get("counts"))

        time_stats = current.get("time")
        daily_time = (
            time_stats.get("daily")
            if isinstance(time_stats, dict)
            and isinstance(time_stats.get("daily"), dict)
            else None
        )
        if isinstance(daily_time, dict):
            logical_date = _normalize_logical_date(daily_time.get("date"))
            if logical_date and start_text <= logical_date <= resolved_end:
                item = rows_by_date.setdefault(
                    logical_date, _empty_history_row(logical_date)
                )
                item["seconds"] = _normalize_time_block(
                    daily_time.get("seconds")
                )

    result: list[dict] = []
    for offset in range(day_count):
        logical_date = (start + timedelta(days=offset)).isoformat()
        item = rows_by_date.get(logical_date, _empty_history_row(logical_date))
        reading = item["reading"]
        reading["pages"] = int(reading.get("pdf_pages", 0)) + int(
            reading.get("epub_pages", 0)
        )
        result.append(item)
    return result


def _history_row_has_activity(row: dict) -> bool:
    counts = _normalize_counts_block(row.get("counts"))
    seconds = _normalize_time_block(row.get("seconds"))
    reading = row.get("reading") if isinstance(row.get("reading"), dict) else {}
    return bool(
        any(sum(group.values()) > 0 for group in counts.values())
        or any(sum(group.values()) > 0 for group in seconds.values())
        or int(reading.get("pages", 0) or 0) > 0
    )


def _csv_number(value: float) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def daily_history_csv(history: list[dict] | tuple[dict, ...]) -> str:
    """Return a spreadsheet-safe, stable numeric export of daily history."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        (
            "date",
            "total_cards",
            "topics",
            "items",
            "other_cards",
            "pdf_pages",
            "epub_pages",
            "total_pages",
            "study_seconds",
            "priority_cards",
            "random_cards",
        )
    )
    for raw_row in list(history or []):
        row = raw_row if isinstance(raw_row, dict) else {}
        logical_date = _normalize_logical_date(row.get("date")) or ""
        counts = _normalize_counts_block(row.get("counts"))
        seconds = _normalize_time_block(row.get("seconds"))
        reading = row.get("reading") if isinstance(row.get("reading"), dict) else {}
        type_counts = counts["type"]
        total_cards = float(sum(type_counts.values()))
        topics = float(type_counts.get("topics", 0) or 0)
        items = float(type_counts.get("items", 0) or 0)
        other_cards = max(0.0, total_cards - topics - items)
        pdf_pages = _coerce_nonnegative_number(
            reading.get("pdf_pages", 0), integer=True
        ) or 0
        epub_pages = _coerce_nonnegative_number(
            reading.get("epub_pages", 0), integer=True
        ) or 0
        type_seconds = float(sum(seconds["type"].values()))
        tag_seconds = float(sum(seconds["tags"].values()))
        total_seconds = type_seconds if type_seconds > 0 else tag_seconds
        writer.writerow(
            (
                logical_date,
                _csv_number(total_cards),
                _csv_number(topics),
                _csv_number(items),
                _csv_number(other_cards),
                int(pdf_pages),
                int(epub_pages),
                int(pdf_pages) + int(epub_pages),
                _csv_number(total_seconds),
                int(counts["mode"].get("priority", 0) or 0),
                int(counts["mode"].get("random", 0) or 0),
            )
        )
    return output.getvalue()


def export_stats_data(
    addon_dir: str,
    profile: str,
    *,
    history_days: int = _MAX_HISTORY_DAYS,
    day_end_time: str = "04:00",
) -> dict:
    """Return normalized aggregates plus recorded (non-empty) daily history."""
    result = load_stats(addon_dir, profile)
    history = load_daily_history(
        addon_dir,
        profile,
        days=history_days,
        day_end_time=day_end_time,
    )
    recorded = [row for row in history if _history_row_has_activity(row)]
    if recorded:
        result["history"] = {"daily": recorded}
    return result


def _increment_map(block: dict, group: str, key: str | None, amount) -> None:
    if key is None:
        return
    target = block.setdefault(group, {})
    target[key] = target.get(key, 0) + amount


def record_tag_breakdown(
    addon_dir: str,
    profile: str,
    *,
    study_kind: str,
    tag: str | None,
    include_count: bool,
    seconds: float,
    day_end_time: str = "04:00",
) -> dict:
    """Record one Topic/Item contribution without changing legacy aggregates.

    This joint attribution powers pie charts where each slice must belong to
    exactly one semantic card kind and one tag. Existing count/time blocks stay
    unchanged so session-owned statistics cannot be double-counted.
    """
    kind = str(study_kind or "").strip().casefold()
    if kind not in _TAG_BREAKDOWN_KINDS:
        raise ValueError("study_kind must be 'topics' or 'items'")
    clean_tag = _clean_stat_key(tag if tag is not None else UNTAGGED_STATS_TAG)
    if clean_tag is None:
        clean_tag = UNTAGGED_STATS_TAG
    try:
        clean_seconds = float(seconds or 0.0)
    except Exception:
        clean_seconds = 0.0
    if not math.isfinite(clean_seconds):
        clean_seconds = 0.0
    clean_seconds = max(0.0, min(_MAX_STAT_VALUE, clean_seconds))
    logical_date = _effective_date(day_end_time)

    def apply_delta(stats: dict) -> dict:
        raw_value = stats.get("tag_breakdown")
        raw: dict = raw_value if isinstance(raw_value, dict) else {}
        daily_value = raw.get("daily")
        daily_raw: dict = daily_value if isinstance(daily_value, dict) else {}
        if daily_raw.get("date") == logical_date:
            daily = _normalize_tag_breakdown_block(daily_raw)
        else:
            daily = _empty_tag_breakdown()
        lifetime = _normalize_tag_breakdown_block(raw.get("lifetime"))

        for block in (daily, lifetime):
            if include_count:
                counts = block["counts"][kind]
                counts[clean_tag] = counts.get(clean_tag, 0) + 1
            if clean_seconds > 0:
                time_values = block["seconds"][kind]
                time_values[clean_tag] = (
                    time_values.get(clean_tag, 0.0) + clean_seconds
                )

        stats["tag_breakdown"] = {
            "daily": {"date": logical_date, **daily},
            "lifetime": lifetime,
        }
        return stats

    return mutate_stats(addon_dir, profile, apply_delta)


def _record_persistent_delta(
    addon_dir: str,
    profile: str,
    *,
    day_end_time: str,
    result,
    include_count: bool,
    seconds: float,
) -> dict:
    logical_date = _effective_date(day_end_time)

    def apply_delta(stats: dict) -> dict:
        daily_raw = stats.get("daily") if isinstance(stats.get("daily"), dict) else {}
        if daily_raw.get("date") == logical_date:
            daily = _normalize_counts_block(daily_raw.get("counts"))
        else:
            daily = _empty()
        lifetime = _normalize_counts_block(stats.get("lifetime"))

        time_raw = stats.get("time") if isinstance(stats.get("time"), dict) else {}
        daily_time_raw = time_raw.get("daily") if isinstance(time_raw.get("daily"), dict) else {}
        if daily_time_raw.get("date") == logical_date:
            daily_time = _normalize_time_block(daily_time_raw.get("seconds"))
        else:
            daily_time = _empty_time()
        lifetime_time = _normalize_time_block(time_raw.get("lifetime"))

        if include_count:
            for block in (daily, lifetime):
                _increment_map(block, "type", result.card_type, 1)
                _increment_map(block, "mode", result.mode, 1)
                _increment_map(block, "tags", result.tag, 1)
        if seconds > 0:
            for block in (daily_time, lifetime_time):
                _increment_map(block, "type", result.card_type, seconds)
                _increment_map(block, "tags", result.tag, seconds)

        stats["daily"] = {"date": logical_date, "counts": daily}
        stats["lifetime"] = lifetime
        stats["time"] = {
            "daily": {"date": logical_date, "seconds": daily_time},
            "lifetime": lifetime_time,
        }
        return stats

    return mutate_stats(addon_dir, profile, apply_delta)


def _delete_history_dates(addon_dir: str, profile: str, dates: set[str]) -> None:
    clean_dates = sorted(
        date_value
        for date_value in (_normalize_logical_date(value) for value in dates)
        if date_value is not None
    )
    if not clean_dates:
        return
    placeholders = ",".join("?" for _ in clean_dates)
    try:
        conn = get_connection(addon_dir, profile)
        with conn:
            conn.execute(
                f"DELETE FROM stats_daily_history WHERE logical_date IN ({placeholders})",
                clean_dates,
            )
            conn.execute(
                f"DELETE FROM reading_page_history WHERE logical_date IN ({placeholders})",
                clean_dates,
            )
            conn.execute(
                f"DELETE FROM video_watch_history WHERE logical_date IN ({placeholders})",
                clean_dates,
            )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass


def delete_daily_stats(
    addon_dir: str,
    profile: str,
    day_end_time: str = "04:00",
) -> None:
    """Remove the current logical day's aggregates, trend row, and pages."""
    def remove_daily(stats: dict) -> dict:
        stats.pop("daily", None)
        if isinstance(stats.get("time"), dict):
            stats["time"].pop("daily", None)
            if not stats["time"]:
                stats.pop("time", None)
        if isinstance(stats.get("tag_breakdown"), dict):
            stats["tag_breakdown"].pop("daily", None)
            if not stats["tag_breakdown"]:
                stats.pop("tag_breakdown", None)
        return stats

    with _stats_lock(addon_dir, profile):
        current = _load_stats_unlocked(addon_dir, profile)
        dates = {_effective_date(day_end_time)}
        daily = current.get("daily")
        if isinstance(daily, dict):
            dates.add(str(daily.get("date") or ""))
        time_stats = current.get("time")
        if isinstance(time_stats, dict) and isinstance(time_stats.get("daily"), dict):
            dates.add(str(time_stats["daily"].get("date") or ""))
        updated = _normalize_stats(remove_daily(current))
        _save_stats_unlocked(addon_dir, profile, updated)
        _delete_history_dates(addon_dir, profile, dates)


def delete_lifetime_stats(addon_dir: str, profile: str) -> None:
    """Remove lifetime statistics."""
    def remove_lifetime(stats: dict) -> dict:
        stats.pop("lifetime", None)
        if isinstance(stats.get("time"), dict):
            stats["time"].pop("lifetime", None)
            if not stats["time"]:
                stats.pop("time", None)
        if isinstance(stats.get("tag_breakdown"), dict):
            stats["tag_breakdown"].pop("lifetime", None)
            if not stats["tag_breakdown"]:
                stats.pop("tag_breakdown", None)
        return stats

    mutate_stats(addon_dir, profile, remove_lifetime)


def delete_all_stats(addon_dir: str, profile: str) -> None:
    """Delete all statistics data."""
    with _stats_lock(addon_dir, profile):
        path = str(_get_stats_path(addon_dir, profile))
        if os.path.exists(path):
            os.remove(path)

        try:
            conn = get_connection(addon_dir, profile)
            with conn:
                conn.execute("DELETE FROM stats")
                conn.execute("DELETE FROM stats_daily_history")
                conn.execute("DELETE FROM reading_page_history")
                conn.execute("DELETE FROM video_watch_history")
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass


class StatsManager:
    def __init__(self, addon_dir: str, profile: str, day_end_time: str = "04:00"):
        self._addon_dir = addon_dir
        self._profile = profile
        self._day_end_time = day_end_time
        self.session = _empty()
        self.session_time = _empty_time()

        raw = load_stats(addon_dir, profile)

        self.lifetime = _normalize_counts_block(raw.get("lifetime"))

        daily_raw = raw.get("daily", {})
        if (
            isinstance(daily_raw, dict)
            and daily_raw.get("date") == _effective_date(self._day_end_time)
            and _is_valid_counts_block(daily_raw.get("counts"))
        ):
            self.daily = _normalize_counts_block(daily_raw["counts"])
        else:
            self.daily = _empty()

        raw_time = raw.get("time") if isinstance(raw.get("time"), dict) else {}

        daily_time_raw = raw_time.get("daily") if isinstance(raw_time, dict) else {}
        if (
            isinstance(daily_time_raw, dict)
            and daily_time_raw.get("date") == _effective_date(self._day_end_time)
            and _is_valid_time_block(daily_time_raw.get("seconds"))
        ):
            self.daily_time = _normalize_time_block(daily_time_raw["seconds"])
        else:
            self.daily_time = _empty_time()

        lt_time = raw_time.get("lifetime") if isinstance(raw_time, dict) else None
        self.lifetime_time = _normalize_time_block(lt_time)

    def counts_for(self, scope: str) -> dict:
        """Return a LIVE reference to the counts dict for *scope*.

        IMPORTANT — the caller must mutate the returned dict in-place to drive
        soft_pick debt.  Do NOT store a copy; debt tracking depends on this
        reference pointing to the same object that record() reads from.
        """
        if scope == "session":
            return self.session
        if scope == "daily":
            return self.daily
        if scope == "lifetime":
            return self.lifetime
        raise ValueError(
            f"Unknown scope: {scope!r}. Must be 'session', 'daily', or 'lifetime'."
        )

    def record(self, result, scheduled_scope: str) -> None:
        if result.card is None:
            return

        # Session counts are the scheduler's live selection/debt state and are
        # intentionally not incremented here. Persistent counters are updated
        # from the latest shared state under the profile stats lock.

        seconds = max(0.0, float(getattr(result, "review_seconds", 0.0) or 0.0))
        if seconds > 0:
            self._record_session_time(result, seconds)

        persisted = _record_persistent_delta(
            self._addon_dir,
            self._profile,
            day_end_time=self._day_end_time,
            result=result,
            include_count=True,
            seconds=seconds,
        )
        self._load_persisted_state(persisted)

    def _record_session_time(self, result, seconds: float) -> None:
        self.session_time["type"][result.card_type] = (
            self.session_time["type"].get(result.card_type, 0.0) + seconds
        )
        if result.tag is not None:
            self.session_time["tags"][result.tag] = (
                self.session_time["tags"].get(result.tag, 0.0) + seconds
            )

    def _load_persisted_state(self, raw: dict) -> None:
        daily_raw = raw.get("daily") if isinstance(raw.get("daily"), dict) else {}
        self.daily = _normalize_counts_block(daily_raw.get("counts"))
        self.lifetime = _normalize_counts_block(raw.get("lifetime"))
        time_raw = raw.get("time") if isinstance(raw.get("time"), dict) else {}
        daily_time_raw = time_raw.get("daily") if isinstance(time_raw.get("daily"), dict) else {}
        self.daily_time = _normalize_time_block(daily_time_raw.get("seconds"))
        self.lifetime_time = _normalize_time_block(time_raw.get("lifetime"))

    def record_time_only(self, result, seconds: float) -> None:
        """Record time without incrementing card/mode/tag counts."""
        if result.card is None:
            return
        seconds = max(0.0, float(seconds or 0.0))
        if seconds <= 0:
            return
        self._record_session_time(result, seconds)
        persisted = _record_persistent_delta(
            self._addon_dir,
            self._profile,
            day_end_time=self._day_end_time,
            result=result,
            include_count=False,
            seconds=seconds,
        )
        self._load_persisted_state(persisted)

    def _save(self) -> None:
        stats = {
            "daily": {
                "date": _effective_date(self._day_end_time),
                "counts": self.daily,
            },
            "lifetime": self.lifetime,
            "time": {
                "daily": {
                    "date": _effective_date(self._day_end_time),
                    "seconds": self.daily_time,
                },
                "lifetime": self.lifetime_time,
            },
        }
        save_stats(self._addon_dir, self._profile, stats)
