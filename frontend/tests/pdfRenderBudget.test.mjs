import assert from 'node:assert/strict';
import test from 'node:test';
import {pdfCanvasPlan} from '../src/pdfRenderBudget.mjs';

test('ordinary PDF pages retain the display pixel density', () => {
  assert.deepEqual(pdfCanvasPlan({width: 600, height: 800}, 2),
    {pixels: 2, canvasWidth: 1200, canvasHeight: 1600});
});

test('extreme aspect ratios and high density stay inside both canvas budgets', () => {
  for (const viewport of [{width: 1, height: 1e9}, {width: 1e9, height: 1},
    {width: 5000, height: 7000}, {width: 1500.3, height: 2000.7}]) {
    const plan = pdfCanvasPlan(viewport, 4);
    assert.ok(plan.canvasWidth > 0 && plan.canvasHeight > 0);
    assert.ok(plan.canvasWidth <= 8192 && plan.canvasHeight <= 8192);
    assert.ok(plan.canvasWidth * plan.canvasHeight <= 8_000_000);
  }
});

test('invalid display density falls back without accepting invalid page geometry', () => {
  for (const density of [undefined, NaN, Infinity, 0, -1]) {
    assert.equal(pdfCanvasPlan({width: 600, height: 800}, density).pixels, 1);
  }
  for (const width of [NaN, Infinity, 0, -1]) {
    assert.throws(() => pdfCanvasPlan({width, height: 800}, 2), RangeError);
  }
});
