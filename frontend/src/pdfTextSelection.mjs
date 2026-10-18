import { joinPdfTextParts } from './pdfCjkText.mjs';
import { pdfRectsShareLine } from './pdfHighlightRects.mjs';

/** Attach only portable emphasis; PDF.js's private font family is not usable in Anki. */
export function annotatePdfTextStyles(textDivs, textContent, commonObjs) {
  const items = textContent?.items?.filter(item => typeof item?.str === 'string');
  if (!Array.isArray(textDivs) || !items || textDivs.length !== items.length
      || textDivs.some((div, index) => div.textContent !== items[index].str)) return false;
  for (let index = 0; index < items.length; index += 1) {
    let font;
    try { font = commonObjs?.get?.(items[index].fontName); } catch { font = null; }
    const name = String(font?.name || font?.fallbackName || '');
    const weight = Number(font?.cssFontInfo?.fontWeight);
    const bold = !!(font?.bold || font?.black || weight >= 600
      || /(?:bold|black|heavy|semibold)/i.test(name));
    const italic = !!(font?.italic || font?.cssFontInfo?.italicAngle
      || /(?:italic|oblique)/i.test(name));
    if (bold) textDivs[index].dataset.incBold = '1';
    if (italic) textDivs[index].dataset.incItalic = '1';
  }
  return true;
}

function normalizedRuns(rawRuns) {
  const runs = [];
  const append = (character, bold, italic) => {
    const last = runs.at(-1);
    if (last && last.bold === bold && last.italic === italic) last.text += character;
    else runs.push({ text: character, bold, italic });
  };
  let horizontalSpace = false;
  for (const run of rawRuns) {
    for (const char of run.text) {
      if (/[ \t\u00a0]/.test(char)) {
        if (!horizontalSpace) append(' ', run.bold, run.italic);
        horizontalSpace = true;
      } else {
        append(char, run.bold, run.italic);
        horizontalSpace = false;
      }
    }
  }
  while (runs.length && /^\s/.test(runs[0].text)) {
    runs[0].text = runs[0].text.slice(1);
    if (!runs[0].text) runs.shift();
  }
  while (runs.length && /\s$/.test(runs.at(-1).text)) {
    runs.at(-1).text = runs.at(-1).text.slice(0, -1);
    if (!runs.at(-1).text) runs.pop();
  }
  return runs;
}

/** Copy selected characters and their portable PDF emphasis, using geometry for gaps. */
export function selectionFormatted(selection, textLayer) {
  if (!selection?.rangeCount || !textLayer) return { text: '', runs: [] };
  try {
    const range = selection.getRangeAt(0);
    if (!textLayer.contains(range.commonAncestorContainer)) return { text: '', runs: [] };
    const doc = textLayer.ownerDocument;
    // Walking text nodes also handles PDF.js marked-content wrappers. Slice the
    // actual Range endpoints rather than guessing them from repeated substrings.
    const walker = doc.createTreeWalker(textLayer, 4); // SHOW_TEXT
    let node;
    const rawRuns = [];
    let text = '';
    const append = (piece, bold = false, italic = false) => {
      if (!piece) return;
      const last = rawRuns.at(-1);
      if (last && last.bold === bold && last.italic === italic) last.text += piece;
      else rawRuns.push({ text: piece, bold, italic });
      text += piece;
    };
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
      if (previous && /\S/.test(piece) && !/\s$/.test(text) && !/^\s/.test(piece)) {
        const gap = rect.x - (previous.x + previous.w);
        if (!sameLine && (
          /^[»›•▪◦]/u.test(piece)
          || rect.y - line.bottom > Math.max(line.bottom - line.top, rect.h) * 0.85
        )) {
          append('\n\n');
        } else if (!sameLine && /\p{L}-$/u.test(text) && /^\p{Ll}/u.test(piece)) {
          const last = rawRuns.at(-1);
          last.text = last.text.slice(0, -1);
          if (!last.text) rawRuns.pop();
          text = text.slice(0, -1);
        } else if (!sameLine || gap > Math.min(previous.h, rect.h) * 0.1) {
          const joinedText = joinPdfTextParts(text, piece);
          if (joinedText !== text + piece) append(' ');
        }
      }
      let element = node.parentNode;
      let bold = false;
      let italic = false;
      while (element && element !== textLayer) {
        bold ||= element.dataset?.incBold === '1';
        italic ||= element.dataset?.incItalic === '1';
        element = element.parentNode;
      }
      append(piece, bold, italic);
      if (/\S/.test(piece) && rect.w > 0 && rect.h > 0) {
        previous = rect;
        line = sameLine ? {
          reference: rect.h > line.reference.h ? rect : line.reference,
          top: Math.min(line.top, rect.y), bottom: Math.max(line.bottom, rect.y + rect.h),
        } : { reference: rect, top: rect.y, bottom: rect.y + rect.h };
      }
    }
    const runs = normalizedRuns(rawRuns);
    return { text: runs.map(run => run.text).join(''), runs };
  } catch {
    const text = (selection.toString() || '').trim();
    return { text, runs: text ? [{ text, bold: false, italic: false }] : [] };
  }
}

/** Copy exactly the selected characters, using rendered geometry for missing spaces. */
export function selectionCleaned(selection, textLayer) {
  return selectionFormatted(selection, textLayer).text;
}
