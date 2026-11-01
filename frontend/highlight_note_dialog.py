from __future__ import annotations

import base64
from html import escape
from pathlib import Path

from aqt.qt import (QAction, QBuffer, QButtonGroup, QColor, QComboBox, QDialog, QDialogButtonBox, QFont, QHBoxLayout,
                    QImage, QImageReader, QInputDialog, QIODevice, QKeySequence, QLabel, QPainter, QPalette,
                    QPointF, QRectF, QPushButton, QSpinBox, Qt, QTextCharFormat, QTextCursor, QTextDocument,
                    QTextBlockFormat, QTextEdit, QTextFormat, QTextFrameFormat, QTextImageFormat, QTextListFormat,
                    QToolBar, QToolButton, QVBoxLayout, QWidget, qconnect)
from aqt.utils import showInfo
try:
    from ..backend.i18n import t
    from ..backend.annotation_notes import MAX_IMAGE_BYTES, MAX_IMAGE_EDGE, image_html, image_info, normalize_note, sanitize_note_html
    from ..backend.content_safety import normalize_external_http_url
except ImportError:
    from backend.i18n import t
    from backend.annotation_notes import MAX_IMAGE_BYTES, MAX_IMAGE_EDGE, image_html, image_info, normalize_note, sanitize_note_html
    from backend.content_safety import normalize_external_http_url


def _image_frame(document, position):
    return next((frame for frame in document.rootFrame().childFrames()
                 if frame.lastPosition() == position and frame.firstPosition() == position + 1), None)


def _image_float(document, position):
    frame = _image_frame(document, position)
    if frame is not None:
        return {QTextFrameFormat.Position.FloatLeft: 'left',
                QTextFrameFormat.Position.FloatRight: 'right'}.get(frame.frameFormat().position(), '')
    return ''


_ALIGNMENTS = {'left': Qt.AlignmentFlag.AlignLeft, 'center': Qt.AlignmentFlag.AlignHCenter,
               'right': Qt.AlignmentFlag.AlignRight}
