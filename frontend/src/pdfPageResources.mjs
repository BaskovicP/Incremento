import {forgetPdfPageText} from './pdfTextCache.mjs';

const owners = new WeakMap();
export function retainPdfPage(page, owner) {
  if (!owners.has(page)) owners.set(page, new Set());
  owners.get(page).add(owner);
}
export function cleanupUnusedPdfPage(page) {
  if (owners.get(page)?.size) return;
  owners.delete(page);
  forgetPdfPageText(page);
  try {page.cleanup();} catch (_) {}
}
export function releasePdfPage(page, owner) {
  owners.get(page)?.delete(owner);
  cleanupUnusedPdfPage(page);
}

export function estimatePdfPageBytes(page) {
  // This version-pinned PDF.js detail is optional: unknown engines get a
  // conservative estimate, so losing the optimization never expands the cache.
  if (!page._intentStates?.values) return 16 * 1024 * 1024;
  let bytes = 65536;
  const seen = new Set();
  for (const state of page._intentStates.values()) {
    const list = state.operatorList;
    bytes += (list?.fnArray?.length || 0) * 32;
    for (const args of list?.argsArray || []) {
      let image = args?.[0];
      if (typeof image === 'string') {
        if (seen.has(image)) continue;
        seen.add(image);
        try {
          image = page.objs?.has(image) ? page.objs.get(image)
            : page.commonObjs?.has(image) ? page.commonObjs.get(image) : null;
        } catch (_) {image = null;}
      } else if (image && typeof image === 'object') {
        if (seen.has(image)) continue;
        seen.add(image);
      }
      const width = image?.width || image?.bitmap?.width;
      const height = image?.height || image?.bitmap?.height;
      if (Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0) {
        bytes += Math.min(512 * 1024 * 1024, Math.max(width * height * 4, image.dataLen || 0));
      }
    }
  }
  return bytes;
}
