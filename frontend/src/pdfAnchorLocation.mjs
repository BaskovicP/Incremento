function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}


export function pdfAnchorScrollRatio({
  clientY,
  wrapperTop,
  pageHeight,
  visibleHeight,
  preferredViewportRatio = 0.25,
} = {}) {
  const y = finiteNumber(clientY);
  const top = finiteNumber(wrapperTop);
  const height = finiteNumber(pageHeight);
  const viewport = finiteNumber(visibleHeight);
  const preferred = finiteNumber(preferredViewportRatio);
  if (
    y === null
    || top === null
    || height === null
    || viewport === null
    || preferred === null
    || height <= 0
    || viewport <= 0
  ) {
    return null;
  }

  const maxOffset = Math.max(0, height - viewport);
  if (maxOffset <= 0) return 0;
  const pointOffset = Math.max(0, Math.min(y - top, height));
  const preferredOffset = viewport * Math.max(0, Math.min(preferred, 1));
  const targetOffset = Math.max(0, Math.min(pointOffset - preferredOffset, maxOffset));
  return targetOffset / maxOffset;
}
