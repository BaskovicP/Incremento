import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { setImmediate } from 'node:timers/promises';
import vm from 'node:vm';
import { normalizePdfPageLabels } from '../src/pdfPageLabels.mjs';
import * as pageLabelModule from '../src/pdfPageLabels.mjs';
import { annotatePdfTextStyles } from '../src/pdfTextSelection.mjs';
import { loadPdfContents } from '../src/pdfContents.mjs';
import { pdfCanvasPlan } from '../src/pdfRenderBudget.mjs';

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
    cardIdRef: {current: 7},
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
    textLayerRef: { current: textLayer }, cardIdRef: {current: 7},
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
  const contents = [];
  const scope = {
    useCallback: callback => callback,
    retireRender: () => {},
    resolveWorkerSrc: () => 'local-worker.js',
    pdfDocRef: { current: null }, pageRef: { current: 1 },
    filenameRef: { current: 'sample.pdf' },
    cardIdRef: { current: 55 },
    loadSequenceRef: { current: 0 }, loadingTaskRef: { current: null },
    pageCacheRef: {current: new Set()},
    renderSequenceRef: { current: 0 }, busyRef: { current: false },
    setTotalPages: () => {}, renderPage: page => rendered.push(page), setError: error => { if (error) errors.push(error); },
    setPageLabels: value => labels.push(value),
    setContents: value => contents.push(value), setContentsReady: () => {}, loadPdfContents,
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
  return { scope, tasks, rendered, errors, labels, pages, messages, contents };
}

test('late contents from a previous PDF never overwrite the current outline', async () => {
  const {scope, tasks, contents} = loader();
  let finishOld;
  scope.start();
  tasks[0].resolve({numPages: 3, getOutline: () => new Promise(resolve => {finishOld = resolve;})});
  await tasks[0].promise;
  scope.start();
  tasks[1].resolve({numPages: 2, getOutline: async () => [{title: 'Current chapter', dest: [1]}]});
  await tasks[1].promise;
  await setImmediate();
  finishOld([{title: 'Old chapter', dest: [0]}]);
  await setImmediate();
  assert.equal(contents.at(-1)[0].title, 'Current chapter');
});

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

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return {promise, resolve, reject};
}

// Run the real hook; only React lifecycle, DOM and PDF.js are boundaries.
function renderHarness({pixelRatio = 2, width = 600, height = 920} = {}) {
  const source = readFileSync(new URL('../src/usePdfRender.js', import.meta.url), 'utf8')
    .replace(/^import .*;\n/gm, '').replace('export function usePdfRender', 'function usePdfRender');
  const slots = [], effects = [], renders = [], commands = [], textPages = [];
  let cursor = 0;
  const useState = initial => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = initial;
    return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
  };
  const documents = [];
  const timers = [];
  let resize;
  const scope = {
    useState, useRef: initial => useState({current: initial})[0],
    useCallback: callback => callback, useEffect: callback => effects.push(callback),
    resolvePdfAnnotationLink: async annotation => annotation,
    normalizePdfPageLabels, pdfPageLabelsMessage: pageLabelModule.pdfPageLabelsMessage,
    annotatePdfTextStyles, loadPdfContents, pdfCanvasPlan,
    setTimeout: callback => {timers.push(callback); return timers.length;}, clearTimeout() {},
    setInterval() {}, clearInterval() {},
    ResizeObserver: class { constructor(callback) { resize = callback; } observe() {} disconnect() {} },
    window: {innerHeight: height, devicePixelRatio: pixelRatio, location: {href: 'http://localhost/'},
      pycmd: command => commands.push(command), pdfjsLib: {
        GlobalWorkerOptions: {},
        TextLayer: class {
          constructor({textContentSource}) { this.page = textContentSource; }
          render() { textPages.push(this.page); return Promise.resolve(); }
          cancel() {}
        },
        getDocument: () => ({promise: Promise.resolve(documents.shift()), destroy: async () => {}}),
      }},
    URL,
  };
  vm.runInNewContext(source + '\nglobalThis.hook = usePdfRender;', scope);
  function state() { cursor = 0; return scope.hook(); }
  const api = state();
  for (const ref of [api.canvasARef, api.canvasBRef]) {
    ref.current = {style: {}, dataset: {}, getContext: () => ({canvas: ref.current})};
  }
  api.containerRef.current = {offsetWidth: width, style: {}};
  api.textLayerRef.current = {style: {setProperty() {}}, addEventListener() {}, removeEventListener() {}};
  const cleanups = effects.map(effect => effect()).filter(Boolean);
  function document(id, {delayedPage = false, numPages = 20} = {}) {
    const pages = [], pageCache = new Map();
    const doc = {numPages, getPageLabels: async () => null, getOutline: async () => [],
      getPage: number => {
        if (pageCache.has(number)) return Promise.resolve(pageCache.get(number));
        const page = {pageNumber: number, streamTextContent: () => `${id}:${number}`,
          cleaned: 0, cleanup() {this.cleaned++; return true;},
          getTextContent: async () => ({items: []}), getAnnotations: async () => [],
          getViewport: ({scale}) => ({width: 600 * scale, height: 800 * scale, scale}),
          render: options => {
            const completion = deferred();
            const job = {id, number, ...options, ...completion, cancelled: false,
              cancel() {this.cancelled = true;}};
            renders.push(job);
            return job;
          }};
        const ready = deferred(); pages.push({number, ready, page});
        pageCache.set(number, page);
        return delayedPage ? ready.promise : Promise.resolve(page);
      }};
    documents.push(doc);
    return {doc, pages};
  }
  return {api, state, document, renders, commands, textPages,
    resize: width => {api.containerRef.current.offsetWidth = width; resize([{contentRect: {width}}]); timers.splice(0).forEach(run => run());},
    unmount: () => cleanups.forEach(cleanup => cleanup())};
}

