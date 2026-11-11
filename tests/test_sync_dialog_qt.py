"""The sync dialog in real Qt (offscreen), driven by a fake controller."""
import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]

SCRIPT_HEAD = dedent(r"""
    import os, sys, types
    package = types.ModuleType("incremento")
    package.__path__ = [os.getcwd()]
    sys.modules["incremento"] = package
    from aqt.qt import QApplication, Qt
    app = QApplication([])
    from incremento.frontend import sync_dialog
    from incremento.backend.sync_service import Conflict, SyncStatus

    class Controller:
        def __init__(self, configured=True, conflicts=(), last_sync=1_700_000_000, waiting_for_anki=0, stale=0):
            self.configured, self._conflicts = configured, list(conflicts)
            self.last_sync, self.waiting_for_anki, self.stale = last_sync, waiting_for_anki, stale
            self.calls, self.done = [], None
        def status(self):
            where = getattr(self, "hub_label", None) or "C:/Cloud"
            return SyncStatus(self.configured, where if self.configured else None,
                              self.last_sync if self.configured else None, len(self._conflicts),
                              self.waiting_for_anki, 0, 0, self.stale)
        def conflicts(self):
            return list(self._conflicts)
        def configure(self, folder):
            self.calls.append(("configure", folder))
            if folder == "bad":
                raise RuntimeError("holds several libraries")
            self.configured = True
        def configure_hub(self, code):
            self.calls.append(("configure_hub", code))
            if code == "bad":
                raise RuntimeError("The hub cannot be used: refused")
            self.configured, self.hub_label = True, "hub:desktop:0a1b2c3d"
        def disable(self):
            self.calls.append(("disable",))
            self.configured = False
        def sync(self, done):
            self.calls.append(("sync",))
            self.done = done
        def discard_stale(self):
            self.calls.append(("discard_stale",))
            self.waiting_for_anki, self.stale = 0, 0
        def resolve(self, conflict_id, value):
            self.calls.append(("resolve", conflict_id, value))
            self._conflicts = [c for c in self._conflicts if c.id != conflict_id]
""")


