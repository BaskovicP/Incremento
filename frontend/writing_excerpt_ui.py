"""Explicit send-to-writing and a source margin over existing reader previews."""
from html import escape
import re
from pathlib import Path

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QDialog, QListWidget, QListWidgetItem, QPushButton, QTextBrowser, QTextDocument, QTextEdit, QVBoxLayout, Qt, QWidget, QToolButton, QMenu
from aqt.utils import tooltip
from PyQt6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat, QDesktopServices
from PyQt6.QtCore import QEvent, QPoint, QTimer, QUrl

try:
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile, get_writing_dir, get_user_files_dir
    from ..backend.recording_links import normalize_source
    from ..backend.study_resources import resolve_document
    from ..backend.writing_links import create_link, list_links, marker, strip_markers
    from ..backend.writing_manager import WRITING_NOTE_TYPE, WRITING_FILE_FIELD, writing_file_abspath
except ImportError:
    from backend.i18n import t
    from backend.paths import get_active_profile, get_writing_dir, get_user_files_dir
    from backend.recording_links import normalize_source
    from backend.study_resources import resolve_document
    from backend.writing_links import create_link, list_links, marker, strip_markers
    from backend.writing_manager import WRITING_NOTE_TYPE, WRITING_FILE_FIELD, writing_file_abspath

_dialogs = []


class ExcerptEditor(QTextEdit):
    def clear_excerpt_reveal(self):
        self._excerpt_selection = None
        if hasattr(self, '_excerpt_timer'):
            self._excerpt_timer.stop()
        if _writing()._writing_dock is not None:
            _writing()._update_editor_highlights()

    def reveal_excerpt(self, cursor):
        from PyQt6.QtCore import QTimer
        self._excerpt_selection = QTextEdit.ExtraSelection()
        self._excerpt_selection.cursor = cursor
        self._excerpt_selection.format.setBackground(QColor(96, 165, 250, 90))
        if not hasattr(self, '_excerpt_timer'):
            self._excerpt_timer = QTimer(self)
            self._excerpt_timer.setSingleShot(True)
            self._excerpt_timer.timeout.connect(self.clear_excerpt_reveal)
        self._excerpt_timer.start(4000)
        _writing()._update_editor_highlights()

    def mousePressEvent(self, event):
        self.clear_excerpt_reveal()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        self.clear_excerpt_reveal()
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.clear_excerpt_reveal()
        super().focusOutEvent(event)

    def setDocument(self, document):
        self.clear_excerpt_reveal()
        super().setDocument(document)

    def createMimeDataFromSelection(self):
        from PyQt6.QtCore import QMimeData
        data = QMimeData()
        data.setText(strip_markers(super().createMimeDataFromSelection().text()))
        return data


class ExcerptMarkers(QSyntaxHighlighter):
    """Keep durable Markdown metadata out of the writing surface, without editing it."""
    def highlightBlock(self, text):
        if re.fullmatch(r'<!-- incremento-excerpt(?:-start)?:[a-f0-9]{32} -->', text):
            style = QTextCharFormat()
            style.setForeground(QColor(0, 0, 0, 0))
            style.setFontPointSize(1)
            self.setFormat(0, len(text), style)


def _writing():
    from . import writing_dock
    return writing_dock


def _keep(dialog):
    _dialogs.append(dialog)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.finished.connect(lambda *_: _dialogs.remove(dialog) if dialog in _dialogs else None)
    dialog.show()


def reset(*_):
    for dialog in list(_dialogs):
        dialog.close()


def source_label(source):
    if source['kind'] == 'pdf':
        return t('study_pdf_page', page=source['page'])
    if source['kind'] == 'epub':
        return t('study_epub_section', section=source['section'] + 1)
    return t('study_card')


def _title(note):
    try:
        return str(note['Title'])[:240]
    except KeyError:
        return str(note.fields[0])[:240]


def _target(col, root, profile, card_id):
    note = col.get_note(col.get_card(card_id).nid)
    if note.note_type()['name'] != WRITING_NOTE_TYPE:
        raise ValueError('Writing card unavailable')
    relpath = str(note[WRITING_FILE_FIELD]).strip()
    path = Path(writing_file_abspath(root, relpath, profile=profile))
    base = get_writing_dir(root, profile).resolve()
    base.relative_to(get_user_files_dir(root, profile).resolve())
    path.relative_to(base)
    if not relpath or not path.is_file():
        raise ValueError('Writing file unavailable')
    return card_id, str(note['Title']), relpath


