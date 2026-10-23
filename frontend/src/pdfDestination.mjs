const clamp = value => Math.max(0, Math.min(value, 1));

/** Capture a physical point even when the entire PDF page fits in the preview. */
export function capturePdfDestination(scroll, page, selection = null, clientY = null) {
  if (!scroll || !page) return null;
  const rect = page.getBoundingClientRect();
  if (!Number.isFinite(rect.height) || rect.height <= 0 || !Number.isFinite(rect.top)) return null;
  let selectedTop = null;
  if (selection && !selection.isCollapsed && selection.rangeCount) {
    const range = selection.getRangeAt(0);
    if (page.contains(range.commonAncestorContainer)) {
      const first = Array.from(range.getClientRects()).find(item => item.width > 0 && item.height > 0);
      if (first) selectedTop = first.top;
    }
  }
  const top = selectedTop ?? (Number.isFinite(clientY) ? clientY : scroll.getBoundingClientRect().top);
  const extent = scroll.scrollHeight - scroll.clientHeight;
  return {page_y: clamp((top - rect.top) / rect.height),
    scroll_ratio: extent > 0 ? clamp(scroll.scrollTop / extent) : 0};
}

/** Place the chosen point a quarter of the way down the available reading area. */
export function pdfDestinationScrollRatio(point, pageHeight, visibleHeight) {
  const extent = pageHeight - visibleHeight;
  if (typeof point !== 'number' || !Number.isFinite(point) || extent <= 0) return 0;
  return clamp((clamp(point) * pageHeight - .25 * visibleHeight) / extent);
}
