"""Native widgets for the approved compact resource picker and inline file rows."""
from aqt.qt import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                    QPushButton, QScrollArea, QShortcut, QKeySequence, QSize, QSizePolicy,
                    QSpinBox, QStyle, QVBoxLayout, QWidget, Qt, QEvent, QPainter, QIcon, pyqtSignal)

try:
    from ..backend.i18n import t
    from .recording_player import timestamp
    from .study_resource_titles import display_resource_title
except ImportError:
    from backend.i18n import t
    from frontend.recording_player import timestamp
    from frontend.study_resource_titles import display_resource_title


class ElidedLabel(QLabel):
    """Keep the full accessible title while preventing filenames from widening a pane."""
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)
        self.setAccessibleName(text)

    def displayedText(self):
        return self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, max(0, self.contentsRect().width()))

    def minimumSizeHint(self):
        return QSize(0, self.fontMetrics().height() + 4)

    def sizeHint(self):
        return QSize(min(400, self.fontMetrics().horizontalAdvance(self.text())), self.fontMetrics().height() + 4)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(self.contentsRect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.displayedText())


class StageButton(QPushButton):
    """One navigation button with an inline, separately styled resource count."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._title, self._count, self._icon = title, None, QIcon()
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(7)
        self.icon_label = QLabel(self)
        self.title_label = QLabel(title, self)
        self.title_label.setObjectName('study-stage-title')
        self.count_label = QLabel(self)
        self.count_label.setObjectName('study-stage-count')
        self.count_label.hide()
        for label in (self.icon_label, self.title_label, self.count_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            row.addWidget(label)
        self.setAutoDefault(False)
        self.toggled.connect(self._refresh_icon)

    def set_title_count(self, title, count=None):
        self._title, self._count = title, count
        self.title_label.setText(title)
        self.count_label.setText(str(count) if count is not None else '')
        self.count_label.setVisible(count is not None)
        self.setAccessibleName(self.text())
        self.updateGeometry()

    def setText(self, title):
        self.set_title_count(title, self._count)

    def text(self):
        return self._title + (' ' + str(self._count) if self._count is not None else '')

    def setIcon(self, icon):
        self._icon = icon
        self._refresh_icon()

    def _refresh_icon(self, *_):
        self.icon_label.setPixmap(self._icon.pixmap(16, 16, QIcon.Mode.Normal,
            QIcon.State.On if self.isChecked() else QIcon.State.Off))

    def icon(self):
        return self._icon

    def sizeHint(self):
        return self.layout().minimumSize()

    def minimumSizeHint(self):
        return self.sizeHint()


class ResourceButton(QPushButton):
    """A button whose native size hint includes its two-line child layout."""
    def sizeHint(self):
        return self.layout().sizeHint()

    def minimumSizeHint(self):
        return self.layout().minimumSize()


class ResourcePicker(QWidget):
    activated = pyqtSignal(int)
    linkRequested = pyqtSignal()
    manageRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('study-resource-picker')
        self._entries, self._index, self._generation = [], -1, 0
        self._signature = None
        self.resource_buttons = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle_button = ResourceButton(self)
        self.toggle_button.setObjectName('study-picker-trigger')
        self.toggle_button.setCheckable(True)
        self.toggle_button.setAutoDefault(False)
        self.toggle_button.toggled.connect(self.setExpanded)
        self.toggle_button.installEventFilter(self)
        row = QHBoxLayout(self.toggle_button)
        row.setContentsMargins(14, 10, 14, 10)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        self.title = ElidedLabel('', self.toggle_button)
        self.title.setObjectName('study-picker-title')
        self.detail = ElidedLabel('', self.toggle_button)
        self.detail.setObjectName('study-picker-detail')
        for label in (self.title, self.detail):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            copy.addWidget(label)
        row.addLayout(copy, 1)
        arrow = QLabel(self.toggle_button)
        arrow.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown).pixmap(12, 12))
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(arrow)
        layout.addWidget(self.toggle_button)
        self.panel = QFrame(self)
        self.panel.setObjectName('study-picker-list')
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(5, 5, 5, 5)
        panel_layout.setSpacing(2)
        self.list_scroll = QScrollArea(self.panel)
        self.list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_scroll.setMaximumHeight(270)
        self.list_host = QWidget(self.list_scroll)
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_scroll.setWidget(self.list_host)
        panel_layout.addWidget(self.list_scroll)
        self.link_button = QPushButton(t('study_link_resources'), self.panel)
        self.manage_button = QPushButton(t('study_manage_links'), self.panel)
        for button, signal in ((self.link_button, self.linkRequested), (self.manage_button, self.manageRequested)):
            button.setObjectName('study-picker-action')
            button.setAutoDefault(False)
            button.installEventFilter(self)
            button.clicked.connect(lambda _=False, signal=signal: self._action(signal))
            panel_layout.addWidget(button)
        layout.addWidget(self.panel)
        self.panel.hide()
        self.escape = QShortcut(QKeySequence('Esc'), self)
        self.escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.escape.activated.connect(lambda: self.setExpanded(False))
        self.escape.setEnabled(False)

    def _action(self, signal):
        self.setExpanded(False)
        signal.emit()

    def setExpanded(self, expanded):
        self.toggle_button.blockSignals(True)
        self.toggle_button.setChecked(expanded)
        self.toggle_button.blockSignals(False)
        self.panel.setVisible(expanded)
        self.escape.setEnabled(expanded)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() == Qt.Key.Key_Escape and self.panel.isVisible():
            if event.type() == QEvent.Type.KeyPress:
                self.setExpanded(False)
            event.accept()
            return True
        if watched is self.toggle_button and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            self.setExpanded(True)
            first = next((button for button in self.resource_buttons if button.isEnabled()), self.link_button)
            first.setFocus()
            return True
        return super().eventFilter(watched, event)

    def set_entries(self, entries, index, *, placeholder='', caption_detail=None):
        signature = tuple((entry['title'], entry.get('full_title'), entry['detail'], entry['available'], entry['icon'].cacheKey()) for entry in entries)
        if signature != self._signature:
            self._signature = signature
            self._generation += 1
            generation = self._generation
            self._entries = [dict(entry) for entry in entries]
            while self.list_layout.count():
                item = self.list_layout.takeAt(0)
                item.widget().deleteLater()
            self.resource_buttons = []
            for position, entry in enumerate(entries):
                button = ResourceButton(self.list_host)
                button.setAutoDefault(False)
                button.installEventFilter(self)
                button.setObjectName('study-picker-resource')
                button.setEnabled(entry['available'])
                button.setAccessibleName(entry['title'] + ' · ' + entry['detail'])
                button.setToolTip(entry.get('full_title', entry['title']) + '\n' + entry['detail'])
                body = QHBoxLayout(button)
                body.setContentsMargins(12, 9, 12, 9)
                icon = QLabel(button)
                icon.setPixmap(entry['icon'].pixmap(18, 18))
                body.addWidget(icon)
                copy = QVBoxLayout()
                copy.setSpacing(3)
                title = ElidedLabel(entry['title'], button)
                title.setObjectName('study-picker-title')
                detail = ElidedLabel(entry['detail'], button)
                detail.setObjectName('study-picker-detail')
                copy.addWidget(title)
                copy.addWidget(detail)
                body.addLayout(copy, 1)
                check = QLabel(button)
                check.setObjectName('study-picker-check')
                check.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton).pixmap(16, 16))
                body.addWidget(check)
                for label in (icon, title, detail, check):
                    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                button.clicked.connect(lambda _=False, position=position, generation=generation:
                    self._choose(position, generation))
                self.resource_buttons.append(button)
                self.list_layout.addWidget(button)
            for button in self.resource_buttons:
                button.ensurePolished()
            list_height = sum(button.sizeHint().height() for button in self.resource_buttons)
            list_height += max(0, len(entries)-1) * self.list_layout.spacing()
            self.list_scroll.setFixedHeight(min(270, max(1, list_height)))
            self.list_scroll.setVisible(bool(entries))
        self._index = index if 0 <= index < len(entries) else -1
        active = entries[self._index] if self._index >= 0 else None
        self.title.setText(active['title'] if active else t('study_choose_resource_title'))
        self.detail.setText(caption_detail if active and caption_detail else active['detail'] if active else placeholder)
        self.toggle_button.setAccessibleName(self.currentText())
        self.toggle_button.setAccessibleDescription(t('study_choose_resources'))
        self.toggle_button.setToolTip((active.get('full_title', active['title']) + '\n' + self.detail.text()) if active else self.currentText())
        for position, button in enumerate(self.resource_buttons):
            button.setProperty('selected', position == self._index)
            button.findChild(QLabel, 'study-picker-check').setVisible(position == self._index)
            button.style().unpolish(button)
            button.style().polish(button)

    def _choose(self, index, generation):
        if generation == self._generation and self._entries[index]['available']:
            self.setExpanded(False)
            self.activated.emit(index)

    def count(self):
        return len(self._entries)

    def itemText(self, index):
        entry = self._entries[index]
        return entry['title'] + '\n' + entry['detail']

    def currentText(self):
        return self.title.text() + '\n' + self.detail.text()


class LibraryResourceRow(QFrame):
    checked = pyqtSignal(bool)
    edited = pyqtSignal()
    previewRequested = pyqtSignal()
    positionRequested = pyqtSignal()

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.setObjectName('study-library-row')
        self.row, self.extra, self._filling = dict(row), {}, False
        self._editors_built = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 12, 0, 12)
        heading = QHBoxLayout()
        heading.setSpacing(10)
        self.check_box = QCheckBox(self)
        self.check_box.setAccessibleName(row['title'])
        self.check_box.setEnabled(row['available'])
        heading.addWidget(self.check_box, 0, Qt.AlignmentFlag.AlignTop)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        self.title = ElidedLabel(display_resource_title(row['title']), self)
        self.title.setToolTip(row['title'])
        self.title.setObjectName('study-picker-title')
        self.kind_label = QLabel(t('study_kind_' + row['kind']) +
            ('' if row['available'] else ' · ' + t('study_missing')), self)
        self.kind_label.setObjectName('study-picker-detail')
        for label in (self.title, self.kind_label):
            label.installEventFilter(self)
            copy.addWidget(label)
        heading.addLayout(copy, 1)
        outer.addLayout(heading)
        self.fields = QWidget(self)
        self.fields_layout = QVBoxLayout(self.fields)
        self.fields_layout.setContentsMargins(26, 0, 0, 0)
        self.fields_layout.setSpacing(8)
        outer.addWidget(self.fields)
        self.fields.hide()
        self.check_box.toggled.connect(self._checked)

    def eventFilter(self, watched, event):
        if watched in (self.title, self.kind_label) and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton and self.check_box.isEnabled():
                self.check_box.toggle()
                return True
        return super().eventFilter(watched, event)

    def _checked(self, checked):
        if checked:
            self._build_editors()
        self.fields.setVisible(checked)
        self.checked.emit(checked)

    def _build_editors(self):
        if self._editors_built:
            return
        self._editors_built = True
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(12)
        self.page = QSpinBox(self.fields)
        self.page.setRange(1, 1_000_000)
        self.page.setValue(1)
        self.start = QLineEdit('0:00', self.fields)
        self.end = QLineEdit(self.fields)
        self.label = QLineEdit(self.fields)
        # Editors not used for this media kind must not become orphaned visible
        # children when the inline field container is shown.
        for editor in ((self.start, self.end) if self.row['kind'] == 'pdf' else (self.page,)):
            editor.hide()
        self.label.setMaxLength(240)
        self.field_hosts = []
        specifications = [('study_resource_page', self.page)] if self.row['kind'] == 'pdf' else [
            ('study_start', self.start), ('study_end', self.end)]
        specifications.append(('study_optional_label', self.label))
        for key, editor in specifications:
            host = QWidget(self.fields)
            layout = QVBoxLayout(host)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            label = QLabel(t(key), host)
            label.setObjectName('study-picker-detail')
            label.setBuddy(editor)
            editor.setAccessibleName(t(key) + ' · ' + self.row['title'])
            layout.addWidget(label)
            layout.addWidget(editor)
            self.field_hosts.append(host)
        self.fields_layout.addLayout(self.grid)
        self.error = QLabel('', self.fields)
        self.error.setObjectName('study-field-error')
        self.error.setWordWrap(True)
        self.error.hide()
        self.fields_layout.addWidget(self.error)
        actions = QHBoxLayout()
        self.preview_button = QPushButton(t('study_preview_short'), self.fields)
        self.preview_button.clicked.connect(self.previewRequested)
        self.position_button = QPushButton(t('study_use_position'), self.fields)
        self.position_button.clicked.connect(self.positionRequested)
        for button in (self.preview_button, self.position_button):
            button.setObjectName('study-quiet-action')
            button.setAutoDefault(False)
            actions.addWidget(button)
        actions.addStretch(1)
        self.fields_layout.addLayout(actions)
        self.preview_host = QVBoxLayout()
        self.fields_layout.addLayout(self.preview_host)
        self.page.valueChanged.connect(self._edited)
        for edit in (self.start, self.end, self.label):
            edit.textChanged.connect(self._edited)
        self._layout_fields()

    def _edited(self, *_):
        if not self._filling:
            self.edited.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._editors_built:
            self._layout_fields()

    def _layout_fields(self):
        narrow = self.width() < 540 and len(self.field_hosts) == 3
        for host in self.field_hosts:
            self.grid.removeWidget(host)
        for index, host in enumerate(self.field_hosts):
            if narrow and index == 2:
                self.grid.addWidget(host, 1, 0, 1, 2)
            else:
                self.grid.addWidget(host, 0, index)
        for index in range(3):
            self.grid.setColumnStretch(index, 1 if (narrow or index == len(self.field_hosts)-1) else 0)
        for host in self.field_hosts[:-1]:
            host.setMaximumWidth(16777215 if narrow else 140)

    def set_values(self, data):
        self._build_editors()
        self._filling = True
        self.extra = dict(data)
        self.page.setValue(data.get('page', 1))
        self.start.setText(data.get('start_text', timestamp(data.get('start', 0))))
        self.end.setText(data.get('end_text', timestamp(data['end']) if data.get('end') is not None else ''))
        self.label.setMaxLength(2000 if self.row['kind'] == 'pdf' and data.get('link_id') else 240)
        self.label.setText(data.get('label', ''))
        self._filling = False

    def values(self):
        self._build_editors()
        data = dict(self.extra, kind=self.row['kind'], card_id=self.row['card_id'], page=self.page.value(),
                    start_text=self.start.text(), end_text=self.end.text(), label=self.label.text())
        if self.row['kind'] == 'pdf' and self.page.value() != self.extra.get('page', 1):
            data['scroll'], data['page_y'] = 0, None
            data.pop('snapshot', None)
        return data


def resource_styles(colors):
    c = colors
    return f"""
        QWidget#study-resource-sheet {{ background:{c['surface']}; color:{c['ink']}; }}
        QPushButton#study-picker-trigger, QFrame#study-picker-list {{ background:{c['paper']}; color:{c['ink']};
            border:1px solid {c['border']}; border-radius:8px; }}
        QPushButton#study-picker-trigger:focus {{ border-color:{c['accent']}; }}
        QLabel#study-picker-title {{ color:{c['ink']}; font-weight:500; border:0; background:transparent; }}
        QLabel#study-picker-detail {{ color:{c['foreground']}; border:0; background:transparent; }}
        QPushButton#study-picker-resource {{ background:transparent; color:{c['ink']}; border:0; border-radius:6px; }}
        QPushButton#study-picker-resource[selected="true"] {{ background:{c['selected']}; }}
        QPushButton#study-picker-resource:hover {{ background:{c['surface']}; }}
        QPushButton#study-picker-action {{ color:{c['foreground']}; background:transparent; border:0;
            border-top:1px solid {c['border']}; border-radius:0; text-align:left; padding:10px 12px; }}
        QFrame#study-library-row {{ background:transparent; border:0; border-bottom:1px solid {c['border']}; }}
        QFrame#study-card-target {{ background:{c['paper']}; border:1px solid {c['border']}; border-radius:8px; }}
        QFrame#study-link-preview {{ background:{c['paper']}; border:1px solid {c['border']}; border-radius:10px; }}
        QFrame#study-link-preview QFrame#study-card-target {{ background:{c['surface']}; }}
        QPushButton#study-draft-link {{ background:transparent; border:1px solid transparent; border-radius:6px; }}
        QPushButton#study-draft-link[selected="true"] {{ background:{c['selected']}; border-color:{c['border']}; }}
        QLabel#study-field-error {{ color:{'#f4b2b5' if c['surface'] == '#25272b' else '#a42936'}; }}
        QScrollArea#study-sheet-scroll, QWidget#study-sheet-list {{ background:transparent; border:0; }}
        QPushButton#study-primary-action {{ background:{c['selected']}; color:{c['accent']};
            border:1px solid {c['border']}; border-radius:7px; padding:8px 12px; }}
        QPushButton#study-quiet-action {{ background:transparent; color:{c['foreground']}; border:0; padding:7px 10px; }}
        QPushButton#study-quiet-action:hover {{ background:{c['paper']}; }}
        QPushButton#study-quiet-action:focus {{ border:1px solid {c['accent']}; }}
    """
