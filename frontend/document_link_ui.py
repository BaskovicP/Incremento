"""Explicit document linking and reference browsing from a captured source."""
from pathlib import Path

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QDialog, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit, QPushButton, QVBoxLayout, Qt
from aqt.utils import tooltip

try:
    from ..backend.document_links import add_document_link, list_document_links, remove_document_link, replace_document_target
    from ..backend.document_links import list_pdf_page_links, remove_pdf_page_link, replace_pdf_page_link
    from ..backend.document_links import normalize_connection_note, set_document_link_note
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
    from ..backend.pdf_reference import resolve_pdf_reference
    from ..backend.pdf_reader_state import maximum_reference_page
    from ..backend.pdf_manager import get_pdf_daily_limit_status
except ImportError:
    from backend.document_links import add_document_link, list_document_links, remove_document_link, replace_document_target
    from backend.document_links import list_pdf_page_links, remove_pdf_page_link, replace_pdf_page_link
    from backend.document_links import normalize_connection_note, set_document_link_note
    from backend.i18n import t
    from backend.paths import get_active_profile
    from backend.pdf_reference import resolve_pdf_reference
    from backend.pdf_reader_state import maximum_reference_page
    from backend.pdf_manager import get_pdf_daily_limit_status

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_dialogs = []
_generation = 0
_choice_request = 0
_choice_dialog = None


def _keep(dialog):
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    _dialogs.append(dialog)
    dialog.finished.connect(lambda *_: _dialogs.remove(dialog) if dialog in _dialogs else None)
    dialog.show()


def reset_for_profile_switch():
    global _generation
    _generation += 1
    for dialog in list(_dialogs):
        dialog.reject()


def choose_pdf(callback, *, is_current=lambda: True, connection_note=None):
    """Choose a document, then browse its PDF before confirming a destination."""
    global _choice_request
    from .pdf_bookshelf import _DocumentBookshelfDialog, _load_bookshelf_entries
    from .pdf_destination_dialog import PdfDestinationDialog
    _choice_request += 1
    request = _choice_request
    if _choice_dialog is not None:
        _choice_dialog.reject()
    profile, generation = get_active_profile(), _generation
    def current():
        return (profile == get_active_profile() and generation == _generation
                and request == _choice_request and is_current())
    def keep_choice(dialog):
        global _choice_dialog
        _choice_dialog = dialog
        def finished(*_):
            global _choice_dialog
            if _choice_dialog is dialog:
                _choice_dialog = None
        dialog.finished.connect(finished)
        _keep(dialog)
    def load(col):
        return [entry for entry in _load_bookshelf_entries(_ADDON_DIR, collection=col, profile=profile)
                if entry.kind == "PDF"]
    def ready(entries):
        if not current():
            return
        picker = _DocumentBookshelfDialog(mw, addon_dir=_ADDON_DIR, entries=entries,
                                          attachment_counts={}, selection_only=True)
        picker.setWindowTitle(t("reader_reference_choose"))
        def accepted():
            target_card_id = picker.selected_card_id
            if not current() or target_card_id is None:
                return
            def load_target(col):
                from .pdf_page_links import pdf_page_count
                snapshot = resolve_pdf_reference(_ADDON_DIR, profile, col, target_card_id)
                count = pdf_page_count(snapshot['path'])
                status = get_pdf_daily_limit_status(_ADDON_DIR, profile, target_card_id,
                                                   count_current_page=False, persist_usage=False)
                return snapshot, min(count, maximum_reference_page(status))
            def preview_target(result):
                if not current():
                    return
                snapshot, maximum = result
                preview = PdfDestinationDialog(snapshot, profile=profile, max_page=maximum, is_current=current,
                                               connection_note=connection_note)
                def selected():
                    location = preview.selected_location
                    if current() and location is not None:
                        callback(dict(location))
                preview.accepted.connect(selected)
                keep_choice(preview)
            QueryOp(parent=mw, op=load_target, success=preview_target).failure(
                lambda error: tooltip(t('reader_reference_unavailable')) if current() else None).run_in_background()
        picker.accepted.connect(accepted)
        keep_choice(picker)
    QueryOp(parent=mw, op=load, success=ready).failure(
        lambda error: tooltip(t("reader_reference_unavailable")) if current() else None).run_in_background()


def choose_reference(*, owner=None):
    from .pdf_reference_workspace import open_reference
    choose_pdf(lambda place: open_reference(place['card_id'], place['page'], scroll_ratio=place['scroll_ratio'],
                                            page_y=place['page_y'], beside=True, owner=owner))


