import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { setImmediate } from 'node:timers/promises';
import vm from 'node:vm';
import { normalizePdfPageLabels } from '../src/pdfPageLabels.mjs';
import * as pageLabelModule from '../src/pdfPageLabels.mjs';
import { annotatePdfTextStyles } from '../src/pdfTextSelection.mjs';

test('rendering keeps PDF spaces, narrow letters, and compressed OCR spans selectable', async () => {
  const source = readFileSync(new URL('../src/usePdfRender.js', import.meta.url), 'utf8');
  const start = source.indexOf('  const renderTextLayer = useCallback(');
  const end = source.indexOf('  const renderLinkAnnotations', start);
  const spans = [' ', 'i', '.', 'compressed'].map(text => ({
    textContent: text, style: { transform: 'scaleX(0.04)' }, removed: false,
    getBoundingClientRect: () => ({ width: 2, height: 10 }),
    remove() { this.removed = true; },
  }));
  const scope = {
    useCallback: callback => callback,
    textLayerRef: { current: { style: { setProperty() {} }, querySelectorAll: () => spans } },
    containerRef: { current: { offsetWidth: 600 } }, lastScaleRef: { current: 1 }, setRenderInfo() {},
    window: { pdfjsLib: { TextLayer: class { render() { return Promise.resolve(); } } } },
  };
  vm.runInNewContext(source.slice(start, end) + '\nglobalThis.render = renderTextLayer;', scope);
  scope.render({ streamTextContent() {} }, { scale: 1, width: 600, height: 800 });
  await Promise.resolve();
  assert.deepEqual(spans.filter(span => !span.removed).map(span => span.textContent), [' ', 'i', '.', 'compressed']);
});

test('rendered PDF font emphasis is attached to selectable text for extraction', async () => {
  const source = readFileSync(new URL('../src/usePdfRender.js', import.meta.url), 'utf8');
  const start = source.indexOf('  const renderTextLayer = useCallback(');
  const end = source.indexOf('  const renderLinkAnnotations', start);
  const spans = [{ textContent: 'The goal:', dataset: {} }, { textContent: ' goal', dataset: {} }];
  const textLayer = { style: { setProperty() {} }, innerHTML: '' };
  const scope = {
    useCallback: callback => callback,
    annotatePdfTextStyles,
    textLayerRef: { current: textLayer },
    containerRef: { current: { offsetWidth: 600 } }, lastScaleRef: { current: 1 }, setRenderInfo() {},
    window: { pdfjsLib: { TextLayer: class {
      textDivs = spans;
      render() { return Promise.resolve(); }
      cancel() {}
    } } },
  };
  const page = {
    streamTextContent() {},
    getTextContent: async () => ({ items: [
      { str: 'The goal:', fontName: 'bold' },
      { str: ' goal', fontName: 'italic' },
    ] }),
    commonObjs: { get: name => ({ bold: { bold: true }, italic: { italic: true } })[name] },
  };
  vm.runInNewContext(source.slice(start, end) + '\nglobalThis.render = renderTextLayer;', scope);

  scope.render(page, { scale: 1, width: 600, height: 800 });
  await setImmediate();

  assert.equal(spans[0].dataset.incBold, '1');
  assert.equal(spans[1].dataset.incItalic, '1');
});

function loader() {
  const source = readFileSync(new URL('../src/usePdfRender.js', import.meta.url), 'utf8');
  const start = source.indexOf('  const doStart = useCallback(');
  const end = source.indexOf('  /**', start);
  const tasks = [];
  const rendered = [], errors = [];
  const labels = [];
  const pages = [];
  const messages = [];
  const scope = {
    useCallback: callback => callback,
    resolveWorkerSrc: () => 'local-worker.js',
    pdfDocRef: { current: null }, pageRef: { current: 1 },
    filenameRef: { current: 'sample.pdf' },
    cardIdRef: { current: 55 },
    loadSequenceRef: { current: 0 }, loadingTaskRef: { current: null },
    renderSequenceRef: { current: 0 }, busyRef: { current: false },
    setTotalPages: () => {}, renderPage: page => rendered.push(page), setError: error => errors.push(error),
    setPageLabels: value => labels.push(value),
    setPage: value => pages.push(value),
    normalizePdfPageLabels,
    pdfPageLabelsMessage: (...args) => pageLabelModule.pdfPageLabelsMessage(...args),
    window: { pycmd: message => messages.push(message), pdfjsLib: {
      GlobalWorkerOptions: {},
      getDocument: () => {
        let resolve, reject;
        const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
        const task = { promise, resolve, reject, destroy: async () => {} };
        tasks.push(task);
        return task;
      },
    } },
  };
  vm.runInNewContext(`${source.slice(start, end)}\nglobalThis.start = doStart;`, scope);
  return { scope, tasks, rendered, errors, labels, pages, messages };
}

