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

export async function copyErrorReport(report, clipboard = globalThis.navigator?.clipboard) {
  if (!clipboard?.writeText) {
    throw new Error("Clipboard is unavailable.");
  }
  await clipboard.writeText(String(report || ""));
}
