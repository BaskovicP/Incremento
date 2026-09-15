import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { transformWithEsbuild } from 'vite';
import { observePdfTextSelection } from '../src/pdfSelection.mjs';

function selectionHarness() {
  const listeners = new Map();
  const frames = new Map();
  const changes = [];
  const node = {};
  let selection = null;
  let nextFrame = 1;
  let mutationCallback;
  let disconnected = false;
  const textLayer = {
    contains: candidate => candidate === node,
    getBoundingClientRect: () => ({ left: 100, top: 40 }),
  };
  const window = {
    getSelection: () => selection,
    requestAnimationFrame: callback => { const id = nextFrame++; frames.set(id, callback); return id; },
    cancelAnimationFrame: id => frames.delete(id),
    MutationObserver: class {
      constructor(callback) { mutationCallback = callback; }
      observe() {}
      disconnect() { disconnected = true; }
    },
  };
  const document = {
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: (name, callback) => {
      assert.equal(listeners.get(name), callback);
      listeners.delete(name);
    },
  };
  const stop = observePdfTextSelection(textLayer, rects => changes.push(rects), { document, window });
  return {
    textLayer, changes, frames, listeners, stop,
    get disconnected() { return disconnected; },
    select(rects, ancestor = node) {
      selection = {
        isCollapsed: false, rangeCount: 1,
        getRangeAt: () => ({ commonAncestorContainer: ancestor, getClientRects: () => rects }),
      };
      listeners.get('selectionchange')?.();
    },
    clear() { selection = null; listeners.get('selectionchange')?.(); },
    collapse() { selection = { isCollapsed: true, rangeCount: 1 }; listeners.get('selectionchange')?.(); },
    mutate() { selection = null; mutationCallback(); },
    flush() {
      const callbacks = [...frames.values()];
      frames.clear();
      callbacks.forEach(callback => callback());
    },
  };
}

test('dragging over fragmented PDF words paints a continuous selection per row with exact endpoints', () => {
  const harness = selectionHarness();
  harness.select([
    { left: 120, top: 80, width: 80, height: 38 },
    { left: 212, top: 80, width: 32, height: 38 },
    { left: 256, top: 80, width: 150, height: 38 },
    { left: 110, top: 120, width: 220, height: 38 },
    { left: 343, top: 122, width: 60, height: 34 },
    { left: 417, top: 120, width: 72, height: 38 },
  ]);
  harness.flush();

  assert.deepEqual(harness.changes.at(-1), [
    { x: 20, y: 40, w: 286, h: 38 },
    { x: 10, y: 80, w: 379, h: 38 },
  ]);
  harness.stop();
});

test('a live PDF selection keeps column gutters clear', () => {
  const harness = selectionHarness();
  harness.select([
    { left: 110, top: 80, width: 80, height: 20 },
    { left: 280, top: 80, width: 80, height: 20 },
  ]);
  harness.flush();
  assert.deepEqual(harness.changes.at(-1), [
    { x: 10, y: 40, w: 80, h: 20 },
    { x: 180, y: 40, w: 80, h: 20 },
  ]);
  harness.stop();
});

test('a live selection joins justified spaces wider than half the text height', () => {
  const harness = selectionHarness();
  harness.select([
    { left: 120, top: 80, width: 80, height: 37 },
    { left: 223, top: 80, width: 32, height: 37 },
    { left: 276, top: 80, width: 150, height: 37 },
    { left: 110, top: 120, width: 220, height: 37 },
    { left: 352, top: 120, width: 60, height: 37 },
  ]);
  harness.flush();
  assert.deepEqual(harness.changes.at(-1), [
    { x: 20, y: 40, w: 306, h: 37 },
    { x: 10, y: 80, w: 302, h: 37 },
  ]);
  harness.stop();
});

