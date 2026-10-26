"""Borrow Anki's content area without reparenting either live reviewer web view."""
from aqt.qt import QEvent, QObject, QVBoxLayout, Qt


class StudySurface(QObject):
    def __init__(self, main, workspace):
        super().__init__(workspace)
        self.main, self.workspace = main, workspace
        self.layout = None
        self.active = False
        self.hidden = []
        self.shortcuts = []

    def _target(self):
        if getattr(self.main, 'state', '') != 'review':
            return None
        reviewer = getattr(self.main, 'reviewer', None)
        web = getattr(reviewer, 'web', None)
        bottom = getattr(reviewer, 'bottom', None)
        bottom = getattr(bottom, 'web', bottom)
        if web is None or bottom is None or not hasattr(web, 'parentWidget'):
            return None
        parent = web.parentWidget()
        layout = parent.layout() if parent is not None else None
        if (not isinstance(layout, QVBoxLayout) or layout.indexOf(web) < 0
                or layout.indexOf(bottom) <= layout.indexOf(web)):
            return None
        # Another focused reader owns this space. Keep its layout intact and
        # use the same themed study shell in a standalone window instead.
        if self.layout is None and web.isHidden():
            return None
        return layout, web, bottom

    def present(self):
        target = self._target()
        if target is not None and not self.active:
            layout, web, bottom = target
            if self.layout is None:
                self.workspace.setParent(web.parentWidget())
                self.workspace.setWindowFlags(Qt.WindowType.Widget)
                layout.insertWidget(layout.indexOf(web), self.workspace, 1)
                self.layout = layout
            self.hidden = [(widget, widget.isHidden()) for widget in (web, bottom)]
            # Anki's state shortcuts belong to the main window. Hiding its web
            # views does not stop number/space keys from answering the card.
            self.shortcuts = [(shortcut, shortcut.isEnabled())
                              for shortcut in getattr(self.main, 'stateShortcuts', ())]
            for shortcut, _ in self.shortcuts:
                shortcut.setEnabled(False)
            self.active = True
            for widget, _ in self.hidden:
                widget.installEventFilter(self)
                widget.hide()
        self.workspace.show()

    def eventFilter(self, watched, event):
        if (self.active and event.type() == QEvent.Type.Show
                and any(watched is widget for widget, _ in self.hidden)):
            watched.hide()
            return True
        return super().eventFilter(watched, event)

    def leave(self, *, detach=False):
        self.workspace.hide()
        if self.active:
            self.active = False
            for index, (widget, was_hidden) in enumerate(self.hidden):
                try:
                    widget.removeEventFilter(self)
                    # Anki owns the bottom bar outside review; never reveal a
                    # previous card's grading controls on a different screen.
                    if index == 0 or getattr(self.main, 'state', '') == 'review':
                        widget.setVisible(not was_hidden)
                except RuntimeError:
                    pass
            self.hidden = []
            for shortcut, was_enabled in self.shortcuts:
                try:
                    if (getattr(self.main, 'state', '') == 'review'
                            and shortcut in getattr(self.main, 'stateShortcuts', ())):
                        shortcut.setEnabled(was_enabled)
                except RuntimeError:
                    pass
            self.shortcuts = []
        if detach and self.layout is not None:
            try:
                self.layout.removeWidget(self.workspace)
            except RuntimeError:
                pass
            self.layout = None
