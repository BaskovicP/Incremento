"""Explicit, reversible layouts for Incremento panes; no operating-system automation."""
from contextlib import ExitStack
import base64

from aqt.qt import QApplication, QByteArray, QDockWidget, QInputDialog, QMenu, QRect, QSignalBlocker, Qt

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.config_service import load_addon_config, save_addon_config
    from ..backend.workspace_layouts import MAX_WORKSPACES, normalize_workspace, saved_workspaces, workspace_name
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.config_service import load_addon_config, save_addon_config
    from backend.workspace_layouts import MAX_WORKSPACES, normalize_workspace, saved_workspaces, workspace_name

_ADDON_PKG = __name__.split('.')[0] if '.' in __name__ else 'incremento'


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
    def __init__(self, main, *, session=None, profile=get_active_profile):
        self.main = main
        self._previous = None
        self._drag = None
        self._session = session
        self._profile = profile
        self._generation = 0

    def _content(self):
        if self._session is None:
            from .workspace_session import WorkspaceSession
            self._session = WorkspaceSession(self.main, self._profile)
        return self._session

    def saved_names(self):
        config = load_addon_config(self.main.addonManager, _ADDON_PKG)
        return sorted(saved_workspaces(config, self._profile()), key=str.casefold)

    def save_named(self, name, done=lambda ok: None):
        name = workspace_name(name)
        panes = self.visible_panes()
        if name is None or not panes:
            done(False)
            return
        self._generation += 1
        generation, profile = self._generation, self._profile()
        # Use stable layout slots instead of persisting reference bridge nonces.
        names = {dock: dock.objectName() for dock in panes}
        aliases = {pane_name: 'incremento_' + ('pdf_reference' if pane_name.startswith('incremento_pdf_reference_')
                    else 'epub_reference') + '_saved_' + str(index)
                   for index, pane_name in enumerate(names.values()) if '_reference_' in pane_name}
        try:
            for dock, pane_name in names.items():
                if pane_name in aliases:
                    with QSignalBlocker(dock):
                        dock.setObjectName(aliases[pane_name])
            snapshot = {'version': 1, 'state': base64.b64encode(bytes(self.main.saveState())).decode('ascii'),
                        'geometry': base64.b64encode(bytes(self.main.saveGeometry())).decode('ascii')}
        finally:
            for dock, pane_name in names.items():
                with QSignalBlocker(dock):
                    dock.setObjectName(pane_name)
        def captured(entries):
            if generation != self._generation or profile != self._profile():
                return
            snapshot['panes'] = [entry | {'name': aliases.get(entry['name'], entry['name'])} for entry in entries]
            clean = normalize_workspace(snapshot)
            if clean is None or len(entries) != len(panes):
                done(False)
                return
            try:
                config = load_addon_config(self.main.addonManager, _ADDON_PKG)
                layouts = config.setdefault('workspace_layouts', {}).setdefault(profile, {})
                if name not in layouts and len(layouts) >= MAX_WORKSPACES:
                    done(False)
                    return
                layouts[name] = clean
                save_addon_config(self.main.addonManager, _ADDON_PKG, config)
            except Exception:
                done(False)
                return
            for dock, entry in zip(panes, clean['panes']):
                if entry['kind'].endswith('_reference'):
                    dock._workspace_saved_name = entry['name']
            done(True)
        self._content().capture(panes, captured)

    def delete_named(self, name):
        try:
            config = load_addon_config(self.main.addonManager, _ADDON_PKG)
            layouts = config.get('workspace_layouts', {}).get(self._profile(), {})
            if name not in layouts:
                return False
            del layouts[name]
            save_addon_config(self.main.addonManager, _ADDON_PKG, config)
        except Exception:
            return False
        return True

    def load_named(self, name, done=lambda ok, missing: None):
        config = load_addon_config(self.main.addonManager, _ADDON_PKG)
        snapshot = saved_workspaces(config, self._profile()).get(name)
        if snapshot is None:
            done(False, 0)
            return
        self._generation += 1
        generation, profile = self._generation, self._profile()
        def current():
            return generation == self._generation and profile == self._profile()
        def opened(panes, missing):
            if not current():
                return
            if not panes:
                done(False, missing)
                return
            self._remember(self.visible_panes())
            live = self.main.findChildren(QDockWidget)
            extra = [dock for dock in self.visible_panes() if dock not in panes]
            with ExitStack() as stack:
                for dock in live:
                    stack.enter_context(QSignalBlocker(dock))
                self._leave_focus(self.visible_panes())
                self.main.restoreGeometry(QByteArray(base64.b64decode(snapshot['geometry'])))
                ok = self.main.restoreState(QByteArray(base64.b64decode(snapshot['state'])))
                for dock in panes + extra:
                    dock.show()
                    self._keep_on_screen(dock)
                focused = {entry['name'] for entry in snapshot['panes'] if entry.get('focused')}
                for dock in panes:
                    mode = _focus(dock)
                    if mode is not None:
                        mode.set_enabled(dock.objectName() in focused)
                        mode.present(eligible=True, title=dock.windowTitle())
            done(ok, missing)
        self._content().restore(snapshot['panes'], current, opened)

    @staticmethod
    def _keep_on_screen(dock):
        if not dock.isFloating():
            return
        rectangle = dock.frameGeometry()
        screens = QApplication.screens()
        if any(screen.availableGeometry().intersects(rectangle) for screen in screens):
            return
        screen = dock.screen() or QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            dock.resize(min(dock.width(), area.width()), min(dock.height(), area.height()))
            dock.move(area.topLeft())

    def enable_dragging(self):
        if self._drag is None:
            from .workspace_drag import WorkspaceDrag
            self._drag = WorkspaceDrag(self)

    @staticmethod
    def is_workspace_pane(dock):
        name = dock.objectName()
        return name in _PANE_NAMES or name.startswith(('incremento_pdf_reference_', 'incremento_epub_reference_'))

    def visible_panes(self):
        panes = []
        for dock in self.main.findChildren(QDockWidget):
            if not self.is_workspace_pane(dock):
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

    def dock_at(self, dock, placement, *, target=None):
        if placement not in ('left', 'right', 'top', 'bottom') or dock not in self.visible_panes():
            return False
        panes = self.visible_panes()
        if target is not None and (target not in panes or target is dock):
            return False
        self._remember(panes)
        with ExitStack() as stack:
            for pane in panes:
                stack.enter_context(QSignalBlocker(pane))
            self._leave_focus([dock] + ([target] if target is not None else []))
            area = {'left': Qt.DockWidgetArea.LeftDockWidgetArea, 'right': Qt.DockWidgetArea.RightDockWidgetArea,
                    'top': Qt.DockWidgetArea.TopDockWidgetArea, 'bottom': Qt.DockWidgetArea.BottomDockWidgetArea}[placement]
            if target is None:
                self.main.removeDockWidget(dock)
                self.main.addDockWidget(area, dock)
                dock.setFloating(False)
            else:
                dock.setFloating(False)
                target.setFloating(False)
                target.show()
                orientation = Qt.Orientation.Horizontal if placement in ('left', 'right') else Qt.Orientation.Vertical
                if placement in ('right', 'bottom'):
                    self.main.splitDockWidget(target, dock, orientation)
                else:
                    # Qt inserts after the first dock. Insert the dropped pane
                    # into the target's area, then split the target after it.
                    target_area = self.main.dockWidgetArea(target)
                    self.main.removeDockWidget(dock)
                    self.main.addDockWidget(target_area, dock)
                    self.main.splitDockWidget(target, dock, orientation)
                    self.main.splitDockWidget(dock, target, orientation)
                self.main.resizeDocks([dock, target], [1, 1], orientation)
            dock.show()
        return True

    def snap(self, dock, placement, *, screen=None):
        if dock not in self.visible_panes():
            return False
        screen = screen or (dock.screen() if dock.isFloating() else self.main.screen())
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
        self._generation += 1
        if self._drag is not None:
            self._drag.cancel(restore=False)
        self._previous = None


