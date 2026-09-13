import catalog from "../../../../locales/translation_catalog.json" with { type: "json" };

export const LANGUAGE_PACKS_KEY = "ui_language_packs";
export const MAX_CSV_BYTES = 2 * 1024 * 1024;
export const MAX_PACKS = 20;
const MAX_ROWS = 20000;
const MAX_CELL = 16384;
const COMPONENTS = ["addon", "reader", "extension"];
const HEADERS = ["component", "key", "form", "source", "translation"];
const FORMULA = /^'*\s*[=+\-@]/;
const CONTROLS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
const byteLength = value => new globalThis.TextEncoder().encode(value).length;
const record = value => value !== null && typeof value === "object" && !Array.isArray(value) && [Object.prototype, null].includes(Object.getPrototypeOf(value));

export class LanguagePackError extends Error {
  constructor(code, row = 1) { super(code); this.name = "LanguagePackError"; this.code = code; this.row = row; }
}
const fail = (code, row) => { throw new LanguagePackError(code, row); };

export function canonicalPackLocale(value) {
  if (typeof value !== "string" || value.length > 48) return null;
  const parts = value.trim().replaceAll("_", "-").split("-");
  if (!/^[A-Za-z]{2,3}$/.test(parts[0])) return null;
  let index = 1;
  const result = [parts[0].toLowerCase()];
  if (/^[A-Za-z]{4}$/.test(parts[index] || "")) { const part = parts[index++]; result.push(part[0].toUpperCase() + part.slice(1).toLowerCase()); }
  if (/^(?:[A-Za-z]{2}|[0-9]{3})$/.test(parts[index] || "")) result.push(parts[index++].toUpperCase());
  const seen = new Set();
  for (; index < parts.length; index += 1) {
    const part = parts[index].toLowerCase();
    if (!/^(?:[A-Za-z0-9]{5,8}|[0-9][A-Za-z0-9]{3})$/.test(part) || seen.has(part)) return null;
    seen.add(part); result.push(part);
  }
  return result.join("-");
}

function cell(value, row) {
  if (typeof value !== "string" || byteLength(value) > MAX_CELL || CONTROLS.test(value)) fail("cell", row);
  return value.replace(/\r\n?/g, "\n");
}
function tokens(text) {
  return [...text.matchAll(/\{[A-Za-z_][A-Za-z_0-9]*(?:![rsa])?(?::[^{}]*)?\}|\$[A-Za-z_][A-Za-z_0-9]*\$/g)].map(match => match[0]).sort();
}
function tags(text) { return [...text.matchAll(/<[A-Za-z/!][^>]*>/g)].map(match => match[0]); }
function formatFields(text, row) {
  const fields = [];
  for (let index = 0; index < text.length;) {
    if (text.startsWith("{{", index) || text.startsWith("}}", index)) { index += 2; continue; }
    if (text[index] === "}") fail("tokens", row);
    if (text[index] !== "{") { index += 1; continue; }
    const end = text.indexOf("}", index);
    if (end < 0) fail("tokens", row);
    const field = text.slice(index, end + 1);
    if (!/^\{[A-Za-z_][A-Za-z_0-9]*(?:![rsa])?(?::[^{}]*)?\}$/.test(field)) fail("tokens", row);
    fields.push(field);
    index = end + 1;
  }
  return fields.sort();
}
function validateText(value, entry, row) {
  const text = cell(value, row);
  if (!text.trim()) return "";
  if (JSON.stringify(tokens(text)) !== JSON.stringify(entry.tokens)) fail("tokens", row);
  if (entry.component !== "extension") {
    const fields = formatFields(text, row);
    if (entry.component === "addon" && JSON.stringify(fields) !== JSON.stringify(formatFields(entry.source, row))) fail("tokens", row);
  }
  const openings = value => [...value.matchAll(/<(?:\/?[A-Za-z]|!)/g)].length;
  if (JSON.stringify(tags(text)) !== JSON.stringify(entry.markup) || openings(text) !== openings(entry.source)) fail("markup", row);
  for (const marker of ["${", "`"]) if (text.split(marker).length > entry.source.split(marker).length) fail("markup", row);
  const schemes = value => [...value.matchAll(/(?:javascript|vbscript)\s*:|data\s*:\s*(?:text\/html|image\/svg)/gi)].map(match => match[0].toLowerCase()).sort();
  if (JSON.stringify(schemes(text)) !== JSON.stringify(schemes(entry.source))) fail("markup", row);
  return text;
}
function schemaIndex(schema) {
  return new Map(schema.entries.map(entry => [`${entry.component}:${entry.key}${entry.form ? `::${entry.form}` : ""}`, entry]));
}
function emptyTranslations() { return { addon: {}, reader: {}, extension: {} }; }

