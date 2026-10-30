"""A live, unsaved card-to-resource preview and bounded PDF page rendering."""
from aqt.qt import (QFrame, QHBoxLayout, QLabel, QLayout, QPainter, QPushButton, QSize,
                    QSizePolicy, QVBoxLayout, QWidget, Qt, pyqtSignal)

try:
    from ..backend.i18n import t
    from .study_resource_widgets import ElidedLabel, ResourceButton
except ImportError:
    from backend.i18n import t
    from frontend.study_resource_widgets import ElidedLabel, ResourceButton


def render_link_page(snapshot, page):
    """Run in the task worker; render one validated page without persisting a cover."""
    from PyQt6.QtPdf import QPdfDocument
    document = QPdfDocument(None)
    try:
        document.load(snapshot['path'])
        maximum = min(document.pageCount(), snapshot['max_page'])
        if maximum < 1:
            raise ValueError('PDF unavailable')
        if page > maximum:
            return dict(image=None, maximum=maximum)
        point = document.pagePointSize(page-1)
        if point.width() <= 0 or point.height() <= 0:
            raise ValueError('PDF page unavailable')
        scale = min(800/point.width(), 1000/point.height())
        image = document.render(page-1, QSize(max(1, round(point.width()*scale)),
                                             max(1, round(point.height()*scale))))
        if image.isNull():
            raise ValueError('PDF preview unavailable')
        return dict(image=image, maximum=maximum)
    finally:
        document.close()


class PageImage(QWidget):
    """Fit a page inside the preview without allowing its pixels to widen the sheet."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.setMinimumHeight(280)
        self.setMaximumHeight(420)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_image(self, image):
        self.image = image
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        if self.image is None:
            return
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        painter = QPainter(self)
        x, y = (self.width()-size.width())//2, (self.height()-size.height())//2
        painter.fillRect(x, y, size.width(), size.height(), Qt.GlobalColor.white)
        painter.drawImage(x, y,
            self.image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class LinkPreviewPanel(QFrame):
    activated = pyqtSignal(object)
    removed = pyqtSignal(object)
    chooseRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('study-link-preview')
        self.link_rows, self._signature = {}, None
        outer = QVBoxLayout(self)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)
        heading = QLabel(t('study_preview_links_heading'), self)
        heading.setObjectName('study-picker-title')
        outer.addWidget(heading)
        target = QFrame(self)
        target.setObjectName('study-card-target')
        target_layout = QVBoxLayout(target)
        target_layout.setContentsMargins(12, 12, 12, 12)
        target_layout.addWidget(QLabel(t('study_current_card_only'), target))
        self.card_title = QLabel(target)
        self.card_title.setTextFormat(Qt.TextFormat.PlainText)
        self.card_title.setWordWrap(True)
        self.card_title.setMinimumWidth(0)
        self.card_title.setMaximumHeight(110)
        self.card_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        target_layout.addWidget(self.card_title)
        outer.addWidget(target)
        connector = QLabel(t('study_preview_connection'), self)
        connector.setObjectName('study-picker-detail')
        connector.setWordWrap(True)
        outer.addWidget(connector)
        self.empty = QLabel(t('study_preview_empty'), self)
        self.empty.setWordWrap(True)
        self.empty.setObjectName('study-picker-detail')
        outer.addWidget(self.empty)
        self.links = QVBoxLayout()
        self.links.setSpacing(4)
        outer.addLayout(self.links)
        self.media_title = ElidedLabel('', self)
        self.media_title.setObjectName('study-picker-title')
        self.media_detail = QLabel('', self)
        self.media_detail.setObjectName('study-picker-detail')
        self.media_detail.setWordWrap(True)
        outer.addWidget(self.media_title)
        outer.addWidget(self.media_detail)
        self.media_message = QLabel(t('study_preview_empty'), self)
        self.media_message.setWordWrap(True)
        self.media_message.setObjectName('study-picker-detail')
        self.media_message.hide()
        outer.addWidget(self.media_message)
        self.page_image = PageImage(self)
        self.page_image.clicked.connect(self.chooseRequested)
        self.page_image.hide()
        outer.addWidget(self.page_image, 1)
        self.media_host = QVBoxLayout()
        outer.addLayout(self.media_host)
        self.choose_button = QPushButton(t('study_preview_choose_spot'), self)
        self.choose_button.setObjectName('study-quiet-action')
        self.choose_button.clicked.connect(self.chooseRequested)
        self.choose_button.hide()
        outer.addWidget(self.choose_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.note = QLabel(t('study_preview_not_saved'), self)
        self.note.setWordWrap(True)
        self.note.setObjectName('study-picker-detail')
        outer.addWidget(self.note)
        outer.addStretch(1)

    def set_links(self, entries, active):
        signature = tuple((row['key'], row['title'], row['detail'], row['error']) for row in entries)
        if signature != self._signature:
            self._signature = signature
            while self.links.count():
                widget = self.links.takeAt(0).widget()
                widget.hide()
                widget.deleteLater()
            self.link_rows = {}
            for entry in entries:
                key = entry['key']
                frame = QFrame(self)
                row = QHBoxLayout(frame)
                row.setContentsMargins(0, 0, 0, 0)
                frame.button = ResourceButton(frame)
                frame.button.setObjectName('study-draft-link')
                frame.button.setAutoDefault(False)
                frame.button.setAccessibleName(entry['title'] + ' · ' + entry['detail'])
                frame.button.clicked.connect(lambda _=False, key=key: self.activated.emit(key))
                copy = QVBoxLayout(frame.button)
                copy.setContentsMargins(10, 8, 10, 8)
                copy.setSpacing(3)
                frame.title = ElidedLabel(entry['title'], frame.button)
                frame.title.setObjectName('study-picker-title')
                frame.detail = ElidedLabel(entry['error'] or entry['detail'], frame.button)
                frame.detail.setObjectName('study-field-error' if entry['error'] else 'study-picker-detail')
                for label in (frame.title, frame.detail):
                    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                    copy.addWidget(label)
                row.addWidget(frame.button, 1)
                frame.remove_button = QPushButton(t('study_preview_remove'), frame)
                frame.remove_button.setObjectName('study-quiet-action')
                frame.remove_button.setAutoDefault(False)
                frame.remove_button.setAccessibleName(t('study_preview_remove_named', title=entry['title']))
                frame.remove_button.clicked.connect(lambda _=False, key=key: self.removed.emit(key))
                row.addWidget(frame.remove_button)
                self.links.addWidget(frame)
                self.link_rows[key] = frame
        self.empty.setVisible(not entries)
        self.media_title.setVisible(bool(entries))
        self.media_detail.setVisible(bool(entries))
        for key, row in self.link_rows.items():
            row.button.setProperty('selected', key == active)
            row.button.style().unpolish(row.button)
            row.button.style().polish(row.button)

    def show_message(self, message):
        self.page_image.hide()
        self.choose_button.hide()
        self.media_message.setText(message)
        self.media_message.setVisible(bool(message))

    def show_page(self, image):
        self.media_message.hide()
        self.page_image.set_image(image)
        self.page_image.show()
        self.choose_button.show()
