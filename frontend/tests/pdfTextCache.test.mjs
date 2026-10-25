import assert from 'node:assert/strict';
import test from 'node:test';
import {ReadableStream} from 'node:stream/web';
import {pdfPageTextSource, pdfPageTextContent, forgetPdfPageText} from '../src/pdfTextCache.mjs';

test('the text layer and formatting metadata share one streamed extraction and zoom reuses it', async () => {
  let extractions = 0;
  const page = {streamTextContent() {
    extractions++;
    return new ReadableStream({start(controller) {
      controller.enqueue({items: [{str:'one'}], styles: {font:{fontFamily:'serif'}}, lang:'en'});
      controller.enqueue({items: [{str:'two'}], styles: {}});
      controller.close();
    }});
  }};
  const first = pdfPageTextSource(page);
  const reader = first.source.getReader();
  assert.equal((await reader.read()).value.items[0].str, 'one');
  await reader.read(); await reader.read();
  assert.deepEqual((await first.content).items.map(item => item.str), ['one','two']);
  const next = pdfPageTextSource(page);
  assert.deepEqual((await next.source).items.map(item => item.str), ['one','two']);
  assert.equal((await pdfPageTextContent(page)).lang, 'en');
  assert.equal(extractions, 1);
  forgetPdfPageText(page);
  const fresh = pdfPageTextSource(page);
  await fresh.content;
  assert.equal(extractions, 2);
  await fresh.source.cancel();
});

test('a preview that requested text first supplies it to a later main-page text layer', async () => {
  let calls=0;
  const page={getTextContent:async()=>{calls++;return {items:[{str:'footnote'}],styles:{}};}};
  assert.equal((await pdfPageTextContent(page)).items[0].str, 'footnote');
  assert.equal((await pdfPageTextSource(page).source).items[0].str, 'footnote');
  assert.equal(calls, 1);
});
