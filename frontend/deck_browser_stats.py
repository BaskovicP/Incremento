"""Legacy deck-browser statistics markup and cleanup helpers."""

from __future__ import annotations

from html import escape
import math
import re

try:
    from .learning_stats import build_daily_learning_html, DeckBrowserLearningStats
except ImportError:
    from frontend.learning_stats import build_daily_learning_html, DeckBrowserLearningStats

try:
    from ..backend.i18n import format_number, t
    from ..backend.statistics import (
        UNTAGGED_STATS_TAG,
        _effective_date,
        _normalize_tag_breakdown_block,
        daily_tag_breakdown_from_collection,
        load_stats,
    )
except ImportError:
    from backend.i18n import format_number, t
    from backend.statistics import (
        UNTAGGED_STATS_TAG,
        _effective_date,
        _normalize_tag_breakdown_block,
        daily_tag_breakdown_from_collection,
        load_stats,
    )


_CHART_START = "<!-- incremento-daily-tag-charts:start -->"
_CHART_END = "<!-- incremento-daily-tag-charts:end -->"
_LEARNING_START = "<!-- incremento-daily-learning:start -->"
_LEARNING_END = "<!-- incremento-daily-learning:end -->"
_LEARNING_BLOCK_RE = re.compile(re.escape(_LEARNING_START) + r".*?" + re.escape(_LEARNING_END), flags=re.DOTALL)
_CHART_BLOCK_RE = re.compile(
    re.escape(_CHART_START) + r".*?" + re.escape(_CHART_END),
    flags=re.DOTALL,
)
_SESSION_TIMER_SUFFIX_RE = re.compile(
    r"\s*<br\s*/?>\s*"
    r"(?:\d+(?:\.\d+)?\s+(?:seconds?|minutes?)|\d{1,3}:\d{2}:\d{2})\s+in\s+session,\s*"
    r"(?:\d+(?:\.\d+)?\s+seconds?|\d{1,3}:\d{2}:\d{2})\s+spent\s+reviewing\s*"
    r"\(\d+(?:\.\d+)?%\)\s*$",
    flags=re.IGNORECASE,
)
_COLORS = (
    "#4e79a7",
    "#f28e2b",
    "#59a14f",
    "#e15759",
    "#b07aa1",
    "#76b7b2",
    "#edc948",
    "#9c755f",
)


def strip_session_timer_line(value: str) -> str:
    """Remove only the exact summary suffix produced by the Session Timer add-on."""
    return _SESSION_TIMER_SUFFIX_RE.sub("", str(value or ""))


def _pie_items(
    breakdown: dict,
    kind: str,
    *,
    maximum_items: int = 8,
) -> list[tuple[str, float, float]]:
    clean = _normalize_tag_breakdown_block(breakdown)
    counts = clean["counts"].get(kind, {})
    seconds = clean["seconds"].get(kind, {})
    items: list[tuple[str, float, float]] = []
    for key in counts:
        duration = float(seconds.get(key, 0) or 0)
        count = float(counts.get(key, 0) or 0)
        if count <= 0:
            continue
        label = t("stats_untagged") if key == UNTAGGED_STATS_TAG else str(key)
        items.append((label, duration, count))
    items.sort(key=lambda item: (-item[2], -item[1], item[0].casefold()))

    limit = max(2, int(maximum_items or 2))
    if len(items) <= limit:
        return items
    visible = items[: limit - 1]
    remainder = items[limit - 1 :]
    visible.append(
        (
            t("stats_other_tags"),
            sum(item[1] for item in remainder),
            sum(item[2] for item in remainder),
        )
    )
    return visible


def _gradient(items: list[tuple[str, float, float]]) -> str:
    if not items:
        return "conic-gradient(rgba(128,128,128,.18) 0 100%)"
    weights = [max(0.0, item[2]) for item in items]
    total = sum(weights)
    if total <= 0:
        return "conic-gradient(rgba(128,128,128,.18) 0 100%)"

    segments: list[str] = []
    start = 0.0
    for index, weight in enumerate(weights):
        end = 100.0 if index == len(weights) - 1 else start + (weight / total * 100.0)
        if end > start:
            color = _COLORS[index % len(_COLORS)]
            segments.append(f"{color} {start:.3f}% {end:.3f}%")
        start = end
    return "conic-gradient(" + ", ".join(segments) + ")"


