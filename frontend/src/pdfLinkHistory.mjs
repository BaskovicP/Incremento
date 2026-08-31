const DEFAULT_MAX_LINK_HISTORY = 50;


function normalizePdfLinkLocation(location) {
  const page = Number(location?.page);
  if (!Number.isInteger(page) || page < 1) return null;

  const rawScrollRatio = Number(location?.scrollRatio);
  const scrollRatio = Number.isFinite(rawScrollRatio)
    ? Math.max(0, Math.min(rawScrollRatio, 1))
    : 0;
  return { page, scrollRatio };
}


export function pushPdfLinkHistory(
  history,
  location,
  maxEntries = DEFAULT_MAX_LINK_HISTORY,
) {
  const normalized = normalizePdfLinkLocation(location);
  if (!normalized) return history;

  const existing = Array.isArray(history) ? history : [];
  const boundedMax = Math.max(1, Math.floor(Number(maxEntries) || DEFAULT_MAX_LINK_HISTORY));
  return [...existing, normalized].slice(-boundedMax);
}


export function takePdfLinkHistory(history) {
  if (!Array.isArray(history) || history.length === 0) {
    return { location: null, history: [] };
  }
  return {
    location: normalizePdfLinkLocation(history.at(-1)),
    history: history.slice(0, -1),
  };
}
