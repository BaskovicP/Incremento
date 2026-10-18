import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { buildSync } from "../../../frontend/node_modules/esbuild/lib/main.js";
import { renderToStaticMarkup } from "../../../frontend/node_modules/react-dom/server.node.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const build = buildSync({
  stdin: {contents: 'export {WebsiteTagControls} from "./chrome_extensions/incremento_companion/src/popup/WebsiteTagControls.jsx"; export {applyStoredLanguageChange} from "./chrome_extensions/incremento_companion/src/shared/i18n.js";', resolveDir: root, loader: "jsx"},
  bundle: true, write: false, platform: "node", format: "cjs", jsx: "automatic",
  nodePaths: [`${root}/frontend/node_modules`],
});
const module = {exports: {}};
new Function("module", "exports", "require", build.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const {WebsiteTagControls, applyStoredLanguageChange} = module.exports;
function nodes(element) {
  if (!element || typeof element !== "object") return [];
  return [element, ...[element.props?.children].flat(3).flatMap(nodes)];
}

test("website checkbox reflects saved choice and dispatches a reversible preference change", () => {
  applyStoredLanguageChange("en", {i18n: {getUILanguage: () => "en"}});
  const changes = [];
  const tree = WebsiteTagControls({state: {site: "example.org", ready: true, enabled: true}, onToggle: value => changes.push(value)});
  const input = nodes(tree).find(node => node.type === "input");
  assert.equal(input.props.checked, true);
  assert.equal(input.props.disabled, false);
  input.props.onChange({target: {checked: false}});
  assert.deepEqual(changes, [false]);
  assert.match(renderToStaticMarkup(tree), /example.org/);
});

test("loading failures disable writes and show a localized retry action", () => {
  for (const [locale, label] of [["en", "Remember tags for this website"], ["hr", "Zapamti oznake za ovu web-stranicu"], ["zh-Hans", "记住此网站的标签"]]) {
    applyStoredLanguageChange(locale, {i18n: {getUILanguage: () => "en"}});
    let retried = false;
    const tree = WebsiteTagControls({state: {ready: false, enabled: false, error: new TypeError("offline")}, onRetry: () => {retried = true;}});
    const all = nodes(tree);
    assert.equal(all.find(node => node.type === "input").props.disabled, true);
    assert.ok(all.some(node => node.props.role === "alert"));
    assert.match(renderToStaticMarkup(tree), new RegExp(label));
    all.find(node => node.type === "button").props.onClick();
    assert.equal(retried, true);
  }
});
