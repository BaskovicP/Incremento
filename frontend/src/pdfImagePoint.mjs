/** Map a reader click to the displayed page, independent of zoom and scroll. */
export function pdfImagePoint(clientX, clientY, rect) {
  if (!rect) return null;
  const { left, top, width, height } = rect;
  if (![clientX, clientY, left, top, width, height].every(Number.isFinite)
    || width <= 0 || height <= 0) return null;
  const x = (clientX - left) / width;
  const y = (clientY - top) / height;
  return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? { x, y } : null;
}
