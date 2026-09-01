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
_DOCUMENT_TYPES = frozenset({"pdf", "epub"})
_STATISTICS_GOAL_KEYS = ("cards", "pages", "minutes")
_MAX_DAILY_GOAL = 1_000_000.0


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

        return {
            "daily": {"date": logical_date, "counts": daily},
            "lifetime": lifetime,
            "time": {
                "daily": {"date": logical_date, "seconds": daily_time},
                "lifetime": lifetime_time,
            },
        }

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
