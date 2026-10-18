"""Shared presentation and background loading of today's Anki memory grades."""

from __future__ import annotations

from html import escape

from aqt import mw

try:
    from ..backend.i18n import format_date, format_number, t
    from ..backend.paths import get_active_profile as _active_profile
    from ..backend.statistics import (
        _coerce_nonnegative_number,
        _effective_date,
        _normalize_number_map,
        daily_learning_outcomes_from_collection,
        learning_outcome_history_from_collection,
        learning_card_states_from_collection,
    )
    from ..backend.document_statistics import document_progress_from_collection
    from ..backend.topic_scheduler import resolve_topic_card_classifier
except ImportError:
    from backend.i18n import format_date, format_number, t
    from backend.paths import get_active_profile as _active_profile
    from backend.statistics import (
        _coerce_nonnegative_number,
        _effective_date,
        _normalize_number_map,
        daily_learning_outcomes_from_collection,
        learning_outcome_history_from_collection,
        learning_card_states_from_collection,
    )
    from backend.document_statistics import document_progress_from_collection
    from backend.topic_scheduler import resolve_topic_card_classifier


def learning_outcome_display(outcomes: dict | None) -> dict | None:
    if not isinstance(outcomes, dict):
        return None
    stages = outcomes.get("stages")
    stages = stages if isinstance(stages, dict) else {}
    totals = dict.fromkeys(("again", "hard", "good", "easy"), 0)
    rows = []

    def recall_rate(counts):
        attempts = sum(counts.values())
        if not attempts:
            return "—"
        percentage = round(100 * (attempts - counts["again"]) / attempts, 1)
        return format_number(int(percentage) if percentage.is_integer() else percentage) + "%"

    for stage, label in (
        ("learning", t("stats_learning_stage")),
        ("review", t("stats_review_stage")),
        ("relearning", t("stats_relearning_stage")),
    ):
        normalized = _normalize_number_map(stages.get(stage), integer=True)
        counts = {rating: normalized.get(rating, 0) for rating in totals}
        for rating in totals:
            totals[rating] += counts[rating]
        rows.append([
            label, format_number(sum(counts.values())),
            *(format_number(counts[rating]) for rating in totals),
            recall_rate(counts),
        ])
    attempts = sum(totals.values())
    cards = _coerce_nonnegative_number(outcomes.get("cards", 0), integer=True) or 0
    failed_cards = _coerce_nonnegative_number(outcomes.get("failed_cards", 0), integer=True) or 0
    return {
        "metrics": [
            (t("stats_answer_attempts"), format_number(attempts)),
            (t("stats_again_fail"), format_number(totals["again"])),
            (t("stats_recalled"), format_number(attempts - totals["again"])),
            (t("stats_recall_rate"), recall_rate(totals)),
        ],
        "headers": [
            t("stats_answer_stage"), t("stats_answer_attempts"),
            t("stats_again_fail"), t("stats_rating_hard"), t("stats_rating_good"),
            t("stats_rating_easy"), t("stats_recall_rate"),
        ],
        "rows": rows,
        "hint": "\n".join([
            t("stats_learning_card_totals", cards=format_number(cards), failed_cards=format_number(failed_cards)),
            t("stats_learning_results_hint"),
            t("stats_learning_results_exclusions"),
        ]),
    }


def _recall_percentage(value: float | None) -> str:
    if value is None:
        return "—"
    rounded = round(value, 1)
    return format_number(int(rounded) if rounded.is_integer() else rounded) + "%"


