import {normalizePdfHighlightRects} from './pdfHighlightRects.mjs';

export function buildPdfHighlightIndex(highlights, compare) {
  const sorted = [...highlights].sort(compare), byPage = new Map(), sortedByPage = new Map(), byId = new Map();
  let missingCards = 0;
  const add = (map, highlight) => {
    if (!map.has(highlight.page)) map.set(highlight.page, []);
    map.get(highlight.page).push(highlight);
  };
  for (const highlight of highlights) add(byPage, highlight);
  sorted.forEach((highlight, index) => {
    add(sortedByPage, highlight);
    const id = String(highlight.id || '');
    if (!byId.has(id)) byId.set(id, index);
    const linked = Number(highlight.linked_note_id || 0);
    if (!(Number.isInteger(linked) && linked > 0) && String(highlight.text || '').trim()) missingCards++;
  });
  return {sorted, byPage, sortedByPage, byId, missingCards};
}

const display = new WeakMap();
export function pdfDisplayHighlights(highlights) {
  if (!display.has(highlights)) display.set(highlights, highlights.map(highlight => ({...highlight,
    rects: highlight.color === 'snapshot' ? highlight.rects : normalizePdfHighlightRects(highlight.rects)})));
  return display.get(highlights);
}
