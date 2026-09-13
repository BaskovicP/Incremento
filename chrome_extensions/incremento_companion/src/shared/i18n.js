import enMessages from "../../_locales/en/messages.json" with { type: "json" };
import hrMessages from "../../_locales/hr/messages.json" with { type: "json" };
import zhMessages from "../../_locales/zh_CN/messages.json" with { type: "json" };

import { canonicalPackLocale, validatedStoredPacks, validateLanguagePack, LANGUAGE_PACKS_KEY, MAX_PACKS, LanguagePackError } from "./languagePacks.js";

export const LANGUAGE_KEY = "ui_language";
export const LANGUAGES = Object.freeze([
  { code: "auto", name: "Automatic" },
  { code: "en", name: "English" },
  { code: "hr", name: "Hrvatski" },
  { code: "zh-Hans", name: "简体中文" },
]);

const CATALOGS = { en: enMessages, hr: hrMessages, "zh-Hans": zhMessages };
const UNAVAILABLE = "Translation unavailable";
let preference = "auto";
let locale = "en";
let revision = 0;
let snapshot = 0;
let packs = {};
const listeners = new Set();

export function normalizeLanguagePreference(value) {
  if (typeof value !== "string") return "auto";
  if (value.startsWith("custom:")) {
    const code = canonicalPackLocale(value.slice(7));
    return code ? `custom:${code}` : "auto";
  }
  const code = value.trim().replaceAll("_", "-").toLowerCase();
  if (code === "auto") return "auto";
  const parts = code.split("-");
  if (!parts.every((part) => /^[a-z0-9]+$/.test(part))) return "auto";
  if (parts[0] === "en" || parts[0] === "hr") return parts[0];
  if (parts[0] === "zh") {
    if (["hant", "tw", "hk", "mo"].some((part) => parts.includes(part))) return "auto";
    if (parts.length === 1 || ["hans", "cn", "sg"].some((part) => parts.includes(part))) return "zh-Hans";
  }
  return "auto";
}

export function resolveLocale(chosen, browserLanguage = "en") {
  const manual = normalizeLanguagePreference(chosen);
  if (manual.startsWith("custom:")) return Object.hasOwn(packs, manual.slice(7)) ? manual.slice(7) : "en";
  if (manual !== "auto") return manual;
  const automatic = normalizeLanguagePreference(browserLanguage);
  return automatic === "auto" ? "en" : automatic;
}

function chromeLanguage(chromeApi) {
  try { return chromeApi?.i18n?.getUILanguage?.() || "en"; } catch (_error) { return "en"; }
}

function broadcast() {
  snapshot += 1;
  for (const callback of listeners) callback(locale, preference);
}

function setLanguage(value, chromeApi, nextPacks = packs) {
  const packsChanged = JSON.stringify(nextPacks) !== JSON.stringify(packs);
  packs = nextPacks;
  const nextPreference = normalizeLanguagePreference(value);
  const nextLocale = resolveLocale(nextPreference, chromeLanguage(chromeApi));
  if (!packsChanged && nextPreference === preference && nextLocale === locale) return;
  preference = nextPreference;
  locale = nextLocale;
  broadcast();
}

export function applyStoredLanguageChange(value, chromeApi = globalThis.chrome) {
  revision += 1;
  setLanguage(value, chromeApi);
}

export async function initializeLanguage(chromeApi = globalThis.chrome) {
  const readRevision = revision;
  try {
    const data = await chromeApi?.storage?.local?.get?.([LANGUAGE_KEY, LANGUAGE_PACKS_KEY]);
    if (revision === readRevision) setLanguage(data?.[LANGUAGE_KEY], chromeApi, validatedStoredPacks(data?.[LANGUAGE_PACKS_KEY]));
  } catch (_error) {
    if (revision === readRevision) setLanguage("auto", chromeApi, {});
  }
  return locale;
}

export function currentLocale() { return locale; }
export function currentPreference() { return preference; }
export function currentLanguagePacks() { return structuredClone(packs); }
export function currentLanguageSnapshot() { return snapshot; }
export function availableLanguages(pending = {}) {
  return [...LANGUAGES, ...Object.values({...packs, ...pending}).map(pack => ({ code: `custom:${pack.locale}`, name: pack.name }))];
}
export function subscribeLanguage(callback) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}

export function watchLanguageStorage(chromeApi = globalThis.chrome) {
  const changed = chromeApi?.storage?.onChanged;
  if (!changed?.addListener) return () => {};
  const listener = (changes, area) => {
    if (area !== "local") return;
    const languageChanged = Object.hasOwn(changes || {}, LANGUAGE_KEY);
    const packsChanged = Object.hasOwn(changes || {}, LANGUAGE_PACKS_KEY);
    if (languageChanged || packsChanged) {
      revision += 1;
      setLanguage(languageChanged ? changes[LANGUAGE_KEY]?.newValue : preference, chromeApi,
        packsChanged ? validatedStoredPacks(changes[LANGUAGE_PACKS_KEY]?.newValue) : packs);
    }
  };
  changed.addListener(listener);
  return () => changed.removeListener?.(listener);
}

