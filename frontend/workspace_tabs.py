"""Appearance and normal close actions for native workspace dock tabs."""
from collections import deque
from html import escape

from aqt.qt import (
    QAbstractButton, QColor, QColorDialog, QDialog, QDialogButtonBox, QDockWidget,
    QEvent, QFormLayout, QInputDialog, QLabel, QMenu, QPainter, QPalette,
    QSpinBox, QTabBar, Qt, QWidget, QObject, QTimer, QLineEdit, QListWidget,
    QListWidgetItem, QVBoxLayout, QIcon, QPixmap, QShortcut, QKeySequence,
)
from PyQt6 import sip

try:
    from ..backend.i18n import t
    from ..backend.workspace_layouts import TAB_OPTIONS, pane_kind, workspace_name
except ImportError:
    from backend.i18n import t
    from backend.workspace_layouts import TAB_OPTIONS, pane_kind, workspace_name


class _TabColors(QWidget):
    """Paint over colored tabs, preserving Qt's tab identities, input and buttons.

    A child overlay also works with Anki's stylesheet, which bypasses proxy
    styles for tab drawing. Mouse events still reach the original native bar.
    """
    def __init__(self, owner, bar):
        super().__init__(bar)
        self.owner = owner
        self.signature = None
        self.active = True
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        bar.installEventFilter(self)

    def sync(self):
        if not self.active:
            self.hide()
            return
        bar = self.parentWidget()
        tabs = [(bar.tabRect(i), bar.tabText(i),
                 getattr(self.owner.dock_for(bar, i), '_workspace_tab_color', '')) for i in range(bar.count())]
        signature = (tabs, tuple(bar.tabIcon(i).cacheKey() for i in range(bar.count())),
                     bar.currentIndex(), bar.rect(), bar.font(), bar.palette().cacheKey())
        if signature == self.signature:
            return
        self.signature = signature
        self.setGeometry(bar.rect())
        self.setVisible(any(color for _, _, color in tabs))
        self.raise_()
        for button in bar.findChildren(QAbstractButton):
            button.raise_()  # Keep native Close and overflow arrows above the colors.
        self.update()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Paint, QEvent.Type.Resize, QEvent.Type.LayoutRequest):
            self.sync()
        return False

    def paintEvent(self, event):
        bar = self.parentWidget()
        painter = QPainter(self)
        painter.setFont(bar.font())
        for index in range(bar.count()):
            color = QColor(getattr(self.owner.dock_for(bar, index), '_workspace_tab_color', ''))
            if not color.isValid():
                continue
            # Choose the higher WCAG contrast of black/white, including mid-tones.
            channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055)**2
                        for c in (color.redF(), color.greenF(), color.blueF())]
            luminance = sum(c * w for c, w in zip(channels, (.2126, .7152, .0722)))
            foreground = QColor('#000000' if luminance > .179 else '#ffffff')
            rect = bar.tabRect(index).adjusted(1, 1, -1, -1)
            painter.fillRect(rect, color)
            text = rect.adjusted(8, 2, -8, -2)
            for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
                button = bar.tabButton(index, side)
                if button is not None and button.isVisible():
                    if button.geometry().center().x() < rect.center().x():
                        text.setLeft(max(text.left(), button.geometry().right() + 5))
                    else:
                        text.setRight(min(text.right(), button.geometry().left() - 5))
            icon = bar.tabIcon(index)
            if not icon.isNull():
                size = bar.iconSize()
                icon.paint(painter, text.left(), text.center().y()-size.height()//2, size.width(), size.height())
                text.setLeft(text.left()+size.width()+5)
            painter.setPen(foreground)
            label = bar.fontMetrics().elidedText(bar.tabText(index), Qt.TextElideMode.ElideRight, max(0, text.width()))
            painter.drawText(text, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextHideMnemonic, label)
            if index == bar.currentIndex():
                painter.fillRect(rect.left()+4, rect.bottom()-2, max(0, rect.width()-8), 3, foreground)


class WorkspaceTabs(QObject):
    def __init__(self, manager):
        super().__init__(manager.main)
        self.manager = manager
        self.suspended = False
        self._refreshing = False
        self._closed = deque(maxlen=20)
        self._history_generation = 0
        self._reopening = False
        self._icons = {}
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def clear_history(self):
        self._closed.clear()
        self._history_generation += 1
        self._reopening = False

    def bar_for(self, dock):
        return next((bar for bar in self.manager.main.findChildren(QTabBar,
                     options=Qt.FindChildOption.FindDirectChildrenOnly)
                     if any(self.dock_for(bar, i) is dock for i in range(bar.count()))), None)

    def current(self):
        focus = self.manager.main.focusWidget()
        while focus is not None and focus is not self.manager.main:
            if isinstance(focus, QDockWidget) and self._live(focus) and not focus.visibleRegion().isEmpty():
                return focus
            focus = focus.parentWidget()
        anchor = self.manager._tab_anchor
        if self._live(anchor) and not anchor.visibleRegion().isEmpty():
            return anchor
        for bar in self.manager.main.findChildren(QTabBar, options=Qt.FindChildOption.FindDirectChildrenOnly):
            dock = self.dock_for(bar, bar.currentIndex())
            if dock is not None:
                return dock
        return None

    def select(self, dock):
        if not self._live(dock):
            return False
        self.collapse_group(dock, False)
        dock.show()
        dock.raise_()
        self.manager._tab_anchor = dock
        view = getattr(dock, '_view', None) or getattr(dock, 'view', None) or dock.widget()
        if isinstance(view, QWidget):
            view.setFocus(Qt.FocusReason.ShortcutFocusReason)
        return True

    def navigate(self, direction):
        current = self.current()
        bar = self.bar_for(current) if current is not None else None
        if bar is None:
            return False
        indexes = [i for i in range(bar.count()) if bar.isTabVisible(i)]
        if not indexes:
            return False
        index = indexes[(indexes.index(bar.currentIndex()) + direction) % len(indexes)]
        return self.select(self.dock_for(bar, index))

    def jump(self, index):
        dock = self.current()
        bar = self.bar_for(dock) if dock is not None else None
        return self.select(self.dock_for(bar, index)) if bar is not None else False

    def pin(self, dock, pinned):
        if self._live(dock):
            dock._workspace_tab_pinned = bool(pinned)
            self.refresh()

    def set_group(self, dock, name):
        if self._live(dock):
            dock._workspace_tab_group = workspace_name(name) or ''
            dock._workspace_tab_collapsed = False
            self.refresh()

    def new_group(self, dock):
        context = (self.manager._profile(), self.manager._generation)
        name, accepted = QInputDialog.getText(self.manager.main, t('workspace_new_group'), t('workspace_group_name'))
        if accepted and self._live(dock) and context == (self.manager._profile(), self.manager._generation):
            self.set_group(dock, name)

    def collapse_group(self, dock, collapsed):
        group = getattr(dock, '_workspace_tab_group', '')
        if not group:
            return
        bar = self.bar_for(dock)
        if bar is None:
            return
        for i in range(bar.count()):
            pane = self.dock_for(bar, i)
            if pane is not None and getattr(pane, '_workspace_tab_group', '') == group:
                pane._workspace_tab_collapsed = bool(collapsed)
        self.refresh()

    def _clicked(self, bar, index):
        dock = self.dock_for(bar, index)
        if dock is not None and getattr(dock, '_workspace_tab_collapsed', False):
            self.collapse_group(dock, False)

    def show_switcher(self):
        panes = self.manager.visible_panes()
        if not panes:
            return
        context = (self.manager._profile(), self.manager._generation)
        dialog = QDialog(self.manager.main)
        dialog.setWindowTitle(t('workspace_switch_tabs'))
        dialog.resize(520, 360)
        layout = QVBoxLayout(dialog)
        field = QLineEdit(dialog)
        field.setPlaceholderText(t('workspace_find_tabs'))
        field.setAccessibleName(t('workspace_find_tabs'))
        layout.addWidget(field)
        listing = QListWidget(dialog)
        listing.setAccessibleName(t('workspace_switch_tabs'))
        layout.addWidget(listing)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Open | QDialogButtonBox.StandardButton.Cancel)
        def accept_selected(*_):
            if listing.currentItem() is not None:
                dialog.accept()
        buttons.accepted.connect(accept_selected)
        buttons.rejected.connect(dialog.reject)
        listing.itemActivated.connect(accept_selected)
        field.returnPressed.connect(accept_selected)
        for key, delta in ((Qt.Key.Key_Down, 1), (Qt.Key.Key_Up, -1)):
            shortcut = QShortcut(QKeySequence(key), field)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(lambda delta=delta: listing.setCurrentRow(
                max(0, min(listing.count()-1, listing.currentRow()+delta))))
        layout.addWidget(buttons)
        def filter_tabs(query=''):
            listing.clear()
            for dock in panes:
                if not self._live(dock):
                    continue
                title, detail, icon = self.details(dock)
                text = title + ' — ' + detail.replace('<br>', ' · ')
                if query.casefold() not in (text + ' ' + getattr(dock, '_workspace_tab_group', '')).casefold():
                    continue
                item = QListWidgetItem(icon, text)
                item.setData(Qt.ItemDataRole.UserRole, panes.index(dock))
                listing.addItem(item)
            if listing.count():
                listing.setCurrentRow(0)
            buttons.button(QDialogButtonBox.StandardButton.Open).setEnabled(bool(listing.count()))
        field.textChanged.connect(filter_tabs)
        filter_tabs()
        field.setFocus()
        try:
            if (dialog.exec() == QDialog.DialogCode.Accepted and listing.currentItem() is not None
                    and context == (self.manager._profile(), self.manager._generation)):
                self.select(panes[listing.currentItem().data(Qt.ItemDataRole.UserRole)])
        finally:
            dialog.deleteLater()

    def close_many(self, dock, mode):
        bar = self.bar_for(dock)
        if bar is None:
            return 0
        panes = [self.dock_for(bar, i) for i in range(bar.count())]
        candidates = panes[panes.index(dock)+1:] if mode == 'right' else panes
        closed = 0
        for pane in candidates:
            if pane is None or (mode == 'others' and pane is dock) or not self._closable(pane):
                continue
            if not self.close(pane):
                break  # A cancelled draft prompt stops the whole bulk operation.
            closed += 1
        return closed

    def reopen(self):
        if self.suspended or self._reopening or not self._closed:
            return False
        profile, entry = self._closed[-1]
        if profile != self.manager._profile():
            return False
        generation = self._history_generation
        self._reopening = True
        def current():
            return profile == self.manager._profile() and generation == self._history_generation
        def ready(panes, missing):
            self._reopening = False
            if not current() or not panes:
                return
            self._closed.pop()
            for dock in panes:
                dock.show()
                self.manager.add_as_tab(dock)
                for key in TAB_OPTIONS:
                    setattr(dock, '_workspace_' + key, entry.get(key, ''))
                dock._workspace_apply_order = True
                dock._workspace_tab_collapsed = False
                self.select(dock)
            self.refresh()
        self.manager._content().restore([entry], current, ready)
        return True

    def eventFilter(self, watched, event):
        if (isinstance(watched, QDockWidget) and event.type() == QEvent.Type.Close
                and not self.suspended and self._live(watched)):
            profile, generation = self.manager._profile(), self._history_generation
            try:
                entries = self.manager.capture_entries([watched])
                entry = entries[0] | self.manager.tab_options(watched) | {'resume_position': True}
            except Exception:
                return False
            def retired():
                if (profile == self.manager._profile() and generation == self._history_generation
                        and (sip.isdeleted(watched) or watched.isHidden())):
                    self._closed.append((profile, entry))
            QTimer.singleShot(0, retired)
        return False

    def details(self, dock):
        kind = (pane_kind(dock.objectName()) or 'web').removesuffix('_reference')
        label = t('workspace_kind_' + kind)
        title = getattr(dock, '_workspace_tab_name', '') or getattr(dock, '_workspace_document_title', dock.windowTitle())
        parts = [label]
        try:
            entry = self.manager.capture_entries([dock])[0]
            if 'page' in entry:
                parts.append(t('workspace_page', number=entry['page']))
            if 'section' in entry:
                parts.append(t('workspace_section', number=entry['section']+1))
            if 'url' in entry:
                parts.append(entry['url'][:240])
        except Exception:
            pass
        state = ('failed' if getattr(dock, '_workspace_failed', False) else
                 'loading' if getattr(dock, '_workspace_loading', False) else
                 'unsaved' if getattr(dock, '_workspace_dirty', False) else '')
        if state:
            parts.append(t('workspace_status_' + state))
        if getattr(dock, '_workspace_tab_pinned', False):
            parts.append(t('workspace_pinned'))
        group = getattr(dock, '_workspace_tab_group', '')
        if group:
            parts.append(group)
        key = (kind, state)
        if key not in self._icons:
            image = QPixmap(32, 32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            color = '#b34336' if state == 'failed' else '#b07817' if state == 'unsaved' else '#406b91'
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(0, 0, 32, 32, 5, 5)
            painter.setPen(QColor('white'))
            font = painter.font()
            font.setPixelSize(23)
            font.setBold(True)
            painter.setFont(font)
            glyph = '!' if state == 'failed' else '*' if state == 'unsaved' else '…' if state == 'loading' else kind[0].upper()
            painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
            painter.end()
            image.setDevicePixelRatio(2)
            self._icons[key] = QIcon(image)
        return title, ' · '.join(parts), self._icons[key]

    def _live(self, dock):
        return (not sip.isdeleted(self.manager.main)
                and getattr(self.manager.main, '_incremento_workspace_layouts', None) is self.manager
                and dock is not None and not sip.isdeleted(dock) and not dock.isHidden()
                and self.manager.is_workspace_pane(dock)
                and self.manager.main.isAncestorOf(dock))

    def _apply_title(self, dock):
        title = getattr(dock, '_workspace_tab_name', '') or dock._workspace_document_title
        title = getattr(dock, '_workspace_group_display', '') or title
        if getattr(dock, '_workspace_dirty', False):
            title = '* ' + title
        if getattr(dock, '_workspace_tab_pinned', False):
            title = '• ' + title
        if dock.windowTitle() == title:
            return
        dock._workspace_setting_title = True
        try:
            # QMainWindow rebuilds native tab labels from this UI-only caption.
            # Keep the document title separately; never edit its file or note.
            dock.setWindowTitle(title)
        finally:
            dock._workspace_setting_title = False

    def _watch_title(self, dock):
        if getattr(dock, '_workspace_title_tracker', None) is self:
            return
        if not hasattr(dock, '_workspace_document_title'):
            dock._workspace_document_title = dock.windowTitle()
        dock._workspace_title_tracker = self
        dock.installEventFilter(self)
        def changed(title):
            if (getattr(dock, '_workspace_title_tracker', None) is self
                    and not getattr(dock, '_workspace_setting_title', False)):
                dock._workspace_document_title = title
                self._apply_title(dock)
        dock.windowTitleChanged.connect(changed)
        view = getattr(dock, '_view', None) or getattr(dock, 'view', None)
        if view is not None and hasattr(view, 'loadStarted') and hasattr(view, 'loadFinished'):
            def status(loading, failed=False):
                if not sip.isdeleted(dock) and getattr(dock, '_workspace_title_tracker', None) is self:
                    dock._workspace_loading, dock._workspace_failed = loading, failed
                    self.refresh()
            view.loadStarted.connect(lambda: status(True))
            view.loadFinished.connect(lambda ok: status(False, not ok))

    def dock_for(self, bar, index):
        if sip.isdeleted(self.manager.main) or not 0 <= index < bar.count():
            return None
        identity = bar.tabData(index)
        # Qt's native dock tabs store a quintptr identifying their dock. Compare
        # only against live owned widgets; never cast/dereference native data or
        # overwrite it. Titles and tab order cannot identify duplicate documents.
        if type(identity) is not int:
            return None
        return next((dock for dock in self.manager.main.findChildren(QDockWidget)
                     if self._live(dock) and sip.unwrapinstance(dock) == identity), None)

    @staticmethod
    def _closable(dock):
        return (not getattr(dock, '_workspace_tab_pinned', False)
                and bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable))

    def close(self, dock):
        if self._live(dock) and self._closable(dock):
            return dock.close()  # Preserve each pane's save/discard and cancelled-close behavior.
        return False

    def rename(self, dock):
        if not self._live(dock):
            return
        context = (self.manager._profile(), self.manager._generation)
        name, accepted = QInputDialog.getText(self.manager.main, t('workspace_rename_tab'),
            t('workspace_tab_name'), text=getattr(dock, '_workspace_tab_name', '') or dock.windowTitle())
        name = workspace_name(name)
        if (accepted and name is not None and self._live(dock)
                and context == (self.manager._profile(), self.manager._generation)):
            dock._workspace_tab_name = name
            self.refresh()

    def color(self, dock):
        context = (self.manager._profile(), self.manager._generation)
        initial = QColor(getattr(dock, '_workspace_tab_color', '') or '#b8d9f2')
        chosen = QColorDialog.getColor(initial, self.manager.main, t('workspace_tab_color'),
            QColorDialog.ColorDialogOption.DontUseNativeDialog)
        if (chosen.isValid() and self._live(dock)
                and context == (self.manager._profile(), self.manager._generation)):
            dock._workspace_tab_color = chosen.name()
            self.refresh()

    def _size_group(self, dock, size):
        for pane in [dock] + self.manager.main.tabifiedDockWidgets(dock):
            if self._live(pane):
                pane._workspace_tab_size = size
                pane._workspace_tab_adaptive = not bool(size)
        self.refresh()

    def resize(self, dock):
        context = (self.manager._profile(), self.manager._generation)
        dialog = QDialog(self.manager.main)
        dialog.setWindowTitle(t('workspace_resize_tabs'))
        layout = QFormLayout(dialog)
        help_text = QLabel(t('workspace_tab_size_help'))
        help_text.setWordWrap(True)
        layout.addRow(help_text)
        fields = []
        size = getattr(dock, '_workspace_tab_size', '') or [180, 32]
        for key, value, low, high in zip(('workspace_tab_width', 'workspace_tab_height'), size, (80, 24), (480, 80)):
            field = QSpinBox(dialog)
            field.setRange(low, high)
            field.setValue(value)
            field.setAccessibleName(t(key))
            layout.addRow(t(key), field)
            fields.append(field)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        try:
            if (dialog.exec() == QDialog.DialogCode.Accepted and self._live(dock)
                    and context == (self.manager._profile(), self.manager._generation)):
                self._size_group(dock, [field.value() for field in fields])
        finally:
            dialog.deleteLater()

    def context_menu(self, bar, position):
        dock = self.dock_for(bar, bar.tabAt(position))
        if dock is None:
            return
        context = (self.manager._profile(), self.manager._generation)
        menu = QMenu(self.manager.main)
        rename = menu.addAction(t('workspace_rename_tab'))
        reset = menu.addAction(t('workspace_reset_tab_name'))
        reset.setEnabled(bool(getattr(dock, '_workspace_tab_name', '')))
        menu.addSeparator()
        resize = menu.addAction(t('workspace_resize_tabs'))
        reset_size = menu.addAction(t('workspace_reset_tab_size'))
        reset_size.setEnabled(bool(getattr(dock, '_workspace_tab_size', '')))
        color = menu.addAction(t('workspace_tab_color'))
        reset_color = menu.addAction(t('workspace_reset_tab_color'))
        reset_color.setEnabled(bool(getattr(dock, '_workspace_tab_color', '')))
        menu.addSeparator()
        handlers = {}
        def command(owner, key, callback, enabled=True):
            action = owner.addAction(t(key))
            action.setEnabled(enabled)
            handlers[action] = callback
            return action
        command(menu, 'workspace_switch_tabs', self.show_switcher)
        command(menu, 'workspace_reopen_tab', self.reopen, bool(self._closed))
        pin = command(menu, 'workspace_pin_tab', lambda: self.pin(dock, not getattr(dock, '_workspace_tab_pinned', False)))
        pin.setCheckable(True)
        pin.setChecked(bool(getattr(dock, '_workspace_tab_pinned', False)))
        adaptive = command(menu, 'workspace_adaptive_tabs', lambda: self._size_group(dock, ''))
        adaptive.setCheckable(True)
        adaptive.setChecked(getattr(dock, '_workspace_tab_adaptive', True) is not False)
        groups = menu.addMenu(t('workspace_move_to_group'))
        command(groups, 'workspace_new_group', lambda: self.new_group(dock))
        command(groups, 'workspace_ungroup_tab', lambda: self.set_group(dock, ''),
                bool(getattr(dock, '_workspace_tab_group', '')))
        for name in dict.fromkeys(getattr(self.dock_for(bar, i), '_workspace_tab_group', '') for i in range(bar.count())):
            if name:
                action = groups.addAction(name.replace('&', '&&'))
                handlers[action] = lambda name=name: self.set_group(dock, name)
        command(menu, 'workspace_expand_group' if getattr(dock, '_workspace_tab_collapsed', False)
                else 'workspace_collapse_group', lambda: self.collapse_group(dock,
                    not getattr(dock, '_workspace_tab_collapsed', False)), bool(getattr(dock, '_workspace_tab_group', '')))
        menu.addSeparator()
        for mode in ('others', 'right', 'unpinned'):
            command(menu, 'workspace_close_' + mode, lambda mode=mode: self.close_many(dock, mode))
        menu.addSeparator()
        close = menu.addAction(t('workspace_close_tab'))
        close.setEnabled(self._closable(dock))
        try:
            selected = menu.exec(bar.mapToGlobal(position))
            if not self._live(dock) or context != (self.manager._profile(), self.manager._generation):
                return
            if selected is rename:
                self.rename(dock)
            elif selected is reset:
                dock._workspace_tab_name = ''
                self.refresh()
            elif selected is resize:
                self.resize(dock)
            elif selected is reset_size:
                self._size_group(dock, '')
            elif selected is color:
                self.color(dock)
            elif selected is reset_color:
                dock._workspace_tab_color = ''
                self.refresh()
            elif selected is close:
                self.close(dock)
            elif selected in handlers:
                handlers[selected]()
        finally:
            menu.deleteLater()

    def refresh(self):
        if self._refreshing or sip.isdeleted(self.manager.main):
            return
        if getattr(self.manager.main, '_incremento_workspace_layouts', None) is not self.manager:
            self._timer.stop()
            return
        self._refreshing = True
        try:
            self._refresh()
        finally:
            self._refreshing = False

    def _refresh(self):
        for key, action in getattr(self.manager, '_tab_actions', {}).items():
            if action.text() != t(key):
                action.setText(t(key))
        for dock in self.manager.main.findChildren(QDockWidget):
            if self.manager.is_workspace_pane(dock):
                self._watch_title(dock)
                self._apply_title(dock)
        for bar in self.manager.main.findChildren(QTabBar, options=Qt.FindChildOption.FindDirectChildrenOnly):
            docks = [self.dock_for(bar, index) for index in range(bar.count())]
            owned = getattr(bar, '_incremento_workspace_tabs', None) is self
            if not docks or any(dock is None for dock in docks):
                if owned and bar.tabsClosable():
                    bar.setTabsClosable(False)
                if owned:
                    if bar.styleSheet() != bar._workspace_original_style:
                        bar.setStyleSheet(bar._workspace_original_style)
                    bar._workspace_colors.active = False
                    bar._workspace_colors.hide()
                continue
            if not owned:
                previous = getattr(bar, '_workspace_colors', None)
                if previous is not None:
                    bar.removeEventFilter(previous)
                    previous.hide()
                    previous.deleteLater()
                bar._incremento_workspace_tabs = self
                bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                bar.customContextMenuRequested.connect(lambda position, b=bar:
                    self.context_menu(b, position) if getattr(b, '_incremento_workspace_tabs', None) is self else None)
                bar.tabCloseRequested.connect(lambda index, b=bar:
                    self.close(self.dock_for(b, index)) if getattr(b, '_incremento_workspace_tabs', None) is self else None)
                bar.tabBarDoubleClicked.connect(lambda index, b=bar:
                    self.rename(self.dock_for(b, index)) if getattr(b, '_incremento_workspace_tabs', None) is self else None)
                bar.tabMoved.connect(lambda *_: self.refresh())
                bar.tabBarClicked.connect(lambda index, b=bar: self._clicked(b, index))
                bar._workspace_original_style = getattr(bar, '_workspace_original_style', bar.styleSheet())
                bar._workspace_colors = _TabColors(self, bar)
            if not bar.tabsClosable():
                bar.setTabsClosable(True)
            bar.setMovable(True)
            bar._workspace_colors.active = True
            indexes = {dock: i for i, dock in enumerate(docks)}
            if any(getattr(d, '_workspace_apply_order', False) for d in docks):
                docks.sort(key=lambda d: getattr(d, '_workspace_tab_order', indexes[d])
                           if type(getattr(d, '_workspace_tab_order', None)) is int else indexes[d])
                for dock in docks:
                    dock._workspace_apply_order = False
                indexes = {dock: i for i, dock in enumerate(docks)}
            first = {}
            for dock in docks:
                group = getattr(dock, '_workspace_tab_group', '')
                first.setdefault(group or dock, indexes[dock])
            docks.sort(key=lambda d: (not bool(getattr(d, '_workspace_tab_pinned', False)),
                first[getattr(d, '_workspace_tab_group', '') or d], indexes[d]))
            for index, dock in enumerate(docks):
                old = next(i for i in range(bar.count()) if self.dock_for(bar, i) is dock)
                if old != index:
                    bar.moveTab(old, index)
            active = self.dock_for(bar, bar.currentIndex())
            groups = {}
            for dock in docks:
                dock._workspace_group_display = ''
                name = getattr(dock, '_workspace_tab_group', '')
                if name:
                    groups.setdefault(name, []).append(dock)
            hidden = set()
            for name, members in groups.items():
                folded = any(getattr(d, '_workspace_tab_collapsed', False) for d in members)
                representative = active if active in members else members[0]
                title = getattr(representative, '_workspace_tab_name', '') or representative._workspace_document_title
                representative._workspace_group_display = t('workspace_group_summary' if folded
                    else 'workspace_group_label', name=name, count=len(members), title=title)
                if folded:
                    hidden.update(d for d in members if d is not representative and not getattr(d, '_workspace_tab_pinned', False))
            for i, dock in enumerate(docks):
                visible = dock not in hidden
                if bar.isTabVisible(i) != visible:
                    bar.setTabVisible(i, visible)
                self._apply_title(dock)
            size = next((getattr(d, '_workspace_tab_size', '') for d in docks
                         if getattr(d, '_workspace_tab_size', '')), '')
            style = bar._workspace_original_style
            if size:
                width, height = size
                style += ('\nQTabBar::tab { padding: 0px; min-width: %dpx; max-width: %dpx; '
                          'min-height: %dpx; max-height: %dpx; }') % (width, width, height, height)
            elif all(getattr(d, '_workspace_tab_adaptive', True) is not False for d in docks):
                count = max(1, len(docks) - len(hidden))
                width = max(80, min(220, (max(d.width() for d in docks)-32)//count))
                style += '\nQTabBar::tab { min-width: 64px; max-width: %dpx; }' % width
            if bar.styleSheet() != style:
                bar.setStyleSheet(style)
            bar._workspace_colors.sync()
            for index, dock in enumerate(docks):
                title, detail, icon = self.details(dock)
                bar.setTabToolTip(index, '<qt><b>'+escape(title)+'</b><br>'+escape(detail)+'</qt>')
                if bar.tabIcon(index).cacheKey() != icon.cacheKey():
                    bar.setTabIcon(index, icon)
                for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
                    button = bar.tabButton(index, side)
                    if button is not None:
                        button.setVisible(self._closable(dock))
                        button.setToolTip(t('workspace_close_tab'))
                        button.setAccessibleName(t('workspace_close_tab'))
