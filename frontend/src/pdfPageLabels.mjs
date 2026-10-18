/** PDF page positions remain one-based; labels are display-only metadata. */
export function normalizePdfPageLabels(labels, totalPages) {
  if (!Array.isArray(labels) || labels.length !== totalPages || totalPages < 1) return null;
  if (labels.some(label => typeof label !== 'string' || label.length > 128 || /[\u0000-\u001f\u007f]/u.test(label))) return null;
  return labels.map(label => label.trim());
}

export function pdfPageLabelsMessage(cardId, filename, labels) {
  if (!Number.isInteger(cardId) || cardId <= 0 || typeof filename !== 'string' || !filename || filename.length > 4096) return '';
  if (labels !== null && (!Array.isArray(labels) || labels.length > 20000 || !normalizePdfPageLabels(labels, labels.length))) return '';
  const message = 'incremento_pdf_page_labels:' + JSON.stringify({ cardId, filename, labels });
  return message.length <= 1000000 ? message : '';
}

export function pdfPageLocation(page, totalPages, labels, tr) {
  const current = totalPages > 0 ? page : '\u2014';
  const total = totalPages || '\u2014';
  const label = totalPages > 0 ? labels?.[page - 1] : null;
  return label
    ? tr('reader_page_location_labeled', { label, current, total })
    : tr('reader_page_location', { current, total });
}