def _refresh_page_links():
    from .pdf_page_links import refresh_page_links
    refresh_page_links()


def link_pdf(source, *, owner=None, is_current=lambda: True, replace_link_id=None,
             replace_direction='outgoing', show_after=True):
    profile, generation = get_active_profile(), _generation
    source = dict(source)
    def current():
        return profile == get_active_profile() and generation == _generation and is_current()
    def chosen(location):
        location = dict(location)
        target, page = location['card_id'], location['page']
        def save(col):
            # Validate both live identities again after the picker has closed.
            col.get_card(source["card_id"])
            if source.get('filename'):
                snapshot = resolve_pdf_reference(_ADDON_DIR, profile, col, source['card_id'])
                if snapshot['filename'] != source['filename']:
                    raise ValueError('Source document changed')
            target_snapshot = resolve_pdf_reference(_ADDON_DIR, profile, col, target)
            if (target_snapshot['filename'] != location['filename']
                    or target_snapshot['path'] != location['path']):
                raise ValueError('Destination document changed')
            from .pdf_page_links import pdf_page_count
            if page > pdf_page_count(target_snapshot['path']):
                raise ValueError('Destination page unavailable')
            status = get_pdf_daily_limit_status(_ADDON_DIR, profile, target, count_current_page=False, persist_usage=False)
            if page > maximum_reference_page(status):
                raise ValueError('Destination page is locked')
            if not current():
                return
            if replace_link_id is not None:
                if source['kind'] == 'pdf' and source.get('page', 0) > 0:
                    return replace_pdf_page_link(_ADDON_DIR, profile, source['card_id'], source['page'],
                        replace_link_id, direction=replace_direction, target_card_id=target, target_page=page,
                        target_scroll=location['scroll_ratio'], target_y=location['page_y'])
                return replace_document_target(_ADDON_DIR, profile, replace_link_id,
                    source_card_id=source["card_id"], target_card_id=target, target_page=page,
                    target_scroll=location['scroll_ratio'], target_y=location['page_y'])
            return add_document_link(_ADDON_DIR, profile, source_card_id=source["card_id"],
                source_kind=source["kind"], source_page=source.get("page", 0), quote=source.get("quote", "")[:2000],
                target_card_id=target, target_page=page, target_scroll=location['scroll_ratio'],
                target_y=location['page_y'], source_y=source.get('page_y'),
                connection_note=location.get('connection_note', ''))
        def saved(result):
            if result:
                _refresh_page_links()
            if current() and result:
                if show_after:
                    show_links(source, owner=owner, is_current=is_current)
        QueryOp(parent=mw, op=save, success=saved).failure(
            lambda error: tooltip(t("reader_reference_unavailable")) if current() else None).run_in_background()
    choose_pdf(chosen, is_current=current, connection_note='' if replace_link_id is None else None)


