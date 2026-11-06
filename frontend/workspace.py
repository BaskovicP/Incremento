"""Explicit, reversible layouts for Incremento panes; no operating-system automation."""
from contextlib import ExitStack
import base64
from weakref import WeakSet
from PyQt6 import sip

from aqt.qt import (
    QApplication, QByteArray, QDockWidget, QInputDialog, QMainWindow, QMenu,
    QRect, QSignalBlocker, QTabWidget, QTimer, Qt, QAction,
)

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.config_service import load_addon_config, save_addon_config
    from ..backend.workspace_layouts import TAB_OPTIONS, MAX_WORKSPACES, normalize_workspace, saved_workspaces, workspace_name
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.config_service import load_addon_config, save_addon_config
    from backend.workspace_layouts import TAB_OPTIONS, MAX_WORKSPACES, normalize_workspace, saved_workspaces, workspace_name

_ADDON_PKG = __name__.split('.')[0] if '.' in __name__ else 'incremento'


_PANE_NAMES = {
    'incremento_pdf_dock', 'incremento_epub_dock', 'incremento_writing_dock',
    'incremento_video_dock', 'incremento_web_dock', 'incremento_local_file_dock',
    'incremento_add_card_dock', 'incremento_search_dock',
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
        self._tabs = None
        self._session = session
        self._profile = profile
        self._generation = 0
        self.tabbed = False
        self._tab_members = WeakSet()
        self._tab_anchor = None
        self._session_profile = None
        self._restoring = False
        self._session_timer = QTimer(main)
        self._session_timer.setInterval(15000)
        self._session_timer.timeout.connect(self.save_last_session)
        main._incremento_workspace_layouts = self
        main.tabifiedDockWidgetActivated.connect(self._tab_activated)

    def _tab_activated(self, dock):
        if self.tabbed and dock in self._tab_members:
            self._tab_anchor = dock

    def add_as_tab(self, dock):
        """Join a newly opened pane without replacing the last explicit layout undo."""
        if (not self.tabbed or not self.is_workspace_pane(dock) or dock.parentWidget() is not self.main
                or not dock.features() & QDockWidget.DockWidgetFeature.DockWidgetMovable):
            return False
        panes = self.visible_panes()
        anchor = self._tab_anchor
        if anchor not in panes or anchor.isFloating():
            anchor = next((pane for pane in panes if pane in self._tab_members
                           and pane is not dock and not pane.isFloating()), None)
        keep = getattr(dock, 'keep_window', None)
        if callable(keep):
            keep()
        with ExitStack() as stack:
            for pane in set(panes + [dock]):
                stack.enter_context(QSignalBlocker(pane))
            self._leave_focus([dock])
            if anchor is not dock and (anchor is None or dock not in self.main.tabifiedDockWidgets(anchor)):
                self.main.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
                dock.setFloating(False)
                if anchor is not None:
                    self._tabify(anchor, dock)
            dock.show()
            dock.raise_()
        self._tab_members.add(dock)
        self._tab_anchor = dock
        return True

    def adopt_new_panes(self):
        if not self.tabbed or getattr(self.main, '_incremento_workspace_layouts', None) is not self:
            return
        panes = self.visible_panes()
        self._tab_members.intersection_update(panes)
        for dock in panes:
            if (dock not in self._tab_members
                    and getattr(dock, '_workspace_open_profile', self._profile()) == self._profile()):
                self.add_as_tab(dock)

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
        tab_options = {dock: self.tab_options(dock) for dock in panes}
        aliases = {pane_name: 'incremento_' + ('pdf_reference' if pane_name.startswith('incremento_pdf_reference_')
                    else 'epub_reference' if pane_name.startswith('incremento_epub_reference_') else 'search_dock')
                    + '_saved_' + str(index) for index, pane_name in enumerate(names.values())
                   if '_reference_' in pane_name or pane_name.startswith('incremento_search_dock')}
        try:
            for dock, pane_name in names.items():
                if pane_name in aliases:
                    with QSignalBlocker(dock):
                        dock.setObjectName(aliases[pane_name])
            snapshot = {'version': 1, 'state': base64.b64encode(bytes(self.main.saveState())).decode('ascii'),
                        'geometry': base64.b64encode(bytes(self.main.saveGeometry())).decode('ascii'),
                        'open_as_tabs': self.tabbed}
        finally:
            for dock, pane_name in names.items():
                with QSignalBlocker(dock):
                    dock.setObjectName(pane_name)
        def captured(entries):
            if generation != self._generation or profile != self._profile():
                return
            snapshot['panes'] = [entry | tab_options[dock] | {'name': aliases.get(entry['name'], entry['name'])}
                                 for dock, entry in zip(panes, entries)]
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
                if entry['kind'].endswith('_reference') or entry['kind'] == 'search':
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
        self._restore_snapshot(snapshot, done)

    def _restore_snapshot(self, snapshot, done=lambda ok, missing: None):
        self._restoring = True
        self._generation += 1
        generation, profile = self._generation, self._profile()
        def current():
            return (not sip.isdeleted(self.main) and generation == self._generation
                    and profile == self._profile())
        def opened(panes, missing):
            if not current():
                return
            self._restoring = False
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
                options = {entry['name']: entry for entry in snapshot['panes']}
                for dock in panes:
                    for key in TAB_OPTIONS:
                        setattr(dock, '_workspace_' + key, options.get(dock.objectName(), {}).get(key, ''))
                    dock._workspace_apply_order = True
                focused = {entry['name'] for entry in snapshot['panes'] if entry.get('focused')}
                for dock in panes:
                    mode = _focus(dock)
                    if mode is not None:
                        mode.set_enabled(dock.objectName() in focused)
                        mode.present(eligible=True, title=dock.windowTitle())
            groups = [dock for dock in panes if self.main.tabifiedDockWidgets(dock)]
            self.tabbed = snapshot.get('open_as_tabs', bool(groups))
            self._tab_members = WeakSet(self.visible_panes())
            self._tab_anchor = next((dock for dock in groups if not dock.visibleRegion().isEmpty()),
                                    groups[0] if groups else panes[0])
            if self._tabs is not None:
                self._tabs.refresh()
            done(ok, missing)
        self._content().restore(snapshot['panes'], current, opened)

    def tab_options(self, dock):
        options = {key: getattr(dock, '_workspace_' + key, '') for key in TAB_OPTIONS}
        if self._tabs is not None:
            bar = self._tabs.bar_for(dock)
            if bar is not None:
                options['tab_order'] = next(i for i in range(bar.count()) if self._tabs.dock_for(bar, i) is dock)
        return options

    def capture_entries(self, panes):
        content = self._content()
        capture = getattr(content, 'capture_immediate', None)
        if capture is not None:
            return capture(panes)
        result = []
        content.capture(panes, result.extend)
        return result

    def save_last_session(self):
        """Store only bounded descriptions and Qt geometry; content stays in its owner."""
        profile = self._profile()
        if self._restoring:
            return False
        if self._session_profile is not None and self._session_profile != profile:
            return False
        panes = self.visible_panes()
        try:
            entries = self.capture_entries(panes) if panes else []
            if len(entries) != len(panes):
                return False
            names = {dock: dock.objectName() for dock in panes}
            try:
                for index, dock in enumerate(panes):
                    kind = entries[index]['kind']
                    if kind in ('pdf_reference', 'epub_reference', 'search'):
                        with QSignalBlocker(dock):
                            dock.setObjectName('incremento_' + ('search_dock' if kind == 'search' else kind)
                                               + '_saved_' + str(index))
                snapshot = {'version': 1, 'state': base64.b64encode(bytes(self.main.saveState())).decode('ascii'),
                            'geometry': base64.b64encode(bytes(self.main.saveGeometry())).decode('ascii'),
                            'open_as_tabs': self.tabbed,
                            'panes': [entry | self.tab_options(dock) | {'name': dock.objectName(), 'resume_position': True}
                                      for dock, entry in zip(panes, entries)]}
            finally:
                for dock, name in names.items():
                    with QSignalBlocker(dock):
                        dock.setObjectName(name)
            clean = normalize_workspace(snapshot) if panes else None
            if panes and clean is None:
                return False
            config = load_addon_config(self.main.addonManager, _ADDON_PKG)
            sessions = config.setdefault('workspace_last_sessions', {})
            changed = sessions.get(profile) != clean
            if clean is None:
                sessions.pop(profile, None)
            else:
                sessions[profile] = clean
            if changed:
                save_addon_config(self.main.addonManager, _ADDON_PKG, config)
            if clean is not None:
                for dock, entry in zip(panes, clean['panes']):
                    if entry['kind'].endswith('_reference') or entry['kind'] == 'search':
                        dock._workspace_saved_name = entry['name']
            return True
        except Exception:
            return False

    def restore_last_session(self):
        config = load_addon_config(self.main.addonManager, _ADDON_PKG)
        snapshot = config.get('workspace_last_sessions', {}).get(self._profile())
        if snapshot is None:
            return False
        self.enable_dragging()
        def restored(ok, missing):
            if missing or not ok:
                from aqt.utils import tooltip
                tooltip(t('workspace_load_partial', count=missing) if missing else t('workspace_open_failed'))
        self._restore_snapshot(snapshot, restored)
        return True

    def start_profile(self):
        self._session_profile = self._profile()
        self.enable_dragging()
        self._tabs.suspended = False
        config = load_addon_config(self.main.addonManager, _ADDON_PKG)
        if config['workspace_restore_last_session']:
            self.restore_last_session()
        self._session_timer.start()

    def close_profile(self):
        self._session_timer.stop()
        if self._session_profile == self._profile():
            self.save_last_session()
        if self._tabs is not None:
            self._tabs.suspended = True

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
            from .workspace_tabs import WorkspaceTabs
            self._tabs = WorkspaceTabs(self)
            self._drag = WorkspaceDrag(self)

    @staticmethod
    def is_workspace_pane(dock):
        name = dock.objectName()
        return name in _PANE_NAMES or name.startswith(('incremento_pdf_reference_', 'incremento_epub_reference_',
                                                      'incremento_search_dock_'))

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
                          tuple(_focus(d) for d in panes if _focus(d) is not None and _focus(d).active), self.tabbed)
        # An explicitly arranged reference is part of the user's workspace,
        # rather than the disposable preview slot for the next PDF link.
        for dock in panes:
            keep = getattr(dock, 'keep_window', None)
            if callable(keep):
                keep()

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
        if self.tabbed:
            return self.add_as_tab(writing)
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
        if layout not in ('columns', 'rows', 'grid', 'tabs'):
            raise ValueError('Unknown workspace layout')
        panes = self.visible_panes() if panes is None else list(panes)
        if not panes or (len(panes) < 2 and layout != 'tabs' and not self.tabbed):
            return False
        if layout == 'tabs':
            self.enable_dragging()
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
            if layout == 'tabs':
                for dock in panes[1:]:
                    self._tabify(panes[0], dock)
                panes[0].raise_()
            elif layout == 'grid':
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
        self.tabbed = layout == 'tabs'
        self._tab_members = WeakSet(self.visible_panes())
        self._tab_anchor = panes[0] if self.tabbed else None
        return True

    def _tabify(self, target, dock):
        dock._workspace_tab_size = getattr(target, '_workspace_tab_size', '')
        dock._workspace_tab_adaptive = getattr(target, '_workspace_tab_adaptive', True)
        dock._workspace_tab_group = getattr(target, '_workspace_tab_group', '')
        self.main.setDockOptions(self.main.dockOptions() | QMainWindow.DockOption.AllowTabbedDocks)
        self.main.setTabPosition(self.main.dockWidgetArea(target), QTabWidget.TabPosition.North)
        self.main.tabifyDockWidget(target, dock)
        dock.show()
        dock.raise_()
        # Qt can leave a newly allocated dock tab bar hidden until the layout
        # is reapplied. Replay it here while the caller blocks pane signals.
        self.main.restoreState(self.main.saveState())
        if self._tabs is not None:
            self._tabs.refresh()

    def dock_at(self, dock, placement, *, target=None):
        if placement not in ('left', 'right', 'top', 'bottom', 'tab') or dock not in self.visible_panes():
            return False
        if placement == 'tab' and target is None:
            return False
        panes = self.visible_panes()
        if target is not None and (target not in panes or target is dock):
            return False
        self._remember(panes)
        with ExitStack() as stack:
            for pane in panes:
                stack.enter_context(QSignalBlocker(pane))
            self._leave_focus([dock] + ([target] if target is not None else []))
            if target is None:
                area = {'left': Qt.DockWidgetArea.LeftDockWidgetArea, 'right': Qt.DockWidgetArea.RightDockWidgetArea,
                        'top': Qt.DockWidgetArea.TopDockWidgetArea, 'bottom': Qt.DockWidgetArea.BottomDockWidgetArea}[placement]
                self.main.removeDockWidget(dock)
                self.main.addDockWidget(area, dock)
                dock.setFloating(False)
            else:
                dock.setFloating(False)
                target.setFloating(False)
                target.show()
                orientation = Qt.Orientation.Horizontal if placement in ('left', 'right') else Qt.Orientation.Vertical
                if placement == 'tab':
                    self._tabify(target, dock)
                elif placement in ('right', 'bottom'):
                    self.main.splitDockWidget(target, dock, orientation)
                else:
                    # Qt inserts after the first dock. Insert the dropped pane
                    # into the target's area, then split the target after it.
                    target_area = self.main.dockWidgetArea(target)
                    self.main.removeDockWidget(dock)
                    self.main.addDockWidget(target_area, dock)
                    self.main.splitDockWidget(target, dock, orientation)
                    self.main.splitDockWidget(dock, target, orientation)
                if placement != 'tab':
                    self.main.resizeDocks([dock, target], [1, 1], orientation)
            dock.show()
        self.tabbed = placement == 'tab'
        self._tab_members = WeakSet(self.visible_panes())
        self._tab_anchor = dock if self.tabbed else None
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
        state, original, focused, tabbed = self._previous
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
        self.tabbed = tabbed
        self._tab_members = WeakSet(self.visible_panes())
        self._tab_anchor = next((dock for dock in self.visible_panes()
                                 if not dock.isFloating() and self.main.tabifiedDockWidgets(dock)), None)
        return True

    def reset(self):
        self._generation += 1
        if self._drag is not None:
            self._drag.cancel(restore=False)
        self._previous = None
        self.tabbed = False
        self._tab_members.clear()
        self._tab_anchor = None
        self._session_timer.stop()
        self._session_profile = None
        self._restoring = False
        for dock in self.main.findChildren(QDockWidget):
            if self.is_workspace_pane(dock):
                for key in TAB_OPTIONS:
                    setattr(dock, '_workspace_' + key, '')
                dock._workspace_group_display = ''
        if self._tabs is not None:
            self._tabs.clear_history()
            self._tabs.refresh()


