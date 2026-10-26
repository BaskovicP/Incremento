from types import SimpleNamespace
import background_reads


def test_dialog_reads_coalesce_and_discard_profile_switch_or_closed_results(monkeypatch):
    pending, shown = [], []
    profile = ["A"]
    col = object()
    monkeypatch.setattr(background_reads, "mw", SimpleNamespace(col=col))
    reads = background_reads.BackgroundReads(
        SimpleNamespace(), "A", current_profile=lambda: profile[0],
        dispatch=lambda *args: pending.append(args),
    )
    reads.submit(lambda collection, cancel: 1, shown.append)
    reads.submit(lambda collection, cancel: 2, shown.append)
    reads.submit(lambda collection, cancel: 3, shown.append)
    assert len(pending) == 1
    pending[0][1](1)
    assert len(pending) == 2 and shown == []
    pending[1][1](3)
    assert shown == [3]
    reads.submit(lambda collection, cancel: 4, shown.append)
    profile[0] = "B"
    pending[2][1](4)
    assert shown == [3]
    profile[0] = "A"
    reads.submit(lambda collection, cancel: 5, shown.append)
    reads.close()
    pending[3][1](5)
    assert shown == [3]
