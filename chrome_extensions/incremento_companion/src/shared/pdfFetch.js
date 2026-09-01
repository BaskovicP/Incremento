export const DEFAULT_MAX_PDF_BYTES = 48 * 1024 * 1024;
const MAX_PDF_FILENAME_CHARS = 180;

export function pdfUrlLooksLikePdf(url) {
  try {
    const parsed = new URL(String(url || ""));
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.username || parsed.password) {
      return false;
    }
    return String(parsed.pathname || "").toLowerCase().endsWith(".pdf");
  } catch (_err) {
    return false;
  }
}

function normalizePdfSourceUrl(rawUrl, field = "PDF URL") {
  let parsed;
  try {
    parsed = new URL(String(rawUrl || ""));
  } catch (_err) {
    throw new Error(`${field} must be a valid HTTP(S) URL.`);
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`${field} must use HTTP(S).`);
  }
  if (parsed.username || parsed.password) {
    throw new Error(`${field} must not contain credentials.`);
  }
  return parsed.toString();
}

function bytesLookLikePdf(bytes) {
  if (!(bytes instanceof Uint8Array) || bytes.length === 0) {
    return false;
  }
  const sample = bytes.slice(0, Math.min(bytes.length, 4096));
  const ascii = new TextDecoder("latin1").decode(sample);
  const trimmed = ascii.replace(/^\s+/, "");
  if (trimmed.startsWith("%PDF-")) {
    return true;
  }
  const lower = trimmed.slice(0, 256).toLowerCase();
  if (lower.startsWith("<!doctype html") || lower.startsWith("<html")) {
    return false;
  }
  return false;
}

function sanitizePdfFilename(rawName) {
  const withoutPath = String(rawName || "")
    .replaceAll("\0", "")
    .split("/")
    .filter(Boolean)
    .pop() || "download.pdf";
  let safe = withoutPath
    .replace(/[\\<>:"|?*\u0000-\u001f\u007f]/g, "_")
    .replace(/\s+/g, " ")
    .replace(/^\.+/, "")
    .trim();
  if (!safe) {
    safe = "download.pdf";
  }
  if (!safe.toLowerCase().endsWith(".pdf")) {
    safe = `${safe}.pdf`;
  }
  if (safe.length > MAX_PDF_FILENAME_CHARS) {
    const stem = safe.slice(0, MAX_PDF_FILENAME_CHARS - 4).replace(/[ ._-]+$/g, "");
    safe = `${stem || "download"}.pdf`;
  }
  return safe;
}

function inferPdfFilename(url, response) {
  const disposition = String(response?.headers?.get("Content-Disposition") || "");
  const starMatch = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
  if (starMatch?.[1]) {
    try {
      return sanitizePdfFilename(decodeURIComponent(starMatch[1]));
    } catch (_err) {
      return sanitizePdfFilename(starMatch[1]);
    }
  }
  const plainMatch = disposition.match(/filename\s*=\s*\"?([^\";]+)\"?/i);
  if (plainMatch?.[1]) {
    return sanitizePdfFilename(plainMatch[1]);
  }
  try {
    const parsed = new URL(String(url || ""));
    const parts = String(parsed.pathname || "").split("/").filter(Boolean);
    const name = parts[parts.length - 1] || "download.pdf";
    return sanitizePdfFilename(name);
  } catch (_err) {
    return "download.pdf";
  }
}

function normalizedMaximumBytes(value) {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    return DEFAULT_MAX_PDF_BYTES;
  }
  return Math.min(parsed, DEFAULT_MAX_PDF_BYTES);
}

function oversizedPdfError(maxBytes) {
  return new Error(`PDF exceeds the maximum size of ${maxBytes} bytes.`);
}

function declaredContentLength(response) {
  const raw = String(response?.headers?.get("Content-Length") || "").trim();
  if (!/^\d+$/.test(raw)) {
    return null;
  }
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}

async function readBoundedResponseBytes(response, maxBytes) {
  const declaredLength = declaredContentLength(response);
  if (declaredLength !== null && declaredLength > maxBytes) {
    throw oversizedPdfError(maxBytes);
  }

  const reader = response?.body?.getReader?.();
  if (!reader) {
    throw new Error("Browser PDF fetch does not support bounded streaming.");
  }

  const chunks = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      const chunk = value instanceof Uint8Array ? value : new Uint8Array(value || []);
      total += chunk.byteLength;
      if (total > maxBytes) {
        await reader.cancel?.("PDF byte limit exceeded");
        throw oversizedPdfError(maxBytes);
      }
      chunks.push(chunk);
    }
  } finally {
    reader.releaseLock?.();
  }

  const bytes = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return bytes;
}

function uint8ToBase64(bytes) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("Failed to encode PDF."));
    reader.onload = () => {
      const result = String(reader.result || "");
      const marker = "base64,";
      const idx = result.indexOf(marker);
      resolve(idx >= 0 ? result.slice(idx + marker.length) : "");
    };
    reader.readAsDataURL(new Blob([bytes], { type: "application/pdf" }));
  });
}

export async function fetchPdfPayloadForImport(url, options = {}) {
  const sourceUrl = normalizePdfSourceUrl(url);
  const maxBytes = normalizedMaximumBytes(options?.maxBytes);
  const response = await fetch(sourceUrl, {
    method: "GET",
    credentials: "include",
    redirect: "follow",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`PDF fetch failed (${response.status})`);
  }
  const finalUrl = String(response.url || "").trim();
  if (finalUrl) {
    normalizePdfSourceUrl(finalUrl, "Final PDF URL");
  }

  const bytes = await readBoundedResponseBytes(response, maxBytes);
  const sampleText = new TextDecoder("latin1")
    .decode(bytes.slice(0, Math.min(bytes.length, 512)))
    .toLowerCase();
  const looksLikeCaptcha = sampleText.includes("sgcaptcha") || response.headers.get("sg-captcha");
  if (looksLikeCaptcha) {
    throw new Error("Site returned a captcha challenge instead of the PDF.");
  }
  if (!bytesLookLikePdf(bytes)) {
    throw new Error("Browser fetch did not return a PDF file.");
  }

  return {
    pdfBase64: await uint8ToBase64(bytes),
    pdfFilename: inferPdfFilename(finalUrl || sourceUrl, response),
  };
}

export async function getPdfPayloadForUrl(url) {
  if (!pdfUrlLooksLikePdf(url)) {
    return null;
  }
  try {
    return await fetchPdfPayloadForImport(url);
  } catch (_err) {
    return null;
  }
}
