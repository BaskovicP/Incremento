import en from './locales/en.json' with { type: 'json' };
import hr from './locales/hr.json' with { type: 'json' };
import zhHans from './locales/zh-Hans.json' with { type: 'json' };

const CATALOGS = { en, hr, 'zh-Hans': zhHans };

export function normalizeReaderLocale(value) {
  if (typeof value !== 'string') return 'en';
  const tag = value.trim().replaceAll('_', '-').toLowerCase();
  const parts = tag.split('-');
  if (!parts.every((part) => /^[a-z0-9]+$/.test(part))) return 'en';
  if (parts[0] === 'en' || parts[0] === 'hr') return parts[0];
  if (parts[0] === 'zh') {
    if (parts.includes('hant') || parts.some((part) => ['tw', 'hk', 'mo'].includes(part))) return 'en';
    if (tag === 'zh' || parts.includes('hans') || parts.some((part) => ['cn', 'sg'].includes(part))) return 'zh-Hans';
  }
  return 'en';
}

function interpolate(template, values) {
  let missing = false;
  const result = template.replace(/\{([a-z][a-z0-9_]*)\}/gi, (_match, key) => {
    if (!Object.hasOwn(values, key)) {
      missing = true;
      return '';
    }
    return String(values[key]);
  });
  return missing ? null : result;
}

export function messageFromCatalogs(catalogs, locale, id, values = {}) {
  const selected = catalogs[normalizeReaderLocale(locale)] ?? catalogs.en ?? {};
  for (const template of [selected[id], catalogs.en?.[id]]) {
    if (typeof template !== 'string') continue;
    const rendered = interpolate(template, values);
    if (rendered !== null) return rendered;
  }
  return 'Translation unavailable';
}

export function readerMessage(locale, id, values = {}) {
  return messageFromCatalogs(CATALOGS, locale, id, values);
}

export function pluralFromCatalogs(catalogs, locale, id, count, values = {}) {
  const normalized = normalizeReaderLocale(locale);
  const selectedKey = `${id}_${new Intl.PluralRules(normalized).select(Number(count))}`;
  const selectedTemplate = catalogs[normalized]?.[selectedKey];
  if (typeof selectedTemplate === 'string') {
    const rendered = interpolate(selectedTemplate, {
      ...values,
      count: new Intl.NumberFormat(normalized).format(count),
    });
    if (rendered !== null) return rendered;
  }

  // A missing or malformed form falls back to the English rule and template together.
  const englishKey = `${id}_${new Intl.PluralRules('en').select(Number(count))}`;
  const englishTemplate = catalogs.en?.[englishKey];
  if (typeof englishTemplate !== 'string') return 'Translation unavailable';
  return interpolate(englishTemplate, {
    ...values,
    count: new Intl.NumberFormat('en').format(count),
  }) ?? 'Translation unavailable';
}

export function readerPlural(locale, id, count, values = {}) {
  return pluralFromCatalogs(CATALOGS, locale, id, count, values);
}

function canonicalCustomLocale(value) {
  if (typeof value !== 'string' || value.length > 64) return null;
  try {
    return Intl.getCanonicalLocales(value.trim().replaceAll('_', '-'))[0] ?? null;
  } catch (_error) {
    return null;
  }
}

function customReaderSnapshot(locale, payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return null;
  const canonical = canonicalCustomLocale(locale);
  if (!canonical || canonicalCustomLocale(payload.locale) !== canonical) return null;
  if (!payload.messages || typeof payload.messages !== 'object' || Array.isArray(payload.messages)) return null;
  // The import boundary validates the workbook. Keep only reader strings here,
  // and copy them so a later document/profile cannot mutate this active snapshot.
  const messages = Object.create(null);
  for (const [key, value] of Object.entries(payload.messages)) {
    const plural = /^([a-z][a-z0-9_]*)::(zero|one|two|few|many|other)$/.exec(key);
    const source = plural ? en[`${plural[1]}_other`] : en[key];
    if (typeof source !== 'string' || typeof value !== 'string' || !value.trim()) continue;
    const fields = (text) => [...new Set([...text.matchAll(/\{([a-z][a-z0-9_]*)\}/gi)].map((match) => match[1]))].sort().join(',');
    if (fields(value) !== fields(source)) continue;
    messages[key] = value;
  }
  return { locale: canonical, messages: Object.freeze(messages) };
}

/** Create one immutable language snapshot for one PDF document start. */
export function createReaderLanguage(locale, customPayload = null) {
  const custom = customReaderSnapshot(locale, customPayload);
  if (!custom) {
    const selected = customPayload == null ? normalizeReaderLocale(locale) : 'en';
    return Object.freeze({
      locale: selected,
      tr: (id, values) => readerMessage(selected, id, values),
      plural: (id, count, values) => readerPlural(selected, id, count, values),
    });
  }

  // A well-formed language tag may be absent from an older WebEngine's ICU data.
  // Retain its display language while using English numeric/plural rules there.
  const numericLocale = Intl.PluralRules.supportedLocalesOf(custom.locale).length
    && Intl.NumberFormat.supportedLocalesOf(custom.locale).length ? custom.locale : 'en';
  const pluralRules = new Intl.PluralRules(numericLocale);
  const numberFormat = new Intl.NumberFormat(numericLocale);
  return Object.freeze({
    locale: custom.locale,
    tr: (id, values = {}) => {
      const template = custom.messages[id];
      return (typeof template === 'string' ? interpolate(template, values) : null)
        ?? readerMessage('en', id, values);
    },
    plural: (id, count, values = {}) => {
      const template = custom.messages[`${id}::${pluralRules.select(Number(count))}`];
      return (typeof template === 'string'
        ? interpolate(template, { ...values, count: numberFormat.format(count) }) : null)
        ?? readerPlural('en', id, count, values);
    },
  });
}
