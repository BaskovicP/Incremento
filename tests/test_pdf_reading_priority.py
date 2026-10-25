"""Background scan pauses are cancellable and bounded without real sleeps."""
from types import SimpleNamespace

import pdf_reading_priority as priority


def test_reader_activity_yields_background_scans_for_at_most_one_quarter_second(monkeypatch):
    now, waits = [0.0], []
    monkeypatch.setattr(priority, '_reading_until', 0.0)
    monkeypatch.setattr(priority, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    def wait(seconds):
        waits.append(seconds)
        now[0] += seconds
    cancel = SimpleNamespace(is_set=lambda: False, wait=wait)
    priority.defer_for_pdf_reading()
    priority.wait_for_pdf_reading(cancel)
    assert abs(sum(waits) - .25) < 1e-9
    assert max(waits) <= .025
    now[0] = 1
    waits.clear()
    priority.wait_for_pdf_reading(cancel)
    assert waits == []


def test_profile_cancel_never_waits_for_a_reader_to_become_idle(monkeypatch):
    monkeypatch.setattr(priority, '_reading_until', float('inf'))
    priority.wait_for_pdf_reading(SimpleNamespace(is_set=lambda: True,
        wait=lambda _: (_ for _ in ()).throw(AssertionError('cancelled scan must not sleep'))))
