import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { transformWithEsbuild } from 'vite';

const sourceUrl = new URL('../src/PdfViewer.jsx', import.meta.url);
const { code } = await transformWithEsbuild(readFileSync(sourceUrl, 'utf8'), sourceUrl.pathname, {
  loader: 'jsx', jsx: 'automatic', format: 'cjs',
});
const imports = {};
for (const [, specifier] of code.matchAll(/require\("([^"]+)"\)/g)) {
  if (specifier === 'react' || specifier.endsWith('.jsx') || specifier === './usePdfRender.js') continue;
  imports[specifier] = await import(specifier.startsWith('.') ? new URL(specifier, sourceUrl).href : specifier);
}

// Keep actual JSX, translations, and state transitions. Only React's lifecycle
// and PDF.js/DOM effects are replaced so the panel can be used without Anki.
function viewer(props = {}, startup = {}) {
  const slots = [], effects = [];
  let cursor = 0;
  const useState = initial => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
    return [slots[index], update => { slots[index] = typeof update === 'function' ? update(slots[index]) : update; }];
  };
  const commands = [];
  const renderState = {
    page: 1, totalPages: 2, pageLabels: [], zoom: 1, readPage: 0, linkAnnotations: [],
    renderInfo: { scale: 1, tlLeft: 0, pageWidth: 600 },
  };
  for (const key of ['canvasARef', 'canvasBRef', 'containerRef', 'textLayerRef', 'pdfDocRef',
    'activeCvsRef', 'cardIdRef', 'pageRef', 'lastScaleRef']) renderState[key] = { current: null };
  renderState.cardIdRef.current = 42;
  const HighlightLayer = () => null;
  const PdfLinkPreview = () => null;
  const PdfPageLinks = () => null;
  const module = { exports: {} };
  const dom = {innerWidth: 1200, innerHeight: 900, _incPdfPending: {controlsCollapsed: false}, ...startup,
    setTimeout: callback => callback(), pycmd: command => commands.push(command)};
  vm.runInNewContext(code, {
    module, exports: module.exports,
    window: dom,
    require: specifier => ({
      ...imports,
      react: { useState, useRef: initial => useState({ current: initial })[0],
        useEffect: run => effects.push(run), useCallback: callback => callback },
      './usePdfRender.js': { usePdfRender: () => renderState },
      './HighlightLayer.jsx': { __esModule: true, default: HighlightLayer },
      './PdfSelectionLayer.jsx': { __esModule: true, default: () => null },
      './PdfSnapshotLayer.jsx': { __esModule: true, default: () => null, PdfSnapshotButton: () => null },
      './PdfLinkPreview.jsx': { __esModule: true, default: PdfLinkPreview },
      './PdfPageLinks.jsx': { __esModule: true, default: PdfPageLinks, usePdfPageLinks: () => ({}) },
    })[specifier],
  });
  function elements(node) {
    if (Array.isArray(node)) return node.flatMap(elements);
    if (!node || typeof node !== 'object') return [];
    return [node, ...elements(node.props?.children)];
  }
  const render = () => {
    cursor = 0;
    return elements(module.exports.default(props));
  };
  const layer = nodes => nodes.find(node => node.type === HighlightLayer);
  const button = (nodes, text) => nodes.find(node => node.type === 'button' && (
    node.props.children === text || node.props.title === text
  ));
  return { render, layer, button, commands, renderState,
    openFind: () => {
      dom._incPdfPending = null;
      effects.find(run => run.toString().includes('window.incrementoPdfStart ='))();
      dom.incrementoPdfOpenFind();
    },
    pageLinks: nodes => nodes.filter(node => node.type === PdfPageLinks), elements,
    preview: nodes => nodes.find(node => node.type === PdfLinkPreview) };
}

test('compact PDF keeps daily actions visible and opens secondary tools without changing the saved view', () => {
  const ui = viewer({}, {_incPdfPending: {controlsCollapsed: true}});
  const labels = nodes => nodes.filter(node => node.type === 'button').map(node => node.props['aria-label']);
  assert.ok(labels(ui.render()).includes('Extract'));
  assert.ok(labels(ui.render()).includes('Read to here'));
  assert.ok(labels(ui.render()).includes('Review All'));
  ui.button(ui.render(), 'Annotate').props.onClick();
  assert.ok(ui.button(ui.render(), 'Show highlights list'));
  assert.ok(ui.button(ui.render(), 'Show controls'));
  ui.button(ui.render(), 'Annotate').props.onClick();
  assert.equal(ui.button(ui.render(), 'Show highlights list'), undefined);
  ui.button(ui.render(), 'More').props.onClick();
  assert.ok(ui.button(ui.render(), 'Customize controls'));
  assert.deepEqual(ui.commands, [], 'Opening drawers must not change stored compact/expanded preference');
});

test('Find in compact PDF is visible without expanding or overwriting the saved preference', () => {
  const ui = viewer({}, {_incPdfPending: {controlsCollapsed: true}});
  ui.render();
  ui.openFind();
  assert.ok(ui.render().some(node => node.type === 'input' && node.props.placeholder === 'Search this PDF'));
  assert.ok(ui.button(ui.render(), 'Show controls'));
  assert.deepEqual(ui.commands, []);
});

