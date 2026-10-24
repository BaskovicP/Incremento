// Bound backing pixels without changing CSS page geometry, text or highlights.
export function pdfCanvasPlan(viewport, pixelRatio) {
  const {width, height} = viewport;
  if (![width, height].every(value => Number.isFinite(value) && value > 0)) {
    throw new RangeError('Invalid PDF page geometry');
  }
  const density = Number.isFinite(pixelRatio) && pixelRatio > 0 ? pixelRatio : 1;
  // Reserve rounding headroom for ceil(width * pixels) and ceil(height * pixels).
  const pixels = Math.min(density, 8192 / width, 8192 / height,
    Math.sqrt((8_000_000 - 32768) / (width * height)));
  return {pixels, canvasWidth: Math.max(1, Math.ceil(width * pixels)),
    canvasHeight: Math.max(1, Math.ceil(height * pixels))};
}
