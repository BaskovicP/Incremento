"""Shared reader palette with the cross-platform HTML hex field."""
from aqt.qt import QColor, QColorDialog, QDialog, QIcon, QPixmap

try:
    from ..backend.i18n import t
    from ..backend.highlight_colors import highlight_appearance
    from ..backend.db import (
        READER_CUSTOM_COLOR_COUNT, get_reader_custom_colors, set_reader_custom_colors,
    )
except ImportError:
    from i18n import t
    from highlight_colors import highlight_appearance
    from db import (
        READER_CUSTOM_COLOR_COUNT, get_reader_custom_colors, set_reader_custom_colors,
    )


def choose_highlight_color(
    parent, current_color: str, *, addon_dir: str, profile: str,
    default_color: bool = False,
) -> str | None:
    """Restore/save profile swatches while leaving unrelated Qt palettes alone."""
    rgb, _opacity = highlight_appearance(current_color)
    saved_colors = get_reader_custom_colors(addon_dir, profile)
    original_colors = [
        QColorDialog.customColor(slot) for slot in range(READER_CUSTOM_COLOR_COUNT)
    ]
    dialog = None
    try:
        if saved_colors is not None:
            for slot, color in enumerate(saved_colors):
                QColorDialog.setCustomColor(slot, QColor(color))
        dialog = QColorDialog(QColor.fromRgbF(*rgb), parent)
        dialog.setWindowTitle(t('reader_default_annotation_color' if default_color else 'reader_choose_annotation_color'))
        # The native macOS panel omits HTML hex entry. Qt's palette has it on every OS.
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        result = dialog.exec()
        # "Add to Custom Colors" edits the palette, even when color selection is cancelled.
        set_reader_custom_colors(addon_dir, profile, [
            QColorDialog.customColor(slot).name().lower()
            for slot in range(READER_CUSTOM_COLOR_COUNT)
        ])
        if result != QDialog.DialogCode.Accepted:
            return None
        selected = dialog.selectedColor()
        return selected.name().lower() if selected.isValid() else None
    finally:
        for slot, color in enumerate(original_colors):
            QColorDialog.setCustomColor(slot, color)
        if dialog is not None:
            dialog.deleteLater()


def refresh_reader_default_highlight_color(profile: str, color: str) -> None:
    """Refresh open readers after the profile's preference was saved successfully."""
    try:
        from . import pdf_dock, epub_dock
    except ImportError:
        import pdf_dock
        import epub_dock
    pdf_dock.refresh_default_highlight_color(profile, color)
    epub_dock.refresh_default_highlight_color(profile, color)


def set_default_color_button(button, color: str) -> None:
    rgb, _opacity = highlight_appearance(color)
    swatch = QPixmap(12, 12)
    swatch.fill(QColor.fromRgbF(*rgb))
    button.setIcon(QIcon(swatch))
    button.setAccessibleName(t('reader_default_annotation_color'))
    button.setToolTip(t('reader_default_annotation_color_help'))
