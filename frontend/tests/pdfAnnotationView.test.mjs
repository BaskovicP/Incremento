import assert from 'node:assert/strict';
import test from 'node:test';
import {buildPdfHighlightIndex, pdfDisplayHighlights} from '../src/pdfHighlightIndex.mjs';
import {createPdfHighlightTooltip} from '../src/pdfHighlightTooltip.mjs';

test('the annotation index groups pages without losing document order or link metadata', () => {
  const a = {id: 'a', page: 2, text: 'Passage', rects: [{x: 1, y: 2, w: 3, h: 4}]};
  const b = {id: 'b', page: 1, linked_note_id: 3, note: 'Note', rects: []};
  const input = [a, b];
  const index = buildPdfHighlightIndex(input, (left, right) => left.page - right.page);
  assert.deepEqual(index.sorted, [b, a]);
  assert.deepEqual(input, [a, b]);
  assert.deepEqual(index.byPage.get(2), [a]);
  assert.equal(index.missingCards, 1);
  assert.equal(index.byId.get('a'), 1);
  assert.equal(pdfDisplayHighlights(index.byPage.get(2)), pdfDisplayHighlights(index.byPage.get(2)));
  assert.notEqual(pdfDisplayHighlights([a]), pdfDisplayHighlights([{...a, rects: []}]));
});

test('tooltip movement batches to one animation frame and hiding cancels late movement', () => {
  const frames = new Map(); let next = 0, updates = 0;
  const tooltip = createPdfHighlightTooltip({schedule: run => {frames.set(++next, run); return next;},
    cancel: id => frames.delete(id)});
  const unsubscribe = tooltip.subscribe(() => updates++);
  tooltip.show({id: 'a', note: ' Note '}, {clientX: 10, clientY: 20});
  for (let i = 0; i < 100; i++) tooltip.move({clientX: i, clientY: i + 1});
  assert.equal(frames.size, 1); assert.equal(updates, 1);
  frames.values().next().value(); frames.clear();
  assert.deepEqual(tooltip.getSnapshot(), {id: 'a', note: 'Note', x: 99, y: 100});
  assert.equal(updates, 2);
  tooltip.move({clientX: 200, clientY: 200}); tooltip.hide();
  assert.equal(frames.size, 0); assert.equal(tooltip.getSnapshot(), null);
  unsubscribe();
});
