"""Read native PDF bitmap pixels without rendering a page or writing media."""

from dataclasses import dataclass
import math
from pathlib import Path


MAX_PDF_BYTES = 512 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
MAX_PAGE_IMAGE_PIXELS = 32_000_000
MAX_PAGE_IMAGES = 2048
MAX_IMAGE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class PdfImageResult:
    status: str
    png: bytes = b""


def extract_pdf_image_at_point(
    pdf_path: str | Path, *, page_number: int, x_ratio: float, y_ratio: float,
) -> PdfImageResult:
    """Select the last painted bitmap at a point on the rotated, cropped page.

    Ratios describe the visible page, independent of reader zoom and scrolling.
    The PNG retains native pixel dimensions and transparency; page text,
    annotations and appearance filters are never rendered into it.
    """
    if (type(page_number) is not int or not 1 <= page_number <= 1_000_000
            or any(type(v) not in (int, float) or not 0 <= v <= 1 or not math.isfinite(v)
                   for v in (x_ratio, y_ratio))):
        return PdfImageResult("not_found")
    try:
        import pymupdf as fitz
    except ImportError:
        return PdfImageResult("unavailable")
    try:
        path = Path(pdf_path)
        if not path.is_file():
            return PdfImageResult("failed")
        if path.stat().st_size > MAX_PDF_BYTES:
            return PdfImageResult("too_large")
        with fitz.open(path) as doc:
            if not doc.is_pdf or doc.needs_pass or page_number > doc.page_count:
                return PdfImageResult("not_found")
            page = doc[page_number - 1]
            point = fitz.Point(page.rect.width * x_ratio, page.rect.height * y_ratio) * page.derotation_matrix
            # Inspect dimensions before the xref lookup hashes/decodes images.
            infos = page.get_image_info()
            if len(infos) > MAX_PAGE_IMAGES:
                return PdfImageResult("too_large")
            hits = []
            for info in infos:
                transform = fitz.Matrix(info["transform"])
                if abs(transform.a * transform.d - transform.b * transform.c) < 1e-12:
                    continue
                local = point * ~transform
                if 0 <= local.x <= 1 and 0 <= local.y <= 1:
                    hits.append(info)
            if not hits:
                return PdfImageResult("not_found")
            if (any(i["width"] * i["height"] > MAX_IMAGE_PIXELS for i in infos)
                    or sum(i["width"] * i["height"] for i in infos) > MAX_PAGE_IMAGE_PIXELS):
                return PdfImageResult("too_large")
            selected = hits[-1]
            resolved = page.get_image_info(xrefs=True)
            info = next(i for i in resolved if i["number"] == selected["number"])
            xref = info.get("xref", 0)
            if xref:
                extracted = doc.extract_image(xref)
                raw = extracted["image"]
                smask = int(extracted.get("smask", 0))
                mask = None
                if smask:
                    width = int(doc.xref_get_key(smask, "Width")[1])
                    height = int(doc.xref_get_key(smask, "Height")[1])
                    if width * height > MAX_IMAGE_PIXELS:
                        return PdfImageResult("too_large")
                    mask = fitz.Pixmap(doc, smask)
            else:
                # Inline PDF images have no xref. The text image block retains
                # their native stream and (where present) transparency mask.
                blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_IMAGES)["blocks"]
                block = next(b for b in blocks if b.get("type") == 1 and b["number"] == info["number"])
                raw = block["image"]
                mask = fitz.Pixmap(block["mask"]) if block.get("mask") else None
            if len(raw) > MAX_IMAGE_BYTES:
                return PdfImageResult("too_large")
            pixmap = fitz.Pixmap(raw)
            if pixmap.colorspace is None:
                return PdfImageResult("not_found")
            if pixmap.colorspace.n != 3:
                pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            if mask is not None:
                if pixmap.alpha:
                    pixmap = fitz.Pixmap(pixmap, 0)
                pixmap = fitz.Pixmap(pixmap, mask)
            png = pixmap.tobytes("png")
            if len(png) > MAX_IMAGE_BYTES:
                return PdfImageResult("too_large")
            return PdfImageResult("ready", png)
    except Exception:
        return PdfImageResult("failed")