def send_to_writing(source, *, is_current=lambda: True):
    writing = _writing()
    dock = writing._writing_dock
    if (dock is None or not dock.isVisible() or not is_current()
            or writing._writing_profile != get_active_profile()):
        return
    source = normalize_source(source)
    identity, document = writing._writing_identity(), dock._editor.document()
    profile, collection, cid = get_active_profile(), mw.col, writing.current_writing_card_id()
    cursor = dock._editor.textCursor()
    # A selection in the destination must never be overwritten by a transfer.
    cursor.clearSelection()
    def current():
        return (profile == get_active_profile() and collection is mw.col and is_current()
                and writing._writing_identity_is_current(identity) and dock.isVisible()
                and dock._editor.document() is document)
    def work(col):
        if col is not collection or get_active_profile() != profile:
            return None
        target = _target(col, writing._ADDON_DIR, profile, cid)
        if target[2] != identity[3]:
            raise ValueError('Writing target changed')
        if source['kind'] != 'card':
            title = resolve_document(writing._ADDON_DIR, profile, col, source)['title']
        else:
            title = _title(col.get_note(col.get_card(source['card_id']).nid))
        anchor = create_link(writing._ADDON_DIR, profile, source, cid, source_title=title[:240])
        return anchor
    def ready(anchor):
        if anchor is None or not current():
            return
        writing.insert_linked_excerpt(source, anchor, cursor=cursor)
        if writing._flush_editor_state():
            dock._source_margin.reload()
            refresh_readers()
        else:
            tooltip(t('writing_autosave_failed'), parent=dock)
    def failed(_error):
        if current():
            tooltip(t('writing_excerpt_failed'), parent=dock)
    QueryOp(parent=mw, op=work, success=ready).failure(failed).run_in_background()


def choose_writing(source, *, is_current=lambda: True):
    from .writing_workspace import WritingPicker
    source = normalize_source(source)
    if not source['quote'] or not is_current():
        return
    profile, collection = get_active_profile(), mw.col
    def current():
        return profile == get_active_profile() and collection is mw.col and is_current()
    def selected(card_id):
        if not current():
            return
        try:
            opener = _writing()._writing_tab_actions.get('open_card')
            if opener is None or not opener(card_id):
                tooltip(t('writing_excerpt_failed'))
                return
            if current():
                send_to_writing(source, is_current=current)
        except (ValueError, RuntimeError, OSError):
            if current():
                tooltip(t('writing_excerpt_failed'))
    for dialog in list(_dialogs):
        if isinstance(dialog, WritingPicker):
            dialog.close()
    picker = WritingPicker(mw, open_card=selected, title=t('writing_send_excerpt'),
                           action_label=t('writing_send_excerpt'), is_current=current)
    _keep(picker)


def add_context_actions(menu, source, *, owner=None, is_current=lambda: True):
    oversized = isinstance(source.get('quote'), str) and len(source['quote']) > 2000
    source = normalize_source({**source, 'quote': ''} if oversized else source)
    menu.setToolTipsVisible(True)
    action = menu.addAction(t('writing_send_excerpt'))
    action.setObjectName('incremento_send_to_writing')
    enabled = bool(source['quote'])
    action.setEnabled(enabled)
    if not enabled:
        action.setToolTip(t('writing_send_excerpt_limit') if oversized else t('writing_send_excerpt_hint'))
    writing = _writing()
    dock = writing._writing_dock
    identity = writing._writing_identity()
    direct = dock is not None and dock.isVisible() and writing._writing_profile == get_active_profile()
    if direct:
        title = dock._title_lbl.text().replace('&', '&&')
        action.setText(t('writing_send_excerpt') + ' · ' + title[:80])
        action.triggered.connect(lambda _=False: send_to_writing(source, is_current=lambda:
            is_current() and writing._writing_identity_is_current(identity)))
        choose = menu.addAction(t('writing_choose_destination'))
        choose.setObjectName('incremento_choose_writing')
        choose.setEnabled(enabled)
        choose.triggered.connect(lambda _=False: choose_writing(source, is_current=is_current) if is_current() else None)
    else:
        action.triggered.connect(lambda _=False: choose_writing(source, is_current=is_current) if is_current() else None)
    backlinks = menu.addAction(t('writing_excerpt_backlinks'))
    backlinks.triggered.connect(lambda _=False: show_backlinks(source, owner=owner, is_current=is_current) if is_current() else None)