export function validateLanguagePack(value, schema = catalog, {stored = false} = {}) {
  if (!record(value) || value.version !== 1) fail("version");
  if ((Object.keys(value).length !== 4 || Object.keys(value).some(key => !["version", "locale", "name", "translations"].includes(key)))) fail("metadata");
  const locale = canonicalPackLocale(value.locale);
  if (!locale) fail("locale");
  if (typeof value.name !== "string" || !value.name.trim() || [...value.name].length > 80 || /[<>\u0000-\u001f\u007f]/.test(value.name)) fail("name");
  if (!record(value.translations) || (Object.keys(value.translations).length !== 3 || Object.keys(value.translations).some(key => !COMPONENTS.includes(key)))) fail("component");
  const entries = schemaIndex(schema);
  const translations = emptyTranslations();
  let count = 0;
  for (const component of COMPONENTS) {
    const values = value.translations[component];
    if (!record(values)) fail("component");
    for (const [key, text] of Object.entries(values)) {
      if (++count > MAX_ROWS) fail("rows");
      cell(key, 1); cell(text, 1);
      const entry = entries.get(`${component}:${key}`);
      if (!entry) { if (stored) continue; fail("unknown"); }
      try {
        const translated = validateText(text, entry, 1);
        if (translated) translations[component][key] = translated;
      } catch (error) { if (!stored) throw error; }
    }
  }
  const result = { version: 1, locale, name: value.name.trim(), translations };
  if (byteLength(JSON.stringify(result)) > MAX_CSV_BYTES) fail("size");
  return result;
}

// A corrupted pack must not prevent the browser's other saved languages loading.
export function validatedStoredPacks(value, schema = catalog) {
  const result = {};
  if (!record(value) || Object.keys(value).length > MAX_PACKS) return result;
  for (const [key, candidate] of Object.entries(value)) {
    try {
      const pack = validateLanguagePack(candidate, schema, {stored: true});
      if (key === pack.locale) result[key] = pack;
    } catch (_error) { /* Ignore malformed stored imports, leaving built-ins available. */ }
  }
  return result;
}

function parseRows(raw) {
  if (typeof raw !== "string" || byteLength(raw) > MAX_CSV_BYTES) fail("size");
  const text = raw.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
  const header = text.slice(0, text.indexOf("\n") < 0 ? text.length : text.indexOf("\n"));
  const delimiter = [",", ";", "\t"].find(candidate => header.replaceAll('"', "").split(candidate).join(",") === HEADERS.join(","));
  if (!delimiter) fail("header", 1);
  const rows = [];
  let fields = [], field = "", quoted = false, closed = false, startLine = 1;
  const endField = () => { fields.push(cell(field, startLine)); field = ""; closed = false; };
  const endRow = () => {
    endField();
    if (startLine > MAX_ROWS + 1) fail("rows", startLine);
    if (fields.length > 1 || fields.some(value => value !== "")) {
      if (fields.length !== HEADERS.length) fail("columns", startLine);
      rows.push({ fields, row: startLine });
      if (rows.length > MAX_ROWS + 1) fail("rows", startLine);
    }
    fields = []; startLine += 1;
  };
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') { field += '"'; index += 1; } else { quoted = false; closed = true; }
      } else { field += character; }
    } else if (character === delimiter) endField();
    else if (character === "\n") { endRow(); }
    else if (character === '"' && field === "" && !closed) quoted = true;
    else { if (closed || character === '"') fail("csv", startLine); field += character; }
    if (byteLength(field) > MAX_CELL) fail("cell", startLine);
  }
  if (quoted) fail("csv", startLine);
  if (field || fields.length || closed) endRow();
  if (!rows.length || JSON.stringify(rows.shift().fields) !== JSON.stringify(HEADERS)) fail("header", 1);
  return rows;
}
const unprotect = value => value.startsWith("'") && FORMULA.test(value.slice(1)) ? value.slice(1) : value;

