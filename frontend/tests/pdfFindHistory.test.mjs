import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import {
  capturePdfFindStartPage,
  pdfFindReturnDelta,
} from '../src/pdfFindHistory.mjs';


test('PDF find remembers the page where the first non-empty search began', () => {
  assert.equal(capturePdfFindStartPage(null, 12), 12);
  assert.equal(capturePdfFindStartPage(12, 37), 12);
  assert.equal(capturePdfFindStartPage(null, 0), null);
});


test('PDF find calculates a return jump without changing the remembered page', () => {
  assert.equal(pdfFindReturnDelta(12, 37), -25);
  assert.equal(pdfFindReturnDelta(12, 12), 0);
  assert.equal(pdfFindReturnDelta(null, 37), null);
});


test('PDF find exposes the captured start page as a return action', () => {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');

  assert.match(source, /setFindStartPage\(\(startPage\) => capturePdfFindStartPage/);
  assert.match(source, /onClick=\{returnToFindStartPage\}/);
  assert.match(source, /tr\('reader_return_to_search_page', \{ page: findStartPage \}\)/);
});
