import { extensionApi as chrome } from "./extensionApi.js";

export const PDF_EXPORT_SETTINGS_KEY = "incremento_pdf_export_settings";
export const DEFAULT_PDF_EXPORT_SETTINGS = Object.freeze({
  style: "print", dynamic: false, includeLinks: false,
});

export function normalizePdfExportSettings(value) {
  const raw = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return {
    style: ["print", "website", "article"].includes(raw.style) ? raw.style : "print",
    dynamic: raw.dynamic === true,
    includeLinks: raw.includeLinks === true,
  };
}

export async function loadPdfExportSettings(chromeApi = chrome) {
  const stored = await chromeApi.storage.local.get(PDF_EXPORT_SETTINGS_KEY);
  return normalizePdfExportSettings(stored?.[PDF_EXPORT_SETTINGS_KEY]);
}

export function pdfExportPayload(settings, {openedPage = false} = {}) {
  return {
    pdfOptions: pdfExportSettingsForCapture(settings, {openedPage}),
    ...(openedPage ? {captureOpenedPage: true} : {}),
  };
}

export function pdfExportSettingsForCapture(settings, {openedPage = false} = {}) {
  const normalized = normalizePdfExportSettings(settings);
  // The opened tab already contains its JavaScript-rendered article and any
  // completed verification. Reloading elsewhere discards that browser state.
  return openedPage ? {...normalized, dynamic: false} : normalized;
}