export async function saveLanguage(value, chromeApi = globalThis.chrome) {
  const normalized = normalizeLanguagePreference(value);
  await chromeApi.storage.local.set({ [LANGUAGE_KEY]: normalized });
  applyStoredLanguageChange(normalized, chromeApi);
  return normalized;
}

function render(entry, params) {
  if (!entry || typeof entry.message !== "string" || !entry.message) return null;
  // Chrome placeholders have named tokens and an ordinal mapping. Resolve from
  // the logical parameter name directly; never process inserted user text again.
  const tokens = entry.placeholders || {};
  const values = params && typeof params === "object" ? params : {};
  let malformed = false;
  const text = entry.message.replace(/\$([A-Za-z][A-Za-z0-9_]*)\$/g, (match, name) => {
    const key = name.toLowerCase();
    if (!Object.hasOwn(tokens, key) || values[key] == null) {
      malformed = true;
      return match;
    }
    return String(values[key]);
  });
  return malformed ? null : text;
}

function numberFormatter(code) {
  try { return new Intl.NumberFormat(code); } catch (_error) { return new Intl.NumberFormat("en"); }
}
function pluralRules(code) {
  try { return new Intl.PluralRules(code); } catch (_error) { return new Intl.PluralRules("en"); }
}

export function createTranslator(chosenLocale, catalogs = CATALOGS, customPack = null) {
  const effective = customPack ? chosenLocale : catalogs[chosenLocale] ? chosenLocale : "en";
  const custom = customPack?.translations?.extension || {};
  const customEntry = (key, sourceKey = key) => Object.hasOwn(custom, key)
    ? {...catalogs.en?.[sourceKey], message: custom[key]} : null;
  const text = (key, params = {}, fallback = "") =>
    render(customPack ? customEntry(key) : catalogs[effective]?.[key], params)
    ?? render(catalogs.en?.[key], params)
    ?? (fallback || UNAVAILABLE);
  const plural = (key, count, params = {}) => {
    const renderFamily = (familyLocale, useCustom = false) => {
      const catalog = catalogs[familyLocale] || {};
      const rules = pluralRules(familyLocale);
      const required = rules.resolvedOptions().pluralCategories;
      const safeCount = numberFormatter(familyLocale).format(Number(count));
      const values = { ...params, count: safeCount };
      const entry = category => useCustom ? customEntry(`${key}::${category}`, catalogs.en?.[`${key}_${category}`] ? `${key}_${category}` : `${key}_other`) : catalog[`${key}_${category}`];
      if (!required.every(category => render(entry(category), values) !== null)) return null;
      return render(entry(rules.select(Number(count))), values);
    };
    return renderFamily(effective, Boolean(customPack)) ?? renderFamily("en") ?? UNAVAILABLE;
  };
  return { text, plural, locale: effective };
}

function activeTranslator() {
  return createTranslator(locale, CATALOGS, preference.startsWith("custom:") ? packs[preference.slice(7)] : null);
}
export function t(key, params = {}, fallback = "") { return activeTranslator().text(key, params, fallback); }
export function tn(key, count, params = {}) { return activeTranslator().plural(key, count, params); }
export function formatNumber(value) { return numberFormatter(locale).format(Number(value)); }
export function message(key, params = {}, pluralCount = null) { return { key, params, pluralCount }; }
export function displayMessage(value) {
  if (!value || typeof value !== "object" || !value.key) return value ?? "";
  const params = Object.fromEntries(Object.entries(value.params || {}).map(([key, parameter]) => [
    key, parameter && typeof parameter === "object" && parameter.key ? displayMessage(parameter) : parameter,
  ]));
  return value.pluralCount == null ? t(value.key, params) : tn(value.key, value.pluralCount, params);
}

export function localizeDocument(titleKey) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale === "zh-Hans" ? "zh-CN" : locale;
  document.title = t(titleKey);
}


// Only this final Save step commits an imported draft. A single storage write
// keeps the preference and its catalog available together in every context.
export async function saveLanguageSettings(value, pending = {}, chromeApi = globalThis.chrome) {
  const stored = await chromeApi.storage.local.get(LANGUAGE_PACKS_KEY);
  const merged = validatedStoredPacks(stored?.[LANGUAGE_PACKS_KEY]);
  for (const candidate of Object.values(pending)) {
    const pack = validateLanguagePack(candidate);
    merged[pack.locale] = pack;
  }
  if (Object.keys(merged).length > MAX_PACKS) throw new LanguagePackError("packs");
  const normalized = normalizeLanguagePreference(value);
  if (normalized.startsWith("custom:") && !Object.hasOwn(merged, normalized.slice(7))) throw new LanguagePackError("locale");
  await chromeApi.storage.local.set({[LANGUAGE_KEY]: normalized, [LANGUAGE_PACKS_KEY]: merged});
  revision += 1;
  setLanguage(normalized, chromeApi, merged);
  return normalized;
}
