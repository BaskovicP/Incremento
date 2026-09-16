export const PDF_APPEARANCE_MODES = Object.freeze(['original', 'dark', 'night']);

const PAGE_APPEARANCE = Object.freeze({
  original: Object.freeze({
    background: '#1e1e1e',
    filter: 'none',
  }),
  dark: Object.freeze({
    background: '#09090b',
    filter: 'invert(0.9) hue-rotate(180deg) brightness(0.92) contrast(0.92)',
  }),
  night: Object.freeze({
    background: '#17130d',
    filter: 'invert(0.88) hue-rotate(180deg) sepia(0.24) saturate(0.78) brightness(0.82) contrast(0.9)',
  }),
});

export function normalizePdfAppearanceMode(value) {
  return PDF_APPEARANCE_MODES.includes(value) ? value : 'original';
}

export function pdfPageAppearance(value) {
  return PAGE_APPEARANCE[normalizePdfAppearanceMode(value)];
}
