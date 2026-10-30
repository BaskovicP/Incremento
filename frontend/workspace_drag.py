"""Title-bar dragging, floating resize borders, and non-activating drop outlines."""
from aqt.qt import (
    QApplication, QDockWidget, QEvent, QFrame, QHBoxLayout, QLabel, QObject,
    QPainter, QPoint, QRect, QRegion, QSignalBlocker, QSizePolicy, QStyle, QStyleOptionSizeGrip,
    QTimer, QToolButton, Qt, QWidget,
)

try:
    from ..backend.i18n import t
except ImportError:
    from backend.i18n import t


def edge_placement(point, area, margin=28):
    """Choose an edge in Qt logical pixels; corners take precedence over halves."""
    if not area.contains(point):
        return None
    left = point.x() - area.left() < margin
    right = area.right() - point.x() < margin
    top = point.y() - area.top() < margin
    bottom = area.bottom() - point.y() < margin
    if top and (left or right):
        return 'top_left' if left else 'top_right'
    if bottom and (left or right):
        return 'bottom_left' if left else 'bottom_right'
    return 'left' if left else 'right' if right else 'top' if top else 'bottom' if bottom else None


class PaneTitleBar(QWidget):
    def __init__(self, dock, controller):
        super().__init__(dock)
        self.dock, self.controller = dock, controller
        self.setAccessibleName(t('workspace_drag_title'))
        self.setToolTip(t('workspace_drag_hint'))
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 6, 6, 3)
        row.setSpacing(4)
        title = QLabel(dock.windowTitle(), self)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(title, 1)
        dock.windowTitleChanged.connect(title.setText)
        for key, icon, callback in (
            ('workspace_float', QStyle.StandardPixmap.SP_TitleBarNormalButton, self.toggle_float),
            ('workspace_close', QStyle.StandardPixmap.SP_TitleBarCloseButton, dock.close),
        ):
            button = QToolButton(self)
            button.setIcon(self.style().standardIcon(icon))
            button.setAccessibleName(t(key))
            button.setToolTip(t(key))
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            row.addWidget(button)
            if key == 'workspace_close':
                self.close_button = button
            else:
                self.float_button = button
        dock.featuresChanged.connect(self.update_features)
        self.update_features()

    def update_features(self, *_):
        features = self.dock.features()
        self.close_button.setVisible(bool(features & QDockWidget.DockWidgetFeature.DockWidgetClosable))
        self.float_button.setVisible(bool(features & QDockWidget.DockWidgetFeature.DockWidgetFloatable))

    def toggle_float(self):
        self.controller.toggle_float(self.dock)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.press(self.dock, self, event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.controller.move(event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.release(event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.cancel()
            self.toggle_float()
            event.accept()
        else:
            event.ignore()


class _PaneResizeHandle(QWidget):
    """Own only a narrow floating border; reader content keeps its mouse events."""

    def __init__(self, dock, controller, edges, cursor):
        super().__init__(dock)
        self.dock, self.controller, self.edges = dock, controller, edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()

    def paintEvent(self, event):
        if self.edges == Qt.Edge.RightEdge | Qt.Edge.BottomEdge:
            option = QStyleOptionSizeGrip()
            option.initFrom(self)
            option.corner = Qt.Corner.BottomRightCorner
            painter = QPainter(self)
            self.style().drawControl(QStyle.ControlElement.CE_SizeGrip, option, painter, self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.press_resize(self.dock, self, event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.controller.move(event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.controller.release(event.globalPosition().toPoint())
            event.accept()
        else:
            event.ignore()


class WorkspaceDrag(QObject):
    def __init__(self, manager):
        super().__init__(manager.main)
        self.manager = manager
        self.active_dock = self.bar = None
        self._resize_edges = None
        self._moved = False
        self._refresh_pending = False
        self._target = None
        self._before = self._previous = None
        # This overlay must never take focus, intercept the drop, or become a pane.
        self.outline = QFrame(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                              | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput
                              | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.outline.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.outline.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.outline.setWindowOpacity(.45)
        self.outline.setStyleSheet('background: #5195d5; border: 3px solid #1675c9; border-radius: 6px;')
        self.outline.hide()
        self.destroyed.connect(self.outline.deleteLater)
        QApplication.instance().installEventFilter(self)
        self.refresh()

    def refresh(self):
        self._refresh_pending = False
        for dock in self.manager.main.findChildren(QDockWidget):
            if self.manager.is_workspace_pane(dock) and dock.titleBarWidget() is None:
                dock.setTitleBarWidget(PaneTitleBar(dock, self))
            if isinstance(dock.titleBarWidget(), PaneTitleBar):
                if not hasattr(dock, '_workspace_resize_handles'):
                    left, right, top, bottom = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
                    dock._workspace_resize_handles = [
                        _PaneResizeHandle(dock, self, edges, cursor) for edges, cursor in (
                            (left, Qt.CursorShape.SizeHorCursor), (right, Qt.CursorShape.SizeHorCursor),
                            (top, Qt.CursorShape.SizeVerCursor), (bottom, Qt.CursorShape.SizeVerCursor),
                            (left | top, Qt.CursorShape.SizeFDiagCursor), (right | top, Qt.CursorShape.SizeBDiagCursor),
                            (left | bottom, Qt.CursorShape.SizeBDiagCursor), (right | bottom, Qt.CursorShape.SizeFDiagCursor),
                        )]
                self._update_resize_handles(dock)

    def _update_resize_handles(self, dock):
        # Custom title bars remove native floating-window decorations. Provide
        # usable hit targets even when the platform/theme paints a 1px frame.
        visible = dock.isFloating() and dock.isVisible() and not (dock.isMaximized() or dock.isFullScreen())
        width, height, border, corner = dock.width(), dock.height(), 6, 16
        rectangles = (
            QRect(0, corner, border, max(0, height - 2 * corner)),
            QRect(width - border, corner, border, max(0, height - 2 * corner)),
            QRect(corner, 0, max(0, width - 2 * corner), border),
            QRect(corner, height - border, max(0, width - 2 * corner), border),
            QRect(0, 0, corner, corner), QRect(width - corner, 0, corner, corner),
            QRect(0, height - corner, corner, corner), QRect(width - corner, height - corner, corner, corner),
        )
        for handle, rectangle in zip(getattr(dock, '_workspace_resize_handles', ()), rectangles):
            handle.setGeometry(rectangle)
            if rectangle.width() == corner and rectangle.height() == corner:
                # Corner hit targets wrap around content and title-bar buttons
                # instead of covering a square inside the reader.
                x = 0 if handle.edges & Qt.Edge.LeftEdge else corner - border
                y = 0 if handle.edges & Qt.Edge.TopEdge else corner - border
                handle.setMask(QRegion(x, 0, border, corner) | QRegion(0, y, corner, border))
            handle.setVisible(visible)
            if visible:
                handle.raise_()

    def eventFilter(self, watched, event):
        kind = event.type()
        if isinstance(watched, QDockWidget) and kind in (
                QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.Resize,
                QEvent.Type.WindowStateChange, QEvent.Type.ParentChange):
            self._update_resize_handles(watched)
        if kind == QEvent.Type.Show and isinstance(watched, QDockWidget) and self.manager.is_workspace_pane(watched):
            if not self._refresh_pending:
                self._refresh_pending = True
                QTimer.singleShot(0, self.refresh)
        if self.active_dock is not None:
            if kind == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                self.cancel()
                return True
            if kind == QEvent.Type.ApplicationDeactivate:
                self.cancel()
            elif kind in (QEvent.Type.Close, QEvent.Type.DeferredDelete) and watched in (self.active_dock, self.manager.main):
                self.cancel(restore=False)
        return False

    def press(self, dock, bar, point):
        features = dock.features()
        if not (features & QDockWidget.DockWidgetFeature.DockWidgetMovable
                and features & QDockWidget.DockWidgetFeature.DockWidgetFloatable):
            return
        self.cancel()
        self.active_dock, self.bar, self._start = dock, bar, QPoint(point)
        self._offset = point - dock.mapToGlobal(QPoint(0, 0))
        self._moved = False

    def press_resize(self, dock, handle, point):
        if not dock.isFloating() or dock.isMaximized() or dock.isFullScreen():
            return
        self.cancel()
        self.active_dock, self.bar, self._start = dock, handle, QPoint(point)
        self._resize_edges = handle.edges
        self._resize_geometry = QRect(dock.geometry())
        handle.grabMouse()

    def _resize(self, point):
        dock, edges, original = self.active_dock, self._resize_edges, self._resize_geometry
        if not dock.isFloating() or not dock.isVisible() or dock.isMaximized() or dock.isFullScreen():
            self.cancel(restore=False)
            return
        delta = point - self._start
        minimum = dock.minimumSizeHint().expandedTo(dock.minimumSize())
        maximum = dock.maximumSize()
        rectangle = QRect(original)
        if edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            change = -delta.x() if edges & Qt.Edge.LeftEdge else delta.x()
            width = max(minimum.width(), min(maximum.width(), original.width() + change))
            rectangle.setWidth(width)
            if edges & Qt.Edge.LeftEdge:
                rectangle.moveRight(original.right())
        if edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            change = -delta.y() if edges & Qt.Edge.TopEdge else delta.y()
            height = max(minimum.height(), min(maximum.height(), original.height() + change))
            rectangle.setHeight(height)
            if edges & Qt.Edge.TopEdge:
                rectangle.moveBottom(original.bottom())
        dock.setGeometry(rectangle)

    def _begin_move(self):
        dock = self.active_dock
        self._previous = self.manager._previous
        self.manager._remember(self.manager.visible_panes())
        self._before = self.manager._previous
        self._moved = True
        with QSignalBlocker(dock):
            self.manager._leave_focus([dock])
            dock.setFloating(True)
            dock.showNormal()
            dock.show()
        self.bar.grabMouse()

    def _drop_target(self, point):
        from .workspace import snap_rectangle
        screen = QApplication.screenAt(point)
        if screen is None:
            return None
        # Screen edges win over Anki's docking edges when the app fills a screen.
        placement = (edge_placement(point, screen.geometry())
                     or edge_placement(point, screen.availableGeometry()))
        if placement:
            return ('screen', screen, placement, snap_rectangle(screen.availableGeometry(), placement))
        for dock in reversed(self.manager.visible_panes()):
            if dock is self.active_dock:
                continue
            mode = getattr(dock, '_pdf_focus_mode', None) or getattr(dock, '_epub_focus_mode', None)
            if dock.isFloating() and not (mode is not None and mode.active):
                continue
            host = mode.host if mode is not None and mode.active else dock
            area = QRect(host.mapToGlobal(QPoint(0, 0)), host.size())
            placement = edge_placement(point, area, margin=48)
            if placement:
                # Dock splits use halves; screen corners are the quarter targets.
                side = 'left' if 'left' in placement else 'right' if 'right' in placement else placement
                return ('pane', dock, side, snap_rectangle(area, side))
        main = self.manager.main
        if main.isVisible() and not main.isMinimized():
            area = QRect(main.mapToGlobal(QPoint(0, 0)), main.size())
            placement = edge_placement(point, area, margin=48)
            if placement:
                side = 'left' if 'left' in placement else 'right' if 'right' in placement else placement
                return ('main', main, side, snap_rectangle(area, side))
        return None

    def move(self, point):
        dock = self.active_dock
        if dock is None:
            return
        if self._resize_edges is not None:
            self._resize(point)
            return
        if not self._moved:
            if (point - self._start).manhattanLength() < QApplication.startDragDistance():
                return
            self._begin_move()
        dock.move(point - self._offset)
        self._target = self._drop_target(point)
        if self._target is not None:
            rectangle = self._target[3]
            minimum = dock.minimumSizeHint().expandedTo(dock.minimumSize())
            margins = dock.windowHandle().frameMargins()
            if (minimum.width() + margins.left() + margins.right() > rectangle.width()
                    or minimum.height() + margins.top() + margins.bottom() > rectangle.height()):
                self._target = None
        if self._target is None:
            self.outline.hide()
        else:
            self.outline.setGeometry(self._target[3])
            self.outline.show()
            self.outline.raise_()

    def release(self, point):
        dock = self.active_dock
        if dock is None:
            return
        if self._resize_edges is not None:
            self._resize(point)
            self._clear()
            return
        if self._moved:
            self.move(point)
            target = self._target
            if target is not None:
                kind, owner, placement, rectangle = target
                if kind == 'screen':
                    self.manager.snap(dock, placement, screen=owner)
                else:
                    self.manager.dock_at(dock, placement, target=owner if kind == 'pane' else None)
            keep = getattr(dock, 'keep_window', None)
            if callable(keep):
                keep()
            self.manager._previous = self._before
        self._clear()

    def _clear(self):
        self.outline.hide()
        if self.bar is not None:
            try:
                self.bar.releaseMouse()
            except RuntimeError:
                pass
        self.active_dock = self.bar = self._target = None
        self._resize_edges = None
        self._moved = False
        self._before = self._previous = None

    def cancel(self, *, restore=True):
        if restore and self._resize_edges is not None:
            self.active_dock.setGeometry(self._resize_geometry)
        if restore and self._moved:
            self.manager._previous = self._before
            self.manager.restore()
            self.manager._previous = self._previous
        self._clear()

    def toggle_float(self, dock):
        if not dock.features() & QDockWidget.DockWidgetFeature.DockWidgetFloatable:
            return
        self.manager._remember(self.manager.visible_panes())
        with QSignalBlocker(dock):
            self.manager._leave_focus([dock])
            dock.setFloating(not dock.isFloating())
            dock.show()
        keep = getattr(dock, 'keep_window', None)
        if callable(keep):
            keep()
