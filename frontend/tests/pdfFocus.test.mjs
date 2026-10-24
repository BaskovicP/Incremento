import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { pdfFocusState, pdfFocusCommand } from '../src/pdfFocus.mjs';

test('focus requests use the committed preference and only target the current open PDF', () => {
  const saved = {cardId: 42, enabled: true, available: true};
  assert.deepEqual(pdfFocusState(saved, 42), {enabled: true, available: true});
  assert.equal(pdfFocusCommand(saved, 42), 'incremento_pdf_focus:{"cardId":42,"enabled":false}');
  assert.equal(pdfFocusCommand({...saved, enabled: false}, 42), 'incremento_pdf_focus:{"cardId":42,"enabled":true}');
  assert.equal(saved.enabled, true, 'Do not show an unsaved preference optimistically');
  for (const state of [null, {}, {...saved, cardId: 99}, {...saved, available: false}]) {
    assert.equal(pdfFocusCommand(state, 42), null);
    assert.equal(pdfFocusState(state, 42).available, false);
  }
});

test('focus remains accessible in both bottom toolbar layouts without another row', () => {
  const source = readFileSync(new URL('../src/PdfViewer.jsx', import.meta.url), 'utf8');
  const toolbar = source.slice(source.indexOf('id="pdf-controls"'), source.indexOf('{/* ── Row 1:'));
  assert.equal(toolbar.match(/\{focusButton\}/g)?.length, 2);
  assert.match(source, /aria-pressed=\{focusState.enabled\}/);
  assert.match(source, /window.incrementoSetPdfFocusState = setPdfFocusState/);
  assert.match(source, /setPdfFocusState\(window._incPdfFocusState\)/);
  assert.match(source, /delete window.incrementoSetPdfFocusState/);
});