def refresh_readers():
    from .pdf_page_links import refresh_page_links
    refresh_page_links()


class SourceMargin(QWidget):
    """Display-only excerpt arrows; keep link metadata out of the editable prose."""
    def __init__(self, dock, editor):
        super().__init__(dock)
        self.dock, self.editor, self.rows, self.identity = dock, editor, [], None
        self.buttons, self.positions = {}, {}
        self.setObjectName('writing_source_margin')
        self.setAccessibleName(t('writing_excerpt_sources'))
        self.setFixedWidth(28)
        self.hide()
        self.request = 0
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self.render)
        editor.textChanged.connect(lambda: self._render_timer.start(0))
        editor.verticalScrollBar().valueChanged.connect(self.update_positions)
        editor.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Paint, QEvent.Type.Resize):
            self.update_positions()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_positions()

    def update_positions(self, *_):
        if not self.current() or self.isHidden():
            return
        candidates = []
        for anchor, cursor in self.positions.items():
            if cursor.document() is not self.editor.document():
                continue
            cursor = type(cursor)(cursor)
            cursor.setPosition(max(0, cursor.selectionStart() - 1))
            rect = self.editor.cursorRect(cursor)
            if rect.bottom() < 0 or rect.top() > self.editor.viewport().height():
                self.buttons[anchor].hide()
                continue
            point = self.editor.viewport().mapToGlobal(QPoint(0, rect.center().y()))
            y = self.mapFromGlobal(point).y() - 11
            candidates.append((y, anchor))
        bottom = -24
        for y, anchor in sorted(candidates):
            y = max(0, y, bottom + 2)
            button = self.buttons[anchor]
            button.move(2, y)
            button.setVisible(y + 22 <= self.height())
            bottom = y + 22

    def description(self, row):
        text = row['source_title'] + ' · ' + source_label(row['source'])
        text += '\n' + row['source']['quote'][:180]
        return '<qt>' + escape(text).replace('\n', '<br>') + '</qt>'

    def context_menu(self, anchor, button, point):
        menu = QMenu(button)
        for action, label in (('source', 'writing_excerpt_preview'), ('excerpt', 'writing_excerpt_jump'),
                              ('unlink', 'writing_excerpt_unlink')):
            menu.addAction(t(label)).triggered.connect(lambda _=False, action=action:
                self.follow(QUrl('inc://' + action + '/' + anchor)))
        menu.exec(button.mapToGlobal(point))

    def preview_markdown(self, text):
        known = {row['anchor'] for row in self.rows} if self.current() else set()
        text = re.sub(r'\n?<!-- incremento-excerpt:([a-f0-9]{32}) -->',
            lambda match: ' [↗](inc://source/' + match[1] + ')' if match[1] in known else '', text)
        return strip_markers(text)

    def style_preview(self):
        preview = self.dock._preview
        color = '#a9c7ff' if preview.palette().color(preview.foregroundRole()).lightness() > 128 else '#275fa6'
        cursor = preview.document().find('↗')
        while not cursor.isNull():
            if cursor.charFormat().anchorHref().startswith('inc://source/'):
                style = QTextCharFormat()
                style.setForeground(QColor(color))
                cursor.mergeCharFormat(style)
            cursor = preview.document().find('↗', cursor)

    def follow_preview(self, url):
        if url.scheme() == 'inc':
            self.follow(url)
        elif not url.scheme() and not url.path() and url.fragment():
            self.dock._preview.scrollToAnchor(url.fragment())
        elif url.isRelative() or url.scheme() in ('file', 'qrc'):
            self.dock._preview.setSource(url)
        else:
            QDesktopServices.openUrl(url)

    def preview_tooltip(self, url):
        row = next((row for row in self.rows if row['anchor'] == url.path().lstrip('/')), None)
        self.dock._preview.setToolTip(self.description(row) if row and url.scheme() == 'inc' and self.current() else '')

    def current(self):
        writing = _writing()
        return self.identity is not None and writing._writing_dock is self.dock and writing._writing_identity_is_current(self.identity)

    def set_rows(self, rows):
        self.rows = rows
        self.identity = _writing()._writing_identity()
        self.render()
        _writing()._refresh_markdown_preview()

    def render(self):
        if not self.current():
            self.hide()
            return
        document = self.editor.document()
        self.positions = {row['anchor']: document.find(marker(row['anchor'])) for row in self.rows}
        self.positions = {anchor: cursor for anchor, cursor in self.positions.items() if not cursor.isNull()}
        for anchor in list(self.buttons):
            if anchor not in self.positions:
                button = self.buttons.pop(anchor)
                button.hide()
                button.deleteLater()
        for row in self.rows:
            anchor = row['anchor']
            if anchor not in self.positions:
                continue
            if anchor not in self.buttons:
                button = QToolButton(self)
                button.setObjectName('writing_source_' + anchor)
                button.setText('↗')
                button.setAutoRaise(True)
                button.setFixedSize(24, 22)
                button.setStyleSheet('QToolButton { padding: 0; min-height: 0; font-size: 16px; border-radius: 3px; }')
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                button.clicked.connect(lambda _=False, anchor=anchor: self.follow(QUrl('inc://source/' + anchor)))
                button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                button.customContextMenuRequested.connect(lambda point, anchor=anchor, button=button:
                    self.context_menu(anchor, button, point))
                self.buttons[anchor] = button
            button = self.buttons[anchor]
            button.setToolTip(self.description(row))
            button.setAccessibleName(t('writing_excerpt_preview') + ': ' + row['source_title'] + ' · ' + source_label(row['source']))
        self.setVisible(bool(self.buttons))
        self.update_positions()

    def reload(self):
        writing = _writing()
        self.request += 1
        request, self.identity = self.request, writing._writing_identity()
        self.rows = []
        self.hide()
        collection = getattr(writing.mw, 'col', None)
        if collection is None or self.identity is None:
            return
        _, profile, cid, _ = self.identity
        root = writing._ADDON_DIR
        def ready(rows):
            if self.current() and request == self.request and collection is writing.mw.col:
                self.set_rows(rows)
        def failed(_error):
            if self.current() and request == self.request:
                tooltip(t('writing_excerpt_failed'), parent=self.dock)
        QueryOp(parent=writing.mw, op=lambda col: list_links(root, profile, writing_card_id=cid)
                if col is collection else [], success=ready).failure(failed).run_in_background()

    def follow(self, url):
        if not self.current():
            return
        anchor = url.path().lstrip('/')
        row = next((row for row in self.rows if row['anchor'] == anchor), None)
        if row is None or url.scheme() != 'inc':
            return
        if url.host() == 'source':
            preview_source(row, owner=self.dock, is_current=lambda: self.current() and self.dock.isVisible())
        elif url.host() == 'excerpt':
            _writing().jump_to_excerpt(anchor)
        elif url.host() == 'unlink':
            self.unlink(anchor)

    def unlink(self, anchor):
        if self.current() and any(row['anchor'] == anchor for row in self.rows):
            # Removing only the marker preserves prose and participates in native Undo.
            cursor = self.dock._editor.document().find(marker(anchor))
            if not cursor.isNull():
                cursor.beginEditBlock()
                cursor.removeSelectedText()
                start = self.dock._editor.document().find(marker(anchor, start=True))
                if not start.isNull():
                    start.removeSelectedText()
                cursor.endEditBlock()
                self.render()
                _writing()._refresh_markdown_preview()

    def preview_at_cursor(self):
        if not self.current():
            return
        editor = self.dock._editor
        positions = []
        for row in self.rows:
            cursor = editor.document().find(marker(row['anchor']))
            if not cursor.isNull():
                positions.append((cursor.selectionStart(), row))
        positions.sort(key=lambda item: item[0])
        if positions:
            position = editor.textCursor().position()
            row = next((row for start, row in positions if start >= position), positions[-1][1])
            preview_source(row, owner=self.dock, is_current=lambda: self.current() and self.dock.isVisible())


