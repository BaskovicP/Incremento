import assert from 'node:assert/strict';
import test from 'node:test';
import {createPdfPageWindow} from '../src/pdfPageWindow.mjs';

function harness(options = {}) {
  const callbacks = [], prepared = [], pages = new Map();
  const page = number => {
    if (!pages.has(number)) pages.set(number, {pageNumber: number, cleaned: 0,
      getOperatorList: async () => {prepared.push(number);}, cleanup() {this.cleaned++;}});
    return pages.get(number);
  };
  const doc = {numPages: 1747, getPage: async number => page(number)};
  const window = createPdfPageWindow(doc, {
    schedule: callback => {callbacks.push(callback); return callback;},
    cancel: callback => {const index = callbacks.indexOf(callback); if (index >= 0) callbacks.splice(index, 1);},
    estimateBytes: () => 65536,
    ...options,
  });
  const drain = async () => {while (callbacks.length) await callbacks.shift()();};
  return {window, page, prepared, callbacks, drain, doc};
}

test('idle preparation visits only the five pages before and after the displayed page', async () => {
  const h = harness(); h.window.display(h.page(800));
  assert.deepEqual(h.prepared, [], 'the first page must not wait for neighbor preparation');
  await h.drain();
  assert.deepEqual(h.prepared, [801, 799, 802, 798, 803, 797, 804, 796, 805, 795]);
  assert.equal(h.callbacks.length, 0, 'do not sweep the remaining 1747-page book');
  h.window.display(h.page(900)); await h.drain();
  for (let number = 795; number <= 805; number++) assert.equal(h.page(number).cleaned, 1);
  assert.deepEqual([...h.prepared.slice(10)].sort((a,b) => a-b), [895,896,897,898,899,901,902,903,904,905]);
});

test('navigation pauses idle work; closing releases cached pages and cancels the next batch', async () => {
  const h = harness(); h.window.display(h.page(1));
  await h.callbacks.shift()();
  assert.deepEqual(h.prepared, [2]);
  h.window.pause(); await h.drain();
  assert.deepEqual(h.prepared, [2]);
  h.window.display(h.page(1747)); await h.drain();
  assert.deepEqual(h.prepared.slice(1), [1746,1745,1744,1743,1742]);
  h.window.dispose();
  assert.equal(h.page(1747).cleaned, 1);
});

test('a stale in-flight page cannot start expensive preparation after a different page is requested', async () => {
  const h = harness(); let finish;
  h.doc.getPage = () => new Promise(resolve => {finish = resolve;});
  h.window.display(h.page(10));
  const pending = h.callbacks.shift()();
  h.window.pause(); finish(h.page(11)); await pending;
  assert.deepEqual(h.prepared, []);
  assert.equal(h.page(11).cleaned, 1);
});

test('neighbor preparation warms the display renderer and cancels it before foreground navigation', async () => {
  const callbacks = [], canvas = {}, calls = [];
  let finish;
  const neighbor = {pageNumber: 2, cleanup() {}, getViewport: ({scale}) => ({width: 600*scale, height: 800*scale}),
    getOperatorList() {assert.fail('operator-list-only intent cannot warm the display-render cache');},
    render(options) {calls.push(options); return {promise: new Promise(resolve => {finish = resolve;}),
      cancel() {calls.push('cancel'); finish();}};}};
  const window = createPdfPageWindow({numPages: 2, getPage: async () => neighbor}, {
    schedule: callback => {callbacks.push(callback); return callback;}, cancel() {},
    createCanvas: () => Object.assign(canvas, {getContext: () => ({canvas})}),
  });
  window.display({pageNumber: 1, cleanup() {}});
  const pending = callbacks.shift()();
  await Promise.resolve();
  assert.equal(calls.length, 1);
  assert.ok(canvas.width <= 32 && canvas.height <= 32);
  window.pause(); await pending;
  assert.equal(calls[1], 'cancel');
  assert.equal(canvas.width * canvas.height, 0);
});

test('image-heavy pages stop idle decoding at the memory budget', async () => {
  const h = harness({maxBytes: 64 * 1024 * 1024, estimateBytes: () => 32 * 1024 * 1024});
  h.window.display(h.page(800)); await h.drain();
  assert.deepEqual(h.prepared, [801], 'do not decode the rest of the window only to discard it');
  assert.equal(h.window.has(h.page(800)), true);
  assert.equal(h.window.has(h.page(801)), true);
  h.window.display(h.page(801)); await h.drain();
  assert.equal(h.window.has(h.page(800)), true, 'a nearby turn reuses the previously displayed page');
  assert.deepEqual(h.prepared, [801]);
});

test('one oversized neighbor stops further speculative decoding instead of evicting every attempted page', async () => {
  const h = harness({maxBytes: 64 * 1024 * 1024,
    estimateBytes: page => (page.pageNumber === 800 ? 48 : 32) * 1024 * 1024});
  h.window.display(h.page(800)); await h.drain();
  assert.deepEqual(h.prepared, [801]);
  assert.equal(h.window.has(h.page(800)), true);
  assert.equal(h.window.has(h.page(801)), false);
  assert.equal(h.page(801).cleaned, 1);
});

test('hiding the reader releases neighbors and pauses preparation until visible', async () => {
  const h = harness(); h.window.display(h.page(100)); await h.drain();
  h.window.setVisible(false);
  assert.equal(h.window.has(h.page(100)), true);
  assert.equal(h.window.has(h.page(101)), false);
  assert.equal(h.page(101).cleaned, 1);
  h.window.display(h.page(102)); await h.drain();
  assert.equal(h.prepared.length, 10);
  h.window.setVisible(true); await h.drain();
  assert.equal(h.window.has(h.page(103)), true);
});
