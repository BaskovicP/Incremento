/**
 * Turn fragmented PDF selection boxes into continuous painted line segments.
 * PDF.js places words/font runs in separate spans, so getClientRects() can leave
 * unpainted word spaces and report overlapping element/text boxes. First group
 * boxes by their vertical alignment, then merge nearby boxes from left to right.
 * Painting each union once also prevents overlapping boxes from darkening the
 * highlight. The result covers the selected endpoints, not the full page width.
 *
 * This helper is shared by the blue live selection preview and saved highlights.
 * Heights and gaps use the same units, so the merge rule works at different zooms
 * and with either rendered CSS coordinates or unscaled PDF coordinates.
 */
export function pdfRectsShareLine(a, b) {
  const overlap = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  const centerDistance = Math.abs((a.y + a.h / 2) - (b.y + b.h / 2));
  // OCR words have different ascenders, descenders, and imperfect baselines.
  // Use the taller word for center tolerance without merging adjacent rows.
  return overlap >= Math.min(a.h, b.h) * 0.35
    && centerDistance <= Math.max(a.h, b.h) * 0.6;
}

export function normalizePdfHighlightRects(rects) {
  const valid = (Array.isArray(rects) ? rects : [])
    .filter(r => r && [r.x, r.y, r.w, r.h].every(Number.isFinite) && r.w > 0 && r.h > 0)
    .map(r => ({ x: r.x, y: r.y, w: r.w, h: r.h }))
    .sort((a, b) => b.h - a.h || a.y - b.y || a.x - b.x);

  const lines = [];
  for (const rect of valid) {
    let nearest = null;
    let distance = Infinity;
    for (const line of lines) {
      const reference = line[0];
      const candidate = Math.abs(reference.y + reference.h / 2 - rect.y - rect.h / 2);
      // The tallest original box anchors a row. Never compare against a growing
      // union, which could gradually bridge neighboring lines.
      if (candidate < distance && pdfRectsShareLine(reference, rect)) {
        nearest = line;
        distance = candidate;
      }
    }
    if (nearest) nearest.push(rect);
    else lines.push([rect]);
  }

  return lines.flatMap(line => {
    const merged = [];
    for (const rect of line.sort((a, b) => a.x - b.x)) {
      const previous = merged.at(-1);
      // The original half-height cutoff missed justified word spaces: the
      // reported 37 px text boxes had 19–23 px gaps, exceeding 18.5 px.
      // Allow one text height instead. This is still a bounded heuristic:
      // larger gaps stay separate, which avoids filling wide column gutters.
      const maxGap = previous ? Math.min(previous.h, rect.h) : 0;
      if (previous && rect.x - (previous.x + previous.w) <= maxGap) {
        const right = Math.max(previous.x + previous.w, rect.x + rect.w);
        const bottom = Math.max(previous.y + previous.h, rect.y + rect.h);
        previous.y = Math.min(previous.y, rect.y);
        previous.w = right - previous.x;
        previous.h = bottom - previous.y;
      } else {
        merged.push({ ...rect });
      }
    }
    return merged;
  }).sort((a, b) => a.y - b.y || a.x - b.x);
}