def _chart_html(title: str, items: list[tuple[str, float, float]]) -> str:
    safe_title = escape(title, quote=True)
    total = sum(count for _label, _seconds, count in items)
    total_value = int(total) if float(total).is_integer() else total
    total_text = t("stats_pie_total", cards=format_number(total_value))
    legend_rows: list[str] = []
    percentage_labels: list[str] = []
    descriptions = [title, total_text]
    start = 0.0
    for index, (label, duration, count) in enumerate(items):
        color = _COLORS[index % len(_COLORS)]
        count_value = int(count) if float(count).is_integer() else count
        value = t(
            "stats_pie_legend_value",
            cards=format_number(count_value),
        )
        legend_rows.append(
            '<li><span class="incremento-pie-swatch" '
            f'style="background:{color}"></span>'
            f'<span class="incremento-pie-tag">{escape(label, quote=True)}</span>'
            f'<span class="incremento-pie-value">{escape(value, quote=True)}</span></li>'
        )
        percentage = count / total * 100 if total > 0 else 0
        rounded_percentage = round(percentage, 1)
        percentage_value = (
            int(rounded_percentage) if rounded_percentage.is_integer() else rounded_percentage
        )
        percentage_text = format_number(percentage_value) + "%"
        descriptions.append(f"{label}: {value} ({percentage_text})")
        if percentage > 0:
            angle = start + percentage * 1.8
            radius = 0 if len(items) == 1 else 34
            x = 50 + radius * math.sin(math.radians(angle))
            y = 50 - radius * math.cos(math.radians(angle))
            # Narrow slices fit a radial label better than a horizontal one.
            rotation = ((angle % 180) - 90) if percentage < 10 else 0
            percentage_labels.append(
                '<span class="incremento-pie-percentage" aria-hidden="true" '
                f'style="left:{x:.3f}%;top:{y:.3f}%;'
                f'transform:translate(-50%,-50%) rotate({rotation:.3f}deg)">'
                + escape(percentage_text, quote=True)
                + "</span>"
            )
        start += percentage * 3.6
    if not legend_rows:
        legend_rows.append(
            '<li class="incremento-pie-empty">'
            + escape(t("stats_no_scope_statistics"), quote=True)
            + "</li>"
        )
    gradient = _gradient(items)
    return (
        '<section class="incremento-daily-tag-chart" aria-label="'
        + safe_title
        + '"><h3>'
        + safe_title
        + '</h3><p class="incremento-pie-total">'
        + escape(total_text, quote=True)
        + '</p><div class="incremento-pie-body">'
        + '<div class="incremento-pie" role="img" aria-label="'
        + escape(". ".join(descriptions), quote=True)
        + '" style="background:'
        + gradient
        + '">'
        + "".join(percentage_labels)
        + '</div><ul class="incremento-pie-legend">'
        + "".join(legend_rows)
        + "</ul></div></section>"
    )


def build_daily_tag_charts_html(breakdown: dict) -> str:
    """Return a self-contained, theme-friendly two-chart HTML fragment."""
    clean = _normalize_tag_breakdown_block(breakdown)
    topics = _pie_items(clean, "topics")
    items = _pie_items(clean, "items")
    css = """
<style>
.incremento-daily-tag-charts{max-width:900px;margin:24px auto 4px;padding:18px 20px;border:1px solid rgba(128,128,128,.28);border-radius:12px;text-align:left;color:inherit}
.incremento-daily-tag-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:26px}
.incremento-daily-tag-chart h3{margin:0 0 4px;text-align:center;font-size:1.05em}
.incremento-pie-total{margin:0 0 12px;text-align:center;font-size:.88em;font-variant-numeric:tabular-nums}
.incremento-pie-body{display:flex;align-items:center;justify-content:center;gap:16px;min-width:0}
.incremento-pie{position:relative;width:132px;height:132px;min-width:132px;border-radius:50%;box-shadow:inset 0 0 0 1px rgba(128,128,128,.22)}
.incremento-pie-percentage{position:absolute;color:white;font-size:10px;font-weight:700;line-height:1;white-space:nowrap;text-shadow:0 1px 2px #222,0 0 2px #222;pointer-events:none;font-variant-numeric:tabular-nums}
.incremento-pie-legend{min-width:0;margin:0;padding:0;list-style:none;font-size:.88em}
.incremento-pie-legend li{display:grid;grid-template-columns:10px minmax(60px,1fr) auto;align-items:center;gap:7px;margin:5px 0}
.incremento-pie-swatch{width:10px;height:10px;border-radius:2px}
.incremento-pie-tag{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.incremento-pie-value{color:rgba(128,128,128,.95);white-space:nowrap;font-variant-numeric:tabular-nums}
.incremento-pie-empty{display:block!important;color:rgba(128,128,128,.95);max-width:190px;text-align:center}
.incremento-daily-tag-hint{margin:14px 0 0;text-align:center;color:rgba(128,128,128,.95);font-size:.82em}
@media(max-width:700px){.incremento-daily-tag-grid{grid-template-columns:1fr}.incremento-pie-body{flex-wrap:wrap}.incremento-daily-tag-charts{margin-left:8px;margin-right:8px}}
</style>
"""
    return (
        _CHART_START
        + css
        + '<div class="incremento-daily-tag-charts">'
        + '<div class="incremento-daily-tag-grid">'
        + _chart_html(t("stats_topic_tag_time"), topics)
        + _chart_html(t("stats_item_tag_time"), items)
        + "</div><p class=\"incremento-daily-tag-hint\">"
        + escape(t("stats_topic_item_pie_hint"), quote=True)
        + "</p></div>"
        + _CHART_END
    )


def render_deck_browser_daily_stats(
    content,
    *,
    addon_dir: str,
    profile: str,
    day_end_time: str = "04:00",
    collection=None,
    show_charts: bool = True,
    show_learning_results: bool = False,
    learning_outcomes: dict | None = None,
    learning_loading: bool = False,
) -> None:
    """Replace stale Incremento markup and optionally append daily panels."""
    current = _CHART_BLOCK_RE.sub("", str(getattr(content, "stats", "") or ""))
    current = _LEARNING_BLOCK_RE.sub("", current)
    current = strip_session_timer_line(current)
    if show_learning_results:
        current += _LEARNING_START + build_daily_learning_html(
            learning_outcomes, loading=learning_loading,
        ) + _LEARNING_END
    if not show_charts:
        content.stats = current
        return
    breakdown = _normalize_tag_breakdown_block({})
    try:
        raw = load_stats(addon_dir, profile)
        tag_breakdown = raw.get("tag_breakdown", {})
        daily = tag_breakdown.get("daily", {}) if isinstance(tag_breakdown, dict) else {}
        if (
            isinstance(daily, dict)
            and daily.get("date") == _effective_date(day_end_time)
        ):
            breakdown = _normalize_tag_breakdown_block(daily)
    except Exception:
        pass
    live_breakdown = daily_tag_breakdown_from_collection(collection, day_end_time)
    if live_breakdown is not None:
        breakdown = _normalize_tag_breakdown_block(live_breakdown)
    content.stats = current + build_daily_tag_charts_html(breakdown)