export function parseLanguagePackCsv(raw, schema = catalog) {
  const rows = parseRows(raw);
  const entries = schemaIndex(schema);
  const translations = emptyTranslations();
  const metadata = new Map();
  const seen = new Set();
  for (const {fields, row} of rows) {
    const [component, key, form, source, translation] = fields.map(unprotect);
    const identity = `${component}:${key}${form ? `::${form}` : ""}`;
    if (seen.has(identity)) fail("duplicate", row);
    seen.add(identity);
    if (component === "meta") {
      if (form || !["version", "locale", "name"].includes(key)) fail("metadata", row);
      metadata.set(key, { value: translation, row });
      continue;
    }
    const entry = entries.get(identity);
    if (!entry) fail("unknown", row);
    if (source !== entry.source) fail("source", row);
    const translated = validateText(translation, entry, row);
    if (translated) translations[component][`${key}${form ? `::${form}` : ""}`] = translated;
  }
  if (metadata.size !== 3) fail("metadata", 1);
  if (metadata.get("version").value !== "1") fail("version", metadata.get("version").row);
  const locale = canonicalPackLocale(metadata.get("locale").value);
  if (!locale) fail("locale", metadata.get("locale").row);
  const name = metadata.get("name").value;
  if (!name.trim() || [...name].length > 80 || /[<>\u0000-\u001f\u007f]/.test(name)) fail("name", metadata.get("name").row);
  return validateLanguagePack({ version: 1, locale, name, translations }, schema);
}

export function exportLanguagePackCsv(pack = null, schema = catalog, delimiter = ",") {
  if (![",", ";", "\t"].includes(delimiter)) fail("header");
  const value = pack ? validateLanguagePack(pack, schema, {stored: true}) : null;
  const rows = [HEADERS, ["meta", "version", "", "File format version; keep 1.", "1"], ["meta", "locale", "", "Language code, for example de, fr or pt-BR.", value?.locale || ""], ["meta", "name", "", "Language name in its own language, for example Deutsch.", value?.name || ""]];
  for (const entry of schema.entries) {
    const key = `${entry.key}${entry.form ? `::${entry.form}` : ""}`;
    rows.push([entry.component, entry.key, entry.form, entry.source, value?.translations[entry.component][key] || ""]);
  }
  const encode = value => {
    let text = FORMULA.test(value) ? `'${value}` : value;
    if (text.includes(delimiter) || /["\r\n]/.test(text)) text = `"${text.replaceAll('"', '""')}"`;
    return text;
  };
  const csv = `\uFEFF${rows.map(row => row.map(encode).join(delimiter)).join("\r\n")}\r\n`;
  if (byteLength(csv) > MAX_CSV_BYTES) fail("size");
  return csv;
}

export function packCoverage(pack, schema = catalog) {
  return { translated: schema.entries.filter(entry => pack?.translations?.[entry.component]?.[`${entry.key}${entry.form ? `::${entry.form}` : ""}`]).length, total: schema.entries.length };
}

export function downloadLanguagePackCsv(pack = null) {
  const blob = new Blob([exportLanguagePackCsv(pack)], {type: "text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `incremento-language-${pack?.locale || "template"}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function stageLanguagePack(pending, candidate) {
  const pack = validateLanguagePack(candidate);
  const result = {...validatedStoredPacks(pending), [pack.locale]: pack};
  if (Object.keys(result).length > MAX_PACKS) fail("packs");
  return result;
}

export async function readLanguagePackFile(file) {
  if (!file || file.size > MAX_CSV_BYTES) fail("size");
  const bytes = await file.arrayBuffer();
  if (bytes.byteLength > MAX_CSV_BYTES) fail("size");
  let text;
  try { text = new TextDecoder("utf-8", {fatal: true}).decode(bytes); }
  catch (_error) { fail("encoding"); }
  return parseLanguagePackCsv(text);
}

export async function builtinLanguagePack(locale) {
  // Only exporting needs all three built-in translations, so keep these large
  // editable catalogs out of background/content startup work.
  const {default: builtins} = await import("../../../../locales/builtin_translation_packs.json", {with: {type: "json"}});
  return validateLanguagePack(builtins[locale] || builtins.en);
}
