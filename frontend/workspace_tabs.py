"""Appearance and normal close actions for native workspace dock tabs."""
from aqt.qt import (
    QAbstractButton, QColor, QColorDialog, QDialog, QDialogButtonBox, QDockWidget,
    QEvent, QFormLayout, QInputDialog, QLabel, QMenu, QPainter, QPalette,
    QSpinBox, QTabBar, Qt, QWidget,
)
from PyQt6 import sip

try:
    from ..backend.i18n import t
    from ..backend.workspace_layouts import workspace_name
except ImportError:
    from backend.i18n import t
    from backend.workspace_layouts import workspace_name


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
        signature = (tabs, bar.currentIndex(), bar.rect(), bar.font(), bar.palette().cacheKey())
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


class WorkspaceTabs:
    def __init__(self, manager):
        self.manager = manager

    def _live(self, dock):
        return (dock is not None and not sip.isdeleted(dock) and not dock.isHidden()
                and self.manager.is_workspace_pane(dock)
                and self.manager.main.isAncestorOf(dock))

    def _apply_title(self, dock):
        title = getattr(dock, '_workspace_tab_name', '') or dock._workspace_document_title
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
        def changed(title):
            if (getattr(dock, '_workspace_title_tracker', None) is self
                    and not getattr(dock, '_workspace_setting_title', False)):
                dock._workspace_document_title = title
                self._apply_title(dock)
        dock.windowTitleChanged.connect(changed)

    def dock_for(self, bar, index):
        if not 0 <= index < bar.count():
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
        return bool(dock.features() & QDockWidget.DockWidgetFeature.DockWidgetClosable)

    def close(self, dock):
        if self._live(dock) and self._closable(dock):
            dock.close()  # Preserve each pane's save/discard and cancelled-close behavior.

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
        finally:
            menu.deleteLater()

    def refresh(self):
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
                bar._incremento_workspace_tabs = self
                bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                bar.customContextMenuRequested.connect(lambda position, b=bar: self.context_menu(b, position))
                bar.tabCloseRequested.connect(lambda index, b=bar: self.close(self.dock_for(b, index)))
                bar.tabBarDoubleClicked.connect(lambda index, b=bar: self.rename(self.dock_for(b, index)))
                bar._workspace_original_style = bar.styleSheet()
                bar._workspace_colors = _TabColors(self, bar)
            if not bar.tabsClosable():
                bar.setTabsClosable(True)
            bar._workspace_colors.active = True
            size = next((getattr(d, '_workspace_tab_size', '') for d in docks
                         if getattr(d, '_workspace_tab_size', '')), '')
            style = bar._workspace_original_style
            if size:
                width, height = size
                style += ('\nQTabBar::tab { padding: 0px; min-width: %dpx; max-width: %dpx; '
                          'min-height: %dpx; max-height: %dpx; }') % (width, width, height, height)
            if bar.styleSheet() != style:
                bar.setStyleSheet(style)
            bar._workspace_colors.sync()
            for index, dock in enumerate(docks):
                bar.setTabToolTip(index, dock.windowTitle())
                for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
                    button = bar.tabButton(index, side)
                    if button is not None:
                        button.setVisible(self._closable(dock))
                        button.setToolTip(t('workspace_close_tab'))
                        button.setAccessibleName(t('workspace_close_tab'))
