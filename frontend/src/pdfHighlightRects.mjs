// A DOM Range can report both an inline element's box and its text box, plus
// separate boxes for changes of font (for example italic words). Paint their
// union once per line, bridging only gaps small enough to be inter-word spaces.
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
      const maxGap = previous ? Math.min(previous.h, rect.h) * 0.5 : 0;
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
