export const BROWSER_CAPTURE_SETTINGS_KEY = "incremento_browser_capture_settings";
export const DEFAULT_PRIORITY = 50;
export const PRIORITY_MIN = 0;
export const PRIORITY_MAX = 100;
export const PRIORITY_STEP = 0.1;
export const MAX_BROWSER_CAPTURE_HTML_CHARS = 2_000_000;
export const MAX_BROWSER_CAPTURE_SELECTED_TEXT_CHARS = 200_000;
export const MAX_BROWSER_CAPTURE_SNAPSHOTS = 12;
export const MAX_BROWSER_CAPTURE_IMAGE_BYTES = 8_000_000;
export const MAX_BROWSER_CAPTURE_TOTAL_IMAGE_BYTES = 32_000_000;
export const MAX_BROWSER_CAPTURE_SCREENSHOT_BYTES = 32_000_000;

function estimatedBase64Bytes(rawValue) {
  const value = String(rawValue || "").replace(/\s+/g, "");
  if (!value) {
    return 0;
  }
  const padding = value.endsWith("==") ? 2 : (value.endsWith("=") ? 1 : 0);
  return Math.max(0, Math.floor((value.length * 3) / 4) - padding);
}

function captureSizeError(label, maximum, unit) {
  return { ok: false, error: `${label} is too large. Maximum is ${maximum} ${unit}.` };
}

export function validateBrowserCaptureContext(context) {
  if (String(context?.html || "").length > MAX_BROWSER_CAPTURE_HTML_CHARS) {
    return captureSizeError("Page HTML", MAX_BROWSER_CAPTURE_HTML_CHARS, "characters");
  }
  if (String(context?.selectionText || "").length > MAX_BROWSER_CAPTURE_SELECTED_TEXT_CHARS) {
    return captureSizeError(
      "Selected text",
      MAX_BROWSER_CAPTURE_SELECTED_TEXT_CHARS,
      "characters"
    );
  }
  return { ok: true, error: "" };
}

export function validateBrowserCaptureScreenshotDataUrl(dataUrl, options = {}) {
  const raw = String(dataUrl || "");
  const marker = "data:image/png;base64,";
  if (!raw.startsWith(marker)) {
    return { ok: false, error: "Screenshot must be a PNG data URL." };
  }
  const requestedMaximum = Number(options?.maxBytes);
  const maxBytes = Number.isSafeInteger(requestedMaximum) && requestedMaximum > 0
    ? Math.min(requestedMaximum, MAX_BROWSER_CAPTURE_SCREENSHOT_BYTES)
    : MAX_BROWSER_CAPTURE_SCREENSHOT_BYTES;
  if (estimatedBase64Bytes(raw.slice(marker.length)) > maxBytes) {
    return captureSizeError("Screenshot", maxBytes, "bytes");
  }
  return { ok: true, error: "" };
}

function clampPriority(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return DEFAULT_PRIORITY;
  }
  return Math.min(PRIORITY_MAX, Math.max(PRIORITY_MIN, Number(numeric.toFixed(4))));
}

export function parseTags(rawValue) {
  return Array.from(
    new Set(
      String(rawValue || "")
        .replaceAll(",", " ")
        .split(/\s+/)
        .map((tag) => tag.trim())
        .filter(Boolean)
    )
  );
}

export function normalizeFieldMappings(rawMappings, fields) {
  const fieldNames = Array.isArray(fields) ? fields.filter(Boolean) : [];
  const firstField = fieldNames[0] || "";
  const pick = (value) => {
    if (value === "") {
      return "";
    }
    if (fieldNames.includes(value)) {
      return value;
    }
    return firstField;
  };
  return {
    titleField: pick(String(rawMappings?.titleField || "")),
    selectedTextField: pick(String(rawMappings?.selectedTextField || "")),
    urlField: pick(String(rawMappings?.urlField || "")),
    snapshotField: pick(String(rawMappings?.snapshotField || "")),
  };
}