_IMAGE_FILE_SUFFIXES = frozenset(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.heic', '.bmp', '.tif', '.tiff'))
_MAX_CLIPBOARD_IMAGE_FILE_BYTES = 32 * 1024 * 1024


def _block_alignment(block):
    fmt = block.blockFormat()
    if fmt.hasProperty(QTextFormat.Property.BlockAlignment):
        return next((name for name, flag in _ALIGNMENTS.items() if fmt.alignment() & flag), '')
    return ''


def _local_clipboard_image_path(source):
    if not source.hasUrls():
        return None
    urls = source.urls()
    if len(urls) != 1 or not urls[0].isLocalFile():
        return None
    path = Path(urls[0].toLocalFile())
    return path if path.suffix.lower() in _IMAGE_FILE_SUFFIXES else None


def _clipboard_image(source):
    if source.hasImage():
        return QImage(source.imageData())
    path = _local_clipboard_image_path(source)
    if path is None:
        return None
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= _MAX_CLIPBOARD_IMAGE_FILE_BYTES:
        raise ValueError('Invalid clipboard image.')
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > 24_000_000:
        raise ValueError('Invalid clipboard image.')
    image = reader.read()
    if image.isNull():
        raise ValueError('Invalid clipboard image.')
    return image


class _ImageResizeHandle(QToolButton):
    def __init__(self, editor, edge):
        super().__init__(editor.viewport())
        self.editor, self.edge = editor, edge
        self.setObjectName('annotation-image-resize-' + edge)
        self.setFixedSize(12, 12)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor({'right': Qt.CursorShape.SizeHorCursor, 'bottom': Qt.CursorShape.SizeVerCursor,
                        'corner': Qt.CursorShape.SizeFDiagCursor}[edge])
        self.setAccessibleName(t('reader_note_image_resize_' + edge))
        self.setToolTip(t('reader_note_image_resize_help'))
        self.setAccessibleDescription(t('reader_note_image_resize_help'))
        self.setStyleSheet('QToolButton {background:#fff;border:2px solid #2563eb;border-radius:2px;}'
                          'QToolButton:hover,QToolButton:focus {background:#bfdbfe;border-color:#1e40af;}')
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.editor._begin_image_resize(self.edge, event.globalPosition())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.editor._move_image_resize(event.globalPosition(), event.modifiers())
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.editor._move_image_resize(event.globalPosition(), event.modifiers())
            self.editor._end_image_resize()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        movement = {Qt.Key.Key_Left: (-5, 0), Qt.Key.Key_Right: (5, 0),
                    Qt.Key.Key_Up: (0, -5), Qt.Key.Key_Down: (0, 5)}.get(event.key())
        if movement:
            self.editor._begin_image_resize(self.edge, QPointF())
            self.editor._move_image_resize(QPointF(*movement), event.modifiers())
            self.editor._end_image_resize()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.editor._end_image_resize(cancel=True)
            self.editor.setFocus()
        else:
            super().keyPressEvent(event)


class _NoteEditor(QTextEdit):
    def __init__(self, parent):
        super().__init__(parent)
        self._image_drag = None
        self._image_handles = {edge: _ImageResizeHandle(self, edge) for edge in ('right', 'bottom', 'corner')}
        for signal in (self.cursorPositionChanged, self.selectionChanged, self.textChanged,
                       self.horizontalScrollBar().valueChanged, self.verticalScrollBar().valueChanged,
                       self.document().documentLayout().documentSizeChanged):
            qconnect(signal, self._position_image_handles)

    def loadResource(self, resource_type, url):
        if resource_type == QTextDocument.ResourceType.ImageResource:
            try:
                data, _width, _height = image_info(url.toString())
                return QImage.fromData(data)
            except ValueError:
                pass
        # Remote/file resources, SVG, and styles never load.
        return None

    def canInsertFromMimeData(self, source):
        return source.hasImage() or _local_clipboard_image_path(source) is not None or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        try:
            image = _clipboard_image(source)
        except (OSError, ValueError):
            showInfo(t('reader_note_image_failed'), parent=self)
            return
        if image is None:
            if source.hasHtml():
                try:
                    if not sanitize_note_html(source.html())[1]:
                        return
                except ValueError:
                    showInfo(t('reader_note_too_long'), parent=self)
                    return
            return super().insertFromMimeData(source)
        try:
            if image.isNull() or image.width() * image.height() > 24_000_000:
                raise ValueError('Invalid clipboard image.')
            image = image.scaled(MAX_IMAGE_EDGE, MAX_IMAGE_EDGE, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation) if max(image.width(), image.height()) > MAX_IMAGE_EDGE else image
            if image.hasAlphaChannel():
                rgba = image.convertToFormat(QImage.Format.Format_RGBA8888)
                alpha = rgba.constBits().asstring(rgba.sizeInBytes())[3::4]
                if alpha.count(255) == len(alpha):
                    image = image.convertToFormat(QImage.Format.Format_RGB32)
            # Paint into fresh pixels to discard clipboard metadata.
            clean = QImage(image.size(), QImage.Format.Format_ARGB32_Premultiplied if image.hasAlphaChannel() else QImage.Format.Format_RGB32)
            clean.fill(Qt.GlobalColor.transparent if image.hasAlphaChannel() else Qt.GlobalColor.white)
            painter = QPainter(clean)
            painter.drawImage(0, 0, image)
            painter.end()
            while True:
                choices = []
                for kind in (('PNG',) if clean.hasAlphaChannel() else ('PNG', 'JPEG')):
                    buffer = QBuffer()
                    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                    if clean.save(buffer, kind, 75):
                        choices.append((bytes(buffer.data()), kind.lower()))
                if not choices:
                    raise ValueError('Image encoding failed.')
                data, kind = min(choices, key=lambda value: len(value[0]))
                if len(data) <= MAX_IMAGE_BYTES:
                    break
                if max(clean.width(), clean.height()) <= 64:
                    raise ValueError('Image is too large.')
                clean = clean.scaled(max(1, int(clean.width() * .75)), max(1, int(clean.height() * .75)),
                                     Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            source_url = f'data:image/{kind};base64,' + base64.b64encode(data).decode('ascii')
            width = min(320, clean.width(), max(1, round(240 * clean.width() / clean.height())))
            markup = '<p align="center">' + image_html(source_url, width) + '</p><p></p>'
            remaining = self.document()
            selection = self.textCursor()
            if selection.hasSelection():
                remaining = self.document().clone()
                selected = QTextCursor(remaining)
                selected.setPosition(selection.selectionStart())
                selected.setPosition(selection.selectionEnd(), QTextCursor.MoveMode.KeepAnchor)
                selected.removeSelectedText()
            normalize_note(remaining.toPlainText().replace('\ufffc', ''), _document_html(remaining) + markup)
            # Check budgets before replacing selected text or mutating Undo.
            fmt = QTextImageFormat()
            fmt.setName(source_url)
            fmt.setWidth(width)
            fmt.setHeight(max(1, int(width * clean.height() / clean.width() + .5)))
            cursor = self.textCursor()
            cursor.beginEditBlock()
            cursor.insertImage(fmt)
            self.setTextCursor(cursor)
            self.set_image_layout('block')
            image_cursor = self.image_cursor()
            cursor.setPosition(image_cursor.selectionEnd())
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
            cursor.endEditBlock()
            self.setTextCursor(cursor)
        except (ValueError, TypeError):
            showInfo(t('reader_note_image_failed'), parent=self)

    def image_cursor(self):
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectionEnd() - cursor.selectionStart() != 1:
            return None
        position = cursor.selectionStart() if cursor.hasSelection() else cursor.position()
        for start in (position, position - 1):
            probe = self._image_at(start)
            if probe is not None:
                return probe
        if cursor.atBlockStart() or not cursor.block().text():
            for block in (cursor.block().previous(), cursor.block().next()):
                if block.isValid() and block.text() == '\ufffc':
                    return self._image_at(block.position())
        return None

    def image_layout(self, cursor):
        floating = _image_float(self.document(), cursor.selectionStart())
        if floating:
            return floating
        block = cursor.block()
        return 'block' if block.text() == '\ufffc' and _block_alignment(block) else 'inline'

    def image_resizes_from_left(self, cursor):
        return (_image_float(self.document(), cursor.selectionStart()) == 'right'
                or self.image_layout(cursor) == 'block' and _block_alignment(cursor.block()) == 'right')

    def set_image_alignment(self, alignment):
        cursor = self.image_cursor()
        if cursor is None or self.image_layout(cursor) != 'block' or alignment not in _ALIGNMENTS:
            return
        self._end_image_resize()
        cursor.beginEditBlock()
        fmt = cursor.blockFormat()
        fmt.setAlignment(_ALIGNMENTS[alignment])
        cursor.setBlockFormat(fmt)
        cursor.endEditBlock()
        self.document().markContentsDirty(cursor.selectionStart(), 1)
        self.setTextCursor(cursor)
        self._position_image_handles()

    def set_image_layout(self, layout):
        cursor = self.image_cursor()
        if cursor is None or layout not in ('block', 'inline', 'left', 'right'):
            return
        own_alignment = _block_alignment(cursor.block()) if self.image_layout(cursor) == 'block' else 'center'
        self._end_image_resize()
        cursor.beginEditBlock()
        position = cursor.selectionStart()
        frame = _image_frame(self.document(), position)
        if frame is not None:
            fmt = frame.frameFormat()
            fmt.setPosition(QTextFrameFormat.Position.InFlow)
            frame.setFrameFormat(fmt)
        if layout == 'block':
            cursor.setPosition(position)
            if cursor.positionInBlock():
                cursor.insertBlock(QTextBlockFormat())
            position = cursor.position()
            cursor.movePosition(QTextCursor.MoveOperation.Right)
            if not cursor.atBlockEnd() or not cursor.block().next().isValid():
                cursor.insertBlock(QTextBlockFormat())
            cursor.setPosition(position)
            block_format = QTextBlockFormat()
            block_format.setAlignment(_ALIGNMENTS[own_alignment])
            if cursor.block().textList():
                cursor.block().textList().remove(cursor.block())
            cursor.setBlockFormat(block_format)
        else:
            cursor.setPosition(position)
            if cursor.block().text() == '\ufffc':
                cursor.setBlockFormat(QTextBlockFormat())
                following = cursor.block().next()
                if following.isValid() and not following.textList():
                    cursor.movePosition(QTextCursor.MoveOperation.Right)
                    cursor.deleteChar()
                    cursor.setPosition(position)
            if layout in ('left', 'right'):
                frame = _image_frame(self.document(), position)
                alignment = QTextFrameFormat.Position.FloatLeft if layout == 'left' else QTextFrameFormat.Position.FloatRight
                if frame is not None:
                    fmt = frame.frameFormat()
                    fmt.setPosition(alignment)
                    frame.setFrameFormat(fmt)
                else:
                    cursor.setPosition(position + 1, QTextCursor.MoveMode.KeepAnchor)
                    image_format = cursor.charFormat().toImageFormat()
                    cursor.removeSelectedText()
                    cursor.insertImage(image_format, alignment)
        cursor.setPosition(position + 1)
        cursor.endEditBlock()
        self.document().markContentsDirty(position, 1)
        self.setTextCursor(cursor)
        self._position_image_handles()

    def _image_at(self, position):
        if not 0 <= position < self.document().characterCount() - 1:
            return None
        cursor = QTextCursor(self.document())
        cursor.setPosition(position)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
        return cursor if cursor.charFormat().isImageFormat() and cursor.selectedText() == '\ufffc' else None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return super().mousePressEvent(event)
        for frame in self.document().rootFrame().childFrames():
            cursor = self._image_at(frame.lastPosition())
            if cursor is not None and _image_float(self.document(), cursor.selectionStart()):
                rect = self._image_rect(cursor)
                if rect is not None and rect.contains(event.position()):
                    self.setTextCursor(cursor)
                    event.accept()
                    return
        super().mousePressEvent(event)
        position = self.textCursor().position()
        for start in (position, position - 1):
            cursor = self._image_at(start)
            rect = self._image_rect(cursor) if cursor is not None else None
            if rect is not None and rect.contains(event.position()):
                self.setTextCursor(cursor)
                break

    def _image_rect(self, cursor=None):
        cursor = self.image_cursor() if cursor is None else QTextCursor(cursor)
        if cursor is None:
            return None
        fmt = cursor.charFormat().toImageFormat()
        if fmt.width() <= 0 or fmt.height() <= 0:
            return None
        position = cursor.selectionStart()
        frame = _image_frame(self.document(), position)
        if frame is not None and frame.frameFormat().position() != QTextFrameFormat.Position.InFlow:
            return self.document().documentLayout().frameBoundingRect(frame).translated(
                -self.horizontalScrollBar().value(), -self.verticalScrollBar().value())
        cursor.setPosition(position)
        caret = self.cursorRect(cursor)
        line = cursor.block().layout().lineForTextPosition(position - cursor.block().position())
        if not line.isValid():
            return None
        return QRectF(caret.x(), caret.y() + line.ascent() - fmt.height(), fmt.width(), fmt.height())

    def _position_image_handles(self, *_args):
        rect = self._image_rect()
        points = {} if rect is None else {'right': QPointF(rect.right(), rect.center().y()),
                                         'bottom': QPointF(rect.center().x(), rect.bottom()),
                                         'corner': rect.bottomRight()}
        cursor = self.image_cursor()
        mirrored = cursor is not None and self.image_resizes_from_left(cursor)
        if rect is not None and mirrored:
            points.update(right=QPointF(rect.left(), rect.center().y()), corner=rect.bottomLeft())
        self._image_handles['corner'].setCursor(Qt.CursorShape.SizeBDiagCursor if mirrored else Qt.CursorShape.SizeFDiagCursor)
        for edge, handle in self._image_handles.items():
            point = points.get(edge)
            visible = point is not None and self.viewport().rect().contains(point.toPoint())
            if point is not None and self._image_drag is not None and self._image_drag[2] == edge:
                point = QPointF(max(6, min(point.x(), self.viewport().width() - 6)),
                                max(6, min(point.y(), self.viewport().height() - 6)))
                visible = True
            handle.setVisible(visible)
            if visible:
                handle.move((point - QPointF(handle.width() / 2, handle.height() / 2)).toPoint())
                handle.raise_()
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self._image_rect()
        if rect is not None:
            painter = QPainter(self.viewport())
            painter.setPen(QColor('#2563eb'))
            painter.drawRect(rect)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_image_handles()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._image_drag is not None:
            self._end_image_resize(cancel=True)
            event.accept()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        self._end_image_resize(cancel=True)
        super().hideEvent(event)

    def _begin_image_resize(self, edge, point):
        cursor = self.image_cursor()
        if cursor is None or self._image_rect(cursor) is None or self._image_drag is not None:
            return
        fmt = cursor.charFormat().toImageFormat()
        cursor.beginEditBlock()
        self._image_drag = (cursor, fmt, edge, QPointF(point))

    def _move_image_resize(self, point, modifiers):
        if self._image_drag is None:
            return
        cursor, original, edge, start = self._image_drag
        delta = point - start
        direction = -1 if self.image_resizes_from_left(cursor) else 1
        width = max(1, original.width() + (delta.x() * direction if edge != 'bottom' else 0))
        height = max(1, original.height() + (delta.y() if edge != 'right' else 0))
        keep_ratio = (edge == 'corner') != bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if keep_ratio:
            scale_x, scale_y = width / original.width(), height / original.height()
            scale = scale_x if abs(scale_x - 1) >= abs(scale_y - 1) else scale_y
            scale = min(scale, 640 / original.width(), MAX_IMAGE_EDGE / original.height())
            width, height = original.width() * scale, original.height() * scale
        fmt = QTextImageFormat(original)
        fmt.setWidth(max(1, min(640, round(width))))
        fmt.setHeight(max(1, min(MAX_IMAGE_EDGE, round(height))))
        cursor.setCharFormat(fmt)
        self._position_image_handles()

    def _end_image_resize(self, *, cancel=False):
        if self._image_drag is not None:
            cursor, original, _edge, _point = self._image_drag
            if cancel:
                cursor.setCharFormat(original)
            cursor.endEditBlock()
            self._image_drag = None
            self._position_image_handles()


def _document_html(document) -> str:
    """Serialize visible Qt text runs, never Qt's resource-bearing HTML."""
    parts = []
    open_list = ''
    block = document.begin()
    while block.isValid():
        text_list = block.textList()
        kind = ''
        if text_list:
            kind = 'ol' if text_list.format().style() == QTextListFormat.Style.ListDecimal else 'ul'
        if kind != open_list:
            if open_list:
                parts.append(f'</{open_list}>')
            if kind:
                parts.append(f'<{kind}>')
            open_list = kind
        tag = 'li' if kind else 'p'
        chosen_alignment = _block_alignment(block) if tag == 'p' else ''
        alignment = f' align="{chosen_alignment}"' if chosen_alignment else ''
        parts.append(f'<{tag}{alignment}>')
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                if fmt.isImageFormat():
                    image = fmt.toImageFormat()
                    try:
                        for offset in range(fragment.text().count('\ufffc')):
                            parts.append(image_html(image.name(), image.width() or 320, image.height() or None,
                                                     _image_float(document, fragment.position() + offset)))
                    except ValueError:
                        pass
                    iterator += 1
                    continue
                text = escape(fragment.text().replace('\ufffc', '')).replace('\u2028', '<br>')
                for enabled, style in ((fmt.fontStrikeOut(), 's'), (fmt.fontUnderline(), 'u'),
                                       (fmt.fontItalic(), 'i'), (fmt.fontWeight() >= QFont.Weight.Bold, 'b')):
                    if enabled and text:
                        text = f'<{style}>{text}</{style}>'
                if fmt.isAnchor() and text:
                    try:
                        url = normalize_external_http_url(fmt.anchorHref())
                        text = f'<a href="{escape(url, quote=True)}">{text}</a>'
                    except ValueError:
                        pass
                parts.append(text)
            iterator += 1
        parts.append(f'</{tag}>')
        block = block.next()
    if open_list:
        parts.append(f'</{open_list}>')
    return ''.join(parts)


class HighlightNoteDialog(QDialog):
    _open_editors = {}

    @classmethod
    def show_for_annotation(cls, parent, *, key, is_current, save, **kwargs):
        """One modeless draft per annotation and collection session."""
        existing = cls._open_editors.get(key)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing
        dialog = cls(parent, **kwargs)
        dialog._is_current = is_current
        dialog._save_annotation = save
        dialog._save_button.setText(t('reader_note_editor_save'))
        dialog.setModal(False)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        cls._open_editors[key] = dialog

        def retire(*_args):
            if cls._open_editors.get(key) is dialog:
                cls._open_editors.pop(key, None)

        qconnect(dialog.finished, retire)
        qconnect(dialog.destroyed, retire)
        dialog.show()
        return dialog

    def __init__(self, parent, *, title: str, excerpt: str, current_note: str, current_note_html: str = ''):
        super().__init__(parent)
        self._is_current = None
        self._save_annotation = None
        self.setWindowTitle(title)
        self.resize(640, 600)

        layout = QVBoxLayout(self)
        excerpt_label = QLabel(t("reader_selected_text_label"))
        excerpt_label.setStyleSheet("font-weight: bold;")
        excerpt_label.setWordWrap(True)
        layout.addWidget(excerpt_label)

        excerpt_preview = QLabel(str(excerpt or "").strip() or t("reader_no_text_parenthesized"))
        excerpt_preview.setTextFormat(Qt.TextFormat.PlainText)
        excerpt_preview.setWordWrap(True)
        excerpt_preview.setStyleSheet(
            "QLabel { background: rgba(74,144,217,0.08); border: 1px solid rgba(74,144,217,0.25); border-radius: 6px; padding: 8px; }"
        )
        layout.addWidget(excerpt_preview)

        note_label = QLabel(t("reader_text_note_label"))
        note_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(note_label)

        self._editor = _NoteEditor(self)
        self._editor.ensurePolished()
        self._link_color = '#8ab4f8' if self._editor.palette().color(QPalette.ColorRole.Text).lightness() > 127 else '#145da0'
        self._editor.document().setDefaultStyleSheet(f'a {{color:{self._link_color};}}')
        self._editor.setAccessibleName(t('reader_text_note_label'))
        self._editor.setPlaceholderText(t("reader_highlight_note_placeholder"))
        plain, markup = normalize_note(current_note, current_note_html)
        if markup:
            self._editor.setHtml(markup)
        else:
            self._editor.setPlainText(plain)
        self._actions = {}
        toolbar = QToolBar(self)
        toolbar.setAccessibleName(t('reader_note_formatting'))
        layout.addWidget(toolbar)
        for name, symbol, shortcut, callback, checkable in (
            ('bold', 'B', 'Ctrl+B', lambda checked: self._format('bold', checked), True),
            ('italic', 'I', 'Ctrl+I', lambda checked: self._format('italic', checked), True),
            ('underline', 'U', 'Ctrl+U', lambda checked: self._format('underline', checked), True),
            ('strike', 'S', '', lambda checked: self._format('strike', checked), True),
            ('link', '🔗', 'Ctrl+K', self._edit_link, False),
            ('bullets', '•', '', lambda _checked: self._list(False), False),
            ('numbers', '1.', '', lambda _checked: self._list(True), False),
            ('clear', 'Tx', '', self._clear_formatting, False),
            ('undo', '↶', '', self._editor.undo, False),
            ('redo', '↷', '', self._editor.redo, False),
        ):
            action = QAction(symbol, self)
            action.setObjectName('annotation-note-' + name)
            action.setCheckable(checkable)
            label = t('reader_note_' + name)
            action.setToolTip(label)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
                action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
                self.addAction(action)
            qconnect(action.triggered, callback)
            toolbar.addAction(action)
            button = toolbar.widgetForAction(action)
            button.setAccessibleName(label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            font = button.font()
            font.setBold(name == 'bold')
            font.setItalic(name == 'italic')
            font.setUnderline(name == 'underline')
            font.setStrikeOut(name == 'strike')
            button.setFont(font)
            self._actions[name] = action
        self._actions['undo'].setShortcut(QKeySequence.StandardKey.Undo)
        self._actions['redo'].setShortcut(QKeySequence.StandardKey.Redo)
        for name in ('undo', 'redo'):
            self._actions[name].setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.addAction(self._actions[name])
            self._actions[name].setEnabled(False)
        qconnect(self._editor.undoAvailable, self._actions['undo'].setEnabled)
        qconnect(self._editor.redoAvailable, self._actions['redo'].setEnabled)
        qconnect(self._editor.currentCharFormatChanged, self._sync_format)
        self._sync_format(self._editor.currentCharFormat())
        layout.addWidget(self._editor, 1)

        self._image_controls = QWidget(self)
        image_controls_layout = QVBoxLayout(self._image_controls)
        image_controls_layout.setContentsMargins(0, 0, 0, 0)
        placement_layout = QHBoxLayout()
        placement_label = QLabel(t('reader_note_image_placement'), self)
        placement_layout.addWidget(placement_label)
        self._image_placement = QComboBox(self)
        for placement in ('block', 'inline', 'left', 'right'):
            self._image_placement.addItem(t('reader_note_image_placement_' + placement), placement)
        self._image_placement.setAccessibleName(t('reader_note_image_placement'))
        self._image_placement.setToolTip(t('reader_note_image_placement_help'))
        placement_label.setBuddy(self._image_placement)
        placement_layout.addWidget(self._image_placement, 1)
        image_controls_layout.addLayout(placement_layout)
        self._image_alignment_controls = QWidget(self)
        self._image_alignment_controls.setAccessibleName(t('reader_note_image_alignment'))
        alignment_layout = QHBoxLayout(self._image_alignment_controls)
        alignment_layout.setContentsMargins(0, 0, 0, 0)
        alignment_layout.addWidget(QLabel(t('reader_note_image_alignment'), self))
        self._image_alignment_group = QButtonGroup(self)
        self._image_alignment_buttons = {}
        for alignment in ('left', 'center', 'right'):
            label = t('reader_note_image_align_' + alignment)
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setAccessibleName(t('reader_note_image_alignment_choice', alignment=label))
            button.setToolTip(t('reader_note_image_alignment_choice', alignment=label))
            self._image_alignment_group.addButton(button)
            qconnect(button.clicked, lambda _checked=False, alignment=alignment: self._editor.set_image_alignment(alignment))
            self._image_alignment_buttons[alignment] = button
            alignment_layout.addWidget(button)
        alignment_layout.addStretch(1)
        image_controls_layout.addWidget(self._image_alignment_controls)
        self._image_wrap_hint = QLabel(t('reader_note_image_wrap_narrow'), self)
        self._image_wrap_hint.setWordWrap(True)
        image_controls_layout.addWidget(self._image_wrap_hint)
        image_layout = QHBoxLayout()
        image_controls_layout.addLayout(image_layout)
        image_label = QLabel(t('reader_note_image_width'))
        image_layout.addWidget(image_label)
        self._image_width = QSpinBox(self)
        self._image_width.setRange(1, 640)
        self._image_width.setSuffix(t('reader_note_image_pixels'))
        self._image_width.setKeyboardTracking(False)
        self._image_width.setAccessibleName(t('reader_note_image_width'))
        image_label.setBuddy(self._image_width)
        image_layout.addWidget(self._image_width)
        self._image_size = QLabel(self)
        image_layout.addWidget(self._image_size)
        remove_image = QPushButton(t('reader_note_image_remove'), self)
        qconnect(remove_image.clicked, self._remove_image)
        image_layout.addWidget(remove_image)
        image_layout.addStretch(1)
        writing_layout = QHBoxLayout()
        for above in (True, False):
            button = QPushButton(t('reader_note_image_write_above' if above else 'reader_note_image_write_below'), self)
            qconnect(button.clicked, lambda _checked=False, above=above: self._write_around_image(above=above))
            writing_layout.addWidget(button)
        writing_layout.addStretch(1)
        image_controls_layout.addLayout(writing_layout)
        layout.addWidget(self._image_controls)
        qconnect(self._image_placement.currentIndexChanged, self._change_image_placement)
        qconnect(self._image_width.valueChanged, self._resize_image)
        qconnect(self._editor.cursorPositionChanged, self._sync_image)
        qconnect(self._editor.textChanged, self._sync_image)
        qconnect(self._editor.document().documentLayout().documentSizeChanged, self._sync_image)
        self._sync_image()
        hint = QLabel(t('reader_note_image_hint'), self)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._save_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._save_button.setText(t("reader_ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("reader_cancel"))
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)
        self._save_status = QLabel(self)
        self._save_status.setTextFormat(Qt.TextFormat.PlainText)
        self._save_status.setWordWrap(True)
        self._save_status.hide()
        layout.addWidget(self._save_status)
        layout.addWidget(buttons)

    def note_text(self) -> str:
        return self._editor.toPlainText().replace('\ufffc', '').strip()

    def note_html(self) -> str:
        return normalize_note(self.note_text(), _document_html(self._editor.document()))[1]

    def _sync_image(self, *_args):
        cursor = self._editor.image_cursor()
        self._image_controls.setVisible(cursor is not None)
        if cursor is None:
            return
        fmt = cursor.charFormat().toImageFormat()
        if fmt.width() <= 0 or fmt.height() <= 0:
            self._image_controls.hide()
            return
        try:
            data, _width, _height = image_info(fmt.name())
        except ValueError:
            self._image_controls.hide()
            return
        self._image_width.blockSignals(True)
        self._image_width.setMaximum(max(1, min(640, int(MAX_IMAGE_EDGE * fmt.width() / fmt.height()))))
        self._image_width.setValue(round(fmt.width()))
        self._image_width.blockSignals(False)
        self._image_placement.blockSignals(True)
        placement = self._editor.image_layout(cursor)
        self._image_placement.setCurrentIndex(self._image_placement.findData(placement))
        self._image_placement.blockSignals(False)
        self._image_alignment_controls.setVisible(placement == 'block')
        current_alignment = _block_alignment(cursor.block())
        for alignment, button in self._image_alignment_buttons.items():
            button.setChecked(alignment == current_alignment)
        self._image_wrap_hint.setVisible(placement in ('left', 'right') and self._editor.viewport().width() - fmt.width() < 160)
        self._image_size.setText(t('reader_note_image_size', size=max(1, round(len(data) / 1024))))

    def _change_image_placement(self, _index):
        self._editor.set_image_layout(self._image_placement.currentData())
        self._sync_image()

    def _write_around_image(self, *, above):
        cursor = self._editor.image_cursor()
        if cursor is None:
            return
        cursor.beginEditBlock()
        self._editor.set_image_layout('block')
        image = self._editor.image_cursor()
        block = image.block()
        adjacent = block.previous() if above else block.next()
        if adjacent.isValid():
            cursor.setPosition(adjacent.position() + (adjacent.length() - 1 if above else 0))
        elif above:
            cursor.setPosition(block.position())
            cursor.insertBlock(block.blockFormat())
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        else:
            cursor.setPosition(block.position() + block.length() - 1)
            cursor.insertBlock(QTextBlockFormat())
        if not cursor.block().text():
            cursor.setBlockFormat(QTextBlockFormat())
        cursor.endEditBlock()
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _resize_image(self, width):
        cursor = self._editor.image_cursor()
        if cursor is None:
            return
        fmt = cursor.charFormat().toImageFormat()
        ratio = fmt.height() / fmt.width()
        fmt.setWidth(width)
        fmt.setHeight(max(1, min(MAX_IMAGE_EDGE, round(width * ratio))))
        cursor.setCharFormat(fmt)

    def _remove_image(self, _checked=False):
        cursor = self._editor.image_cursor()
        if cursor:
            cursor.removeSelectedText()
            self._editor.setTextCursor(cursor)
            self._editor.setFocus()

    def _sync_format(self, fmt):
        for name, enabled in (('bold', fmt.fontWeight() >= QFont.Weight.Bold), ('italic', fmt.fontItalic()),
                              ('underline', fmt.fontUnderline()), ('strike', fmt.fontStrikeOut())):
            self._actions[name].setChecked(enabled)

    def _format(self, name, enabled):
        fmt = QTextCharFormat()
        if name == 'bold':
            fmt.setFontWeight(QFont.Weight.Bold if enabled else QFont.Weight.Normal)
        elif name == 'italic':
            fmt.setFontItalic(enabled)
        elif name == 'underline':
            fmt.setFontUnderline(enabled)
        elif name == 'strike':
            fmt.setFontStrikeOut(enabled)
        self._editor.mergeCurrentCharFormat(fmt)
        self._editor.setFocus()

    def _list(self, numbered):
        fmt = QTextListFormat()
        fmt.setStyle(QTextListFormat.Style.ListDecimal if numbered else QTextListFormat.Style.ListDisc)
        self._editor.textCursor().createList(fmt)
        self._editor.setFocus()

    def _clear_formatting(self):
        cursor = self._editor.textCursor()
        cursor.beginEditBlock()
        block = self._editor.document().findBlock(cursor.selectionStart())
        end = cursor.selectionEnd()
        ranges = []
        while block.isValid() and block.position() <= end:
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and not fragment.charFormat().isImageFormat():
                    start = max(cursor.selectionStart(), fragment.position())
                    stop = min(end, fragment.position() + fragment.length())
                    if start < stop:
                        ranges.append((start, stop))
                iterator += 1
            if block.textList():
                block.textList().remove(block)
            block = block.next()
        for start, stop in ranges:
            run = QTextCursor(self._editor.document())
            run.setPosition(start)
            run.setPosition(stop, QTextCursor.MoveMode.KeepAnchor)
            run.setCharFormat(QTextCharFormat())
        if not cursor.hasSelection():
            self._editor.setCurrentCharFormat(QTextCharFormat())
        cursor.endEditBlock()
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def _set_link(self, value):
        url = normalize_external_http_url(value) if value.strip() else ''
        cursor = self._editor.textCursor()
        # Editing a link at the caret updates its complete label, including
        # adjacent text runs with different bold/italic formatting.
        href = cursor.charFormat().anchorHref()
        if not cursor.hasSelection() and href:
            runs = []
            iterator = cursor.block().begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if fragment.isValid() and fragment.charFormat().anchorHref() == href:
                    start, end = fragment.position(), fragment.position() + fragment.length()
                    if runs and runs[-1][1] == start:
                        runs[-1] = (runs[-1][0], end)
                    else:
                        runs.append((start, end))
                iterator += 1
            for start, end in runs:
                if start <= cursor.position() <= end:
                    cursor.setPosition(start)
                    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                    break
        fmt = QTextCharFormat()
        fmt.setAnchor(bool(url))
        fmt.setAnchorHref(url)
        fmt.setFontUnderline(bool(url))
        fmt.setForeground(QColor(self._link_color) if url else self._editor.palette().color(QPalette.ColorRole.Text))
        if cursor.hasSelection() or not url:
            cursor.mergeCharFormat(fmt)
        else:
            cursor.insertText(url, fmt)
        self._editor.setTextCursor(cursor)
        self._editor.setFocus()

    def accept(self):
        try:
            normalize_note(self.note_text(), self.note_html())
        except ValueError:
            showInfo(t('reader_note_too_long'), parent=self)
            return
        if self._save_annotation is not None:
            try:
                message = (self._save_annotation(self) if self._is_current()
                           else t('reader_note_editor_stale'))
            except Exception as exc:
                message = t('reader_note_editor_save_failed', error=exc)
            if message:
                self._save_status.setText(str(message))
                self._save_status.show()
                return
        super().accept()

    def _edit_link(self):
        url, accepted = QInputDialog.getText(self, t('reader_note_link'), t('reader_note_link_prompt'),
                                             text=self._editor.currentCharFormat().anchorHref())
        if accepted:
            try:
                self._set_link(url)
            except ValueError:
                showInfo(t('reader_note_link_invalid'), parent=self)
