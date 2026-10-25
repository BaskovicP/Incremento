import assert from 'node:assert/strict';
import test from 'node:test';
import {retainPdfPage, releasePdfPage, cleanupUnusedPdfPage, estimatePdfPageBytes} from '../src/pdfPageResources.mjs';

test('closing a preview cannot clean the page still owned by the active reader', () => {
  let cleaned=0;
  const page={cleanup(){cleaned++;}};
  const reader={}, preview={};
  retainPdfPage(page,reader); retainPdfPage(page,preview);
  releasePdfPage(page,preview);
  cleanupUnusedPdfPage(page);
  assert.equal(cleaned,0);
  releasePdfPage(page,reader);
  assert.equal(cleaned,1);
});

test('decoded image sizes contribute to the page resource budget once per image', () => {
  const image={width:4000,height:6000};
  const page={_intentStates:new Map([['display',{operatorList:{fnArray:[1,1],argsArray:[['img_1'],['img_1']]}}]]),
    objs:{has:()=>true,get:()=>image}};
  assert.ok(estimatePdfPageBytes(page)>=96_000_000);
  assert.ok(estimatePdfPageBytes(page)<97_000_000);
});
