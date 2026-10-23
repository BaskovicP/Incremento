import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {transformWithEsbuild} from 'vite';
import * as jsx from 'react/jsx-runtime';
import * as model from '../src/pdfPageLinks.mjs';
import {createReaderLanguage} from '../src/i18n.mjs';

const source = new URL('../src/PdfPageLinks.jsx', import.meta.url);
const {code} = await transformWithEsbuild(readFileSync(source, 'utf8'), source.pathname,
  {loader: 'jsx', jsx: 'automatic', format: 'cjs'});

// Use the real component, model and translations; substitute only React's
// scheduler and the DOM event boundary so lifecycle races remain deterministic.
function controls(locale = 'en') {
  const slots = [], effects = [], listeners = new Map(), commands = [];
  let cursor = 0, dirty = false, nodes;
  let location = {cardId: 7, page: 3, generation: 1, enabled: true};
  const useState = initial => {
    const index = cursor++;
    if (!(index in slots)) slots[index] = typeof initial === 'function' ? initial() : initial;
    return [slots[index], value => {
      const next = typeof value === 'function' ? value(slots[index]) : value;
      if (!Object.is(next, slots[index])) {slots[index] = next; dirty = true;}
    }];
  };
  const useEffect = (run, deps) => {
    const index = cursor++, before = slots[index];
    if (before && deps?.every((value, i) => Object.is(value, before.deps?.[i]))) return;
    effects.push(() => {before?.cleanup?.(); slots[index] = {deps, cleanup: run()};});
  };
  const dom = {
    addEventListener: (name, handler) => listeners.set(name, handler),
    removeEventListener: (name, handler) => {if (listeners.get(name) === handler) listeners.delete(name);},
  };
  const module = {exports: {}};
  vm.runInNewContext(code, {module, exports: module.exports, window: dom, document: dom,
    require: name => ({react: {useState, useRef: initial => useState({current: initial})[0], useEffect},
      'react/jsx-runtime': jsx, './pdfPageLinks.mjs': model})[name]});
  const all = node => Array.isArray(node) ? node.flatMap(all)
    : !node || typeof node !== 'object' ? [] : [node, ...all(node.props?.children)];
  const render = () => {
    do {
      dirty = false; cursor = 0;
      const linksState = module.exports.usePdfPageLinks?.({...location, onCommand: value => commands.push(value)});
      nodes = all(module.exports.default({...location, linksState, tr: createReaderLanguage(locale).tr,
        onCommand: value => commands.push(value)}));
      effects.splice(0).forEach(run => run());
    } while (dirty);
    return nodes;
  };
  const button = label => render().find(node => node.type === 'button'
    && (node.props['aria-label'] === label || node.props.children === label || node.props.title === label));
  return {render, button, commands,
    receive: (links, request = commands.at(-1)) => {dom.incrementoReceivePdfPageLinks({...request, links}); render();},
    move: next => {location = {...location, ...next}; render();},
    event: (name, extra = {}) => {listeners.get(name)?.({preventDefault() {}, stopPropagation() {}, ...extra}); render();}};
}

const destination = {id: 4, direction: 'outgoing', title: 'Other book', target_page: 42, available: true};

for (const locale of ['en', 'hr', 'zh-Hans']) {
  test(`opening a linked PDF beside the reader has a visible text label in ${locale}`, () => {
    const ui = controls(locale), {tr} = createReaderLanguage(locale);
    ui.render(); ui.receive([destination]);
    ui.button(tr('reader_page_links')).props.onClick();
    const beside = ui.button(tr('reader_reference_pin'));
    assert.equal(beside.props.children, tr('reader_reference_pin'));
    beside.props.onClick();
    assert.equal(ui.commands.at(-1).operation, 'jump');
    assert.equal(ui.commands.at(-1).mode, 'beside');
    assert.equal(ui.commands.at(-1).id, destination.id);
    assert.equal(ui.button(tr('reader_page_links')).props['aria-expanded'], false);
  });
}

test('page links occupy one toolbar button until opened, and choosing a connection closes the panel', () => {
  const ui = controls();
  assert.equal(ui.render().filter(node => node.type === 'button').length, 1);
  assert.equal(ui.button('Link this page…'), undefined);
  ui.receive([destination]);
  const trigger = ui.button('Page links');
  assert.equal(trigger.props['aria-expanded'], false);
  assert.ok(JSON.stringify(trigger.props.children).includes('(1)'), 'closed button indicates saved connections');
  trigger.props.onClick();
  assert.equal(ui.button('Page links').props['aria-expanded'], true);
  assert.ok(ui.button('Link this page…'));
  ui.button('Jump to linked page').props.onClick();
  assert.equal(ui.commands.at(-1).operation, 'jump');
  assert.equal(ui.commands.at(-1).id, 4);
  assert.equal(ui.button('Page links').props['aria-expanded'], false);
});

test('Escape and outside clicks dismiss page links without navigating or creating links', () => {
  const ui = controls();
  ui.render(); ui.receive([destination]);
  const before = ui.commands.length;
  ui.button('Page links').props.onClick(); ui.render();
  ui.event('keydown', {key: 'Escape'});
  assert.equal(ui.button('Page links').props['aria-expanded'], false);
  ui.button('Page links').props.onClick(); ui.render();
  ui.event('pointerdown', {target: {}});
  assert.equal(ui.button('Page links').props['aria-expanded'], false);
  assert.equal(ui.commands.length, before);
});

test('page navigation closes the popup and rejects a late reply from its old page', () => {
  const ui = controls();
  ui.render(); const old = ui.commands.at(-1);
  ui.receive([destination]);
  ui.button('Page links').props.onClick(); ui.render();
  ui.move({page: 4});
  assert.equal(ui.button('Page links').props['aria-expanded'], false);
  // The matching receiver must still belong to the stable reader model.
  ui.receive([destination], old);
  assert.ok(!JSON.stringify(ui.button('Page links').props.children).includes('(1)'));
  assert.equal(ui.commands.at(-1).page, 4);
  assert.equal(old.page, 3);
  ui.move({enabled: false});
  assert.equal(ui.button('Page links').props.disabled, true);
});