export function normalizeBrowserCaptureSettings(rawSettings, meta) {
  const noteTypes = Array.isArray(meta?.noteTypes) ? meta.noteTypes : [];
  const deckNames = Array.isArray(meta?.deckNames) ? meta.deckNames.filter(Boolean) : [];
  const preferredNoteType = String(rawSettings?.noteTypeName || "");
  const noteType = noteTypes.find((item) => item?.name === preferredNoteType) || noteTypes[0] || null;
  const noteTypeName = noteType?.name || "";
  const fields = Array.isArray(noteType?.fields) ? noteType.fields : [];
  const mappingsByNoteType = rawSettings?.mappingsByNoteType && typeof rawSettings.mappingsByNoteType === "object"
    ? rawSettings.mappingsByNoteType
    : {};
  const fieldMappings = normalizeFieldMappings(mappingsByNoteType[noteTypeName], fields);

  const preferredDeck = String(rawSettings?.deckName || "");
  const deckName = deckNames.includes(preferredDeck)
    ? preferredDeck
    : (deckNames[0] || "Default");

  return {
    noteTypeName,
    deckName,
    priority: clampPriority(rawSettings?.priority),
    tagsText: String(rawSettings?.tagsText || ""),
    fieldMappings,
    mappingsByNoteType,
  };
}

export function updateMappingsForNoteType(settings, noteTypeName, fieldMappings) {
  return {
    ...settings,
    noteTypeName,
    fieldMappings: { ...fieldMappings },
    mappingsByNoteType: {
      ...(settings?.mappingsByNoteType || {}),
      [noteTypeName]: { ...fieldMappings },
    },
  };
}

export function normalizeBrowserCaptureSelectedText(mode, selectedText, fallbackSelectedText = "") {
  if (String(mode || "").trim().toLowerCase() === "snapshot") {
    return String(selectedText || "").trim();
  }
  return String(selectedText || fallbackSelectedText || "").trim();
}

export function buildBrowserCapturePayload(context, formState) {
  return {
    url: String(context?.url || "").trim(),
    title: String(context?.title || "").trim() || String(context?.url || "").trim() || "Untitled",
    selectedText: String(context?.selectedText || "").trim(),
    noteTypeName: String(formState?.noteTypeName || "").trim(),
    deckName: String(formState?.deckName || "").trim(),
    tags: parseTags(formState?.tagsText),
    priority: clampPriority(formState?.priority),
    fieldMappings: {
      titleField: String(formState?.fieldMappings?.titleField || "").trim(),
      selectedTextField: String(formState?.fieldMappings?.selectedTextField || "").trim(),
      urlField: String(formState?.fieldMappings?.urlField || "").trim(),
      snapshotField: String(formState?.fieldMappings?.snapshotField || "").trim(),
    },
    snapshots: Array.isArray(context?.snapshots)
      ? context.snapshots.map((snapshot, index) => ({
        mimeType: "image/png",
        filename: String(snapshot?.filename || `browser-capture-${index + 1}.png`),
        base64: String(snapshot?.base64 || "").trim(),
      })).filter((snapshot) => snapshot.base64)
      : [],
  };
}

export function validateBrowserCapturePayload(payload) {
  if (!String(payload?.noteTypeName || "").trim() || !String(payload?.deckName || "").trim()) {
    return { ok: false, error: "Choose a note type and deck." };
  }
  const hasMappedContent = Boolean(
    payload?.fieldMappings?.titleField
    || (payload?.selectedText && payload?.fieldMappings?.selectedTextField)
    || payload?.fieldMappings?.urlField
    || ((payload?.snapshots?.length || 0) > 0 && payload?.fieldMappings?.snapshotField)
  );
  if (!hasMappedContent) {
    return { ok: false, error: "Map at least one available capture part to a note field." };
  }
  if (String(payload?.selectedText || "").length > MAX_BROWSER_CAPTURE_SELECTED_TEXT_CHARS) {
    return captureSizeError(
      "Selected text",
      MAX_BROWSER_CAPTURE_SELECTED_TEXT_CHARS,
      "characters"
    );
  }
  const snapshots = Array.isArray(payload?.snapshots) ? payload.snapshots : [];
  if (snapshots.length > MAX_BROWSER_CAPTURE_SNAPSHOTS) {
    return {
      ok: false,
      error: `Too many snapshots. Maximum is ${MAX_BROWSER_CAPTURE_SNAPSHOTS}.`,
    };
  }
  let totalImageBytes = 0;
  for (const snapshot of snapshots) {
    const imageBytes = estimatedBase64Bytes(snapshot?.base64);
    if (imageBytes > MAX_BROWSER_CAPTURE_IMAGE_BYTES) {
      return captureSizeError(
        "A snapshot",
        MAX_BROWSER_CAPTURE_IMAGE_BYTES,
        "bytes"
      );
    }
    totalImageBytes += imageBytes;
    if (totalImageBytes > MAX_BROWSER_CAPTURE_TOTAL_IMAGE_BYTES) {
      return captureSizeError(
        "Combined snapshots",
        MAX_BROWSER_CAPTURE_TOTAL_IMAGE_BYTES,
        "bytes"
      );
    }
  }
  return { ok: true, error: "" };
}
