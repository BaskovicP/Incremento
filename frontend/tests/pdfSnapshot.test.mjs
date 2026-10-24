import assert from 'node:assert/strict';
import test from 'node:test';
import { encodePdfSnapshot, paintPdfSnapshotPreview } from '../src/pdfSnapshot.mjs';

test('snapshot PNG encoding is asynchronous and keeps the bridge image format', async () => {
  let finish;
  class Reader {
    readAsDataURL(blob) {
      assert.equal(blob.type, 'image/png');
      this.result = 'data:image/png;base64,cG5n';
      this.onload();
    }
  }
  const pending = encodePdfSnapshot({ toBlob: callback => { finish = callback; } }, () => true, Reader);
  finish({ type: 'image/png' });
  assert.equal(await pending, 'data:image/png;base64,cG5n');
});

test('a snapshot completed after document change is discarded', async () => {
  let finish;
  const pending = encodePdfSnapshot({ toBlob: callback => { finish = callback; } }, () => false,
    class { constructor() { assert.fail('stale image must not be read'); } });
  finish({ type: 'image/png' });
  assert.equal(await pending, null);
});

test('failed PNG encoding does not produce an image', async () => {
  const image = await encodePdfSnapshot({ toBlob: callback => callback(null) }, () => true);
  assert.equal(image, null);
});

test('moving the snapshot preview updates only its DOM geometry', () => {
  const preview = { style: {} };
  paintPdfSnapshotPreview(preview, { x: 12, y: 34, w: 56, h: 78 });
  assert.deepEqual(preview.style, { display: 'block', left: '12px', top: '34px', width: '56px', height: '78px' });
  paintPdfSnapshotPreview(preview, null);
  assert.equal(preview.style.display, 'none');
});

test('document changes while the encoded PNG is read also discard the image', async () => {
  let current = true;
  let reader;
  class Reader {
    constructor() { reader = this; }
    readAsDataURL() {}
  }
  const pending = encodePdfSnapshot({ toBlob: callback => callback({}) }, () => current, Reader);
  current = false;
  reader.result = 'data:image/png;base64,cG5n';
  reader.onload();
  assert.equal(await pending, null);
});

test('a reader failure rejects without sending a partial snapshot', async () => {
  class Reader { readAsDataURL() { this.onerror(); } }
  await assert.rejects(encodePdfSnapshot({ toBlob: callback => callback({}) }, () => true, Reader),
    /encoding failed/);
});

test('snapshot mode notifies only its subscribers and ignores redundant activation', async () => {
  const { createPdfSnapshotMode } = await import('../src/pdfSnapshot.mjs');
  const mode = createPdfSnapshotMode();
  const states = [];
  const stop = mode.subscribe(() => states.push(mode.getSnapshot()));
  assert.equal(mode.getSnapshot(), false);
  mode.setActive(true);
  mode.setActive(true);
  mode.setActive(false);
  assert.deepEqual(states, [true, false]);
  stop();
  mode.setActive(true);
  assert.deepEqual(states, [true, false]);
});

test('snapshot activation is subscribed below the reader and outside saved annotation rendering', async () => {
  const { readFileSync } = await import('node:fs');
  const source = name => readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8');
  const viewer = source('PdfViewer.jsx');
  // Source-level ownership check complements the browser check: a toolbar
  // toggle must not be routed back through state owned by the full reader.
  assert.doesNotMatch(viewer, /setSnapshotMode/);
  assert.match(viewer, /<PdfSnapshotButton\b/);
  assert.match(viewer, /<PdfSnapshotLayer\b/);
  assert.doesNotMatch(source('HighlightLayer.jsx'), /snapshotMode|handleSnapStart|handleSnapEnd/);
});
