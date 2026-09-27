import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { transformWithEsbuild } from 'vite';
import {
  installPrecisePdfSelectionDrag,
  movePdfSelectionEndpoint,
  observePdfTextSelection,
} from '../src/pdfSelection.mjs';

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

test('dragging a live selection handle moves only that endpoint and cannot cross the other', () => {
  const textNode = {};
  const foreignNode = {};
  let caretNode = textNode;
  const selected = [];
  const createRange = () => {
    let startOffset = 0;
    let endOffset = 0;
    return {
      startContainer: textNode,
      endContainer: textNode,
      commonAncestorContainer: textNode,
      get startOffset() { return startOffset; },
      get endOffset() { return endOffset; },
      get collapsed() { return startOffset === endOffset; },
      setStart(_node, value) {
        startOffset = value;
        if (startOffset > endOffset) endOffset = startOffset;
      },
      setEnd(_node, value) {
        endOffset = value;
        if (endOffset < startOffset) startOffset = endOffset;
      },
    };
  };
  const document = {
    caretRangeFromPoint: (x) => ({ startContainer: caretNode, startOffset: x }),
    createRange,
  };
  const window = { getSelection: () => ({
    removeAllRanges: () => selected.splice(0),
    addRange: range => selected.push(range),
  }) };
  const textLayer = { contains: node => node === textNode };
  const current = { startContainer: textNode, startOffset: 2, endContainer: textNode, endOffset: 6 };

  const extended = movePdfSelectionEndpoint(textLayer, current, 'end', 9, 10, { document, window });
  assert.equal(extended.startOffset, 2);
  assert.equal(extended.endOffset, 9);
  assert.equal(selected[0], extended);

  const crossed = movePdfSelectionEndpoint(textLayer, extended, 'start', 10, 10, { document, window });
  assert.equal(crossed, null);
  assert.equal(selected[0], extended, 'a crossed endpoint must leave the prior selection unchanged');

  caretNode = foreignNode;
  assert.equal(movePdfSelectionEndpoint(textLayer, extended, 'end', 11, 10, { document, window }), null);
  assert.equal(selected[0], extended, 'dragging outside the PDF text layer must fail closed');
});

