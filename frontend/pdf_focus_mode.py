"""Put the live PDF reader across Anki's content area, retaining review controls."""

from aqt.qt import QSignalBlocker, QVBoxLayout


class PdfFocusMode:
    """Keep the dock layout and WebEngine instance intact across focus changes.

    Only the reader's content moves. The hidden dock retains its original split,
    floating state and geometry, and Anki still owns both reviewer web views.
    The saved preference survives restarts; changing cards restores Anki's pane.
    """

    def __init__(self, main_window, dock, view, *, enabled=False, save_preference=None, state_changed=None):
        self.main = main_window
        self.dock = dock
        self.active = False
        self._layout = None
        self._web = None
        self._web_was_hidden = False
        self.save_preference = save_preference
        self.state_changed = state_changed
        self.enabled = bool(enabled)
        self.available = False
        # The toggle lives in the PDF's existing bottom toolbar. Moving the
        # view itself avoids a second header consuming document height.
        self.host = view
        dock.setWidget(self.host)

    def _target_layout(self):
        web = getattr(self.main, 'web', None)
        bottom = getattr(self.main, 'bottomWeb', None)
        if web is None or bottom is None:
            return None
        parent = web.parentWidget()
        layout = parent.layout() if parent is not None else None
        if (not isinstance(layout, QVBoxLayout) or layout.indexOf(web) < 0
                or layout.indexOf(bottom) <= layout.indexOf(web)):
            return None
        return layout

    def present(self, *, eligible: bool, title: str) -> None:
        self.dock.setWindowTitle(title)
        self.available = eligible and self._target_layout() is not None
        if self.available and self.enabled:
            self._enter()
        else:
            self._restore()
        if not self.active:
            self.dock.show()
            self.dock.raise_()
        self._notify()

    def request_enabled(self, enabled: bool) -> None:
        """Commit a toolbar request before changing layout or its pressed state."""
        if not self.available:
            return
        if self.save_preference is not None and not self.save_preference(enabled):
            self._notify()
            return
        self.set_enabled(enabled)

    def _notify(self) -> None:
        if self.state_changed is not None:
            self.state_changed()

    def set_enabled(self, enabled: bool) -> None:
        """Apply a preference already saved by Settings or loaded on reopening."""
        self.enabled = bool(enabled)
        if self.available:
            self._apply_enabled(bool(enabled))
        self._notify()

    def _apply_enabled(self, enabled: bool) -> None:
        if enabled and self.available:
            self._enter()
        else:
            self._restore()
            self.dock.show()

    def _enter(self) -> None:
        if self.active:
            return
        layout = self._target_layout()
        if layout is None:
            return
        web = self.main.web
        self._layout, self._web = layout, web
        self._web_was_hidden = web.isHidden()
        self.active = True
        # Moving the content is not a reader-close event. In particular, do not
        # clear the document identity, bridge nonce, progress or reading timer.
        with QSignalBlocker(self.dock):
            self.dock.setWidget(None)
            self.host.setParent(web.parentWidget())
            layout.insertWidget(layout.indexOf(web), self.host, 1)
            web.hide()
            self.dock.hide()
            self.host.show()

    def _restore(self) -> None:
        if not self.active:
            return
        self.active = False
        with QSignalBlocker(self.dock):
            self._layout.removeWidget(self.host)
            self.host.hide()
            self.dock.setWidget(self.host)
            self.host.show()
            self._web.setVisible(not self._web_was_hidden)
        self._layout = self._web = None

    def stop(self, *, reset: bool = False) -> None:
        self._restore()
        self.available = False
        if reset:
            self.enabled = False
        self._notify()

    def is_visible(self) -> bool:
        return self.host.isVisible() if self.active else self.dock.isVisible()
