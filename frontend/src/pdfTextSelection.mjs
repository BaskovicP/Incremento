import { joinPdfTextParts } from './pdfCjkText.mjs';
import { pdfRectsShareLine } from './pdfHighlightRects.mjs';

/** Copy exactly the selected characters, using rendered geometry for missing spaces. */
export function selectionCleaned(selection, textLayer) {
  if (!selection?.rangeCount || !textLayer) return '';
  try {
    const range = selection.getRangeAt(0);
    if (!textLayer.contains(range.commonAncestorContainer)) return '';
    const doc = textLayer.ownerDocument;
    // Walking text nodes also handles PDF.js marked-content wrappers. Slice the
    // actual Range endpoints rather than guessing them from repeated substrings.
    const walker = doc.createTreeWalker(textLayer, 4); // SHOW_TEXT
    let node;
    let text = '';
    let previous = null;
    let line = null;
    while ((node = walker.nextNode())) {
      if (!range.intersectsNode(node)) continue;
      const start = node === range.startContainer ? range.startOffset : 0;
      const end = node === range.endContainer ? range.endOffset : node.textContent.length;
      const piece = node.textContent.slice(start, end);
      if (!piece) continue;
      const part = doc.createRange();
      part.setStart(node, start);
      part.setEnd(node, end);
      const bounds = part.getBoundingClientRect();
      const rect = { x: bounds.left, y: bounds.top, w: bounds.width, h: bounds.height };
      const sameLine = line && pdfRectsShareLine(line.reference, rect);
      let joined = false;
      if (previous && /\S/.test(piece) && !/\s$/.test(text) && !/^\s/.test(piece)) {
        const gap = rect.x - (previous.x + previous.w);
        if (!sameLine && rect.y - line.bottom > Math.max(line.bottom - line.top, rect.h) * 0.85) {
          text += '\n\n';
        } else if (!sameLine && /\p{L}-$/u.test(text) && /^\p{Ll}/u.test(piece)) {
          text = text.slice(0, -1);
        } else if (!sameLine || gap > Math.min(previous.h, rect.h) * 0.1) {
          text = joinPdfTextParts(text, piece);
          joined = true;
        }
      }
      if (!joined) text += piece;
      if (/\S/.test(piece) && rect.w > 0 && rect.h > 0) {
        previous = rect;
        line = sameLine ? {
          reference: rect.h > line.reference.h ? rect : line.reference,
          top: Math.min(line.top, rect.y), bottom: Math.max(line.bottom, rect.y + rect.h),
        } : { reference: rect, top: rect.y, bottom: rect.y + rect.h };
      }
    }
    return text.replace(/[ \t\u00a0]+/g, ' ').trim();
  } catch {
    return (selection.toString() || '').trim();
  }
}
