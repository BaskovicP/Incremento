"""Profile unload waits for a close-triggered full backup without freezing Qt."""

from frontend.backup_close_gate import ProfileCloseBackupGate


class _Window:
    def __init__(self):
        self.closed = []
        self.enabled = True

    def setEnabled(self, enabled):
        self.enabled = bool(enabled)

    def unloadCollection(self, callback):
        self.closed.append(callback)


def test_close_gate_defers_unload_until_backup_completion_and_ignores_duplicate_close():
    window = _Window()
    pending = []
    gate = ProfileCloseBackupGate(window, pending.append)
    gate.install()
    completed = object()

    window.unloadCollection(completed)
    window.unloadCollection(object())
    assert window.closed == []
    assert window.enabled is False
    assert len(pending) == 1

    pending[0]()
    pending[0]()
    assert window.closed == [completed]


def test_close_gate_recovers_from_prepare_failure_and_can_reset_for_next_profile():
    window = _Window()
    pending = []

    def prepare(done):
        if not pending:
            raise RuntimeError("unavailable")
        pending.append(done)

    gate = ProfileCloseBackupGate(window, prepare)
    gate.install()
    first = object()
    window.unloadCollection(first)
    assert window.closed == [first]

    gate.reset()
    pending.append("ready")
    second = object()
    window.unloadCollection(second)
    assert window.closed == [first]
    pending[1]()
    assert window.closed == [first, second]