def _run(body: str) -> None:
    result = subprocess.run([sys.executable, "-c", SCRIPT_HEAD + dedent(body)], cwd=ROOT,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_unconfigured_profile_offers_only_choosing_a_folder():
    _run(r"""
        dialog = sync_dialog.SyncDialog("Main", Controller(configured=False))
        assert dialog._folder.text() == "Not set up"
        assert "Not synced yet." in dialog._status.text()
        assert not dialog._sync.isEnabled() and not dialog._stop.isEnabled()
        assert dialog._choose.isEnabled()
        assert dialog._list.item(0).text() == "No conflicts."
        assert not dialog._keep_mine.isEnabled()
    """)


def test_a_conflict_reads_as_this_computer_against_the_other_and_can_be_settled():
    _run(r"""
        conflict = Conflict(4, "priority", "card:7", ["h1", "h2"], [{"priority": 30.0}, {"priority": 90.0}], 1)
        controller = Controller(conflicts=[conflict], waiting_for_anki=2)
        dialog = sync_dialog.SyncDialog("Main", controller)
        assert dialog._list.item(0).text() == "Priority of card 7: this computer 90 · other computer 30"
        assert "Waiting for cards from AnkiWeb: 2" in dialog._status.text()
        assert not dialog._use_theirs.isEnabled()

        dialog._list.setCurrentRow(0)
        assert dialog._use_theirs.isEnabled()
        dialog._use_theirs.click()

        assert controller.calls == [("resolve", 4, {"priority": 30.0})]
        assert dialog._list.item(0).text() == "No conflicts."
    """)


def test_sync_now_shows_progress_and_refreshes_when_done():
    _run(r"""
        controller = Controller()
        dialog = sync_dialog.SyncDialog("Main", controller)
        dialog._sync.click()
        assert controller.calls == [("sync",)]
        assert dialog._sync.text() == "Syncing…" and not dialog._sync.isEnabled()
        assert not dialog._stop.isEnabled() and not dialog._choose.isEnabled()

        controller.done()

        assert dialog._sync.text() == "Sync now" and dialog._sync.isEnabled()
    """)


def test_a_folder_the_service_refuses_is_explained_and_changes_nothing():
    _run(r"""
        shown = []
        sync_dialog.showInfo = lambda text, **kwargs: shown.append(text)
        controller = Controller(configured=False)
        dialog = sync_dialog.SyncDialog("Main", controller)

        dialog.use_folder("bad")

        assert shown == ["This folder can't be used: holds several libraries"]
        assert dialog._folder.text() == "Not set up"
        dialog.use_folder("C:/Cloud")
        assert dialog._folder.text() == "C:/Cloud" and dialog._sync.isEnabled()
    """)


def test_stopping_asks_first_and_keeps_syncing_when_declined():
    _run(r"""
        answers = [False, True]
        sync_dialog.askUser = lambda text, **kwargs: answers.pop(0)
        controller = Controller()
        dialog = sync_dialog.SyncDialog("Main", controller)

        dialog._stop.click()
        assert controller.calls == [] and dialog._sync.isEnabled()
        dialog._stop.click()

        assert controller.calls == [("disable",)]
        assert dialog._folder.text() == "Not set up" and not dialog._sync.isEnabled()
    """)


def test_values_are_described_briefly_and_deletions_are_named():
    _run(r"""
        assert sync_dialog.describe_value("priority", {"priority": 12.5}) == "12.5"
        assert sync_dialog.describe_value("reading_position", {"page": 42, "scroll_ratio": 0.1,
                                                                "read_page": 41, "read_anchor_json": ""}) == "page 42"
        assert sync_dialog.describe_value("pdf_highlight", None) == "deleted"
        long = sync_dialog.describe_value("reader_bookmark", {"comment_text": "x" * 200})
        assert len(long) == sync_dialog.MAX_VALUE_TEXT and long.endswith("…")
    """)


def test_changes_waiting_too_long_can_be_discarded_after_confirming():
    _run(r"""
        answers = [False, True]
        sync_dialog.askUser = lambda text, **kwargs: answers.pop(0) if "Discard 3" in text else None
        controller = Controller(waiting_for_anki=3, stale=3)
        dialog = sync_dialog.SyncDialog("Main", controller)
        assert "Changes waiting over 30 days: 3" in dialog._status.text()
        assert dialog._discard.isVisible() or not dialog._discard.isHidden()

        dialog._discard.click()
        assert controller.calls == []
        dialog._discard.click()

        assert controller.calls == [("discard_stale",)]
        assert "30 days" not in dialog._status.text() and dialog._discard.isHidden()
    """)


def test_the_discard_button_is_hidden_when_nothing_waited_too_long():
    _run(r"""
        dialog = sync_dialog.SyncDialog("Main", Controller(waiting_for_anki=2, stale=0))
        assert dialog._discard.isHidden()
    """)


def test_a_hub_is_paired_with_a_code_and_shown_by_the_device_it_was_paired_as():
    _run(r"""
        shown = []
        sync_dialog.showInfo = lambda text, **kwargs: shown.append(text)
        controller = Controller(configured=False)
        dialog = sync_dialog.SyncDialog("Main", controller)

        dialog.use_hub("bad")

        assert shown == ["This folder can't be used: The hub cannot be used: refused"] and not dialog._sync.isEnabled()
        dialog.use_hub("  ihub1-code  ")
        assert controller.calls[-1] == ("configure_hub", "ihub1-code")
        assert dialog._sync.isEnabled()
        assert "desktop" in dialog._folder.text() and "0a1b2c3d" not in dialog._folder.text()
    """)


def test_the_hub_button_is_there_and_disabled_while_syncing():
    _run(r"""
        controller = Controller()
        dialog = sync_dialog.SyncDialog("Main", controller)
        assert dialog._hub.isEnabled()
        dialog._sync.click()
        assert not dialog._hub.isEnabled()
    """)
