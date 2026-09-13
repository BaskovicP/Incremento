import assert from 'node:assert/strict';
import test from 'node:test';
import { joinPdfTextParts, truncatePdfText } from '../src/pdfCjkText.mjs';

test('joining Chinese text fragments does not inject ASCII spaces', () => {
  assert.equal(joinPdfTextParts('中文', '内容'), '中文内容');
  assert.equal(joinPdfTextParts('hello', 'world'), 'hello world');
  assert.equal(joinPdfTextParts('中文', 'word'), '中文 word');
});

test('truncating extracted text keeps supplementary Unicode characters intact', () => {
  assert.equal(truncatePdfText('中😀文', 2), '中😀');
});