def show_links(source, *, owner=None, is_current=lambda: True):
    from .pdf_reference_workspace import open_reference
    source = dict(source)
    profile, generation = get_active_profile(), _generation
    collection = mw.col
    def current():
        return (profile == get_active_profile() and generation == _generation
                and collection is mw.col and is_current())
    def load(col):
        if source['kind'] == 'pdf' and source.get('page', 0) > 0:
            rows = list_pdf_page_links(_ADDON_DIR, profile, source['card_id'], source['page'])
        else:
            rows = list_document_links(_ADDON_DIR, profile, source['card_id'])
        for row in rows:
            try:
                row["title"] = resolve_pdf_reference(_ADDON_DIR, profile, col, row["target_card_id"])["title"]
            except ValueError:
                row["title"] = t("reader_reference_unavailable")
        return rows
    def ready(rows):
        if not current():
            return
        dialog = QDialog(mw)
        alive = [True]
        dialog.finished.connect(lambda *_: alive.__setitem__(0, False))
        def dialog_current():
            return alive[0] and current()
        dialog.setWindowTitle(t("reader_reference_links"))
        dialog.resize(640, 360)
        layout = QVBoxLayout(dialog)
        hint = QLabel(t("reader_reference_links_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        listing = QListWidget(dialog)
        listing.setAccessibleName(t("reader_reference_links"))
        for row in rows:
            label = t("reader_pdf_copied_label", title=row["title"], page=row["target_page"])
            listing.addItem(label + (" — " + row["quote"] if row["quote"] else ""))
        layout.addWidget(listing)
        note_header = QHBoxLayout()
        note_label = QLabel(t('reader_connection_note'), dialog)
        note_label.setWordWrap(True)
        note_header.addWidget(note_label, 1)
        save_note = QPushButton(t('reader_connection_note_save'), dialog)
        save_note.setObjectName('save-connection-note')
        save_note.setAutoDefault(False)
        note_header.addWidget(save_note)
        layout.addLayout(note_header)
        note_editor = QPlainTextEdit(dialog)
        note_editor.setObjectName('connection-note')
        note_editor.setAccessibleName(t('reader_connection_note'))
        note_editor.setPlaceholderText(t('reader_connection_note_placeholder'))
        note_editor.setMaximumHeight(100)
        note_label.setBuddy(note_editor)
        layout.addWidget(note_editor)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        def selected():
            index = listing.currentRow()
            return rows[index] if 0 <= index < len(rows) else None
        note_drafts = {}
        active_note = [None]
        note_pending = [False]
        def note_changed():
            row = selected()
            try:
                note = normalize_connection_note(note_editor.toPlainText())
                changed = row is not None and note != row['connection_note']
            except ValueError:
                changed = False
            save_note.setEnabled(changed and not note_pending[0])
        def load_note(*_):
            if active_note[0] is not None:
                note_drafts[active_note[0]] = note_editor.toPlainText()
            row = selected()
            active_note[0] = row['id'] if row else None
            note_editor.setPlainText(note_drafts.get(row['id'], row['connection_note']) if row else '')
            note_editor.setEnabled(row is not None and not note_pending[0])
            note_changed()
        def persist_note():
            row = selected()
            if not dialog_current() or not row or note_pending[0]:
                return
            try:
                note = normalize_connection_note(note_editor.toPlainText())
            except ValueError:
                return
            note_pending[0] = True
            listing.setEnabled(False)
            note_editor.setEnabled(False)
            note_changed()
            def work(col):
                if col is collection and dialog_current():
                    return set_document_link_note(_ADDON_DIR, profile, row['id'], source_card_id=source['card_id'],
                        source_page=source['page'] if source['kind'] == 'pdf' and source.get('page', 0) > 0 else None,
                        connection_note=note)
            def finished(result):
                if not dialog_current():
                    return
                if result:
                    _refresh_page_links()
                note_pending[0] = False
                if result:
                    row['connection_note'] = note
                else:
                    tooltip(t('reader_connection_note_failed'))
                listing.setEnabled(True)
                note_editor.setEnabled(selected() is not None)
                note_changed()
            QueryOp(parent=mw, op=work, success=finished).failure(lambda _error: finished(False)).run_in_background()
        note_editor.textChanged.connect(note_changed)
        listing.currentRowChanged.connect(load_note)
        save_note.clicked.connect(persist_note)
        if rows:
            listing.setCurrentRow(0)
        else:
            load_note()
        def preview(beside=False):
            row = selected()
            if dialog_current() and row:
                open_reference(row["target_card_id"], row["target_page"], scroll_ratio=row["target_scroll"],
                               page_y=row.get('target_y'), beside=beside, owner=owner, is_current=dialog_current)
        def remove():
            row = selected()
            if not dialog_current() or not row:
                return
            def work(col):
                if current():
                    if source['kind'] == 'pdf' and source.get('page', 0) > 0:
                        return remove_pdf_page_link(_ADDON_DIR, profile, source['card_id'], source['page'], row['id'])
                    return remove_document_link(_ADDON_DIR, profile, row["id"], source_card_id=source["card_id"])
            def removed(result):
                if result:
                    _refresh_page_links()
                if dialog_current() and result:
                    index = rows.index(row)
                    rows.pop(index)
                    listing.takeItem(index)
                    load_note()
            QueryOp(parent=mw, op=work, success=removed).run_in_background()
        actions = [("reader_reference_preview", lambda: preview()),
                   ("reader_reference_pin", lambda: preview(True)),
                   ("reader_reference_add", lambda: link_pdf(source, owner=owner, is_current=current)),
                   ("reader_reference_change", lambda: link_pdf(source, owner=owner, is_current=current,
                        replace_link_id=selected()["id"], replace_direction=selected().get('direction', 'outgoing')) if selected() else None),
                   ("reader_reference_remove", remove), ("reader_close", dialog.close)]
        for key, callback in actions:
            button = QPushButton(t(key))
            button.clicked.connect(lambda checked=False, action=callback: action())
            buttons.addWidget(button)
        listing.itemActivated.connect(lambda *_: preview())
        _keep(dialog)
    QueryOp(parent=mw, op=load, success=ready).failure(
        lambda error: tooltip(t("reader_reference_unavailable")) if current() else None).run_in_background()
