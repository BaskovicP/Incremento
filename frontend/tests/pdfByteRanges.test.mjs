import assert from 'node:assert/strict';
import test from 'node:test';
import {createPdfByteRangeTransport, decodePdfByteRange} from '../src/pdfByteRanges.mjs';

test('PDF bytes decode directly into the requested view without disturbing adjacent bytes', () => {
  const buffer = new Uint8Array(260).fill(99);
  const bytes = Uint8Array.from({length:256}, (_, index) => index);
  const encoded = Buffer.from(bytes).toString('base64');
  decodePdfByteRange(encoded, buffer.subarray(2, 258), atob);
  assert.deepEqual([...buffer.subarray(2, 258)], [...bytes]);
  assert.deepEqual([...buffer.subarray(0, 2)], [99, 99]);
  assert.deepEqual([...buffer.subarray(258)], [99, 99]);
});

test('the older-browser decoder validates length before delivering any bytes', () => {
  const bytes = new Uint8Array(4);
  bytes.setFromBase64 = undefined;
  let decoded = 0;
  decodePdfByteRange('AAECAw==', bytes, value => {decoded++; return atob(value);});
  assert.equal(decoded, 1);
  assert.deepEqual([...bytes], [0, 1, 2, 3]);
  assert.throws(() => decodePdfByteRange('AA==', bytes, atob));
});

function harness() {
  const requested = [], received = [], failures = [], host = {atob};
  class Range {
    constructor(length, initialData) {this.length = length; this.initialData = initialData;}
    onDataRange(begin, data) {received.push([begin, [...data]]);}
  }
  const metadata = {token: 'document-a', cardId: 42, length: 1_000_000, chunkSize: 262144};
  const range = createPdfByteRangeTransport({PDFDataRangeTransport: Range}, metadata,
    command => requested.push(JSON.parse(command.slice('incremento_pdf_range:'.length))),
    error => failures.push(error), host);
  const reply = request => host.incrementoReceivePdfRange({token: request.token,
    requestId: request.requestId, begin: request.begin,
    data: Buffer.alloc(request.end - request.begin, 7).toString('base64')});
  return {host, range, requested, received, failures, metadata, reply};
}

test('PDF loading requests bounded chunks on demand without fetching the whole file', () => {
  const h = harness();
  assert.equal(h.range.initialData.length, 0);
  assert.equal(h.requested.length, 0);
  h.range.requestDataRange(0, 800000);
  assert.equal(h.requested.length, 2, 'bound parallel reads');
  assert.ok(h.requested.every(r => r.end - r.begin <= 262144));
  h.reply(h.requested[1]); h.reply(h.requested[0]);
  assert.equal(h.requested.length, 4);
  assert.equal(h.received.length, 0, 'PDF.js needs one complete response per requested range');
  h.reply(h.requested[3]); h.reply(h.requested[2]);
  assert.deepEqual(h.received.map(([begin, data]) => [begin, data.length]), [[0, 800000]]);
  assert.ok(h.requested.every(r => r.token === 'document-a' && r.cardId === 42));
});

test('a newer page range is read before queued chunks from obsolete preparation', () => {
  const h = harness(); h.range.requestDataRange(0, 800000);
  h.range.requestDataRange(900000, 901000);
  h.reply(h.requested[0]);
  assert.equal(h.requested[2].begin, 900000);
});

test('retiring a document ignores pending and foreign replies and stops queued reads', () => {
  const h = harness(); h.range.requestDataRange(0, 800000);
  h.host.incrementoReceivePdfRange({...h.requested[0], token: 'another-document', data: 'Bw=='});
  assert.deepEqual(h.received, []);
  const receiver = h.host.incrementoReceivePdfRange;
  h.range.abort();
  receiver({...h.requested[0], data: 'Bw=='});
  assert.deepEqual(h.received, []);
  assert.equal(h.requested.length, 2);
  assert.equal(h.failures.length, 0);
});

test('failed and truncated reads stop the transport instead of falling back to a full-file load', () => {
  for (const response of [{error: true}, {data: 'Bw=='}]) {
    const h = harness(); h.range.requestDataRange(0, 500);
    h.host.incrementoReceivePdfRange({token: h.metadata.token, requestId: h.requested[0].requestId,
      begin: 0, ...response});
    assert.equal(h.failures.length, 1);
    assert.equal(h.received.length, 0);
  }
});