test('initial trackpad drag follows the nearest character instead of accepting native row jumps', () => {
  const textNode = { nodeType: 3, nodeValue: '0123456789' };
  const foreignNode = {};
  const layerListeners = new Map();
  const documentListeners = new Map();
  const selected = [];
  let caretNode = textNode;
  const visualTop = offset => ({ 1: 10, 2: 20, 3: 20, 4: 40, 5: 60, 9: 260 }[offset] ?? 20);
  const makeRange = (start = 0, end = start) => ({
    startContainer: textNode,
    endContainer: textNode,
    startOffset: start,
    endOffset: end,
    commonAncestorContainer: textNode,
    get collapsed() { return this.startOffset === this.endOffset; },
    setStart(node, offset) { this.startContainer = node; this.startOffset = offset; },
    setEnd(node, offset) { this.endContainer = node; this.endOffset = offset; },
    collapse() { this.endContainer = this.startContainer; this.endOffset = this.startOffset; },
    cloneRange() { return makeRange(this.startOffset, this.endOffset); },
    compareBoundaryPoints(_how, source) { return this.startOffset - source.startOffset; },
    selectNodeContents(node) { this.selectedNode = node; },
    getClientRects() {
      if (!this.selectedNode) return [];
      return [20, 40, 60].map(top => ({ left: 0, right: 10, top, bottom: top + 18, width: 10, height: 18 }));
    },
    getBoundingClientRect() {
      return { left: this.startOffset, top: visualTop(this.startOffset), width: 0, height: 18 };
    },
  });
  const document = {
    caretRangeFromPoint: (x, y) => {
      const offset = x === 9 && y === 57 ? 4 : x;
      const range = makeRange(offset, offset);
      range.startContainer = caretNode;
      range.endContainer = caretNode;
      range.commonAncestorContainer = caretNode;
      return range;
    },
    createRange: () => makeRange(),
    createTreeWalker: () => {
      let visited = false;
      return {
        currentNode: null,
        nextNode() {
          if (visited) return false;
          visited = true;
          this.currentNode = textNode;
          return true;
        },
      };
    },
    addEventListener: (name, callback) => documentListeners.set(name, callback),
    removeEventListener: (name, callback) => {
      assert.equal(documentListeners.get(name), callback);
      documentListeners.delete(name);
    },
  };
  const window = {
    PointerEvent: function PointerEvent() {},
    getSelection: () => ({
      removeAllRanges: () => selected.splice(0),
      addRange: range => selected.push(range),
    }),
  };
  let capturedPointer = null;
  const textLayer = {
    contains: node => node === textNode,
    setPointerCapture: pointerId => { capturedPointer = pointerId; },
    releasePointerCapture: pointerId => {
      assert.equal(pointerId, capturedPointer);
      capturedPointer = null;
    },
    addEventListener: (name, callback) => layerListeners.set(name, callback),
    removeEventListener: (name, callback) => {
      assert.equal(layerListeners.get(name), callback);
      layerListeners.delete(name);
    },
  };
  const event = (x, overrides = {}) => ({
    button: 0,
    buttons: 1,
    isPrimary: true,
    pointerId: 12,
    clientX: x,
    clientY: 20,
    target: {},
    preventDefault() { this.defaultPrevented = true; },
    ...overrides,
  });

  const stop = installPrecisePdfSelectionDrag(textLayer, { document, window });
  const down = event(2);
  layerListeners.get('pointerdown')(down);
  assert.equal(down.defaultPrevented, true);
  assert.equal(capturedPointer, 12);
  assert.equal(selected[0].collapsed, true);
  assert.equal(selected[0].startOffset, 2);

  const nativeSelection = event(2);
  documentListeners.get('selectstart')(nativeSelection);
  assert.equal(nativeSelection.defaultPrevented, true, 'native selection must not overwrite the precise range');

  const oneCharacter = event(3);
  documentListeners.get('pointermove')(oneCharacter);
  assert.equal(oneCharacter.defaultPrevented, true);
  assert.deepEqual([selected[0].startOffset, selected[0].endOffset], [2, 3]);

  documentListeners.get('pointermove')(event(5, { clientY: 60 }));
  assert.deepEqual([selected[0].startOffset, selected[0].endOffset], [2, 5]);

  documentListeners.get('pointermove')(event(9, { clientY: 59 }));
  assert.deepEqual(
    [selected[0].startOffset, selected[0].endOffset],
    [2, 4],
    'an interline pointer must snap to the nearest rendered row',
  );

  documentListeners.get('pointermove')(event(9, { clientY: 55 }));
  assert.deepEqual(
    [selected[0].startOffset, selected[0].endOffset],
    [2, 4],
    'reversing upward must reject a caret that spuriously jumps many rows downward',
  );

  documentListeners.get('pointermove')(event(1, { clientY: 10 }));
  assert.deepEqual([selected[0].startOffset, selected[0].endOffset], [1, 2]);

  caretNode = foreignNode;
  documentListeners.get('pointermove')(event(9));
  assert.deepEqual([selected[0].startOffset, selected[0].endOffset], [1, 2]);

  documentListeners.get('pointerup')(event(1, { buttons: 0 }));
  assert.equal(capturedPointer, null);
  const selectionAfterRelease = event(1);
  documentListeners.get('selectstart')(selectionAfterRelease);
  assert.equal(selectionAfterRelease.defaultPrevented, undefined);
  stop();
  assert.equal(layerListeners.size, 0);
  assert.equal(documentListeners.size, 0);
});

const sourceUrl = new URL('../src/PdfSelectionLayer.jsx', import.meta.url);
const { code } = await transformWithEsbuild(readFileSync(sourceUrl, 'utf8'), sourceUrl.pathname, {
  loader: 'jsx', jsx: 'automatic',
});
let previewRects = [];
const hooks = 'data:text/javascript,' + encodeURIComponent(
  'export const useState = () => [globalThis.__pdfSelectionTestRects, () => {}]; export const useEffect = () => {}; export const useRef = value => ({ current: value });',
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
    assert.equal(overlay.props['aria-hidden'], false);
    assert.equal(overlay.props.style.pointerEvents, 'none');
    assert.equal(overlay.props.style.left, 30);
    const painted = elements(overlay.props.children).filter(node => node.type === 'div');
    assert.equal(painted.length, 1);
    assert.deepEqual(painted[0].props.style, {
      position: 'absolute', left: 20, top: 40, width: 286, height: 38,
      background: 'rgba(0,100,255,0.3)', mixBlendMode: 'multiply',
    });
    const handles = nodes.filter(node => node.props?.className === 'incremento-pdf-selection-resize-handle');
    assert.equal(handles.length, 2);
    assert.deepEqual(handles.map(node => node.props['data-endpoint']), ['start', 'end']);
    assert.deepEqual(handles.map(node => [node.props.style.left, node.props.style.top]), [[8, 12], [294, 78]]);
    assert.ok(handles.every(node => node.props.style.pointerEvents === 'auto'));
    assert.ok(handles.every(node => node.props.style.touchAction === 'none'));
    assert.match(nodes.find(node => node.type === 'style').props.children,
      /#pdf-text-layer ::selection\s*\{\s*background:\s*transparent/);
    globalThis.__pdfSelectionTestRects = [];
    assert.equal(PdfSelectionLayer({ textLayerRef: { current: {} }, renderInfo: { tlLeft: 30 } }), null);
  } finally {
    delete globalThis.__pdfSelectionTestRects;
  }
});
