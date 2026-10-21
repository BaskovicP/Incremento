import test from 'node:test';
import assert from 'node:assert/strict';
import {
  pdfLinkAtPoint, pdfPreviewRegion, createPdfPreviewRenderer, attachPdfLinkPreview,
  normalizePdfLinkPreviewZoom,
} from '../src/pdfLinkPreview.mjs';

const footnote = { kind: 'internal', targetPage: 2, destination: [1, { name: 'XYZ' }, 40, 100, null],
  left: 20, top: 30, width: 10, height: 12 };

function page(width = 600, height = 800) {
  return { getViewport: ({scale}) => ({width: width * scale, height: height * scale,
    convertToViewportPoint: (x, y) => [x * scale, (height - y) * scale]}),
  getTextContent: async () => ({items: [{str: '1. The footnote itself.', transform: [1, 0, 0, 1, 40, 90]}]}) };
}

test('passive hover finds internal links without adding text-selection hit targets', () => {
  assert.equal(pdfLinkAtPoint([footnote], 25, 35), footnote);
  assert.equal(pdfLinkAtPoint([footnote], 31, 35), null);
  assert.equal(pdfLinkAtPoint([{...footnote, kind: 'external'}], 25, 35), null);
  assert.equal(pdfLinkAtPoint([footnote], NaN, 35), null);
});

test('preview crops at the actual footnote rather than the top of its page', () => {
  const region = pdfPreviewRegion(page(), footnote.destination, 2);
  assert.equal(region.top, 1026); // 700 PDF points at 1.5x, with 24px context above.
  assert.equal(region.height, 174);
  assert.equal(region.width, 900);
  assert.equal(region.pixelRatio, 2);
  assert.equal(region.scrollLeft, 36);
});

test('preview regions support rotated destinations, FitH, FitR, missing and hostile coordinates', () => {
  assert.equal(pdfPreviewRegion(page(), [0, {name: 'FitH'}, 100]).top, 1026);
  assert.equal(pdfPreviewRegion(page(), [0, {name: 'FitR'}, 40, 0, 400, 100]).top, 1026);
  assert.equal(pdfPreviewRegion(page(), [0, {name: 'XYZ'}, null, null]).top, 0);
  const rotated = { getViewport: () => ({width: 800, height: 600,
    convertToViewportPoint: (x, y) => [y, x]}) };
  assert.equal(pdfPreviewRegion(rotated, [0, {name: 'XYZ'}, 80, 30]).top, 56);
  const huge = pdfPreviewRegion(page(100000, 100000), [0, {name: 'XYZ'}, Infinity, -1e30], 100);
  // Zoomed notes retain full ordinary-page width; a pixel budget, including
  // device scaling, bounds memory even on huge pages at maximum zoom.
  assert.ok(huge.width <= 4096 && huge.height <= 640 && huge.pixelRatio <= 2);
  assert.ok(Math.ceil(huge.width * huge.pixelRatio) * Math.ceil(huge.height * huge.pixelRatio) <= 4 * 1024 * 1024);
  assert.ok(Number.isFinite(huge.top));
  assert.equal(pdfPreviewRegion({getViewport: () => ({width: NaN, height: 0})}, []), null);
});

test('preview zoom defaults safely and is bounded to the same quarter steps as saved preferences', () => {
  for (const raw of [undefined, null, '', ' ', true, NaN, Infinity, {}, []]) {
    assert.equal(normalizePdfLinkPreviewZoom(raw), 1.5);
  }
  assert.equal(normalizePdfLinkPreviewZoom('2.5'), 2.5);
  assert.equal(normalizePdfLinkPreviewZoom(2.13), 2.25);
  assert.equal(normalizePdfLinkPreviewZoom(0), 1);
  assert.equal(normalizePdfLinkPreviewZoom(9), 4);
});