def preview_source(row, *, owner=None, is_current=lambda: True):
    source = row['source']
    if source['kind'] == 'pdf':
        from .pdf_reference_workspace import open_reference
        open_reference(source['card_id'], source['page'], scroll_ratio=source.get('scroll', 0),
            page_y=source.get('page_y'), excerpt=source['quote'], owner=owner, is_current=is_current,
            beside=True, reuse_source=True)
    elif source['kind'] == 'epub':
        from .epub_reference_workspace import open_reference
        open_reference(source, owner=owner, is_current=is_current)
    else:
        profile, collection = get_active_profile(), mw.col
        def work(col):
            return col.get_note(col.get_card(source['card_id']).nid).fields
        def ready(fields):
            if profile != get_active_profile() or collection is not mw.col or not is_current():
                return
            dialog = QDialog(owner or mw)
            dialog.setWindowTitle(t('writing_excerpt_preview'))
            dialog.resize(620, 580)
            layout = QVBoxLayout(dialog)
            text = QTextBrowser(dialog)
            plain = QTextDocument()
            plain.setHtml('<hr>'.join(str(field)[:100000] for field in fields[:32]))
            text.setPlainText(plain.toPlainText())
            layout.addWidget(text)
            _keep(dialog)
        QueryOp(parent=mw, op=work, success=ready).failure(
            lambda _: tooltip(t('writing_excerpt_failed')) if profile == get_active_profile() and is_current() else None
        ).run_in_background()


