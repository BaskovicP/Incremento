import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import test from 'node:test';
import { TextDecoder, TextEncoder } from 'node:util';
import { ReadableStream } from 'node:stream/web';

const root = fileURLToPath(new URL('../../', import.meta.url));

test('all shipped PDF.js scripts retain notices and load through their browser globals', () => {
  const context = vm.createContext({ console, URL, TextDecoder, TextEncoder, ReadableStream });
  for (const name of ['pdf', 'pdf.worker', 'pdf.sandbox']) {
    const code = fs.readFileSync(path.join(root, 'web/pdfjs', `${name}.min.js`), 'utf8');
    assert.ok(code.includes('Copyright 2024 Mozilla Foundation'), `${name}: upstream attribution`);
    assert.ok(code.includes('SPDX-License-Identifier: Apache-2.0'), `${name}: license identifier`);
    assert.ok(code.includes('Modified for Incremento'), `${name}: transformation notice`);
    vm.runInContext(code, context, { timeout: 3000, filename: `${name}.min.js` });
  }
  assert.equal(context.pdfjsLib.version, '4.10.38');
  assert.equal(typeof context.pdfjsLib.getDocument, 'function');
  assert.equal(typeof context.pdfjsLib.TextLayer, 'function');
  assert.equal(typeof context.pdfjsLib.PDFDataRangeTransport, 'function');
  assert.equal(typeof context.pdfjsWorker.WorkerMessageHandler, 'function');
  assert.equal(typeof context.pdfjsSandbox.QuickJSSandbox, 'function');
});

test('committed PDF.js scripts reproduce from the pinned editable inputs without a network fetch', () => {
  const result = spawnSync(process.execPath, ['scripts/build_pdfjs.mjs', '--check'], {
    cwd: root,
    encoding: 'utf8',
    timeout: 30000,
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
});
