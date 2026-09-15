"""Explicit original-file linking and annotation refresh in the PDF reader."""
from pathlib import Path
import sys

from aqt.qt import QDialog, QDialogButtonBox, QFileDialog, QLabel, QPushButton, QVBoxLayout, Qt

try:
    from ..backend.i18n import t
    from .pdf_annotation_sync import sync_error_text
    from .file_shell import open_local_file, reveal_local_file
except ImportError:
    from i18n import t
    from pdf_annotation_sync import sync_error_text
    from file_shell import open_local_file, reveal_local_file


def show_pdf_annotation_dialog(parent, managed_path, source_path, request):
    existing = getattr(parent, '_annotation_dialog', None)
    if existing is not None:
        try:
            if existing.isVisible():
                existing.raise_()
                return
        except RuntimeError:
            pass
    dialog = QDialog(parent)
    parent._annotation_dialog = dialog
    dialog.setWindowTitle(t('reader_pdf_sync_title'))
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    intro = QLabel(t('reader_pdf_sync_explanation'))
    intro.setWordWrap(True)
    layout.addWidget(intro)
    source_label = QLabel()
    source_label.setTextFormat(Qt.TextFormat.PlainText)
    source_label.setWordWrap(True)
    layout.addWidget(source_label)
    status = QLabel(t('reader_pdf_sync_ready'))
    status.setWordWrap(True)
    layout.addWidget(status)
    source = [source_path]
    def update_source():
        source_label.setText(t('reader_pdf_sync_files', managed=managed_path,
                              original=source[0] or t('reader_pdf_sync_unlinked')))
    update_source()
    controls = []
    def sync(path=None, *, open_after=False):
        for control in controls:
            control.setEnabled(False)
        status.setText(t('reader_pdf_sync_running'))
        def done(result, error):
            if not dialog.isVisible():
                return
            for control in controls:
                control.setEnabled(True)
            if error:
                status.setText(sync_error_text(error))
                return
            source[0] = result['source_path']
            update_source()
            status.setText(t('reader_pdf_sync_conflicts') if result.get('conflicts') else t('reader_pdf_sync_complete'))
            if open_after:
                target = Path(source[0] or managed_path)
                if target.is_file() and not target.is_symlink():
                    open_local_file(str(target))
        request(path, done)
    def link():
        path, _filter = QFileDialog.getOpenFileName(dialog, t('reader_pdf_sync_link_original'), '', t('reader_pdf_file_filter'))
        if path:
            sync(path)
    def reveal():
        target = Path(source[0] or managed_path)
        if not target.is_file() or target.is_symlink() or not reveal_local_file(str(target)):
            status.setText(t('reader_pdf_sync_reveal_failed'))
    reveal_key = ('reader_pdf_sync_reveal_finder' if sys.platform == 'darwin' else
                  'reader_pdf_sync_reveal_explorer' if sys.platform.startswith('win') else
                  'reader_pdf_sync_reveal_folder')
    for key, action in [
        ('reader_pdf_sync_now', lambda: sync()),
        ('reader_pdf_sync_link_original', link),
        ('reader_pdf_sync_unlink', lambda: sync('')),
        ('reader_pdf_sync_open', lambda: sync(open_after=True)),
        (reveal_key, reveal),
    ]:
        button = QPushButton(t(key))
        button.clicked.connect(lambda _checked=False, action=action: action())
        layout.addWidget(button)
        controls.append(button)
    close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close.rejected.connect(dialog.reject)
    layout.addWidget(close)
    dialog.show()
