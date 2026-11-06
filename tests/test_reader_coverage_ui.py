"""Coverage reports own their profile and ignore hidden or stale readers."""
from concurrent.futures import Future

from frontend.reader_coverage import CoverageTracker


def test_hidden_readers_do_not_count_and_stale_results_cannot_update_the_next_document(tmp_path):
    state = dict(current=True, visible=False)
    pending, replies = [], []
    def run(work, done, **options):
        assert options == {'uses_collection': False}
        pending.append((work, done))
    tracker = CoverageTracker(str(tmp_path), 'A', 'pdf', 7, 'book.pdf', run=run,
        current=lambda: state['current'], visible=lambda: state['visible'], reply=replies.append)
    sample = dict(cardId=7, position=0, start=2, end=3, totalPages=100)
    assert not tracker.receive(sample)
    assert not pending
    state['visible'] = True
    assert tracker.receive(sample)
    assert len(pending) == 1
    work, done = pending.pop()
    future = Future()
    future.set_result(work())
    state['current'] = False
    done(future)
    assert replies == []
    from backend.reader_coverage import coverage_summary
    assert coverage_summary(str(tmp_path), 'A', 'pdf', 7, 'book.pdf', total=100)['viewed'] == 1


def test_forged_card_and_malformed_or_unbounded_ranges_never_dispatch_storage(tmp_path):
    pending = []
    tracker = CoverageTracker(str(tmp_path), 'A', 'epub', 7, 'book.epub', lengths=(3000,),
        run=lambda *a, **kw: pending.append(a), current=lambda: True, visible=lambda: True, reply=lambda data: None)
    for sample in [dict(cardId=8, position=0, start=0, end=10),
                   dict(cardId=7, position=0, start=0, end=3001),
                   dict(cardId=7, position=1, start=0, end=10),
                   dict(cardId=7, position=0, start=True, end=10)]:
        assert not tracker.receive(sample)
    assert pending == []
