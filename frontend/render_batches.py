"""Bound UI object creation by both item count and callback elapsed time."""
from time import perf_counter


def build_in_batches(items, apply, *, valid, done, schedule=None, batch_size=40, budget_ms=5):
    if schedule is None:
        from aqt.qt import QTimer
        def schedule(callback):
            QTimer.singleShot(0, callback)
    iterator = iter(items)
    def step():
        started = perf_counter()
        for _ in range(max(1, batch_size)):
            if not valid():
                return
            try:
                item = next(iterator)
            except StopIteration:
                done()
                return
            apply(item)
            if (perf_counter() - started) * 1000 >= budget_ms:
                break
        schedule(step)
    step()
