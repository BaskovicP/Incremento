// PDF.js may split a CJK word across text-layer spans. A synthetic English
// word separator must not change the selected text or a search excerpt.
const CJK = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;

export function joinPdfTextParts(left, right) {
  const previous = String(left || '');
  const next = String(right || '');
  if (!previous) return next;
  if (!next) return previous;
  const last = Array.from(previous).at(-1);
  const first = Array.from(next)[0];
  return `${previous}${CJK.test(last) && CJK.test(first) ? '' : ' '}${next}`;
}

export function truncatePdfText(value, length) {
  return Array.from(String(value || '')).slice(0, Math.max(0, length)).join('');
}
