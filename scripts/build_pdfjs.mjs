/** Rebuild the shipped PDF.js classic scripts from verified, offline inputs. */
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const vendor = path.join(root, 'vendor/pdfjs');
const manifest = JSON.parse(fs.readFileSync(path.join(vendor, 'manifest.json'), 'utf8'));
const require = createRequire(path.join(root, 'frontend/package.json'));
const esbuild = require('esbuild');
const check = process.argv.length === 3 && process.argv[2] === '--check';
if (process.argv.length > 2 && !check) {
  throw new Error('Usage: node scripts/build_pdfjs.mjs [--check]');
}
if (esbuild.version !== manifest.esbuild_version) {
  throw new Error(`PDF.js requires esbuild ${manifest.esbuild_version}; run npm ci --prefix frontend.`);
}
for (const archive of manifest.source_archives) {
  const bytes = fs.readFileSync(path.join(vendor, archive.archive));
  if (createHash('sha256').update(bytes).digest('hex') !== archive.sha256) {
    throw new Error(`${archive.archive} differs from the documented upstream source archive.`);
  }
}

const outputs = [
  ['pdf', 'pdfjsLib'],
  ['pdf.worker', 'pdfjsWorker'],
  ['pdf.sandbox', 'pdfjsSandbox'],
].map(([name, globalName]) => {
  const input = `${name}.mjs`;
  const bytes = fs.readFileSync(path.join(vendor, input));
  if (createHash('sha256').update(bytes).digest('hex') !== manifest.inputs[input]) {
    throw new Error(`${input} differs from its pinned upstream input; review its source and update the manifest intentionally.`);
  }
  const source = bytes.toString('utf8');
  const upstreamNotice = source.match(/^\/\*\*[\s\S]*?\*\//)?.[0];
  if (!upstreamNotice?.includes('Copyright 2024 Mozilla Foundation')) {
    throw new Error(`${input} is missing its upstream license notice.`);
  }
  const notice = `${upstreamNotice}\n/*!\n * SPDX-License-Identifier: Apache-2.0\n * Modified for Incremento: PDF.js ${manifest.version}, converted to a classic\n * script and minified with esbuild ${esbuild.version}.\n * Rebuild: node scripts/build_pdfjs.mjs\n * Inputs and provenance: vendor/pdfjs/README.md and manifest.json.\n * Additional component notices: THIRD_PARTY_NOTICES.txt.\n */\n`;
  const { code } = esbuild.transformSync(source, {
    sourcefile: input,
    format: 'iife',
    globalName,
    target: 'es2022',
    minify: true,
    legalComments: 'none',
    charset: 'utf8',
  });
  return [path.join(root, 'web/pdfjs', `${name}.min.js`), notice + code];
});

for (const [destination, content] of outputs) {
  const existing = fs.existsSync(destination) ? fs.readFileSync(destination, 'utf8') : null;
  if (existing === content) continue;
  if (check) throw new Error(`${path.relative(root, destination)} is stale; run node scripts/build_pdfjs.mjs.`);
  fs.writeFileSync(destination, content);
}
console.log(`PDF.js ${manifest.version}: ${check ? 'verified' : 'built'} ${outputs.length} reproducible scripts.`);