def show_backlinks(source, *, owner=None, is_current=lambda: True):
    writing = _writing()
    profile, collection, root = get_active_profile(), mw.col, writing._ADDON_DIR
    dialog = QDialog(owner or mw)
    dialog.setWindowTitle(t('writing_excerpt_backlinks'))
    dialog.resize(480, 400)
    layout = QVBoxLayout(dialog)
    choices = QListWidget(dialog)
    choices.setAccessibleName(t('writing_excerpt_backlinks'))
    layout.addWidget(choices)
    button = QPushButton(t('writing_excerpt_jump'), dialog)
    button.setEnabled(False)
    layout.addWidget(button)
    alive = [True]
    dialog.finished.connect(lambda _: alive.__setitem__(0, False))
    def current():
        return alive[0] and profile == get_active_profile() and collection is mw.col and is_current()
    def work(col):
        result = []
        for row in list_links(root, profile, source=source):
            try:
                note = col.get_note(col.get_card(row['writing_card_id']).nid)
                if note.note_type()['name'] == WRITING_NOTE_TYPE:
                    result.append((row, str(note['Title'])[:240], str(note[WRITING_FILE_FIELD])))
            except (KeyError, ValueError):
                continue
        return result
    def ready(rows):
        if not current():
            return
        for row, title, relpath in rows:
            item = QListWidgetItem(title + '\n' + row['source']['quote'][:160])
            item.setData(Qt.ItemDataRole.UserRole, (row, title, relpath))
            choices.addItem(item)
        button.setEnabled(bool(rows))
        if rows:
            choices.setCurrentRow(0)
        else:
            item = QListWidgetItem(t('writing_excerpt_none'))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            choices.addItem(item)
    def open_selected():
        item = choices.currentItem()
        if item is None or not current() or not item.data(Qt.ItemDataRole.UserRole):
            return
        row, _, _ = item.data(Qt.ItemDataRole.UserRole)
        open_backlink(source, row['anchor'], is_current=current, on_open=dialog.accept)
    button.clicked.connect(open_selected)
    choices.itemDoubleClicked.connect(lambda _: open_selected())
    _keep(dialog)
    QueryOp(parent=mw, op=work, success=ready).failure(
        lambda _: tooltip(t('writing_excerpt_failed')) if current() else None).run_in_background()


def open_backlink(source, anchor, *, is_current=lambda: True, on_open=lambda: None):
    writing = _writing()
    profile, collection, root = get_active_profile(), mw.col, writing._ADDON_DIR
    def current():
        return profile == get_active_profile() and collection is mw.col and is_current()
    def work(col):
        row = next((row for row in list_links(root, profile, source=source) if row['anchor'] == anchor), None)
        if row is None:
            raise ValueError('Excerpt is no longer linked')
        return _target(col, root, profile, row['writing_card_id'])
    def ready(result):
        if current() and writing.show_writing_in_dock(*result, keep_open=True):
            writing.jump_to_excerpt(anchor)
            on_open()
    QueryOp(parent=mw, op=work, success=ready).failure(
        lambda _: tooltip(t('writing_excerpt_failed')) if current() else None).run_in_background()
