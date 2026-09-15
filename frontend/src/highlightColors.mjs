/** Legacy swatches plus validated RGB hex colors; never interpolate arbitrary CSS. */
export const HL_COLORS = {
  yellow: 'rgba(255,220,0,0.45)', green: 'rgba(0,200,80,0.4)',
  blue: 'rgba(30,144,255,0.4)', pink: 'rgba(255,80,140,0.4)',
  aqua: 'rgba(45,212,191,0.42)', orange: 'rgba(251,146,60,0.42)',
  red: 'rgba(248,113,113,0.42)', purple: 'rgba(168,85,247,0.4)',
};
export const HL_SOLID = {
  yellow: '#FFE000', green: '#00C850', blue: '#1E90FF', pink: '#FF508C',
  aqua: '#2DD4BF', orange: '#FB923C', red: '#F87171', purple: '#A855F7',
  snapshot: '#2563EB',
};
export function normalizeHighlightColor(value) {
  const color = String(value || '').trim().toLowerCase();
  if (Object.hasOwn(HL_COLORS, color)) return color;
  if (/^#[0-9a-f]{3}$/.test(color)) return '#' + [...color.slice(1)].map(c => c + c).join('');
  return /^#[0-9a-f]{6}$/.test(color) ? color : null;
}
export function highlightSolidColor(value) {
  const color = value === 'snapshot' ? value : normalizeHighlightColor(value);
  return Object.hasOwn(HL_SOLID, color) ? HL_SOLID[color] : color || '#9CA3AF';
}
export function highlightBackgroundColor(value) {
  const color = normalizeHighlightColor(value);
  if (!color) return HL_COLORS.yellow;
  if (HL_COLORS[color]) return HL_COLORS[color];
  return `rgba(${[1, 3, 5].map(i => parseInt(color.slice(i, i + 2), 16)).join(',')},0.42)`;
}
