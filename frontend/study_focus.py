"""Temporarily give a study view the screen without moving its live widgets."""
from aqt.qt import QDockWidget, QEvent, QObject, Qt


class StudyFocus(QObject):
    def __init__(self, workspace, main):
        super().__init__(workspace)
        self.workspace, self.main = workspace, main
        self.window = None
        self.hidden = []

    def enter(self):
        if self.window is not None:
            return
        self.window = self.workspace.window()
        self.state = self.window.windowState()
        self.geometry = self.window.geometry()
        if self.window is self.main:
            widgets = [dock for dock in self.main.findChildren(QDockWidget)
                       if dock.window() is self.main and not dock.isFloating()
                       and not self.workspace.isAncestorOf(dock)]
            toolbar = getattr(self.main, 'toolbarWeb', None)
            if toolbar is not None:
                widgets.append(toolbar)
            self.hidden = [(widget, widget.isHidden()) for widget in widgets]
            for widget, _ in self.hidden:
                widget.installEventFilter(self)
                widget.setVisible(False)
        if not self.state & Qt.WindowState.WindowFullScreen:
            self.window.showFullScreen()

    def eventFilter(self, watched, event):
        if (self.window is not None and event.type() == QEvent.Type.Show
                and any(watched is widget for widget, _ in self.hidden)):
            watched.setVisible(False)
            return True
        return super().eventFilter(watched, event)

    def leave(self):
        window, self.window = self.window, None
        if window is None:
            return
        for widget, was_hidden in self.hidden:
            try:
                widget.removeEventFilter(self)
                widget.setVisible(not was_hidden)
            except RuntimeError:
                pass
        self.hidden = []
        if not self.state & Qt.WindowState.WindowFullScreen:
            window.setWindowState(self.state)
            if not self.state & Qt.WindowState.WindowMaximized:
                window.setGeometry(self.geometry)
