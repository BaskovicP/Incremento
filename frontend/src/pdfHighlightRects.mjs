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
export function normalizePdfHighlightRects(rects) {
  const valid = (Array.isArray(rects) ? rects : [])
    .filter(r => r && [r.x, r.y, r.w, r.h].every(Number.isFinite) && r.w > 0 && r.h > 0)
    .map(r => ({ x: r.x, y: r.y, w: r.w, h: r.h }))
    .sort((a, b) => (a.y + a.h / 2) - (b.y + b.h / 2) || a.x - b.x);

  const lines = [];
  for (const rect of valid) {
    const line = lines.at(-1);
    const reference = line?.[0];
    const overlap = reference
      ? Math.min(reference.y + reference.h, rect.y + rect.h) - Math.max(reference.y, rect.y)
      : 0;
    const minHeight = reference ? Math.min(reference.h, rect.h) : 0;
    const centerDistance = reference
      ? Math.abs((reference.y + reference.h / 2) - (rect.y + rect.h / 2))
      : Infinity;
    // Compare against the original line box, so expanding a union cannot
    // gradually join neighboring lines in tightly spaced text.
    if (reference && overlap >= minHeight * 0.6 && centerDistance <= minHeight * 0.5) {
      line.push(rect);
    } else {
      lines.push([rect]);
    }
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
  });
}
