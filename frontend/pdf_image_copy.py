"""Background native-image extraction for the PDF's standard context menu."""

import math

from aqt.qt import QApplication, QImage

try:
    from ..backend.i18n import t
    from ..backend.pdf_embedded_images import extract_pdf_image_at_point
except ImportError:
    from backend.i18n import t
    from backend.pdf_embedded_images import extract_pdf_image_at_point


def _set_image_clipboard(png: bytes) -> None:
    image = QImage.fromData(png, "PNG")
    if not image.isNull():
        QApplication.clipboard().setImage(image)


def add_pdf_image_copy_action(menu, *, pdf_path, point, is_current, run_in_background) -> None:
    """Keep the native menu responsive while checking the clicked bitmap.

    ``is_current`` covers the originating menu, profile, card and reader load.
    No Qt object is accessed by the worker and copying requires a user click.
    """
    if not isinstance(point, dict):
        return
    page, x, y = point.get("page"), point.get("x"), point.get("y")
    if (type(page) is not int or not 1 <= page <= 1_000_000
            or any(type(v) not in (int, float) or not 0 <= v <= 1 or not math.isfinite(v)
                   for v in (x, y))):
        return
    action = menu.addAction(t("reader_pdf_copy_embedded_image"))
    action.setEnabled(False)
    action.setToolTip(t("reader_pdf_image_checking"))
    menu.setToolTipsVisible(True)

    def done(future):
        if not is_current():
            return
        try:
            result = future.result()
        except Exception:
            action.setToolTip(t("reader_pdf_image_failed"))
            return
        if result.status != "ready":
            key = {
                "not_found": "reader_pdf_image_not_found",
                "too_large": "reader_pdf_image_too_large",
                "unavailable": "reader_pdf_image_unavailable",
            }.get(result.status, "reader_pdf_image_failed")
            action.setToolTip(t(key))
            return

        def copy(_checked=False):
            if is_current():
                _set_image_clipboard(result.png)

        action.triggered.connect(copy)
        action.setToolTip(t("reader_pdf_image_native_size"))
        action.setEnabled(True)

    try:
        run_in_background(
            lambda: extract_pdf_image_at_point(pdf_path, page_number=page, x_ratio=x, y_ratio=y), done,
        )
    except Exception:
        action.setToolTip(t("reader_pdf_image_failed"))
