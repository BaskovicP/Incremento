import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { buildSync } from "../../../frontend/node_modules/esbuild/lib/main.js";
import { renderToStaticMarkup } from "../../../frontend/node_modules/react-dom/server.node.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const build = buildSync({
  stdin: {contents: 'export {PdfCaptureButton} from "./chrome_extensions/incremento_companion/src/popup/PdfCaptureButton.jsx"; export {applyStoredLanguageChange} from "./chrome_extensions/incremento_companion/src/shared/i18n.js";', resolveDir: root, loader: "jsx"},
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  nodePaths: [`${root}/frontend/node_modules`],
});
const module = {exports: {}};
new Function("module", "exports", "require", build.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const {PdfCaptureButton, applyStoredLanguageChange} = module.exports;

test("opened-page PDF button imports in one action with the current page capture mode", () => {
  applyStoredLanguageChange("en", {i18n: {getUILanguage: () => "en"}});
  const calls = [];
  const button = PdfCaptureButton({busy: false, hasSupportedPage: true, onAdd: (...args) => calls.push(args)});

  button.props.onClick();

  assert.deepEqual(calls, [["pdf", {openedPage: true}]]);
  assert.equal(button.props.disabled, false);
  assert.match(renderToStaticMarkup(button), /Capture opened page as PDF/);
});

test("opened-page PDF button is unavailable during another import or on a protected browser page", () => {
  for (const [busy, hasSupportedPage] of [[true, true], [false, false]]) {
    const button = PdfCaptureButton({busy, hasSupportedPage, onAdd: () => assert.fail("Import not available")});
    assert.equal(button.props.disabled, true);
  }
});
