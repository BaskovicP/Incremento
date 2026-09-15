"""Shared reader palette with the cross-platform HTML hex field."""
from aqt.qt import QColor, QColorDialog, QDialog

try:
    from ..backend.i18n import t
    from ..backend.highlight_colors import highlight_appearance
except ImportError:
    from i18n import t
    from highlight_colors import highlight_appearance


def choose_highlight_color(parent, current_color: str) -> str | None:
    rgb, _opacity = highlight_appearance(current_color)
    dialog = QColorDialog(QColor.fromRgbF(*rgb), parent)
    dialog.setWindowTitle(t('reader_choose_annotation_color'))
    # The native macOS panel omits HTML hex entry. Qt's palette has it on every OS.
    dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    selected = dialog.selectedColor()
    return selected.name().lower() if selected.isValid() else None