def learning_history_display(history: list[dict] | None, days: int) -> dict | None:
    """Use answer-weighted period rates and preserve missing daily rates."""
    if not isinstance(history, list):
        return None
    count = 7 if days == 7 else 30

    def values(row):
        stages = row.get("stages") if isinstance(row, dict) else None
        stages = stages if isinstance(stages, dict) else {}
        totals = dict.fromkeys(("again", "hard", "good", "easy"), 0)
        for stage in ("learning", "review", "relearning"):
            clean = _normalize_number_map(stages.get(stage), integer=True)
            for rating in totals:
                totals[rating] += clean.get(rating, 0)
        attempts = sum(totals.values())
        return attempts, totals["again"], attempts - totals["again"]

    def period_rate(rows):
        totals = [values(row) for row in rows]
        attempts = sum(row[0] for row in totals)
        recalled = sum(row[2] for row in totals)
        return 100 * recalled / attempts if attempts else None

    selected = history[-count:]
    previous = history[-count * 2:-count]
    day_values = [values(row) for row in selected]
    attempts = sum(row[0] for row in day_values)
    failed = sum(row[1] for row in day_values)
    recalled = attempts - failed
    rate, previous_rate = period_rate(selected), period_rate(previous)
    if rate is None:
        comparison = t("stats_learning_no_answers")
    elif previous_rate is None:
        comparison = t("stats_recall_no_previous", days=count)
    else:
        change = round(rate - previous_rate, 1)
        key = "stats_recall_comparison_up" if change > 0 else "stats_recall_comparison_down" if change < 0 else "stats_recall_comparison_same"
        comparison = t(
            key, change=format_number(abs(change)), current=_recall_percentage(rate),
            previous=_recall_percentage(previous_rate), days=count,
        )
    labels = [format_date(row.get("date", "")) for row in selected]
    rates = [100 * recalled / total if total else None for total, _failed, recalled in day_values]
    details = [t(
        "stats_learning_day_summary", date=label, attempts=format_number(total),
        failed=format_number(failures), recalled=format_number(successes), rate=_recall_percentage(daily_rate),
    ) for label, (total, failures, successes), daily_rate in zip(labels, day_values, rates)]
    return {
        "metrics": [
            (t("stats_answer_attempts"), format_number(attempts)),
            (t("stats_again_fail"), format_number(failed)),
            (t("stats_recalled"), format_number(recalled)),
            (t("stats_recall_rate"), _recall_percentage(rate)),
        ],
        "labels": labels,
        "series": [(t("stats_recalled"), [row[2] for row in day_values]), (t("stats_again_fail"), [row[1] for row in day_values])],
        "rates": rates,
        "comparison": comparison,
        "daily_details": details,
    }


def build_daily_learning_html(outcomes: dict | None, *, loading: bool = False) -> str:
    title = escape(t("stats_learning_results_title"), quote=True)
    display = learning_outcome_display(outcomes)
    body = ""
    if display is None:
        body = "<p>" + escape(t(
            "stats_learning_results_loading" if loading else "stats_learning_results_unavailable",
        ), quote=True) + "</p>"
    else:
        body = '<div class="incremento-learning-metrics">' + "".join(
            '<div><strong>' + escape(value, quote=True) + '</strong><span>'
            + escape(label, quote=True) + '</span></div>'
            for label, value in display["metrics"]
        ) + '</div><div class="incremento-learning-table"><table><thead><tr>'
        body += "".join('<th scope="col">' + escape(label, quote=True) + '</th>' for label in display["headers"])
        body += '</tr></thead><tbody>'
        for row in display["rows"]:
            body += '<tr><th scope="row">' + escape(row[0], quote=True) + '</th>'
            body += "".join('<td>' + escape(value, quote=True) + '</td>' for value in row[1:]) + '</tr>'
        body += '</tbody></table></div><p class="incremento-learning-hint">'
        body += '<br>'.join(escape(line, quote=True) for line in display["hint"].splitlines()) + '</p>'
    css = """<style>
.incremento-learning-results{max-width:900px;margin:20px auto;padding:16px 20px;border:1px solid rgba(128,128,128,.28);border-radius:12px;text-align:left;color:inherit}
.incremento-learning-results h3{margin:0 0 14px;font-size:1.05em}
.incremento-learning-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px;text-align:center}
.incremento-learning-metrics strong{display:block;font-size:1.5em;font-variant-numeric:tabular-nums}
.incremento-learning-metrics span{display:block;font-size:.85em;margin-top:4px}
.incremento-learning-table{overflow-x:auto}
.incremento-learning-table table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.incremento-learning-table th,.incremento-learning-table td{padding:7px 10px;text-align:right;border-bottom:1px solid rgba(128,128,128,.2)}
.incremento-learning-table th:first-child{text-align:left}
.incremento-learning-hint{margin:12px 0 0;font-size:.82em;line-height:1.5;opacity:.8}
@media(max-width:600px){.incremento-learning-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.incremento-learning-results{margin-left:8px;margin-right:8px}}
</style>"""
    return css + '<section class="incremento-learning-results"><h3>' + title + '</h3>' + body + '</section>'


