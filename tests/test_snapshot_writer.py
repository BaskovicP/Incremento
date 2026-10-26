from threading import Event
import pytest
from snapshot_writer import OrderedWriter


def test_writer_coalesces_pending_snapshots_and_flushes_in_order():
    entered, release = Event(), Event()
    writes = []
    def write(snapshot):
        if snapshot == 1:
            entered.set()
            assert release.wait(5)
        writes.append(snapshot)
    writer = OrderedWriter(write)
    writer.submit(1)
    assert entered.wait(5)
    writer.submit(2)
    writer.submit(3)
    release.set()
    writer.flush()
    assert writes == [1, 3]
    writer.close()


def test_failed_save_is_visible_and_successful_retry_clears_failure():
    def write(value):
        if value == "bad":
            raise OSError("synthetic failure")
    writer = OrderedWriter(write)
    writer.submit("bad")
    with pytest.raises(OSError):
        writer.flush()
    writer.submit("good")
    writer.flush()
    writer.close()
