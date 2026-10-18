import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { buildSync } from "../../../frontend/node_modules/esbuild/lib/main.js";
import { renderToStaticMarkup } from "../../../frontend/node_modules/react-dom/server.node.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const build = buildSync({
  stdin: {contents: 'export {PdfExportSettingsPanel} from "./chrome_extensions/incremento_companion/src/popup/PdfExportSettingsPanel.jsx"; export {applyStoredLanguageChange} from "./chrome_extensions/incremento_companion/src/shared/i18n.js";', resolveDir: root, loader: "jsx"},
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  nodePaths: [`${root}/frontend/node_modules`],
});
const module = {exports: {}};
new Function("module", "exports", "require", build.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const {PdfExportSettingsPanel, applyStoredLanguageChange} = module.exports;
function nodes(element) {
  if (!element || typeof element !== "object") return [];
  return [element, ...[element.props?.children].flat(3).flatMap(nodes)];
}

test("PDF settings render all layouts and flag changes only update the unsaved draft", () => {
  applyStoredLanguageChange("en", {i18n: {getUILanguage: () => "en"}});
  const settings = {style: "print", dynamic: false, includeLinks: false};
  const changes = [];
  const elements = nodes(PdfExportSettingsPanel({settings, onChange: value => changes.push(value)}));
  const select = elements.find(node => node.type === "select");
  assert.deepEqual(nodes(select).filter(node => node.type === "option").map(node => node.props.value), ["website", "article", "print"]);
  select.props.onChange({target: {value: "article"}});
  elements.find(node => node.props.id === "pdf-export-dynamic").props.onChange({target: {checked: true}});
  elements.find(node => node.props.id === "pdf-export-links").props.onChange({target: {checked: true}});
  assert.deepEqual(changes, [{...settings, style: "article"}, {...settings, dynamic: true}, {...settings, includeLinks: true}]);
  assert.deepEqual(settings, {style: "print", dynamic: false, includeLinks: false});
});

test("PDF settings are localized and every control is disabled while saving", () => {
  for (const [locale, heading] of [["en", "Webpage to PDF"], ["hr", "Web-stranica u PDF"], ["zh-Hans", "网页转 PDF"]]) {
    applyStoredLanguageChange(locale, {i18n: {getUILanguage: () => "en"}});
    const tree = PdfExportSettingsPanel({settings: {style: "website", dynamic: true, includeLinks: true}, busy: true});
    assert.match(renderToStaticMarkup(tree), new RegExp(heading));
    assert.ok(nodes(tree).filter(node => ["select", "input"].includes(node.type)).every(node => node.props.disabled));
  }
});
