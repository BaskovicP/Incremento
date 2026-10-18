import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizePdfPageLabels, pdfPageLocation } from '../src/pdfPageLabels.mjs';
import * as pageLabelModule from '../src/pdfPageLabels.mjs';
import { createReaderLanguage } from '../src/i18n.mjs';

test('PDF citation metadata sends printed labels with exact document identity', () => {
  const message = pageLabelModule.pdfPageLabelsMessage(55, 'physics.pdf', ['i', 'ii']);
  assert.deepEqual(JSON.parse(message.slice('incremento_pdf_page_labels:'.length)), {
    cardId: 55, filename: 'physics.pdf', labels: ['i', 'ii'],
  });
});

test('PDF citation metadata stays bounded and rejects malformed labels', () => {
  for (const labels of [[], ['v\u0000'], ['x'.repeat(129)], Array(20001).fill(''), Array(10000).fill('x'.repeat(128))]) {
    assert.equal(pageLabelModule.pdfPageLabelsMessage(55, 'physics.pdf', labels), '');
  }
  assert.deepEqual(JSON.parse(pageLabelModule.pdfPageLabelsMessage(55, 'physics.pdf', null).slice('incremento_pdf_page_labels:'.length)), {
    cardId: 55, filename: 'physics.pdf', labels: null,
  });
});

test('the textbook page 551 is displayed beside physical PDF page 579 of 1453', () => {
  const labels = Array.from({ length: 1453 }, (_, index) => String(index - 27));
  const { tr } = createReaderLanguage('en');
  assert.equal(pdfPageLocation(579, 1453, labels, tr), 'Printed 551 · PDF 579 / 1453');
});

test('Roman numerals and appendix prefixes retain their exact page labels', () => {
  const { tr } = createReaderLanguage('en');
  const labels = normalizePdfPageLabels([' iv ', 'A-12', '1'], 3);
  assert.equal(pdfPageLocation(1, 3, labels, tr), 'Printed iv · PDF 1 / 3');
  assert.equal(pdfPageLocation(2, 3, labels, tr), 'Printed A-12 · PDF 2 / 3');
  assert.equal(pdfPageLocation(3, 3, labels, tr), 'Printed 1 · PDF 3 / 3');
});

test('PDFs without labels and unlabelled cover pages show only the PDF position', () => {
  const { tr } = createReaderLanguage('en');
  assert.equal(pdfPageLocation(579, 1453, null, tr), 'PDF 579 / 1453');
  assert.equal(pdfPageLocation(1, 3, normalizePdfPageLabels(['', 'i', '1'], 3), tr), 'PDF 1 / 3');
  assert.equal(pdfPageLocation(1, 0, null, tr), 'PDF — / —');
});

test('malformed label metadata cannot misidentify another PDF page', () => {
  for (const labels of [null, {}, ['1'], ['1', 2], ['1', 'x'.repeat(129)], ['1', 'a\u0000b']]) {
    assert.equal(normalizePdfPageLabels(labels, 2), null);
  }
});

test('dual numbering is localized without translating document labels', () => {
  assert.equal(pdfPageLocation(2, 3, ['i', 'A-1', 'A-2'], createReaderLanguage('hr').tr), 'Tiskana A-1 · PDF 2 / 3');
  assert.equal(pdfPageLocation(2, 3, ['i', 'A-1', 'A-2'], createReaderLanguage('zh-Hans').tr), '印刷页码 A-1 · PDF 2 / 3');
});
