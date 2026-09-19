import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { normalizeHighlightColor } from '../src/highlightColors.mjs';
import vm from 'node:vm';
import { transformWithEsbuild } from 'vite';
import { normalizePdfHighlightRects } from '../src/pdfHighlightRects.mjs';
import { selectionCleaned } from '../src/pdfTextSelection.mjs';

// Render the actual JSX component without PDF.js or a browser. The resulting
// React elements retain both the painted geometry and the hover handlers.
const sourceUrl = new URL('../src/HighlightLayer.jsx', import.meta.url);
const { code } = await transformWithEsbuild(readFileSync(sourceUrl, 'utf8'), sourceUrl.pathname, {
  loader: 'jsx', jsx: 'automatic',
});
const resolvedCode = code.replace(/from (["'])([^"']+)\1/g, (_match, _quote, specifier) => (
  `from ${JSON.stringify(specifier.startsWith('.')
    ? new URL(specifier, sourceUrl).href
    : import.meta.resolve(specifier))}`
));
const { default: HighlightLayer } = await import(`data:text/javascript;base64,${Buffer.from(resolvedCode).toString('base64')}`);

function elements(node) {
  if (Array.isArray(node)) return node.flatMap(elements);
  if (!node || typeof node !== 'object') return [];
  return [node, ...elements(node.props?.children)];
}

function render(highlights, overrides = {}) {
  return elements(HighlightLayer({
    pageHighlights: highlights,
    renderInfo: { scale: 1, tlLeft: 0 },
    ...overrides,
  }));
}

function paintedRects(nodes) {
  return nodes.filter(node => node.props?.style?.zIndex === 1).map(({ props: { style } }) => ({
    x: style.left, y: style.top, w: style.width, h: style.height,
  }));
}

test('one multiline highlight paints each line once and joins the small gaps around italic text', () => {
  const rects = [
    { x: 50, y: 10, w: 400, h: 24 },
    ...[50, 90, 130, 170].flatMap(y => [
      { x: 10, y, w: 440, h: 24 },
      { x: 10, y: y + 2, w: 440, h: 20 },
    ]),
    { x: 10, y: 210, w: 300, h: 24 },
    { x: 314, y: 212, w: 20, h: 20 },
    { x: 338, y: 210, w: 90, h: 24 },
  ];
  const original = structuredClone(rects);

  const actual = paintedRects(render([{ id: 'single', color: 'yellow', rects }]));

  assert.deepEqual(actual, [
    { x: 50, y: 10, w: 400, h: 24 },
    ...[50, 90, 130, 170].map(y => ({ x: 10, y, w: 440, h: 24 })),
    { x: 10, y: 210, w: 418, h: 24 },
  ]);
  assert.deepEqual(rects, original, 'display normalization must not alter saved geometry');
});

test('highlight geometry preserves separate lines, column gaps, and different annotations', () => {
  const left = { x: 10, y: 10, w: 80, h: 20 };
  const right = { x: 180, y: 10, w: 80, h: 20 };
  const nextLine = { x: 10, y: 32, w: 80, h: 20 };
  const actual = paintedRects(render([
    { id: 'first', color: 'yellow', rects: [nextLine, right, left] },
    { id: 'second', color: 'green', rects: [left] },
  ]));

  const byPosition = (a, b) => a.y - b.y || a.x - b.x;
  assert.deepEqual(actual.sort(byPosition), [left, right, nextLine, left].sort(byPosition));
});

test('justified PDF words with wide spaces paint one uninterrupted line at every zoom', () => {
  // The reported line: "errors or omissions. No liability is assumed ...".
  // Its justified spaces are 19–23 px wide with 37 px selection boxes.
  const rects = [
    [55, 87], [165, 30], [216, 155], [392, 45], [458, 113],
    [592, 23], [637, 128], [787, 42], [850, 146], [1017, 30], [1069, 202],
  ].map(([x, w]) => ({ x, y: 125, w, h: 37 }));
  const original = structuredClone(rects);

  for (const scale of [0.5, 1, 2]) {
    const actual = paintedRects(render([{ id: 'justified', color: 'blue', rects }], {
      renderInfo: { scale, tlLeft: 0 },
    }));
    assert.deepEqual(actual, [{ x: 55 * scale, y: 125 * scale, w: 1216 * scale, h: 37 * scale }]);
  }
  assert.deepEqual(rects, original);
});

test('wide word-space merging stays bounded at a text height and leaves larger gutters clear', () => {
  assert.deepEqual(normalizePdfHighlightRects([
    { x: 10, y: 20, w: 50, h: 20 },
    { x: 80, y: 20, w: 40, h: 20 },
    { x: 141, y: 20, w: 60, h: 20 },
  ]), [
    { x: 10, y: 20, w: 110, h: 20 },
    { x: 141, y: 20, w: 60, h: 20 },
  ]);
});

test('snapshot highlights retain their exact selected region', () => {
  const rects = [{ x: 10, y: 10, w: 80, h: 20 }, { x: 95, y: 10, w: 40, h: 20 }];
  assert.deepEqual(paintedRects(render([{ id: 'snapshot', color: 'snapshot', rects }])), rects);
});

test('OCR baseline variation paints each line once without jagged overlapping fragments', () => {
  const rects = [
    { x: 10, y: 20, w: 30, h: 8 },
    { x: 44, y: 23.3, w: 20, h: 8 },
    { x: 68, y: 20.5, w: 30, h: 11 },
    { x: 102, y: 22, w: 15, h: 5 },
    { x: 10, y: 36, w: 107, h: 8 },
  ];
  for (const scale of [0.5, 1, 2]) {
    const actual = paintedRects(render([{ id: 'ocr', color: 'yellow', rects }], { renderInfo: { scale, tlLeft: 0 } }));
    assert.deepEqual(actual, [
      { x: 10 * scale, y: 20 * scale, w: 107 * scale, h: 11.5 * scale },
      { x: 10 * scale, y: 36 * scale, w: 107 * scale, h: 8 * scale },
    ]);
  }
});

test('merged text highlight geometry scales and offsets with the PDF text layer', () => {
  const nodes = render([{ id: 'scaled', color: 'blue', rects: [
    { x: 10, y: 20, w: 40, h: 20 },
    { x: 54, y: 22, w: 26, h: 16 },
  ] }], { renderInfo: { scale: 2, tlLeft: 30 } });

  assert.deepEqual(paintedRects(nodes), [{ x: 50, y: 40, w: 140, h: 40 }]);
});

test('hovering a saved note invokes the custom popup without a second native tooltip', () => {
  const highlight = { id: 'noted', color: 'yellow', note: 'Arabic العربية\n\nA saved note', rects: [
    { x: 10, y: 20, w: 100, h: 20 },
    { x: 10, y: 22, w: 100, h: 16 },
  ] };
  const calls = [];
  const nodes = render([highlight], {
    showHighlightNote: (value, event) => calls.push(['show', value.note, event.clientX]),
    moveHighlightNote: () => calls.push(['move']),
    hideHighlightNote: () => calls.push(['hide']),
  });
  const targets = nodes.filter(node => node.props?.onMouseEnter);

  assert.ok(targets.length > 0);
  for (const target of targets) {
    assert.equal(target.props.title, undefined, 'a title would trigger the duplicate native tooltip');
  }
  assert.equal(targets.length, 1);
  const target = targets[0];
  target.props.onMouseEnter({ clientX: 60 });
  target.props.onMouseMove({ clientX: 70 });
  target.props.onMouseLeave();
  assert.deepEqual(calls, [['show', highlight.note, 60], ['move'], ['hide']]);
});

test('blank highlight notes do not create hover targets', () => {
  const nodes = render([{ id: 'blank', note: ' \n ', rects: [{ x: 10, y: 20, w: 100, h: 20 }] }]);
  assert.equal(nodes.filter(node => node.props?.onMouseEnter).length, 0);
});

test('native underline and text comments keep their PDF appearance and offer editable notes', () => {
  for (const kind of ['Underline', 'Text', 'FreeText', 'Square']) {
    const edits = [];
    const nodes = render([{ id: kind, color: 'yellow', note: 'Imported note', pdf_annotation: { kind },
      rects: [{ x: 10, y: 20, w: 100, h: 20 }] }], { editHighlightNote: id => edits.push(id) });
    assert.equal(nodes.find(node => node.props?.style?.zIndex === 1).props.style.background, 'transparent');
    nodes.find(node => node.props?.className === 'incremento-pdf-note-action').props.onClick();
    assert.deepEqual(edits, [kind]);
  }
});

test('native highlight colors and opacity are preserved and painted only once', () => {
  const highlight = { id: 'native', color: 'yellow', pdf_annotation: { kind: 'Highlight', color: [0.2, 0.8, 0.4], opacity: 0.6 },
    rects: [{ x: 10, y: 20, w: 100, h: 20 }] };
  const paint = overrides => render([highlight], overrides).find(node => node.props?.style?.zIndex === 1).props.style.background;
  assert.equal(paint(), 'rgba(51,204,102,0.6)');
  assert.equal(paint({ nativeHighlightsVisible: true }), 'transparent');
});

test('custom hex highlights paint their own color before PDF sync', () => {
  for (const color of ['#123abc', '#123ABC']) {
    const nodes = render([{ id: 'custom', color, rects: [{ x: 10, y: 20, w: 100, h: 20 }] }]);
    assert.equal(nodes.find(node => node.props?.style?.zIndex === 1).props.style.background, 'rgba(18,58,188,0.42)');
  }
});

test('annotation note icons are transparent until hover or keyboard focus and still edit the chosen note', () => {
  for (const note of ['', 'Saved annotation note']) {
    const edits = [];
    const nodes = render([{ id: 'annotation', color: 'yellow', note, rects: [
      { x: 10, y: 20, w: 100, h: 20 },
    ] }], { editHighlightNote: id => edits.push(id) });
    const css = nodes.filter(node => node.type === 'style').map(node => node.props.children).join('\n');
    const action = nodes.find(node => node.type === 'button' && node.props.className === 'incremento-pdf-note-action');

    assert.ok(action, 'the note action must use the hover-only visibility rules');
    assert.match(css, /\.incremento-pdf-note-action\s*\{\s*opacity:\s*0\s*;/);
    assert.match(css, /\.incremento-pdf-highlight-actions:hover\s+\.incremento-pdf-note-action\s*,\s*\.incremento-pdf-note-action:focus-visible\s*\{\s*opacity:\s*1\s*;/);
    assert.ok(nodes.some(node => node.props?.className === 'incremento-pdf-highlight-actions'));
    assert.equal(action.props['aria-label'], note ? 'Edit highlight note' : 'Add highlight note');
    assert.notEqual(action.props.tabIndex, -1, 'keyboard users must still be able to reach the action');
    action.props.onClick();
    assert.deepEqual(edits, ['annotation']);
  }
});

test('highlight normalization is stable across selection order and repeated display', () => {
  const rects = [
    { x: 10, y: 20, w: 40, h: 20 },
    { x: 54, y: 22, w: 26, h: 16 },
    { x: 10, y: 44, w: 80, h: 20 },
  ];
  const normalized = normalizePdfHighlightRects(rects);

  assert.deepEqual(normalizePdfHighlightRects([...rects].reverse()), normalized);
  assert.deepEqual(normalizePdfHighlightRects(normalized), normalized);
});

test('empty or invalid selection rectangles do not produce painted geometry', () => {
  for (const rects of [null, [], [null, {},
    { x: 0, y: 0, w: 0, h: 10 },
    { x: 0, y: 0, w: 10, h: -1 },
    { x: Infinity, y: 0, w: 10, h: 10 },
    { x: 0, y: NaN, w: 10, h: 10 },
  ]]) {
    assert.deepEqual(paintedRects(render([{ id: 'invalid', color: 'yellow', rects }])), []);
  }
});

test('creating a text highlight saves merged PDF coordinates and preserves text, page, and color', () => {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
  const start = source.indexOf('  const makeHighlight = useCallback(');
  const finish = source.indexOf('  const pickHighlightColor', start);
  assert.ok(start > 0 && finish > start);
  const saved = [];
  let displayed = [];
  const scope = {
    useCallback: callback => callback,
    normalizePdfHighlightRects,
    selectionCleaned,
    textLayerRef: { current: {
      contains: () => true,
      getBoundingClientRect: () => ({ left: 100, top: 40 }),
    } },
    lastScaleRef: { current: 2 },
    pageRef: { current: 6 },
    cardIdRef: { current: 42 },
    hlColorRef: { current: 'purple' },
    setHighlights: update => { displayed = update(displayed); },
    window: { pycmd: command => saved.push(command) },
  };
  vm.runInNewContext(`${source.slice(start, finish)}\nglobalThis.createHighlight = makeHighlight;`, scope);
  const selection = {
    isCollapsed: false,
    rangeCount: 1,
    toString: () => 'A passage with italic text.',
    getRangeAt: () => ({
      commonAncestorContainer: {},
      getClientRects: () => [
        { left: 120, top: 80, width: 80, height: 40 },
        { left: 208, top: 84, width: 52, height: 32 },
      ],
    }),
  };

  assert.equal(scope.createHighlight(selection, 'green'), true);

  assert.equal(saved.length, 1);
  assert.ok(saved[0].startsWith('incremento_pdf_hl_add:'));
  const payload = JSON.parse(saved[0].slice('incremento_pdf_hl_add:'.length));
  assert.equal(payload.cardId, 42);
  assert.equal(payload.highlight.page, 6);
  assert.equal(payload.highlight.color, 'green');
  assert.equal(payload.highlight.text, selection.toString());
  assert.deepEqual(payload.highlight.rects, [{ x: 10, y: 20, w: 70, h: 20 }]);
  assert.deepEqual(JSON.parse(JSON.stringify(displayed)), [payload.highlight]);
});

for (const outcome of ['selected', 'cancelled', 'page-changed']) {
  test(`custom PDF picker ${outcome} preserves selection and applies only to its page`, () => {
    const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
    const start = source.indexOf('  const makeHighlight = useCallback(');
    const finish = source.indexOf('  const limitAwareNav', start);
    const saved = [];
    const node = {};
    const range = {
      collapsed: false, commonAncestorContainer: node,
      toString: () => 'Selected passage',
      getClientRects: () => [{ left: 10, top: 20, width: 100, height: 20 }],
    };
    let selection = { isCollapsed: false, rangeCount: 1,
      getRangeAt: () => ({ ...range, cloneRange: () => range }) };
    const scope = {
      useCallback: callback => callback, normalizePdfHighlightRects, normalizeHighlightColor, selectionCleaned,
      textLayerRef: { current: { contains: candidate => candidate === node,
        getBoundingClientRect: () => ({ left: 0, top: 0 }) } },
      lastScaleRef: { current: 1 }, pageRef: { current: 6 }, cardIdRef: { current: 42 },
      hlColorRef: { current: 'yellow' }, pendingHighlightSelectionRef: { current: null },
      setHlColor: () => {}, setHighlights: () => {},
      window: { getSelection: () => selection, pycmd: command => saved.push(command) },
    };
    vm.runInNewContext(`${source.slice(start, finish)}\nglobalThis.open = openHighlightColorPicker; globalThis.finish = finishHighlightColorPicker;`, scope);
    scope.open();
    assert.deepEqual(JSON.parse(saved[0].slice('incremento_pdf_hl_color:'.length)),
      { cardId: 42, currentColor: 'yellow' });
    selection = null; // Opening the Qt panel may remove the browser's selection.
    if (outcome === 'page-changed') scope.pageRef.current = 7;
    scope.finish(outcome === 'cancelled' ? null : '#123ABC');
    assert.equal(scope.pendingHighlightSelectionRef.current, null);
    if (outcome === 'selected') {
      const highlight = JSON.parse(saved[1].slice('incremento_pdf_hl_add:'.length)).highlight;
      assert.equal(highlight.color, '#123abc');
      assert.equal(highlight.text, 'Selected passage');
      assert.equal(highlight.page, 6);
    } else assert.equal(saved.length, 1, 'Cancel and page changes must not add annotations');
    assert.equal(scope.hlColorRef.current, outcome === 'cancelled' ? 'yellow' : '#123abc');
    scope.finish('#654321');
    assert.equal(saved.length, outcome === 'selected' ? 2 : 1, 'A selection is consumed only once');
  });
}
