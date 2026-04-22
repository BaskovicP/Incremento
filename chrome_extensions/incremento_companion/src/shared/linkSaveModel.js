export const LINK_SAVE_SETTINGS_KEY = "incremento_link_save_settings";

export const MODIFIER_OPTIONS = [
  { value: "alt", label: "Alt" },
  { value: "shift", label: "Shift" },
  { value: "ctrl", label: "Ctrl" },
  { value: "meta", label: "Meta / Cmd" },
];

export const DEFAULT_LINK_SAVE_SETTINGS = {
  modifierClickEnabled: true,
  modifierKey: "alt",
  navigateAfterSave: true,
  contextMenuEnabled: true,
};

function collapseWhitespace(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

export function isSupportedLinkSaveUrl(rawUrl) {
  return /^https?:\/\//i.test(String(rawUrl || "").trim());
}

export function normalizeLinkSaveSettings(rawSettings) {
  const raw = rawSettings && typeof rawSettings === "object" ? rawSettings : {};
  const modifierKey = MODIFIER_OPTIONS.some((option) => option.value === raw.modifierKey)
    ? raw.modifierKey
    : DEFAULT_LINK_SAVE_SETTINGS.modifierKey;
  return {
    modifierClickEnabled: raw.modifierClickEnabled === undefined
      ? DEFAULT_LINK_SAVE_SETTINGS.modifierClickEnabled
      : Boolean(raw.modifierClickEnabled),
    modifierKey,
    navigateAfterSave: raw.navigateAfterSave !== false,
    contextMenuEnabled: raw.contextMenuEnabled !== false,
  };
}

export function eventMatchesLinkSaveModifier(event, settings) {
  const normalized = normalizeLinkSaveSettings(settings);
  const expected = normalized.modifierKey;
  const state = {
    alt: Boolean(event?.altKey),
    shift: Boolean(event?.shiftKey),
    ctrl: Boolean(event?.ctrlKey),
    meta: Boolean(event?.metaKey),
  };
  if (!state[expected]) {
    return false;
  }
  return Object.entries(state).every(([key, active]) => key === expected || !active);
}

function decodeUrlSegment(value) {
  try {
    return decodeURIComponent(String(value || ""));
  } catch (_error) {
    return String(value || "");
  }
}

export function buildLinkSaveFallbackTitle(rawUrl) {
  const url = String(rawUrl || "").trim();
  if (!url) {
    return "Saved link";
  }
  try {
    const parsed = new URL(url);
    const host = String(parsed.hostname || "").replace(/^www\./i, "");
    const segments = parsed.pathname
      .split("/")
      .map((segment) => decodeUrlSegment(segment).trim())
      .filter(Boolean);
    const tail = collapseWhitespace(segments[segments.length - 1] || "");
    if (tail) {
      return collapseWhitespace(`${host} / ${tail}`) || host || "Saved link";
    }
    return host || "Saved link";
  } catch (_error) {
    return collapseWhitespace(url) || "Saved link";
  }
}

export function buildLinkSaveTitle(rawLinkText, rawUrl) {
  const linkText = collapseWhitespace(rawLinkText);
  if (linkText) {
    return linkText.slice(0, 240);
  }
  return buildLinkSaveFallbackTitle(rawUrl).slice(0, 240);
}
