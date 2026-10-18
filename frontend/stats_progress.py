"""Bounded presentation model over Incremento's canonical daily history."""

from __future__ import annotations

import math
from datetime import date, timedelta
from itertools import accumulate

try:
    from ..backend.statistics import _normalize_counts_block, _normalize_time_block
except ImportError:
    from backend.statistics import _normalize_counts_block, _normalize_time_block


METRICS = ("pages", "cards", "minutes", "pdf_pages", "epub_pages")


def _positive(value) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return numeric if math.isfinite(numeric) and numeric > 0 else 0.0


def _day_values(row: dict) -> dict:
    counts = _normalize_counts_block(row.get("counts"))
    seconds = _normalize_time_block(row.get("seconds"))
    reading = row.get("reading")
    reading = reading if isinstance(reading, dict) else {}
    pdf, epub = (_positive(reading.get(key)) for key in ("pdf_pages", "epub_pages"))
    duration = sum(seconds["type"].values()) or sum(seconds["tags"].values())
    return {"pages": pdf + epub, "cards": sum(counts["type"].values()),
            "minutes": duration / 60, "pdf_pages": pdf, "epub_pages": epub}


def progress_model(history: list[dict], *, end_date: str, days: int) -> dict:
    """Keep calendar gaps, use equal comparison windows, and group long charts.

    This is a read model only. Pages retain the source's unique-per-document/day
    semantics; cumulative pages are the sum of those observations, not a count
    of distinct pages across all time. No card or reading activity is inferred
    from elapsed time.
    """
    end = date.fromisoformat(end_date)
    days = max(1, min(365, int(days)))
    first = end - timedelta(days=729)
    by_date = {}
    for row in list(history or [])[-730:]:
        if not isinstance(row, dict):
            continue
        try:
            day = date.fromisoformat(str(row.get("date", "")))
        except ValueError:
            continue
        if first <= day <= end:
            by_date[day.isoformat()] = _day_values(row)

    def window(length, last):
        return [
            {"date": key, **by_date.get(key, dict.fromkeys(METRICS, 0.0))}
            for offset in range(length)
            for key in [(last - timedelta(days=length - offset - 1)).isoformat()]
        ]

    daily = window(days, end)
    previous = window(days, end - timedelta(days=days))
    totals = {metric: sum(row[metric] for row in daily) for metric in METRICS}
    comparisons = {}
    for metric in ("pages", "cards", "minutes"):
        before = sum(row[metric] for row in previous)
        delta = totals[metric] - before
        comparisons[metric] = {"previous": before, "delta": delta,
                               "percent": delta * 100 / before if before > 0 else None}

    bucket_size = 7 if days > 31 else 1
    buckets = []
    for offset in range(0, days, bucket_size):
        rows = daily[offset:offset + bucket_size]
        buckets.append({"start": rows[0]["date"], "end": rows[-1]["date"], "days": len(rows),
                        **{metric: sum(row[metric] for row in rows) for metric in METRICS}})

    streak = 0
    cursor = end
    if by_date.get(cursor.isoformat(), {}).get("pages", 0) <= 0:
        cursor -= timedelta(days=1)
    while cursor >= first and by_date.get(cursor.isoformat(), {}).get("pages", 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)

    return {"daily": daily, "buckets": buckets, "totals": totals, "comparison": comparisons,
            "reading_days": sum(row["pages"] > 0 for row in daily), "reading_streak": streak,
            "active_days": sum(any(row[metric] > 0 for metric in ("pages", "cards", "minutes")) for row in daily),
            "cumulative": {metric: list(accumulate(row[metric] for row in buckets))
                           for metric in ("pages", "cards", "minutes")}}
