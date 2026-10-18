import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

import { pdfAnchorScrollRatio } from '../src/pdfAnchorLocation.mjs';


function contextAnchor(pageLabels, page = 7) {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
  const start = source.indexOf('    window.incrementoPdfAnchorAtPoint =');
  const end = source.indexOf('    return () => {', start);
  const scope = {
    window: {},
    document: { elementFromPoint: () => ({}) },
    containerRef: { current: { contains: () => true, getBoundingClientRect: () => ({ top: 0 }) } },
    cardIdRef: { current: 55 }, pageRef: { current: page }, pageLabels,
    getPdfViewportMetrics: () => ({ pageHeight: 2000, visibleHeight: 800 }),
    pdfAnchorScrollRatio,
  };
  vm.runInNewContext(source.slice(start, end), scope);
  return JSON.parse(JSON.stringify(scope.window.incrementoPdfAnchorAtPoint(100, 500)));
}


test('Copy Link to This Place carries printed v separately from physical PDF page 7', () => {
  assert.deepEqual(contextAnchor(['', '', 'i', 'ii', 'iii', 'iv', 'v']), {
    cardId: 55, page: 7, pageLabel: 'v', scrollRatio: 0.25,
  });
});


test('right-click citations use the clicked page label and clear unavailable labels', () => {
  assert.equal(contextAnchor(['i', 'A-12'], 2).pageLabel, 'A-12');
  assert.equal(contextAnchor(null).pageLabel, '');
  assert.equal(contextAnchor([''], 1).pageLabel, '');
});


test('PDF right-click anchor restores the clicked row near the upper reading area', () => {
  assert.equal(pdfAnchorScrollRatio({
    clientY: 500,
    wrapperTop: -300,
    pageHeight: 2000,
    visibleHeight: 800,
  }), 0.5);
});


test('PDF right-click anchor clamps page boundaries and rejects invalid geometry', () => {
  assert.equal(pdfAnchorScrollRatio({
    clientY: -100,
    wrapperTop: 0,
    pageHeight: 2000,
    visibleHeight: 800,
  }), 0);
  assert.equal(pdfAnchorScrollRatio({
    clientY: 5000,
    wrapperTop: -300,
    pageHeight: 2000,
    visibleHeight: 800,
  }), 1);
  assert.equal(pdfAnchorScrollRatio({
    clientY: 10,
    wrapperTop: 0,
    pageHeight: 0,
    visibleHeight: 800,
  }), null);
});
