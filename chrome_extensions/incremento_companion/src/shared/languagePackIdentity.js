// Small runtime identity rules; spreadsheet/catalog validation loads on demand.
export const LANGUAGE_PACKS_KEY = "ui_language_packs";
export const MAX_PACKS = 20;

export class LanguagePackError extends Error {
  constructor(code, row = 1) { super(code); this.name = "LanguagePackError"; this.code = code; this.row = row; }
}

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
