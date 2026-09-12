"""Defer Anki collection unload until an in-flight full backup has completed."""

from __future__ import annotations

from collections.abc import Callable


class ProfileCloseBackupGate:
    def __init__(self, main_window, prepare: Callable[[Callable[[], None]], None]):
        self._window = main_window
        self._original = main_window.unloadCollection
        self._prepare = prepare
        self._closing = False
        self._resumed = False

    def install(self) -> None:
        self._window.unloadCollection = self.unload_collection

    def reset(self) -> None:
        self._closing = False
        self._resumed = False

    def unload_collection(self, on_success: Callable) -> None:
        if self._closing:
            return
        self._closing = True
        disable = getattr(self._window, "setEnabled", None)
        if callable(disable):
            try:
                disable(False)
            except Exception:
                pass

        def resume() -> None:
            if self._resumed:
                return
            self._resumed = True
            self._original(on_success)

        try:
            self._prepare(resume)
        except Exception:
            # A backup adapter must never make profile shutdown impossible.
            resume()
