import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { buildSync } from "../../../frontend/node_modules/esbuild/lib/main.js";
import { renderToStaticMarkup } from "../../../frontend/node_modules/react-dom/server.node.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const build = buildSync({
  stdin: {contents: 'export {LanguageSettingsPanel} from "./chrome_extensions/incremento_companion/src/popup/LanguageSettingsPanel.jsx"; export {applyStoredLanguageChange} from "./chrome_extensions/incremento_companion/src/shared/i18n.js";', resolveDir: root, loader: "jsx"},
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  nodePaths: [`${root}/frontend/node_modules`],
});
const module = {exports: {}};
new Function("module", "exports", "require", build.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const {LanguageSettingsPanel, applyStoredLanguageChange} = module.exports;
const defaults = {languageDraft: "en", pendingPacks: {}, busy: false, error: "", preview: null, fileInputRef: {current: null}};
function nodes(element) {
  if (!element || typeof element !== "object") return [];
  return [element, ...[element.props?.children].flat(3).flatMap(nodes)];
}

test("the real Language panel renders readable imported-language controls and a validation preview", () => {
  applyStoredLanguageChange("hr", {i18n: {getUILanguage: () => "en"}});
  const pack = {version: 1, locale: "de", name: "Deutsch", translations: {addon: {}, reader: {}, extension: {}}};
  const tree = LanguageSettingsPanel({...defaults, languageDraft: "custom:de", pendingPacks: {de: pack}, preview: {name: "Deutsch", translated: 12, total: 100}});
  const html = renderToStaticMarkup(tree);
  assert.match(html, /Izvezi prazan predložak/);
  assert.match(html, /Izvezi odabrani jezik/);
  assert.match(html, /Uvezi prijevode/);
  assert.match(html, /Deutsch \(uvezeno\)/);
  assert.match(html, /12 od 100/);
  assert.match(html, /class="actions"/);
  assert.match(html, /aria-label="Uvezi prijevode/);
});

test("selection, export, import, Save and Cancel controls invoke their distinct handlers", () => {
  applyStoredLanguageChange("en", {i18n: {getUILanguage: () => "en"}});
  const events = [];
  const props = {...defaults, onSelect: value => events.push(["select", value]), onExportTemplate: () => events.push("template"), onExportSelected: () => events.push("export"), onImport: event => events.push(["import", event]), onSave: () => events.push("save"), onCancel: () => events.push("cancel"), fileInputRef: {current: {click: () => events.push("pick-file")}}};
  const elements = nodes(LanguageSettingsPanel(props));
  elements.find(element => element.type === "select").props.onChange({target: {value: "hr"}});
  for (const element of elements.filter(element => element.type === "button")) element.props.onClick();
  const file = {target: {files: ["file"]}};
  elements.find(element => element.type === "input").props.onChange(file);
  assert.deepEqual(events, [["select", "hr"], "template", "export", "pick-file", "save", "cancel", ["import", file]]);
});

test("busy storage or import operations disable every language action and errors remain plain text", () => {
  const elements = nodes(LanguageSettingsPanel({...defaults, busy: true, error: '<img src=x onerror="bad()">'}));
  assert.ok(elements.filter(element => ["button", "select"].includes(element.type)).every(element => element.props.disabled));
  const html = renderToStaticMarkup(LanguageSettingsPanel({...defaults, error: '<img src=x onerror="bad()">'}));
  assert.match(html, /role="alert"/);
  assert.ok(!html.includes('<img'));
  assert.match(html, /&lt;img/);
});
