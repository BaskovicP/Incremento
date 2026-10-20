import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { pushPdfLinkHistory } from '../src/pdfLinkHistory.mjs';
import { loadPdfContents, resolvePdfContentsLocation } from '../src/pdfContents.mjs';

test('PDF contents preserve nesting and resolve named and explicit destinations', async () => {
  const doc = {
    numPages: 20,
    getOutline: async () => [
      { title: 'Chapter <one>', dest: 'one', items: [{ title: 'Detail', dest: [4, { name: 'Fit' }] }] },
      { title: 'Remote', url: 'https://example.com' },
      { title: 'Broken', dest: 'missing' },
    ],
    getDestination: async name => name === 'one' ? [{ num: 5 }, { name: 'XYZ' }, 0, 600] : null,
    getPageIndex: async () => 2,
  };
  const entries = await loadPdfContents(doc);
  assert.deepEqual(entries.map(({ title, depth, page }) => ({ title, depth, page })), [
    { title: 'Chapter <one>', depth: 0, page: 3 },
    { title: 'Detail', depth: 1, page: 5 },
  ]);
  doc.getPage = async () => ({ getViewport: () => ({ height: 800, convertToViewportPoint: (_x, y) => [0, 800 - y] }) });
  assert.deepEqual(await resolvePdfContentsLocation(doc, entries[0]), { page: 3, pageFraction: 0.25 });
});

test('outline loading is bounded, cancellable, and tolerates absent metadata', async () => {
  assert.deepEqual(await loadPdfContents({getOutline: async () => null}), []);
  const node = {title: 'Cycle', dest: [0]};
  node.items = [node];
  const doc = {numPages: 1, getOutline: async () => [node]};
  assert.equal((await loadPdfContents(doc)).length, 1);
  assert.deepEqual(await loadPdfContents(doc, () => false), []);
});

function contentsBridge(allowed = true) {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
  const start = source.indexOf('    window.incrementoPdfOpenContents = openContents;');
  const end = source.indexOf('    return () => {', start);
  let history = [];
  const scope = {
    window: {}, openContents() {}, contentsGenerationRef: {current: 3},
    pdfDocRef: {current: {numPages: 20}}, pageRef: {current: 2},
    capturePdfLinkLocation: () => ({page: 2, scrollRatio: 0.625}),
    limitAwareNav: delta => {if (allowed) scope.pageRef.current += delta; return allowed;},
    setLinkBackHistory: callback => {history = callback(history);},
    pushPdfLinkHistory, resolvePdfContentsLocation,
    clampScrollRatio: value => Math.max(0, Math.min(Number(value) || 0, 1)),
    suppressScrollPersistence() {}, setLinkBackScrollNonce() {},
    rawSetReadProgress: () => assert.fail('Contents must not change the read marker'),
    contents: [{id: 0, page: 10, destination: [9]}],
  };
  for (const name of ['pendingHighlightScrollRef', 'pendingExcerptJumpRef', 'pendingReadAnchorScrollRef',
    'pendingPageTopScrollRef', 'pendingResumePageRef', 'pendingResumeScrollRef', 'pendingContentsFractionRef']) {
    scope[name] = {current: null};
  }
  vm.runInNewContext(source.slice(start, end), scope);
  return {scope, history: () => history};
}

test('contents jumps use return history and exact saved positions independently of Links Off', async () => {
  const {scope, history} = contentsBridge();
  await scope.window.incrementoPdfContentsJump({saved_place: true, page: 12, scroll_ratio: 0.4}, 3);
  assert.equal(scope.pageRef.current, 12);
  assert.equal(scope.pendingResumePageRef.current, 12);
  assert.equal(scope.pendingResumeScrollRef.current, 0.4);
  assert.deepEqual(history(), [{page: 2, scrollRatio: 0.625}]);
});

test('blocked and stale contents jumps leave both location and return history intact', async () => {
  const {scope, history} = contentsBridge(false);
  await scope.window.incrementoPdfContentsJump({id: 0}, 3);
  await scope.window.incrementoPdfContentsJump({saved_place: true, page: 12}, 2);
  assert.equal(scope.pageRef.current, 2);
  assert.deepEqual(history(), []);
  assert.equal(scope.pendingResumePageRef.current, null);
});