for (const action of ['clear', 'collapse', 'mutate']) {
  test(`${action} removes the previous PDF selection preview`, () => {
    const harness = selectionHarness();
    harness.select([{ left: 110, top: 80, width: 80, height: 20 }]);
    harness.flush();
    assert.equal(harness.changes.at(-1).length, 1);
    harness[action]();
    harness.flush();
    assert.deepEqual(harness.changes.at(-1), []);
    harness.stop();
  });
}

test('selection outside the PDF text layer does not create a PDF preview', () => {
  const harness = selectionHarness();
  harness.select([{ left: 110, top: 80, width: 80, height: 20 }], {});
  harness.flush();
  assert.deepEqual(harness.changes.at(-1), []);
  harness.stop();
});

test('rapid drag updates share one animation frame and closing cancels pending work', () => {
  const harness = selectionHarness();
  harness.select([{ left: 110, top: 80, width: 80, height: 20 }]);
  harness.select([{ left: 110, top: 80, width: 120, height: 20 }]);
  assert.equal(harness.frames.size, 1);
  harness.flush();
  assert.deepEqual(harness.changes.at(-1), [{ x: 10, y: 40, w: 120, h: 20 }]);
  harness.select([{ left: 110, top: 80, width: 160, height: 20 }]);
  const changeCount = harness.changes.length;
  harness.stop();
  harness.flush();
  assert.equal(harness.changes.length, changeCount);
  assert.equal(harness.listeners.size, 0);
  assert.equal(harness.frames.size, 0);
  assert.equal(harness.disconnected, true);
});

const sourceUrl = new URL('../src/PdfSelectionLayer.jsx', import.meta.url);
const { code } = await transformWithEsbuild(readFileSync(sourceUrl, 'utf8'), sourceUrl.pathname, {
  loader: 'jsx', jsx: 'automatic',
});
let previewRects = [];
const hooks = 'data:text/javascript,' + encodeURIComponent(
  'export const useState = () => [globalThis.__pdfSelectionTestRects, () => {}]; export const useEffect = () => {};',
);
const resolvedCode = code.replace(/from (["'])([^"']+)\1/g, (_match, _quote, specifier) => (
  `from ${JSON.stringify(specifier === 'react' ? hooks : specifier.startsWith('.')
    ? new URL(specifier, sourceUrl).href : import.meta.resolve(specifier))}`
));
const { default: PdfSelectionLayer } = await import(`data:text/javascript;base64,${Buffer.from(resolvedCode).toString('base64')}`);

function elements(node) {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!node || typeof node !== 'object') return [];
  return [node, ...elements(node.props?.children)];
}

test('the joined live preview replaces native fragmented paint without blocking text selection', () => {
  previewRects = [{ x: 20, y: 40, w: 286, h: 38 }];
  globalThis.__pdfSelectionTestRects = previewRects;
  try {
    const nodes = elements(PdfSelectionLayer({ textLayerRef: { current: {} }, renderInfo: { tlLeft: 30 } }));
    const overlay = nodes.find(node => node.props?.id === 'pdf-selection-layer');
    assert.ok(overlay);
    assert.equal(overlay.props['aria-hidden'], true);
    assert.equal(overlay.props.style.pointerEvents, 'none');
    assert.equal(overlay.props.style.left, 30);
    const painted = elements(overlay.props.children).filter(node => node.type === 'div');
    assert.equal(painted.length, 1);
    assert.deepEqual(painted[0].props.style, {
      position: 'absolute', left: 20, top: 40, width: 286, height: 38,
      background: 'rgba(0,100,255,0.3)', mixBlendMode: 'multiply',
    });
    assert.match(nodes.find(node => node.type === 'style').props.children,
      /#pdf-text-layer ::selection\s*\{\s*background:\s*transparent/);
    globalThis.__pdfSelectionTestRects = [];
    assert.equal(PdfSelectionLayer({ textLayerRef: { current: {} }, renderInfo: { tlLeft: 30 } }), null);
  } finally {
    delete globalThis.__pdfSelectionTestRects;
  }
});
