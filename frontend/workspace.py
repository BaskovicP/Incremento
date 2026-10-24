"""Explicit, reversible layouts for Incremento panes; no operating-system automation."""
from contextlib import ExitStack

from aqt.qt import QDockWidget, QMenu, QRect, QSignalBlocker, Qt

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


_PANE_NAMES = {
    'incremento_pdf_dock', 'incremento_epub_dock', 'incremento_writing_dock',
    'incremento_video_dock', 'incremento_web_dock', 'incremento_local_file_dock',
    'incremento_add_card_dock',
}


def snap_rectangle(area, placement):
    """Use logical screen coordinates, including screens left of the primary one."""
    fractions = {
        'left': (0, 0, 1, 2), 'right': (1, 0, 2, 2),
        'top': (0, 0, 2, 1), 'bottom': (0, 1, 2, 2),
        'top_left': (0, 0, 1, 1), 'top_right': (1, 0, 2, 1),
        'bottom_left': (0, 1, 1, 2), 'bottom_right': (1, 1, 2, 2),
        'maximize': (0, 0, 2, 2),
    }
    if placement not in fractions:
        raise ValueError('Unknown window placement')
    x1, y1, x2, y2 = fractions[placement]
    left, top = area.x() + area.width() * x1 // 2, area.y() + area.height() * y1 // 2
    return QRect(left, top, area.width() * x2 // 2 - area.width() * x1 // 2,
                 area.height() * y2 // 2 - area.height() * y1 // 2)


def _focus(dock):
    return getattr(dock, '_pdf_focus_mode', None) or getattr(dock, '_epub_focus_mode', None)


class WorkspaceLayouts:
    def __init__(self, main):
        self.main = main
        self._previous = None

    def visible_panes(self):
        panes = []
        for dock in self.main.findChildren(QDockWidget):
            name = dock.objectName()
            if name not in _PANE_NAMES and not name.startswith(('incremento_pdf_reference_', 'incremento_epub_reference_')):
                continue
            mode = _focus(dock)
            if dock.isVisible() or (mode is not None and mode.active):
                panes.append(dock)
        return panes

    def _remember(self, panes):
        self._previous = (self.main.saveState(), tuple(panes),
                          tuple(_focus(d) for d in panes if _focus(d) is not None and _focus(d).active))

    @staticmethod
    def _leave_focus(panes):
        for dock in panes:
            mode = _focus(dock)
            if mode is not None and mode.active:
                mode.stop()

    def beside(self, writing):
        panes = self.visible_panes()
        if writing not in panes:
            return False
        focused = next((d for d in panes if _focus(d) is not None and _focus(d).active), None)
        if focused is not None:
            # The PDF/EPUB already occupies Anki's central area. Keep it there
            # and give writing half the width, retaining the answer controls.
            self._remember(panes)
            with QSignalBlocker(writing):
                self.main.removeDockWidget(writing)
                self.main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, writing)
                writing.setFloating(False)
                writing.show()
                self.main.resizeDocks([writing], [self.main.width() // 2], Qt.Orientation.Horizontal)
            return True
        reader = next((d for d in panes if d.objectName() in {
            'incremento_pdf_dock', 'incremento_epub_dock'}), None)
        return self.arrange('columns', [reader, writing]) if reader is not None else False

    def arrange(self, layout, panes=None):
        if layout not in ('columns', 'rows', 'grid'):
            raise ValueError('Unknown workspace layout')
        panes = self.visible_panes() if panes is None else list(panes)
        if len(panes) < 2:
            return False
        self._remember(panes)
        with ExitStack() as stack:
            for dock in panes:
                stack.enter_context(QSignalBlocker(dock))
            self._leave_focus(panes)
            for dock in panes:
                self.main.removeDockWidget(dock)
                self.main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
                dock.setFloating(False)
                dock.show()
            horizontal, vertical = Qt.Orientation.Horizontal, Qt.Orientation.Vertical
            if layout == 'grid':
                # Two columns, as many rows as needed; every pane stays reachable.
                for index, dock in enumerate(panes[1:], 1):
                    previous = panes[index - 1] if index % 2 else panes[index - 2]
                    self.main.splitDockWidget(previous, dock, horizontal if index % 2 else vertical)
                self.main.resizeDocks(panes, [1] * len(panes), horizontal)
                self.main.resizeDocks(panes, [1] * len(panes), vertical)
            else:
                orientation = horizontal if layout == 'columns' else vertical
                for previous, dock in zip(panes, panes[1:]):
                    self.main.splitDockWidget(previous, dock, orientation)
                size = self.main.width() if layout == 'columns' else self.main.height()
                self.main.resizeDocks(panes, [max(1, size // len(panes))] * len(panes), orientation)
        return True

    def snap(self, dock, placement):
        if dock not in self.visible_panes():
            return False
        screen = dock.screen() if dock.isFloating() else self.main.screen()
        if screen is None:
            return False
        rectangle = snap_rectangle(screen.availableGeometry(), placement)
        minimum = dock.minimumSizeHint().expandedTo(dock.minimumSize())
        if minimum.width() > rectangle.width() or minimum.height() > rectangle.height():
            return False
        self._remember(self.visible_panes())
        with QSignalBlocker(dock):
            self._leave_focus([dock])
            dock.setFloating(True)
            dock.showNormal()
            # Geometry describes client area; leave room for the native title bar.
            margins = dock.windowHandle().frameMargins()
            rectangle.adjust(margins.left(), margins.top(), -margins.right(), -margins.bottom())
            if minimum.width() > rectangle.width() or minimum.height() > rectangle.height():
                self.restore()
                return False
            dock.setGeometry(rectangle)
            dock.show()
        return True

    def restore(self):
        if self._previous is None:
            return False
        state, original, focused = self._previous
        self._previous = None
        current = self.visible_panes()
        live = self.main.findChildren(QDockWidget)
        panes = [d for d in original if d in live]
        # Closed panes must stay closed, and no deleted wrapper may be dereferenced.
        with ExitStack() as stack:
            for dock in live:
                stack.enter_context(QSignalBlocker(dock))
            self._leave_focus(current)
            self.main.restoreState(state)
            for dock in panes:
                dock.setVisible(dock in current)
            for mode in focused:
                if mode.dock in current:
                    mode.present(eligible=True, title=mode.dock.windowTitle())
        return True

    def reset(self):
        self._previous = None


def add_workspace_menu(parent, manager, open_writing):
    """Rebuild window targets when shown, so closed windows cannot remain actionable."""
    menu = parent.addMenu(t('workspace_title'))
    menu.menuAction().setProperty('incremento_translation_key', 'workspace_title')

    def action(owner, key, callback, enabled=True):
        item = owner.addAction(t(key))
        item.setEnabled(enabled)
        item.triggered.connect(lambda checked=False: callback())
        return item

    def arrange(layout):
        if not manager.arrange(layout):
            from aqt.utils import tooltip
            tooltip(t('workspace_need_two'))

    def snap(dock, placement):
        if not manager.snap(dock, placement):
            from aqt.utils import tooltip
            tooltip(t('workspace_too_small'))

    def rebuild():
        menu.clear()
        action(menu, 'workspace_write_beside', open_writing)
        menu.addSeparator()
        panes = manager.visible_panes()
        for layout in ('columns', 'rows', 'grid'):
            action(menu, 'workspace_' + layout, lambda value=layout: arrange(value), len(panes) >= 2)
        action(menu, 'workspace_restore', manager.restore, manager._previous is not None)
        menu.addSeparator()
        windows = menu.addMenu(t('workspace_position'))
        windows.setEnabled(bool(panes))
        for dock in panes:
            target = windows.addMenu(dock.windowTitle().replace('&', '&&'))
            for placement in ('left', 'right', 'top', 'bottom', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'maximize'):
                action(target, 'workspace_' + placement, lambda d=dock, p=placement: snap(d, p))
    menu.aboutToShow.connect(rebuild)
    return menu