test('rapid page and zoom requests render only the latest pending destination at unchanged pixel density', async () => {
  const h = renderHarness(); h.document('first');
  h.api.startViewer(7, 'first.pdf', 1, 1);
  await setImmediate();
  h.api.nav(1); h.api.nav(1); h.api.adjustZoom(1); h.api.adjustZoom(1);
  assert.equal(h.renders.length, 1, 'never render concurrently into a canvas');
  assert.equal(h.renders[0].cancelled, true, 'obsolete image decoding must be cancelled promptly');
  h.renders[0].resolve(); await setImmediate();
  assert.deepEqual(h.renders.map(job => job.number), [1, 3]);
  assert.equal(h.api.pageRef.current, 3, 'obsolete completion must not rewind the requested page');
  assert.equal(h.renders[1].viewport.scale, 1.2);
  h.renders[1].resolve(); await setImmediate();
  assert.equal(h.state().page, 3);
  assert.equal(h.state().zoom, 1.2);
  assert.equal(h.api.busyRef.current, false);
  assert.deepEqual(h.textPages, ['first:3']);
  assert.equal(h.renders[1].canvasContext.canvas.width, 600 * 1.2 * 2);
  assert.ok(h.commands.includes('incremento_pdf_nav:7:3'));
});

test('a resize during rendering is queued and the newest width wins', async () => {
  const h = renderHarness(); h.document('first');
  h.api.startViewer(7, 'first.pdf', 1, 1); await setImmediate();
  h.resize(500); h.resize(450);
  h.renders[0].resolve(); await setImmediate();
  assert.equal(h.renders.length, 2);
  assert.equal(h.renders[1].viewport.width, 450);
  h.renders[1].resolve(); await setImmediate();
  assert.equal(h.api.busyRef.current, false);
});

test('an obsolete render failure drains the queue without showing a stale error', async () => {
  const h = renderHarness(); h.document('first');
  h.api.startViewer(7, 'first.pdf', 1, 1); await setImmediate();
  h.api.nav(1);
  h.renders[0].reject(new Error('obsolete render')); await setImmediate();
  assert.equal(h.renders.length, 2);
  assert.equal(h.state().error, '');
  h.renders[1].reject(new Error('current render')); await setImmediate();
  assert.equal(h.state().error, 'reader_render_error');
  assert.equal(h.api.busyRef.current, false);
  h.api.nav(1); await setImmediate();
  h.renders[2].resolve(); await setImmediate();
  assert.equal(h.state().error, '');
  assert.equal(h.state().page, 3);
});

