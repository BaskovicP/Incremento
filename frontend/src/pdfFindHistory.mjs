function normalizedPage(value) {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : null;
}


export function capturePdfFindStartPage(startPage, currentPage) {
  return normalizedPage(startPage) ?? normalizedPage(currentPage);
}


export function pdfFindReturnDelta(startPage, currentPage) {
  const target = normalizedPage(startPage);
  const current = normalizedPage(currentPage);
  if (target === null || current === null) return null;
  return target - current;
}
