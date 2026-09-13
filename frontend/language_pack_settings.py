"""Spreadsheet import/export drafts for the captured Settings profile."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import stat
import tempfile

from aqt.qt import QFileDialog, QLabel, QPushButton, Qt, QVBoxLayout, QWidget
from anki import lang as anki_language

try:
    from ..backend.i18n import resolve_locale, t
    from ..backend.language_packs import (
        MAX_FILE_BYTES, LanguagePackError, builtin_pack, export_csv,
        list_packs, load_pack, parse_csv,
    )
except ImportError:
    from backend.i18n import resolve_locale, t
    from backend.language_packs import (
        MAX_FILE_BYTES, LanguagePackError, builtin_pack, export_csv,
        list_packs, load_pack, parse_csv,
    )


class LanguagePackControls(QWidget):
    """Import stages one pack; the Settings composition root owns persistence."""

    def __init__(self, combo, addon_dir: str, profile: str, parent=None):
        super().__init__(parent)
        self.combo, self.addon_dir, self.profile = combo, addon_dir, profile
        self._pending_pack = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(t('settings_language_pack_hint'))
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.template_button = QPushButton(t('settings_language_export_template'))
        self.export_button = QPushButton(t('settings_language_export_selected'))
        self.import_button = QPushButton(t('settings_language_import'))
        for button in (self.template_button, self.export_button, self.import_button):
            layout.addWidget(button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.template_button.clicked.connect(lambda: self._choose_export(True))
        self.export_button.clicked.connect(lambda: self._choose_export(False))
        self.import_button.clicked.connect(self._choose_import)
        self._refresh_choices()

    @property
    def pending_pack(self):
        return copy.deepcopy(self._pending_pack)

    def _refresh_choices(self, selected=None):
        selected = selected or self.combo.currentData()
        for index in reversed(range(self.combo.count())):
            if str(self.combo.itemData(index)).startswith('custom:'):
                self.combo.removeItem(index)
        packs = {p['locale']: p for p in list_packs(self.addon_dir, self.profile)}
        if self._pending_pack:
            packs[self._pending_pack['locale']] = self._pending_pack
        for code, pack in sorted(packs.items()):
            self.combo.addItem(t('settings_language_imported_name', name=pack['name']), 'custom:' + code)
        if str(selected).startswith('custom:') and self.combo.findData(selected) < 0:
            self.combo.addItem(t('settings_language_missing_pack', locale=selected[7:]), selected)
        index = self.combo.findData(selected)
        if index >= 0:
            self.combo.setCurrentIndex(index)

    def select_choice(self, choice):
        self._refresh_choices(choice)

    def import_file(self, path) -> bool:
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
            with os.fdopen(fd, 'rb') as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
                    raise LanguagePackError('size')
                pack = parse_csv(stream.read(MAX_FILE_BYTES + 1))
            # No filesystem or active translator changes until Settings is accepted.
            self._pending_pack = pack
            self._refresh_choices('custom:' + pack['locale'])
            self.status.setText(t('settings_language_import_ready', name=pack['name'],
                                  count=sum(len(items) for items in pack['translations'].values())))
            return True
        except (OSError, ValueError) as exc:
            detail = str(exc) if isinstance(exc, LanguagePackError) else t('settings_language_file_error')
            self.status.setText(t('settings_language_import_failed', detail=detail))
            return False

    def export_file(self, path, *, template=False) -> bool:
        temporary = None
        try:
            pack = None
            if not template:
                choice = self.combo.currentData()
                if str(choice).startswith('custom:'):
                    locale = choice[7:]
                    pack = self._pending_pack if self._pending_pack and self._pending_pack['locale'] == locale else load_pack(self.addon_dir, self.profile, locale)
                    if pack is None:
                        raise LanguagePackError('format')
                else:
                    pack = builtin_pack(resolve_locale(choice, getattr(anki_language, 'current_lang', 'en')))
            data = export_csv(pack)
            destination = Path(path)
            fd, temporary = tempfile.mkstemp(prefix='.incremento-translations-', dir=destination.parent)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            temporary = None
            self.status.setText(t('settings_language_export_success'))
            return True
        except (OSError, ValueError) as exc:
            detail = str(exc) if isinstance(exc, LanguagePackError) else t('settings_language_file_error')
            self.status.setText(t('settings_language_export_failed', detail=detail))
            return False
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)

    def _choose_import(self):
        path, _filter = QFileDialog.getOpenFileName(self, t('settings_language_import'), '', t('settings_language_csv_filter'))
        if path:
            self.import_file(path)

    def _choose_export(self, template):
        path, _filter = QFileDialog.getSaveFileName(self, t('settings_language_export_template') if template else t('settings_language_export_selected'), 'incremento-translations.csv', t('settings_language_csv_filter'))
        if path:
            self.export_file(path, template=template)