def _document_pdf_pages(path):
    """Use Anki's bundled PDF engine; create/close it entirely in the worker."""
    from PyQt6.QtPdf import QPdfDocument
    document = QPdfDocument(None)
    try:
        document.load(str(path))
        return document.pageCount() or None
    finally:
        document.close()


def request_document_progress(parent, addon_dir, profile, day_end_time, on_result, *, is_current, cancelled):
    _request_learning_statistics(
        parent, profile, day_end_time, on_result, is_current=is_current,
        load=lambda col, _classifier: document_progress_from_collection(
            col, addon_dir, profile, should_cancel=cancelled, pdf_page_counter=_document_pdf_pages,
        ),
    )


def request_learning_card_states(parent, profile, day_end_time, on_result, *, is_current, cancelled):
    _request_learning_statistics(
        parent, profile, day_end_time, on_result, is_current=is_current,
        load=lambda col, classifier: learning_card_states_from_collection(
            col, classifier=classifier, should_cancel=cancelled,
        ),
    )


def request_daily_learning_outcomes(parent, profile, day_end_time, on_result, *, is_current):
    _request_learning_statistics(
        parent, profile, day_end_time, on_result, is_current=is_current,
        load=lambda col, classifier: daily_learning_outcomes_from_collection(col, day_end_time, classifier=classifier),
    )


def request_learning_outcome_history(parent, profile, day_end_time, on_result, *, is_current):
    _request_learning_statistics(
        parent, profile, day_end_time, on_result, is_current=is_current,
        load=lambda col, classifier: learning_outcome_history_from_collection(col, day_end_time, days=60, classifier=classifier),
    )


def _request_learning_statistics(parent, profile, day_end_time, on_result, *, is_current, load):
    """Capture settings on the UI thread; discard stale/profile-switched results."""
    collection = getattr(mw, "col", None)
    logical_date = _effective_date(day_end_time)

    def current():
        return (
            is_current() and _active_profile() == profile
            and getattr(mw, "col", None) is collection
            and _effective_date(day_end_time) == logical_date
        )

    def received(result):
        if current():
            on_result(result)

    if collection is None:
        received(None)
        return
    try:
        from aqt.operations import QueryOp
        classifier = resolve_topic_card_classifier()
        QueryOp(
            parent=parent,
            op=lambda col: load(col, classifier),
            success=received,
        ).failure(lambda _exc: received(None)).run_in_background()
    except Exception:
        received(None)


class DeckBrowserLearningStats:
    """Cache one asynchronous render and avoid a refresh/query feedback loop."""

    def __init__(self):
        self._key = None
        self._outcomes = None
        self._pending = None
        self._skip_next_request = False

    @property
    def loading(self):
        return self._pending is not None

    def get(self, window, profile, day_end_time):
        key = (profile, day_end_time, _effective_date(day_end_time), id(getattr(window, "col", None)))
        if key != self._key:
            self._key = key
            self._outcomes = None
            self._pending = None
            self._skip_next_request = False
        if self._skip_next_request:
            self._skip_next_request = False
            return self._outcomes
        if self.loading or getattr(window, "col", None) is None:
            return self._outcomes
        token = object()
        self._pending = token

        def received(result):
            self._pending = None
            self._outcomes = result
            if getattr(window, "state", None) == "deckBrowser":
                self._skip_next_request = True
                window.deckBrowser.refresh()

        request_daily_learning_outcomes(
            window, profile, day_end_time, received,
            is_current=lambda: self._pending is token and self._key == key,
        )
        return self._outcomes
