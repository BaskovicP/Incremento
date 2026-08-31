import test from 'node:test';
import assert from 'node:assert/strict';

import { pdfAnchorScrollRatio } from '../src/pdfAnchorLocation.mjs';


test('PDF right-click anchor restores the clicked row near the upper reading area', () => {
  assert.equal(pdfAnchorScrollRatio({
    clientY: 500,
    wrapperTop: -300,
    pageHeight: 2000,
    visibleHeight: 800,
  }), 0.5);
});


test('PDF right-click anchor clamps page boundaries and rejects invalid geometry', () => {
  assert.equal(pdfAnchorScrollRatio({
    clientY: -100,
    wrapperTop: 0,
    pageHeight: 2000,
    visibleHeight: 800,
  }), 0);
  assert.equal(pdfAnchorScrollRatio({
    clientY: 5000,
    wrapperTop: -300,
    pageHeight: 2000,
    visibleHeight: 800,
  }), 1);
  assert.equal(pdfAnchorScrollRatio({
    clientY: 10,
    wrapperTop: 0,
    pageHeight: 0,
    visibleHeight: 800,
  }), null);
});