def add_workspace_menu(parent, manager, open_writing, open_pdf=None):
    """Rebuild window targets when shown, so closed windows cannot remain actionable."""
    manager.enable_dragging()
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

    def saved(ok):
        from aqt.utils import tooltip
        tooltip(t('workspace_saved' if ok else 'workspace_save_failed'))

    def save():
        from aqt.utils import askUser
        name, accepted = QInputDialog.getText(manager.main, t('workspace_save'), t('workspace_name'))
        if not accepted:
            return
        name = workspace_name(name)
        if name is None:
            saved(False)
            return
        if name in manager.saved_names() and not askUser(t('workspace_replace', name=name), parent=manager.main):
            return
        manager.save_named(name, saved)

    def load(name):
        def finished(ok, missing):
            from aqt.utils import tooltip
            tooltip(t('workspace_load_partial', count=missing) if missing else
                    t('workspace_loaded' if ok else 'workspace_open_failed'))
        manager.load_named(name, finished)

    def delete(name):
        from aqt.utils import askUser, tooltip
        if askUser(t('workspace_delete_confirm', name=name), parent=manager.main):
            if not manager.delete_named(name):
                tooltip(t('workspace_save_failed'))

    def rebuild():
        menu.clear()
        if open_pdf is not None:
            action(menu, 'workspace_open_pdf_window', open_pdf)
        action(menu, 'workspace_write_beside', open_writing)
        menu.addSeparator()
        panes = manager.visible_panes()
        action(menu, 'workspace_save', save, bool(panes))
        names = manager.saved_names()
        saved_menu = menu.addMenu(t('workspace_load'))
        delete_menu = menu.addMenu(t('workspace_delete'))
        saved_menu.setEnabled(bool(names))
        delete_menu.setEnabled(bool(names))
        for name in names:
            for owner, callback in ((saved_menu, load), (delete_menu, delete)):
                item = owner.addAction(name.replace('&', '&&'))
                item.triggered.connect(lambda checked=False, value=name, cb=callback: cb(value))
        menu.addSeparator()
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
