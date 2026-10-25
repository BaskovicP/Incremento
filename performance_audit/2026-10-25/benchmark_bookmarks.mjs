// Pure source benchmark. Does not start a browser or call an extension API.
import {performance} from 'node:perf_hooks';
import {readFileSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {buildBookmarkItems} from '../../chrome_extensions/incremento_companion/src/bookmarks/bookmarkModel.js';

const results = [];
for (const style of ['numeric', 'opaque']) {
  for (const size of [1000, 2500, 5000]) {
    const nodes = Array.from({length: size}, (_, i) => ({
      id: style === 'numeric' ? String(i + 1) : `bookmark_${i}`,
      title: `Synthetic bookmark ${i}`, url: `https://example.test/page${i}`,
    }));
    const samples = [];
    for (let repeat = 0; repeat < 3; repeat++) {
      const started = performance.now();
      const built = buildBookmarkItems(nodes);
      samples.push(performance.now() - started);
      assert.equal(Object.keys(built).length, size);
      assert.equal(built[nodes.at(-1).id].title, nodes.at(-1).title);
      assert.equal(built[nodes[0].id].selected, false);
    }
    results.push({id_style: style, bookmarks: size,
      median_ms: Number([...samples].sort((a, b) => a - b)[1].toFixed(3)),
      samples_ms: samples.map(value => Number(value.toFixed(3)))});
  }
}
const source = new URL('../../chrome_extensions/incremento_companion/src/bookmarks/bookmarkModel.js', import.meta.url);
const report = JSON.stringify({environment: {node: process.version, platform: process.platform,
  architecture: process.arch}, source_sha256: createHash('sha256').update(readFileSync(source)).digest('hex'),
  scope: 'Pure source functions and synthetic nodes; no extension UI latency measured', results}, null, 2) + '\n';
const outputIndex = process.argv.indexOf('--output');
if (outputIndex >= 0) writeFileSync(process.argv[outputIndex + 1], report);
else process.stdout.write(report);
