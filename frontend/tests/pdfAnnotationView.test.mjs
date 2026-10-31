import assert from 'node:assert/strict';
import test from 'node:test';
import {buildPdfHighlightIndex, pdfDisplayHighlights} from '../src/pdfHighlightIndex.mjs';
import {createPdfHighlightTooltip, pdfHighlightTooltipLayout,
  pdfHighlightTooltipSurfaceStyle} from '../src/pdfHighlightTooltip.mjs';

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

test('annotation tooltip leaves time to enter its scroll surface before closing', () => {
  const timers = new Map(); let next = 0;
  const tooltip = createPdfHighlightTooltip({
    schedule: run => run(), cancel: () => {},
    delay: run => {timers.set(++next, run); return next;},
    cancelDelay: id => timers.delete(id),
  });
  tooltip.show({id: 'a', note: 'Several images'}, {clientX: 10, clientY: 20});
  tooltip.scheduleHide();
  assert.equal(timers.size, 1);
  assert.equal(tooltip.getSnapshot().note, 'Several images');

  tooltip.cancelHide();
  assert.equal(timers.size, 0);
  assert.equal(tooltip.getSnapshot().note, 'Several images');

  tooltip.scheduleHide();
  timers.values().next().value();
  assert.equal(tooltip.getSnapshot(), null);
});

test('annotation tooltip uses a wide viewport-bounded surface above or below the highlight', () => {
  assert.deepEqual(pdfHighlightTooltipLayout({x: 900, y: 700}, 1000, 800), {
    left: 548, bottom: 116, width: 440, maxHeight: 520,
  });
  assert.deepEqual(pdfHighlightTooltipLayout({x: 290, y: 200}, 300, 240), {
    left: 12, bottom: 56, width: 276, maxHeight: 172,
  });
  assert.deepEqual(pdfHighlightTooltipLayout({x: 20, y: 40}, 1000, 800), {
    left: 34, top: 56, width: 440, maxHeight: 520,
  });
  assert.deepEqual(
    Object.fromEntries(Object.entries(pdfHighlightTooltipSurfaceStyle({x: 20, y: 40}, 1000, 800))
      .filter(([key]) => ['overflowY', 'overflowX', 'overscrollBehavior', 'pointerEvents'].includes(key))),
    {overflowY: 'auto', overflowX: 'hidden', overscrollBehavior: 'contain', pointerEvents: 'auto'},
  );
});