test('switching PDFs cancels obsolete work and waits for its canvas before rendering the new document', async () => {
  const h = renderHarness(); h.document('old');
  h.api.startViewer(7, 'old.pdf', 1, 1); await setImmediate();
  h.api.nav(1);
  h.document('new'); h.api.startViewer(8, 'new.pdf', 9, 1); await setImmediate();
  assert.equal(h.renders[0].cancelled, true);
  assert.equal(h.renders.length, 1, 'cancellation must settle before reusing the canvas');
  h.renders[0].resolve(); await setImmediate();
  assert.deepEqual(h.renders.map(job => `${job.id}:${job.number}`), ['old:1', 'new:9']);
  h.renders[1].resolve(); await setImmediate();
  assert.deepEqual(h.textPages, ['new:9']);
  assert.equal(h.state().page, 9);
});

test('obsolete page loading is discarded and unmount prevents queued rendering', async () => {
  const h = renderHarness(); const old = h.document('old', {delayedPage: true});
  h.api.startViewer(7, 'old.pdf', 1, 1); await setImmediate();
  h.document('new'); h.api.startViewer(8, 'new.pdf', 5, 1); await setImmediate();
  old.pages[0].ready.resolve(old.pages[0].page); await setImmediate();
  assert.deepEqual(h.renders.map(job => job.id), ['new']);
  h.api.nav(1); h.unmount();
  h.renders[0].resolve(); await setImmediate();
  assert.equal(h.renders.length, 1);
  assert.deepEqual(h.textPages, []);
});

test('large textbook navigation retains at most three decoded pages and can revisit evicted pages', async () => {
  const h = renderHarness(); const {pages} = h.document('textbook', {numPages: 1747});
  h.api.startViewer(7, 'textbook.pdf', 1, 1);
  for (let number = 1; number <= 12; number++) {
    await setImmediate();
    const job = h.renders.at(-1);
    assert.equal(job.number, number);
    job.resolve(); await setImmediate();
    assert.ok(pages.filter(({page}) => !page.cleaned).length <= 3,
      'decoded images and operator lists must not grow with every page visited');
    assert.equal(pages.at(-1).page.cleaned, 0, 'keep the displayed page ready for zoom and selection');
    if (number < 12) h.api.nav(1);
  }
  assert.ok(pages[0].page.cleaned > 0);
  h.api.nav(-11); await setImmediate();
  h.renders.at(-1).resolve(); await setImmediate();
  assert.equal(h.state().page, 1, 'cleanup must not destroy the document or prevent back navigation');
  assert.equal(h.state().error, '');
});

test('superseded and failed pages release decoded resources after their renders settle', async () => {
  const h = renderHarness(); const {pages} = h.document('textbook');
  h.api.startViewer(7, 'textbook.pdf', 1, 1); await setImmediate();
  h.api.nav(1);
  assert.equal(pages[0].page.cleaned, 0, 'do not clean resources used by an active renderer');
  h.renders[0].reject(new Error('RenderingCancelledException')); await setImmediate();
  assert.equal(pages[0].page.cleaned, 1);
  h.renders[1].reject(new Error('image decode failed')); await setImmediate();
  assert.equal(pages[1].page.cleaned, 1);
  assert.equal(h.state().error, 'reader_render_error');
});

test('high zoom and display density keep the page geometry while bounding canvas memory', async () => {
  const h = renderHarness({pixelRatio: 3, width: 2400, height: 1800});
  h.document('illustrated'); h.api.startViewer(7, 'illustrated.pdf', 1, 4);
  await setImmediate();
  const first = h.renders[0];
  const canvas = first.canvasContext.canvas;
  assert.equal(first.viewport.width, 5040, 'preserve CSS geometry for highlights and selection');
  assert.equal(first.viewport.height, 6720);
  assert.ok(canvas.width * canvas.height <= 8_000_000, 'cap each rendering surface at eight million pixels');
  assert.ok(canvas.width <= 8192 && canvas.height <= 8192);
  assert.ok(first.transform[0] < 1, 'reduce backing resolution, not the reader zoom');
  assert.equal(canvas.style.width, '5040px');
  first.resolve(); await setImmediate();
  h.api.nav(1); await setImmediate();
  const second = h.renders[1];
  assert.ok(canvas.width > 0, 'keep the previous page visible until the replacement is ready');
  second.resolve(); await setImmediate();
  assert.equal(canvas.width * canvas.height, 0, 'release the hidden canvas after the page swap');
  assert.equal(h.state().page, 2);
});