function renderer() {
  const changes = [], tasks = [], canvases = [];
  const pg = page();
  pg.render = options => {
    let resolve, reject;
    const promise = new Promise((done, fail) => {resolve = done; reject = fail;});
    const task = {promise, resolve, reject, options, cancelled: false,
      cancel() {this.cancelled = true; reject(new Error('cancelled'));}};
    tasks.push(task);
    return task;
  };
  const doc = {numPages: 3, getPage: async () => pg};
  const preview = createPdfPreviewRenderer({
    createCanvas: () => {const canvas = {getContext: () => ({})}; canvases.push(canvas); return canvas;},
    onChange: state => changes.push(state), pixelRatio: 2,
  });
  return {preview, doc, pg, changes, tasks, canvases};
}

test('hover immediately opens a bounded preview without navigation or progress writes and reuses it', async () => {
  const {preview, doc, changes, tasks, canvases} = renderer();
  const pending = preview.show(doc, footnote, {x: 100, y: 50});
  assert.equal(changes.at(-1).status, 'loading');
  await Promise.resolve();
  assert.deepEqual(tasks[0].options.transform, [2, 0, 0, 2, 0, -2052]);
  assert.equal(canvases[0].width, 1800);
  assert.equal(canvases[0].height, 348);
  tasks[0].resolve();
  await pending;
  assert.equal(changes.at(-1).status, 'ready');
  assert.equal(changes.at(-1).text, '1. The footnote itself.');
  preview.clear();
  await preview.show(doc, footnote, {x: 10, y: 20});
  assert.equal(changes.at(-1).status, 'ready');
  assert.equal(tasks.length, 1, 're-hover should use the cached crop');
});

test('leaving, changing pages or switching documents discards pending preview work', async () => {
  const {preview, doc, tasks, changes} = renderer();
  let finish;
  const pending = preview.show({...doc, getPage: () => new Promise(resolve => {finish = resolve;})}, footnote, {});
  preview.clear();
  finish(page());
  await pending;
  assert.equal(changes.at(-1), null);
  const rendering = preview.show(doc, footnote, {});
  await Promise.resolve();
  preview.clear();
  await rendering;
  assert.equal(tasks[0].cancelled, true);
  assert.equal(changes.at(-1), null);
  const next = preview.show(doc, footnote, {});
  await Promise.resolve();
  tasks[1].resolve();
  await next;
  const newDoc = preview.show({...doc}, footnote, {});
  await Promise.resolve();
  assert.equal(changes.at(-1).status, 'loading', 'a different document cannot reuse an old crop');
  tasks[2].resolve();
  await newDoc;
  preview.dispose();
  assert.equal(changes.at(-1), null);
});

test('invalid, remote and reading-limit-blocked links never load a destination page', async () => {
  const {preview, changes} = renderer();
  const doc = {numPages: 3, getPage() {assert.fail('must not read this page');}};
  for (const link of [{...footnote, kind: 'external'}, {...footnote, targetPage: 0}, {...footnote, targetPage: 4}]) {
    await preview.show(doc, link, {});
  }
  await preview.show(doc, footnote, {}, 1);
  assert.equal(changes.at(-1).status, 'limited');
});

test('broken PDF destinations fail quietly while the main reader stays usable', async () => {
  const {preview, changes} = renderer();
  await preview.show({numPages: 2, getPage: async () => {throw new Error('bad PDF');}}, footnote, {});
  assert.equal(changes.at(-1).status, 'unavailable');
});

test('zooming an open preview enlarges the note, retains its destination and remembers zoom on rehover', async () => {
  const {preview, doc, tasks, changes} = renderer();
  const first = preview.show(doc, footnote, {x: 10, y: 20});
  await Promise.resolve(); tasks[0].resolve(); await first;
  const enlarged = preview.setZoom(2.5);
  await Promise.resolve();
  assert.equal(tasks[1].options.viewport.width, 1500);
  assert.equal(tasks[1].options.viewport.height, 2000);
  tasks[1].resolve(); await enlarged;
  assert.deepEqual(changes.at(-1).anchor, {x: 10, y: 20});
  assert.equal(changes.at(-1).link, footnote);
  assert.equal(changes.at(-1).region.top, 1726);
  preview.clear();
  await preview.show(doc, footnote, {x: 30, y: 40});
  assert.equal(tasks.length, 2, 'rehover reuses the preview at the new zoom');
  assert.equal(changes.at(-1).region.viewport.width, 1500);
});

