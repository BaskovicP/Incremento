export const BROWSER_CAPTURE_SETTINGS_KEY = "incremento_browser_capture_settings";
export const DEFAULT_PRIORITY = 50;
export const PRIORITY_MIN = 0;
export const PRIORITY_MAX = 100;
export const PRIORITY_STEP = 0.1;

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
