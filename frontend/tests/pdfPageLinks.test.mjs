import test from 'node:test';
import assert from 'node:assert/strict';
import {createPdfPageLinks} from '../src/pdfPageLinks.mjs';
import {pdfPageLinksViewport} from '../src/pdfPageLinks.mjs';
import * as pageLinks from '../src/pdfPageLinks.mjs';

test('wrapped toolbar height reserves the actual reading area and stops updating after teardown', () => {
  let height = 109, resized;
  let disconnected = false;
  const actual = [];
  const toolbar = {getBoundingClientRect: () => ({height})};
  class Observer {
    constructor(callback) {resized = callback;}
    observe(element) {assert.equal(element, toolbar);}
    disconnect() {disconnected = true;}
  }
  const close = pageLinks.observePdfToolbarHeight(toolbar, value => actual.push(value), Observer);
  assert.deepEqual(actual, [109]);
  height = 57.5; resized(); resized();
  assert.deepEqual(actual, [109, 58]);
  close();
  height = 250; resized();
  assert.equal(disconnected, true);
  assert.deepEqual(actual, [109, 58]);
});

test('toolbar page links reserve no space above the PDF or its restored anchors', () => {
  const metrics = pdfPageLinksViewport({scrollY: 0, wrapperTop: 0, pageHeight: 1000,
    windowHeight: 720, controlsHeight: 58});
  assert.deepEqual(metrics, {pageTop: 0, pageHeight: 1000, visibleHeight: 662, maxOffset: 338});
  const restoredScroll = metrics.pageTop + metrics.maxOffset * .5;
  const restoredDocumentPoint = -restoredScroll + metrics.maxOffset * .5;
  assert.equal(restoredDocumentPoint, 0);
});

test('visible destinations jump by saved connection identity and refresh after page changes', () => {
  const sent = [], updates = [];
  const model = createPdfPageLinks(message => sent.push(message), value => updates.push(value));
  model.start(7, 3, 1);
  const request = sent.at(-1);
  assert.equal(request.operation, 'list');
  const row = {id: 4, direction: 'outgoing', title: 'Other book', target_page: 42, available: true};
  model.receive({...request, links: [row]});
  assert.deepEqual(updates.at(-1).links, [row]);
  model.jump(row);
  assert.deepEqual(sent.at(-1), {...request, operation: 'jump', id: 4, direction: 'outgoing', mode: 'jump'});
  model.start(8, 42, 2);
  assert.deepEqual(updates.at(-1).links, []);
  model.receive({...request, links: [row]});
  model.jump(row);
  assert.equal(sent.at(-1).operation, 'list');
  assert.equal(sent.at(-1).cardId, 8);
});

test('refresh generations reject old responses even when returning to the same PDF page', () => {
  const sent = [], updates = [];
  const model = createPdfPageLinks(message => sent.push(message), value => updates.push(value));
  model.start(7, 3, 1);
  const old = sent.at(-1);
  model.refresh();
  model.receive({...old, links: [{id: 1, direction: 'incoming', target_page: 2}]});
  assert.equal(updates.at(-1).loading, true);
  model.receive({...sent.at(-1), links: [], error: true});
  assert.equal(updates.at(-1).error, true);
  model.start(0, 0, 2);
  model.create();
  assert.equal(sent.length, 2);
});

test('unavailable and forged destinations cannot dispatch jumps', () => {
  const sent = [];
  const model = createPdfPageLinks(message => sent.push(message), () => {});
  model.start(7, 3, 1);
  const request = sent.at(-1);
  const row = {id: 1, direction: 'incoming', title: 'Missing', target_page: 2, available: false};
  model.receive({...request, links: [row]});
  model.jump(row);
  model.jump({...row, available: true});
  assert.equal(sent.length, 1);
  model.create();
  assert.equal(sent.at(-1).operation, 'create');
  model.manage();
  assert.equal(sent.at(-1).operation, 'manage');
});
