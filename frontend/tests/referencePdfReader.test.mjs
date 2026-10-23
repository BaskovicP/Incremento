import assert from 'node:assert/strict';
import test from 'node:test';
import {createReferenceReader, referenceRestoreRatio, referenceExcerptItemIndex, referenceScrollSnapshot} from '../src/referencePdfReader.mjs';
import {referenceRenderPlan, referenceActionLocation, referenceSelectionText} from '../src/referencePdfReader.mjs';

test('copy and extract wait until the requested page is actually rendered', () => {
  const requested = {page: 4, zoom: 1, generation: 2};
  assert.equal(referenceActionLocation(requested, {page: 3, zoom: 1, generation: 2}), null);
  assert.equal(referenceActionLocation(requested, {page: 4, zoom: 1, generation: 1}), null);
  assert.equal(referenceActionLocation(requested, null), null);
  assert.deepEqual(referenceActionLocation(requested, requested), {page: 4, zoom: 1});
});

test('reference extracts accept only text selected inside the displayed PDF', () => {
  const inside = {}, outside = {};
  const layer = {contains: node => node === inside};
  const selection = node => ({isCollapsed: false, rangeCount: 1,
    getRangeAt: () => ({commonAncestorContainer: node}), toString: () => 'PDF passage'});
  assert.equal(referenceSelectionText(selection(inside), layer), 'PDF passage');
  assert.equal(referenceSelectionText(selection(outside), layer), '');
});

test('extreme PDF page geometry cannot bypass the canvas memory and dimension limits', () => {
  for (const base of [{width: 1, height: 1e9}, {width: 1e9, height: 1}, {width: 600, height: 800}]) {
    const plan = referenceRenderPlan(base, 1200, 4, 2);
    assert.ok(plan.canvasWidth > 0 && plan.canvasHeight > 0);
    assert.ok(plan.canvasWidth <= 8192 && plan.canvasHeight <= 8192);
    assert.ok(plan.canvasWidth * plan.canvasHeight <= 8_000_000);
  }
  assert.throws(() => referenceRenderPlan({width: 0, height: Infinity}, 600, 1, 1));
});

test('pinning and resizing retain scroll within the same page; page navigation resets it', () => {
  assert.equal(referenceRestoreRatio({page: 4, renderedPage: 4, ratio: .75}), .75);
  assert.equal(referenceRestoreRatio({page: 5, renderedPage: 4, ratio: .75}), 0);
  assert.equal(referenceRestoreRatio({page: 4, renderedPage: 0, ratio: 0, initial: .25}), .25);
});

test('resize-generated scroll events cannot overwrite the last stable reading position', () => {
  const rendered = {width: 900, height: 600};
  assert.equal(referenceScrollSnapshot({width: 540, height: 550, top: 200, extent: 300}, rendered, .65), .65);
  assert.equal(referenceScrollSnapshot({width: 900, height: 600, top: 100, extent: 200}, rendered, .65), .5);
});

test('legacy excerpt citations locate their text across PDF spans and line wraps', () => {
  const items = [{str: 'Heading'}, {str: 'The target'}, {str: 'passage continues.'}];
  assert.equal(referenceExcerptItemIndex(items, 'The target\npassage'), 1);
  assert.equal(referenceExcerptItemIndex(items, 'unrelated'), -1);
});

function library() {
  const docs = [];
  return {docs, getDocument: () => {
    const doc = {numPages: 50, destroyed: false, destroy() {this.destroyed = true;},
      getPage: async n => ({getTextContent: async () => ({items: [{str: n === 4 ? 'needle' : 'other'}]})})};
    docs.push(doc);
    return {promise: Promise.resolve(doc), destroy() {doc.destroy();}};
  }};
}

test('independent readers navigate and search without changing the other reader', async () => {
  const lib = library();
  const left = createReferenceReader(), right = createReferenceReader();
  await left.load(lib, 'one', 2);
  await right.load(lib, 'one', 40);
  right.navigate(41);
  assert.equal(left.state().page, 2);
  assert.equal(right.state().page, 41);
  assert.equal(await left.find('needle'), 4);
  assert.equal(left.state().page, 4);
  assert.equal(right.state().page, 41);
});

test('reference reader enforces locked page boundary and bounded zoom', async () => {
  const reader = createReferenceReader();
  await reader.load(library(), 'one', 9, 3);
  assert.equal(reader.state().page, 3);
  assert.equal(reader.navigate(4), false);
  reader.setZoom(100);
  assert.equal(reader.state().zoom, 4);
  assert.equal(await reader.find('needle'), null);
});

test('closing a reader retires a pending document and search', async () => {
  let finish;
  const reader = createReferenceReader();
  const pending = reader.load({getDocument: () => ({promise: new Promise(resolve => {finish = resolve;}), destroy() {}})}, 'one');
  reader.close();
  let destroyed = false;
  finish({numPages: 20, destroy() {destroyed = true;}});
  await pending;
  assert.ok(destroyed);
  assert.equal(reader.document(), null);
});

test('manual navigation cancels an earlier unfinished search', async () => {
  const reader = createReferenceReader();
  let finish;
  await reader.load({getDocument: () => ({promise: Promise.resolve({numPages: 10,
    getPage: () => new Promise(resolve => {finish = resolve;}), destroy() {}}), destroy() {}})}, 'one');
  const pending = reader.find('needle');
  reader.navigate(8);
  finish({getTextContent: async () => ({items: [{str: 'needle'}]})});
  await pending;
  assert.equal(reader.state().page, 8);
});
