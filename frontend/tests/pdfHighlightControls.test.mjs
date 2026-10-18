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
function viewer() {
  const slots = [];
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
  const module = { exports: {} };
  vm.runInNewContext(code, {
    module, exports: module.exports,
    window: { pycmd: command => commands.push(command) },
    require: specifier => ({
      ...imports,
      react: { useState, useRef: initial => useState({ current: initial })[0],
        useEffect: () => {}, useCallback: callback => callback },
      './usePdfRender.js': { usePdfRender: () => renderState },
      './HighlightLayer.jsx': { __esModule: true, default: HighlightLayer },
      './PdfSelectionLayer.jsx': { __esModule: true, default: () => null },
    })[specifier],
  });
  function elements(node) {
    if (Array.isArray(node)) return node.flatMap(elements);
    if (!node || typeof node !== 'object') return [];
    return [node, ...elements(node.props?.children)];
  }
  const render = () => {
    cursor = 0;
    return elements(module.exports.default());
  };
  const layer = nodes => nodes.find(node => node.type === HighlightLayer);
  const button = (nodes, text) => nodes.find(node => node.type === 'button' && (
    node.props.children === text || node.props.title === text
  ));
  return { render, layer, button, commands, renderState };
}

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
