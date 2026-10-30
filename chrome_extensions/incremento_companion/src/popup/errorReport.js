import { displayMessage, formatNumber, t } from "../shared/i18n.js";

function cleanReportText(value, maxLength = 1000) {
  return String(value ?? "")
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength);
}

export function safePositiveInteger(value) {
  const numeric = Number(value);
  return Number.isSafeInteger(numeric) && numeric > 0 ? numeric : null;
}

export function normalizeErrorCode(value) {
  const code = String(value || "").trim().toLowerCase();
  return /^[a-z][a-z0-9_]{0,79}$/.test(code) ? code : "unexpected_error";
}

export function buildErrorReport({ title, fields = [] }) {
  const lines = [cleanReportText(title, 120) || "Incremento Companion error"];
  for (const entry of fields) {
    if (!Array.isArray(entry) || entry.length < 2) {
      continue;
    }
    const label = cleanReportText(entry[0], 80);
    const value = cleanReportText(entry[1]);
    if (label && value) {
      lines.push(`${label}: ${value}`);
    }
  }
  return lines.join("\n");
}

export function buildImportErrorReport(details, extensionVersion = "") {
  if (!details) return "";
  const stageKeys = {
    validation: "error_anki_validation", preparation: "error_anki_preparation", card_creation: "error_anki_creation",
  };
  const layoutKeys = {print: "pdf_export_print", website: "pdf_export_website", article: "pdf_export_article"};
  const scopeKeys = {main: "main_content", full: "entire_page"};
  const known = (keys, value) => Object.hasOwn(keys, value) ? t(keys[value]) : "";
  const yesNo = (value) => typeof value === "boolean" ? t(value ? "error_yes" : "error_no") : "";
  const httpStatus = Number.isInteger(details.httpStatus) && details.httpStatus >= 100 && details.httpStatus <= 599
    ? details.httpStatus : "";
  return buildErrorReport({
    title: t("error_report_title"),
    fields: [
      [t("error_extension_version"), extensionVersion],
      [t("error_action"), displayMessage(details.action)],
      [t("error_stage"), displayMessage(details.stage)],
      [t("error_reason"), displayMessage(details.reason)],
      [t("error_anki_detail"), typeof details.serverMessage === "string" ? details.serverMessage : ""],
      [t("error_http_status"), httpStatus],
      [t("error_anki_stage"), known(stageKeys, details.backendStage)],
      [t("error_code"), normalizeErrorCode(details.code)],
      [t("error_pdf_layout"), known(layoutKeys, details.pdfOptions?.style)],
      [t("pdf_export_dynamic"), yesNo(details.pdfOptions?.dynamic)],
      [t("pdf_export_links"), yesNo(details.pdfOptions?.includeLinks)],
      [t("error_content_scope"), known(scopeKeys, details.contentScope)],
      [t("error_actual_chars"), safePositiveInteger(details.actualChars) ? formatNumber(details.actualChars) : ""],
      [t("error_max_chars"), safePositiveInteger(details.maxChars) ? formatNumber(details.maxChars) : ""],
    ],
  });
}

export async function copyErrorReport(report, clipboard = globalThis.navigator?.clipboard) {
  if (!clipboard?.writeText) {
    throw new Error("Clipboard is unavailable.");
  }
  await clipboard.writeText(String(report || ""));
}