test('loaded printed labels become available to Python extraction citations', async () => {
  const { scope, tasks, messages } = loader();
  scope.start();
  tasks[0].resolve({ numPages: 2, getPageLabels: async () => ['iv', 'v'] });
  await tasks[0].promise;
  await setImmediate();
  assert.equal(messages.length, 1);
  assert.deepEqual(JSON.parse(messages[0].slice('incremento_pdf_page_labels:'.length)), {
    cardId: 55, filename: 'sample.pdf', labels: ['iv', 'v'],
  });
});

test('a restored PDF page is shown before its labels arrive rather than pairing with the previous page', async () => {
  const { scope, tasks, pages } = loader();
  scope.pageRef.current = 579;
  scope.start();
  tasks[0].resolve({ numPages: 1453, getPageLabels: async () => null });
  await tasks[0].promise;
  assert.equal(pages.at(-1), 579);
});

test('PDF page labels load without delaying rendering or changing the physical page', async () => {
  const { scope, tasks, rendered, labels } = loader();
  let resolveLabels;
  const labelPromise = new Promise(resolve => { resolveLabels = resolve; });
  scope.pageRef.current = 3;
  scope.start();
  tasks[0].resolve({ numPages: 3, getPageLabels: () => labelPromise });
  await tasks[0].promise;
  assert.deepEqual(rendered, [3]);
  resolveLabels(['i', '1', '2']);
  await labelPromise;
  await setImmediate();
  assert.deepEqual(labels.at(-1), ['i', '1', '2']);
  assert.equal(scope.pageRef.current, 3);
});

test('switching documents clears printed labels and discards a late result from the old PDF', async () => {
  const { scope, tasks, labels, messages } = loader();
  let resolveOldLabels;
  const oldLabels = new Promise(resolve => { resolveOldLabels = resolve; });
  scope.start();
  tasks[0].resolve({ numPages: 2, getPageLabels: () => oldLabels });
  await tasks[0].promise;
  scope.start();
  assert.equal(labels.at(-1), null);
  tasks[1].resolve({ numPages: 2, getPageLabels: async () => ['A-1', 'A-2'] });
  await tasks[1].promise;
  await setImmediate();
  resolveOldLabels(['i', 'ii']);
  await oldLabels;
  await setImmediate();
  assert.deepEqual(labels.at(-1), ['A-1', 'A-2']);
  assert.equal(messages.length, 1);
  assert.deepEqual(JSON.parse(messages[0].slice('incremento_pdf_page_labels:'.length)).labels, ['A-1', 'A-2']);
});

test('missing or unreadable PDF page labels leave physical navigation working', async () => {
  for (const getPageLabels of [async () => null, async () => { throw new Error('invalid labels'); }]) {
    const { scope, tasks, rendered, errors, labels } = loader();
    scope.start();
    tasks[0].resolve({ numPages: 2, getPageLabels });
    await tasks[0].promise;
    await setImmediate();
    assert.deepEqual(rendered, [1]);
    assert.deepEqual(errors, []);
    assert.equal(labels.at(-1), null);
  }
});

test('an older PDF load cannot overwrite the latest annotation display copy', async () => {
  const { scope, tasks, rendered } = loader();
  scope.start();
  scope.start();
  const latest = { numPages: 5 };
  const stale = { numPages: 2, destroy: async () => {} };
  tasks[1].resolve(latest);
  await tasks[1].promise;
  tasks[0].resolve(stale);
  await tasks[0].promise;
  assert.equal(scope.pdfDocRef.current, latest);
  assert.deepEqual(rendered, [1]);
});

test('a cancelled older PDF load cannot show an error over a newer document', async () => {
  const { scope, tasks, errors } = loader();
  scope.start();
  scope.start();
  tasks[0].reject(new Error('cancelled'));
  await tasks[0].promise.catch(() => {});
  await Promise.resolve();
  assert.deepEqual(errors, []);
});