function surface() {
  const handlers = new Map();
  return {addEventListener: (name, fn) => handlers.set(name, fn),
    removeEventListener: name => handlers.delete(name),
    emit: (name, event = {}) => handlers.get(name)?.(event), handlers,
    getBoundingClientRect: () => ({left: 50, top: 100}), contains: () => false};
}

test('hover works with Links Off, preserves selection, stays open over the popup and dismisses on Escape', () => {
  const container = surface(), popup = surface(), host = surface();
  let timer;
  host.setTimeout = fn => {timer = fn; return 1;};
  host.clearTimeout = () => {timer = null;};
  const shown = [], cleared = [];
  const cleanup = attachPdfLinkPreview({container, popup, host, links: [footnote], tlLeft: 10,
    doc: {}, preview: {show: (...args) => shown.push(args), clear: () => cleared.push(true)}});
  const move = () => container.emit('pointermove', {clientX: 85, clientY: 135, buttons: 0});
  move();
  assert.equal(shown.length, 1);
  container.emit('pointerleave');
  popup.emit('pointerenter');
  assert.equal(timer, null, 'moving into the popup keeps it readable');
  host.emit('keydown', {key: 'Escape'});
  assert.equal(cleared.length, 1);
  move();
  assert.equal(shown.length, 1, 'Escape suppresses reopening until the pointer leaves the link');
  container.emit('pointermove', {clientX: 200, clientY: 300, buttons: 0});
  move();
  assert.equal(shown.length, 2);
  container.emit('pointermove', {clientX: 85, clientY: 135, buttons: 1});
  assert.equal(cleared.length, 2, 'selection drags dismiss the preview without intercepting the event');
  cleanup();
  assert.equal(container.handlers.size + popup.handlers.size + host.handlers.size, 0);
});

test('Escape suppression ends after leaving the document and a new hover opens normally', () => {
  const container = surface(), popup = surface(), host = surface();
  host.setTimeout = () => 1;
  host.clearTimeout = () => {};
  const shown = [];
  const cleanup = attachPdfLinkPreview({container, popup, host, links: [footnote], tlLeft: 0,
    doc: {}, preview: {show: (...args) => shown.push(args), clear() {}}});
  const hover = () => container.emit('pointermove', {clientX: 75, clientY: 135});
  hover();
  host.emit('keydown', {key: 'Escape'});
  container.emit('pointerleave');
  hover();
  assert.equal(shown.length, 2);
  cleanup();
});

test('render failures show an unavailable preview without leaking rejected promises', async () => {
  const {preview, doc, tasks, changes} = renderer();
  const pending = preview.show(doc, footnote, {});
  await Promise.resolve();
  tasks[0].reject(new Error('Unreadable page'));
  await pending;
  assert.equal(changes.at(-1).status, 'unavailable');
});

test('scrolling inside the preview keeps it open while document scroll and outside clicks dismiss it', () => {
  const container = surface(), popup = surface(), host = surface(), inside = {};
  popup.contains = target => target === inside;
  host.setTimeout = () => 1; host.clearTimeout = () => {};
  let clears = 0;
  const cleanup = attachPdfLinkPreview({container, popup, host, links: [footnote], tlLeft: 0,
    doc: {}, preview: {show() {}, clear() {++clears;}}});
  container.emit('pointermove', {clientX: 75, clientY: 135});
  host.emit('scroll', {target: inside});
  host.emit('pointerdown', {target: inside});
  assert.equal(clears, 0);
  host.emit('scroll', {target: container});
  assert.equal(clears, 1);
  host.emit('pointerdown', {target: container});
  assert.equal(clears, 2);
  cleanup();
});
