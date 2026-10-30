/** Stable text-mark vocabulary. Color and selection remain independent. */
export const ANNOTATION_STYLES = ['highlight', 'underline', 'squiggly', 'dashed', 'dotted', 'strikeout'];
const kinds = {highlight: 'Highlight', underline: 'Underline', squiggly: 'Squiggly',
  dashed: 'Underline', dotted: 'Underline', strikeout: 'StrikeOut'};

export function annotationStyle(mark) {
  if (mark?.color === 'snapshot') return null;
  const native = mark?.pdf_annotation;
  if (native?.kind && !Object.values(kinds).includes(native.kind)) return null;
  if (ANNOTATION_STYLES.includes(native?.incremento_style) && kinds[native.incremento_style] === native.kind) {
    return native.incremento_style;
  }
  if (native?.kind) return Object.keys(kinds).find(key => kinds[key] === native.kind);
  return ANNOTATION_STYLES.includes(mark?.style) ? mark.style : 'highlight';
}

export function withAnnotationStyle(mark, style) {
  if (!ANNOTATION_STYLES.includes(style) || annotationStyle(mark) === null) return null;
  const native = {...mark.pdf_annotation, kind: kinds[style], incremento_style: style,
    opacity: style === 'highlight' ? .42 : 1};
  delete native.quads;
  delete native.xref;
  return {...mark, pdf_annotation: native};
}

/** Coordinates stay in PDF points; SVG scales naturally with zoom. */
export function annotationLine(style, width, height) {
  if (!ANNOTATION_STYLES.includes(style) || style === 'highlight'
      || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  const y = style === 'strikeout' ? height / 2 : Math.max(1, height - 2);
  let path = `M0 ${y} L${width} ${y}`;
  if (style === 'squiggly') {
    path = `M0 ${y}`;
    // Bound work for malformed geometry without distorting normal page widths.
    const step = Math.max(4, width / 2000);
    for (let x = 0, i = 0; x < width; x += step, i++) {
      const end = Math.min(width, x + step);
      path += ` Q${(x + end) / 2} ${y + (i % 2 ? 2 : -2)} ${end} ${y}`;
    }
  }
  return {path, dash: style === 'dashed' ? '4 3' : style === 'dotted' ? '0 3' : undefined,
    cap: style === 'dotted' ? 'round' : 'butt'};
}
