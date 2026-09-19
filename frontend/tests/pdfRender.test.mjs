import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

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

function loader() {
  const source = readFileSync(new URL('../src/usePdfRender.js', import.meta.url), 'utf8');
  const start = source.indexOf('  const doStart = useCallback(');
  const end = source.indexOf('  /**', start);
  const tasks = [];
  const rendered = [], errors = [];
  const scope = {
    useCallback: callback => callback,
    resolveWorkerSrc: () => 'local-worker.js',
    pdfDocRef: { current: null }, pageRef: { current: 1 },
    filenameRef: { current: 'sample.pdf' },
    loadSequenceRef: { current: 0 }, loadingTaskRef: { current: null },
    renderSequenceRef: { current: 0 }, busyRef: { current: false },
    setTotalPages: () => {}, renderPage: page => rendered.push(page), setError: error => errors.push(error),
    window: { pdfjsLib: {
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
  return { scope, tasks, rendered, errors };
}

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