test('Find opens visibly from a minimized side reader even when the Reading group was hidden', () => {
  const ui = viewer({readingOnly: true});
  ui.button(ui.render(), 'Customize controls').props.onClick();
  const labels = ui.render().filter(node => node.type === 'label');
  const reading = labels.find(node => ui.elements(node).some(child => child.props?.children === 'Reading'));
  ui.elements(reading).find(node => node.type === 'input').props.onChange({target: {checked: false}});
  ui.button(ui.render(), 'Minimize controls').props.onClick();
  ui.openFind();
  assert.ok(ui.button(ui.render(), 'Show controls'), 'Find must retain the compact presentation');
  assert.ok(ui.render().find(node => node.type === 'input' && node.props.placeholder === 'Search this PDF'),
    'Find must restore the Reading group and display the search field');
});

test('side-reader Highlights and Bookmarks panels stay above the bottom toolbar in a short window', () => {
  for (const title of ['Show highlights list', 'Show saved interesting-place bookmarks']) {
    const ui = viewer({readingOnly: true});
    ui.button(ui.render(), title).props.onClick();
    const panel = ui.render().find(node => node.props?.style?.overflowY === 'auto'
      && node.props.style.position === 'fixed');
    assert.equal(panel.props.style.top, 8);
    assert.equal(panel.props.style.maxHeight, 'calc(100vh - var(--pdf-controls-height, 58px) - 24px)');
  }
});

for (const readingOnly of [false, true]) {
  test(`PDF controls restore the saved open/closed choice after reopening (${readingOnly ? 'side' : 'main'})`, () => {
    const open = viewer({readingOnly}, {innerWidth: 600, innerHeight: 500,
      _incPdfPending: {controlsCollapsed: false}});
    assert.ok(open.button(open.render(), 'Minimize controls'), 'saved open wins over narrow size');
    assert.deepEqual(open.commands, [], 'restoring a preference must not write it back');
    open.button(open.render(), 'Minimize controls').props.onClick();
    assert.deepEqual(open.commands, ['incremento_pdf_controls:{"cardId":42,"collapsed":true}']);

    const closed = viewer({readingOnly}, {_incPdfPending: {controlsCollapsed: true}});
    assert.ok(closed.button(closed.render(), 'Show controls'), 'saved closed wins over wide size');
    closed.button(closed.render(), 'Show controls').props.onClick();
    assert.deepEqual(closed.commands, ['incremento_pdf_controls:{"cardId":42,"collapsed":false}']);
  });
}

test('a reader with no saved controls preference starts compact at every window size', () => {
  const compact = viewer({}, {innerWidth: 600, innerHeight: 500, _incPdfPending: null});
  assert.ok(compact.button(compact.render(), 'Show controls'));
  const wide = viewer({}, {_incPdfPending: null});
  assert.ok(wide.button(wide.render(), 'Show controls'));
  assert.deepEqual(compact.commands, []);
});

test('page links live inside the existing toolbar in both expanded and compact modes', () => {
  const {render, elements, pageLinks, button} = viewer();
  for (let compact = false; ; compact = true) {
    const nodes = render();
    const toolbar = nodes.find(node => node.props?.id === 'pdf-controls');
    assert.equal(pageLinks(nodes).length, 1);
    assert.equal(pageLinks(elements(toolbar)).length, 1, 'page links must not reserve a strip above the PDF');
    if (compact) break;
    button(nodes, 'Minimize controls').props.onClick();
  }
});

test('changing footnote preview zoom updates the open preview and persists only that preference for the active card', () => {
  const {render, preview, commands} = viewer();
  assert.equal(preview(render()).props.zoom, 1.5);
  preview(render()).props.onZoom(2.5);
  assert.equal(preview(render()).props.zoom, 2.5);
  assert.deepEqual(commands, ['incremento_pdf_link_preview_zoom:{"cardId":42,"zoom":2.5}']);
});

test('the Highlights panel hides controls across pages and restores them without writing annotations', () => {
  const { render, layer, button, commands, renderState } = viewer();
  let nodes = render();
  assert.equal(layer(nodes).props.showHighlightControls, true);
  button(nodes, 'Show highlights list').props.onClick();
  nodes = render();
  const hide = button(nodes, 'Hide highlight controls');
  assert.ok(hide, 'the Highlights panel must offer a clean screenshot action');
  hide.props.onClick();
  nodes = render();
  assert.equal(layer(nodes).props.showHighlightControls, false);
  renderState.page = 2;
  nodes = render();
  assert.equal(layer(nodes).props.showHighlightControls, false, 'page navigation keeps the chosen visibility');
  button(nodes, 'Show highlights list').props.onClick();
  nodes = render();
  button(nodes, 'Show highlight controls').props.onClick();
  assert.equal(layer(render()).props.showHighlightControls, true);
  assert.deepEqual(commands, [], 'visibility changes must not delete or rewrite annotations');
});


test('side reading keeps navigation, reading and annotation tools but cannot expose review controls', () => {
  const {render, button, elements, layer, commands} = viewer({readingOnly: true});
  let nodes = render();
  assert.ok(button(nodes, 'Contents'));
  assert.ok(button(nodes, 'Show highlights list'));
  assert.ok(button(nodes, 'Bookmark the current page as an interesting place'));
  assert.ok(layer(nodes));
  const text = nodes.flatMap(node => typeof node.props?.children === 'string' ? [node.props.children] : []);
  for (const label of ['Review', 'Review All', 'Add card', 'Finished reading', 'Cards']) {
    assert.ok(!text.includes(label), label + ' must not appear in side reading');
  }
  button(nodes, 'Customize controls').props.onClick();
  nodes = render();
  const chooser = nodes.find(node => node.props?.role === 'dialog');
  const checkboxLabels = elements(chooser).filter(node => node.type === 'label')
    .flatMap(node => elements(node).flatMap(child => typeof child.props?.children === 'string' ? [child.props.children] : []));
  assert.ok(!checkboxLabels.includes('Review & cards'));
  assert.deepEqual(commands, []);
});
