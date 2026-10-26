// Compile the production JSX for Node SSR, using the already pinned toolchain.
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
const requireFrontend = createRequire(new URL('../../../frontend/package.json', import.meta.url));
const {transform} = requireFrontend('esbuild');
export const React = requireFrontend('react');
export const {renderToString} = requireFrontend('react-dom/server');

export async function loadJsx(url, source = file => readFileSync(file, 'utf8')) {
  const file = url instanceof URL ? fileURLToPath(url) : url;
  const transformed = await transform(source(file), {loader: 'jsx', jsx: 'automatic', format: 'esm'});
  const pattern = /from\s*["']([^"']+)["']/g;
  let code = transformed.code;
  const replacements = [];
  for (const match of code.matchAll(pattern)) {
    const specifier = match[1];
    let target;
    if (specifier.startsWith('.')) {
      const resolved = path.resolve(path.dirname(file), specifier);
      target = resolved.endsWith('.jsx') ? await jsxUrl(resolved, source) : pathToFileURL(resolved).href;
    } else {
      target = pathToFileURL(requireFrontend.resolve(specifier)).href;
    }
    replacements.push([match[0], `from ${JSON.stringify(target)}`]);
  }
  for (const [original, replacement] of replacements) code = code.replace(original, replacement);
  return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
}

async function jsxUrl(file, source) {
  const transformed = await transform(source(file), {loader: 'jsx', jsx: 'automatic', format: 'esm'});
  let code = transformed.code;
  for (const match of [...code.matchAll(/from\s*["']([^"']+)["']/g)]) {
    const specifier = match[1];
    const resolved = specifier.startsWith('.') ? path.resolve(path.dirname(file), specifier) : requireFrontend.resolve(specifier);
    const target = resolved.endsWith('.jsx') ? await jsxUrl(resolved, source) : pathToFileURL(resolved).href;
    code = code.replace(match[0], `from ${JSON.stringify(target)}`);
  }
  return `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`;
}
