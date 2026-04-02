"use strict";

(function attachPdfFetchHelpers(globalScope) {
  function pdfUrlLooksLikePdf(url) {
    try {
      const parsed = new URL(String(url || ""));
      return String(parsed.pathname || "").toLowerCase().endsWith(".pdf");
    } catch (_err) {
      return false;
    }
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

  function inferPdfFilename(url, response) {
    const disposition = String(response?.headers?.get("Content-Disposition") || "");
    const starMatch = disposition.match(/filename\*\s*=\s*UTF-8''([^;]+)/i);
    if (starMatch?.[1]) {
      try {
        return decodeURIComponent(starMatch[1]);
      } catch (_err) {
        return starMatch[1];
      }
    }
    const plainMatch = disposition.match(/filename\s*=\s*\"?([^\";]+)\"?/i);
    if (plainMatch?.[1]) {
      return plainMatch[1];
    }
    try {
      const parsed = new URL(String(url || ""));
      const parts = String(parsed.pathname || "").split("/").filter(Boolean);
      const name = parts[parts.length - 1] || "download.pdf";
      return name.toLowerCase().endsWith(".pdf") ? name : `${name}.pdf`;
    } catch (_err) {
      return "download.pdf";
    }
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

  async function fetchPdfPayloadForImport(url) {
    const response = await fetch(String(url || ""), {
      method: "GET",
      credentials: "include",
      redirect: "follow",
      cache: "no-store",
    });
    const bytes = new Uint8Array(await response.arrayBuffer());
    const contentType = String(response.headers.get("Content-Type") || "").toLowerCase();
    const sampleText = new TextDecoder("latin1").decode(bytes.slice(0, Math.min(bytes.length, 512))).toLowerCase();
    const looksLikeCaptcha = sampleText.includes("sgcaptcha") || response.headers.get("sg-captcha");
    const looksLikePdf = contentType.includes("pdf") || bytesLookLikePdf(bytes);

    if (!response.ok) {
      throw new Error(`PDF fetch failed (${response.status})`);
    }
    if (looksLikeCaptcha) {
      throw new Error("Site returned a captcha challenge instead of the PDF.");
    }
    if (!looksLikePdf && !pdfUrlLooksLikePdf(url)) {
      throw new Error("Browser fetch did not return a PDF file.");
    }

    return {
      pdfBase64: await uint8ToBase64(bytes),
      pdfFilename: inferPdfFilename(url, response),
    };
  }

  globalScope.pdfUrlLooksLikePdf = pdfUrlLooksLikePdf;
  globalScope.fetchPdfPayloadForImport = fetchPdfPayloadForImport;
})(globalThis);
