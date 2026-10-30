from __future__ import annotations

from html import escape

from aqt.qt import (QAction, QColor, QDialog, QDialogButtonBox, QFont, QInputDialog, QKeySequence,
                    QLabel, QPalette, Qt, QTextCharFormat, QTextCursor, QTextEdit, QTextListFormat,
                    QToolBar, QVBoxLayout, qconnect)
from aqt.utils import showInfo
try:
    from ..backend.i18n import t
    from ..backend.annotation_notes import normalize_note
    from ..backend.content_safety import normalize_external_http_url
except ImportError:
    from backend.i18n import t
    from backend.annotation_notes import normalize_note
    from backend.content_safety import normalize_external_http_url


class _NoteEditor(QTextEdit):
    def loadResource(self, resource_type, url):
        # Rich paste may contain images/styles; annotation notes never load them.
        return None


def _document_html(editor) -> str:
    """Serialize visible Qt text runs, never Qt's resource-bearing HTML."""
    parts = []
    open_list = ''
    block = editor.document().begin()
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
        parts.append(f'<{tag}>')
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                text = escape(fragment.text().replace('\ufffc', '')).replace('\u2028', '<br>')
                fmt = fragment.charFormat()
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
    def __init__(self, parent, *, title: str, excerpt: str, current_note: str, current_note_html: str = ''):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(600, 400)

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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(t("reader_ok"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("reader_cancel"))
        qconnect(buttons.accepted, self.accept)
        qconnect(buttons.rejected, self.reject)
        layout.addWidget(buttons)

    def note_text(self) -> str:
        return self._editor.toPlainText().replace('\ufffc', '').strip()

    def note_html(self) -> str:
        return normalize_note(self.note_text(), _document_html(self._editor))[1]

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
        cursor.setCharFormat(QTextCharFormat())
        block = self._editor.document().findBlock(cursor.selectionStart())
        end = cursor.selectionEnd()
        while block.isValid() and block.position() <= end:
            if block.textList():
                block.textList().remove(block)
            block = block.next()
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
        super().accept()

    def _edit_link(self):
        url, accepted = QInputDialog.getText(self, t('reader_note_link'), t('reader_note_link_prompt'),
                                             text=self._editor.currentCharFormat().anchorHref())
        if accepted:
            try:
                self._set_link(url)
            except ValueError:
                showInfo(t('reader_note_link_invalid'), parent=self)
