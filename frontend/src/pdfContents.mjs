const MAX_ENTRIES = 2000;
const MAX_DEPTH = 12;

export async function loadPdfContents(doc, isCurrent = () => true) {
  const result = [];
  const seen = new Set();
  const destinations = new Map();
  try {
    const outline = await doc.getOutline();
    const pending = (Array.isArray(outline) ? outline : []).slice(0, MAX_ENTRIES).reverse().map(node => ({node, depth: 0}));
    let visited = 0;
    while (pending.length && visited++ < MAX_ENTRIES && isCurrent()) {
      const {node, depth} = pending.pop();
      if (!node || seen.has(node)) continue;
      seen.add(node);
      try {
        let dest = node.dest;
        if (typeof dest === 'string') {
          if (!destinations.has(dest)) destinations.set(dest, await doc.getDestination(dest));
          dest = destinations.get(dest);
        }
        if (Array.isArray(dest) && dest.length) {
          const index = Number.isInteger(dest[0]) ? dest[0] : await doc.getPageIndex(dest[0]);
          if (Number.isInteger(index) && index >= 0 && index < doc.numPages) {
            const title = String(node.title || '').trim().slice(0, 240);
            if (title) result.push({id: result.length, title, depth, page: index + 1, destination: dest});
          }
        }
      } catch (_) { /* A broken destination must not hide the remaining chapters. */ }
      if (depth < MAX_DEPTH && Array.isArray(node.items)) {
        for (let i = Math.min(node.items.length, MAX_ENTRIES - visited - pending.length) - 1; i >= 0; --i) {
          pending.push({node: node.items[i], depth: depth + 1});
        }
      }
    }
  } catch (_) { /* Outlines are optional. Saved places remain available. */ }
  return isCurrent() ? result : [];
}

export async function resolvePdfContentsLocation(doc, entry) {
  if (!entry || !Number.isInteger(entry.page) || entry.page < 1 || entry.page > doc.numPages) return null;
  let pageFraction = 0;
  const dest = entry.destination;
  const type = dest?.[1]?.name;
  const top = type === 'XYZ' ? dest[3]
    : type === 'FitH' || type === 'FitBH' ? dest[2]
      : type === 'FitR' ? dest[5] : null;
  if (Number.isFinite(top)) {
    try {
      const pg = await doc.getPage(entry.page);
      const viewport = pg.getViewport({scale: 1});
      const [, y] = viewport.convertToViewportPoint(0, top);
      pageFraction = Math.max(0, Math.min(y / viewport.height, 1));
    } catch (_) { /* Page-level navigation is still useful without coordinates. */ }
  }
  return {page: entry.page, pageFraction};
}
