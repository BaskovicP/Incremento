import assert from 'node:assert/strict';
import test from 'node:test';
import { selectionCleaned } from '../src/pdfTextSelection.mjs';

function selection(words, { start = 0, end = words.at(-1)[0].length, nested = false } = {}) {
  const elements = words.map(([text, x, y, w, h = 10]) => ({
    nodeType: 1, nodeName: 'SPAN', tagName: 'SPAN', innerText: text, textContent: text,
    offsetLeft: x, offsetTop: y,
    style: { fontSize: 'calc(var(--scale-factor)*5px)', fontFamily: 'Droid', transform: 'scaleX(2)' },
    getBoundingClientRect: () => ({ x, y, left: x, top: y, right: x + w, bottom: y + h, width: w, height: h }),
  }));
  const nodes = elements.map(element => ({ nodeType: 3, nodeName: '#text', textContent: element.textContent, parentNode: element }));
  elements.forEach((element, index) => { element.firstChild = nodes[index]; });
  const doc = {
    createTreeWalker: () => { let index = 0; return { nextNode: () => nodes[index++] || null }; },
    createRange: () => ({
      setStart(node, offset) { this.node = node; this.start = offset; },
      setEnd(_node, offset) { this.end = offset; },
      getBoundingClientRect() {
        const rect = this.node.parentNode.getBoundingClientRect();
        const charWidth = rect.width / this.node.textContent.length;
        const left = rect.left + charWidth * this.start;
        const width = charWidth * (this.end - this.start);
        return { ...rect, x: left, left, width, right: left + width };
      },
    }),
  };
  const layer = { ownerDocument: doc, children: nested ? [{ nodeName: 'SPAN', children: elements }] : elements,
    contains: node => node === layer || nodes.includes(node) || elements.includes(node) };
  const range = { startContainer: nodes[0], endContainer: nodes.at(-1), startOffset: start, endOffset: end,
    commonAncestorContainer: layer, intersectsNode: node => nodes.includes(node) };
  const original = words.map(([text], index) => text.slice(index === 0 ? start : 0, index === words.length - 1 ? end : undefined)).join('');
  return [{ rangeCount: 1, getRangeAt: () => range, toString: () => original }, layer];
}

test('copying scaled OCR words keeps word spaces without canvas font estimates', () => {
  assert.equal(selectionCleaned(...selection([['Read', 0, 0, 24], ['this', 28, 1, 20], ['text.', 52, 0, 25]])), 'Read this text.');
});

test('partial selection clips exact endpoints even in nested PDF marked content', () => {
  assert.equal(selectionCleaned(...selection([['before', 0, 0, 30], ['after', 34, 0, 25]], { start: 2, end: 3, nested: true })), 'fore aft');
});

test('small OCR baseline variations do not split a sentence into paragraphs', () => {
  assert.equal(selectionCleaned(...selection([['A', 0, 0, 5, 12], ['word', 8, 6, 24, 6], ['continues', 0, 17, 40, 10]])), 'A word continues');
});

test('wrapped OCR lines use the whole line height instead of a short last word', () => {
  assert.equal(selectionCleaned(...selection([
    ['Read', 0, 0, 24, 11], ['more', 28, 0, 24, 8], ['words.', 0, 16, 32, 8],
  ])), 'Read more words.');
});

test('explicit whitespace, touching Latin fragments, and CJK characters retain their boundaries', () => {
  for (const [words, expected] of [
    [[['one ', 0, 0, 20], [' two', 22, 0, 20]], 'one two'],
    [[['frag', 0, 0, 20], ['ment', 20, 0, 20]], 'fragment'],
    [[['中文', 0, 0, 20], ['内容', 23, 0, 20]], '中文内容'],
  ]) assert.equal(selectionCleaned(...selection(words)), expected);
});

test('an empty or foreign selection cannot copy text from the PDF', () => {
  const [sel, layer] = selection([['private', 0, 0, 35]]);
  assert.equal(selectionCleaned(null, layer), '');
  assert.equal(selectionCleaned({ rangeCount: 0 }, layer), '');
  assert.equal(selectionCleaned(sel, { ...layer, contains: () => false }), '');
});

test('a selection inside a single repeated word uses exact character offsets', () => {
  assert.equal(selectionCleaned(...selection([['banana', 0, 0, 30]], { start: 1, end: 4 })), 'ana');
});

test('copying joins hyphenated line wraps and preserves a visible paragraph gap', () => {
  assert.equal(selectionCleaned(...selection([
    ['inter-', 0, 0, 30], ['esting.', 0, 16, 35], ['Next', 0, 45, 25],
  ])), 'interesting.\n\nNext');
});