def add_workspace_menu(parent, manager, open_writing, open_pdf=None, register_action=None):
    """Rebuild window targets when shown, so closed windows cannot remain actionable."""
    manager.enable_dragging()
    menu = parent.addMenu(t('workspace_title'))
    menu.menuAction().setProperty('incremento_translation_key', 'workspace_title')
    tabs = manager._tabs
    commands = {
        'workspace_switch_tabs': tabs.show_switcher,
        'workspace_next_tab': lambda: tabs.navigate(1),
        'workspace_previous_tab': lambda: tabs.navigate(-1),
        'workspace_close_tab': lambda: tabs.close(tabs.current()),
        'workspace_reopen_tab': tabs.reopen,
    }
    commands.update({'workspace_tab_' + str(i+1): lambda i=i: tabs.jump(i) for i in range(9)})
    tab_actions = getattr(manager, '_tab_actions', {})
    for key, callback in commands.items():
        if key not in tab_actions:
            item = QAction(t(key), manager.main)
            item.setObjectName('incremento_' + key)
            item.setProperty('incremento_translation_key', key)
            item.triggered.connect(lambda checked=False, callback=callback: callback())
            manager.main.addAction(item)
            tab_actions[key] = item
        if register_action is not None:
            register_action(key, tab_actions[key])
    manager._tab_actions = tab_actions

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
        for key in ('workspace_switch_tabs', 'workspace_next_tab', 'workspace_previous_tab',
                    'workspace_close_tab', 'workspace_reopen_tab'):
            menu.addAction(tab_actions[key])
        jumps = menu.addMenu(t('workspace_jump_to_tab'))
        for i in range(9):
            jumps.addAction(tab_actions['workspace_tab_' + str(i+1)])
        menu.addSeparator()
        action(menu, 'workspace_restore_session', manager.restore_last_session)
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
        for layout in ('tabs', 'columns', 'rows', 'grid'):
            action(menu, 'workspace_' + layout, lambda value=layout: arrange(value),
                   bool(panes) if layout == 'tabs' or manager.tabbed else len(panes) >= 2)
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
