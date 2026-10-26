from concurrent.futures import CancelledError
import sys

import pytest

from pdf_extraction import ExtractionBudget, ExtractionLimit, bounded_text_process


def test_page_budget_stops_before_next_page_and_cancellation_is_distinct():
    budget = ExtractionBudget(max_pages=2, max_bytes=12)
    budget.add_page("éé")
    budget.add_page("text")
    with pytest.raises(ExtractionLimit):
        budget.add_page("x")
    with pytest.raises(ExtractionLimit):
        ExtractionBudget(max_bytes=3).add_page("éé")
    with pytest.raises(CancelledError):
        ExtractionBudget(cancelled=lambda: True).check()


def test_external_extractor_output_is_bounded_and_process_is_reaped():
    with pytest.raises(ExtractionLimit):
        bounded_text_process(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 200000)"],
            ExtractionBudget(max_bytes=1024),
        )


def test_external_extractor_is_cancelled_without_waiting_for_child_sleep():
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 3

    with pytest.raises(CancelledError):
        bounded_text_process(
            [sys.executable, "-c", "import time; time.sleep(120)"],
            ExtractionBudget(cancelled=cancelled),
        )


def test_external_extractor_decodes_successful_text():
    assert bounded_text_process(
        [sys.executable, "-c", "print('résumé\\fpage two')"], ExtractionBudget(),
    ) == "résumé\fpage two\n"
