import {joinPdfTextParts} from './pdfCjkText.mjs';

const normalize = text => String(text || '').normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim();

// Preserve character offsets so a reveal never paints unrelated surrounding text.
export function matchExcerpt(parts, quote, occurrence = 0) {
  const anchor = typeof quote === 'object' && quote ? quote : {quote};
  const target = normalize(anchor.quote);
  if (!target || target.length > 2000) return null;
  let text = '';
  const points = [];
  for (let part = 0; part < parts.length; part += 1) {
    const value = String(parts[part]);
    if (text.length + value.length > 1_000_000) return null;
    const last = text.slice(-2), first = value.slice(0, 2);
    if (text && joinPdfTextParts(last, first).length > last.length + first.length) {
      if (!text.endsWith(' ')) { text += ' '; points.push(null); }
    }
    for (let offset = 0; offset < value.length;) {
      const char = String.fromCodePoint(value.codePointAt(offset));
      const folded = char.normalize('NFKC').toLowerCase().replace(/\s/g, ' ');
      for (const letter of folded) {
        if (letter === ' ' && (!text || text.endsWith(' '))) continue;
        text += letter;
        for (let unit = 0; unit < letter.length; unit += 1) points.push({part, offset, end: offset + char.length});
      }
      offset += char.length;
    }
  }
  let index = text.indexOf(target);
  const prefix = normalize(anchor.prefix), suffix = normalize(anchor.suffix);
  while (index >= 0) {
    const matches = (!prefix || text.slice(0, index).trimEnd().endsWith(prefix))
      && (!suffix || text.slice(index + target.length).trimStart().startsWith(suffix));
    if (matches && occurrence-- <= 0) break;
    index = text.indexOf(target, index + 1);
  }
  if (index < 0) return null;
  const start = points[index], end = points[index + target.length - 1];
  return start && end ? {start: {part: start.part, offset: start.offset}, end: {part: end.part, offset: end.end}} : null;
}

/** Save the selected range without creating a persistent PDF annotation. */
export function capturePdfPassage(page, textLayer, selection = window.getSelection()) {
  if (!page || !textLayer || !selection?.rangeCount || selection.isCollapsed) return {};
  const range = selection.getRangeAt(0);
  if (!textLayer.contains(range.commonAncestorContainer)) return {};
  const joined = (source, tail = false) => {
    const fragment = source.cloneContents(), walker = document.createTreeWalker(fragment, 4);
    let result = '';
    while (walker.nextNode()) {
      result = joinPdfTextParts(result, walker.currentNode.textContent);
      if (tail) result = result.slice(-160);
      else if (result.length >= 2000) break;
    }
    return result;
  };
  const quote = joined(range).slice(0, 2000);
  if (!quote.trim()) return {};
  const before = document.createRange(), after = document.createRange();
  before.selectNodeContents(textLayer); before.setEnd(range.startContainer, range.startOffset);
  after.selectNodeContents(textLayer); after.setStart(range.endContainer, range.endOffset);
  const bounds = page.getBoundingClientRect();
  const rects = bounds.width > 0 && bounds.height > 0 ? Array.from(range.getClientRects())
    .filter(rect => rect.width > 0 && rect.height > 0).slice(0, 64).map(rect => {
      const x = Math.max(0, Math.min(1, (rect.left - bounds.left) / bounds.width));
      const y = Math.max(0, Math.min(1, (rect.top - bounds.top) / bounds.height));
      return [x, y, Math.min(1 - x, rect.width / bounds.width), Math.min(1 - y, rect.height / bounds.height)];
    }).filter(rect => rect[2] > 0 && rect[3] > 0) : [];
  return {quote, prefix: joined(before, true), suffix: joined(after).slice(0, 160), rects};
}

export function pdfExcerptRange(textLayer, quote) {
  if (!textLayer) return null;
  const nodes = [];
  const walker = document.createTreeWalker(textLayer, 4 /* SHOW_TEXT */);
  while (walker.nextNode()) nodes.push(walker.currentNode);
  const parts = nodes.map(node => node.textContent);
  const page = textLayer.parentElement?.getBoundingClientRect();
  const expected = typeof quote === 'object' ? quote?.rects?.[0]?.[1] : null;
  let nearest = null, distance = Infinity;
  for (let occurrence = 0; occurrence < 64; occurrence += 1) {
    const match = matchExcerpt(parts, quote, occurrence);
    if (!match) break;
    const range = document.createRange();
    range.setStart(nodes[match.start.part], match.start.offset);
    range.setEnd(nodes[match.end.part], match.end.offset);
    if (!Number.isFinite(expected) || !page?.height) return range;
    const rect = range.getBoundingClientRect();
    const delta = Math.abs((rect.top - page.top) / page.height - expected);
    if (delta < distance) {nearest = range; distance = delta;}
  }
  return nearest;
}

export function revealPdfExcerpt(textLayer, wrapper, quote, options) {
  const range = pdfExcerptRange(textLayer, quote);
  const bounds = wrapper.getBoundingClientRect();
  const fallback = !quote?.quote && Array.isArray(quote?.rects) ? quote.rects.map(([x,y,w,h]) =>
    ({left: bounds.left + x * bounds.width, top: bounds.top + y * bounds.height,
      width: w * bounds.width, height: h * bounds.height})) : [];
  const overlays = Array.from(range?.getClientRects() || fallback).filter(rect => rect.width && rect.height).map(rect => {
    const overlay = document.createElement('div');
    overlay.dataset.incExcerptReveal = '1';
    Object.assign(overlay.style, {position: 'absolute', pointerEvents: 'none', zIndex: 9,
      left: `${rect.left - bounds.left}px`, top: `${rect.top - bounds.top}px`,
      width: `${rect.width}px`, height: `${rect.height}px`, borderRadius: '2px',
      background: 'rgba(59,130,246,.28)', outline: '1px solid rgba(59,130,246,.8)'});
    wrapper.append(overlay);
    return overlay;
  });
  if (!overlays.length) return null;
  overlays[0].scrollIntoView({block: 'center', inline: 'nearest', behavior: 'smooth'});
  return dismissibleReveal(() => overlays.forEach(overlay => overlay.remove()), options);
}

function dismissibleReveal(remove, {duration = 4000, onDismiss = () => {}} = {}) {
  let timer;
  const clear = (notify = true) => {
    clearTimeout(timer);
    remove();
    document.removeEventListener('pointerdown', onPointer, true);
    document.removeEventListener('keydown', onKey, true);
    if (notify === true) onDismiss();
  };
  const onPointer = () => clear();
  const onKey = event => { if (event.key === 'Escape') clear(); };
  document.addEventListener('pointerdown', onPointer, true);
  document.addEventListener('keydown', onKey, true);
  timer = setTimeout(clear, duration);
  return clear;
}
