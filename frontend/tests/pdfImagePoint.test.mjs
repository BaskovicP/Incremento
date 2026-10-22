import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { pdfImagePoint } from '../src/pdfImagePoint.mjs';

test('image hit coordinates use the displayed canvas at any zoom and scroll', () => {
  assert.deepEqual(pdfImagePoint(150, 20, { left: 50, top: -80, width: 400, height: 200 }),
    { x: .25, y: .5 });
});

test('points outside the page and malformed canvas geometry cannot select an image', () => {
  const rect = { left: 50, top: -80, width: 400, height: 200 };
  for (const [x, y, box] of [[49, 20, rect], [150, 121, rect], [NaN, 20, rect],
    [150, 20, { ...rect, width: 0 }], [150, 20, null]]) {
    assert.equal(pdfImagePoint(x, y, box), null);
  }
});

test('the reader selects only the active, fully rendered canvas for the current card and page', () => {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
  const start = source.indexOf('    window.incrementoPdfImagePointAtPoint =');
  const end = source.indexOf('    return () =>', start);
  const canvas = {
    dataset: { pdfCard: '55', pdfPage: '7' },
    getBoundingClientRect: () => ({ left: 50, top: -80, width: 400, height: 200 }),
  };
  const scope = {
    window: {}, pdfDocRef: { current: {} }, busyRef: { current: false },
    activeCvsRef: { current: 'b' }, canvasARef: { current: null }, canvasBRef: { current: canvas },
    cardIdRef: { current: 55 }, pageRef: { current: 7 }, pdfImagePoint,
  };
  vm.runInNewContext(source.slice(start, end), scope);
  assert.deepEqual(scope.window.incrementoPdfImagePointAtPoint(150, 20), { x: .25, y: .5 });
  scope.busyRef.current = true;
  assert.equal(scope.window.incrementoPdfImagePointAtPoint(150, 20), null);
  scope.busyRef.current = false;
  scope.pageRef.current = 8;
  assert.equal(scope.window.incrementoPdfImagePointAtPoint(150, 20), null);
  scope.pageRef.current = 7;
  scope.cardIdRef.current = 56;
  assert.equal(scope.window.incrementoPdfImagePointAtPoint(150, 20), null);
  scope.cardIdRef.current = 55;
  scope.pdfDocRef.current = null;
  assert.equal(scope.window.incrementoPdfImagePointAtPoint(150, 20), null);
});
