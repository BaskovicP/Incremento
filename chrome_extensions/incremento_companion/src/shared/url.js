export function isHttpUrl(url) {
  return /^https?:\/\//i.test(String(url || ""));
}

export function supportedVideoIdentity(url) {
  try {
    const parsed = new URL(String(url || ""));
    const host = String(parsed.hostname || "").toLowerCase();
    if (host === "youtu.be" || host.endsWith(".youtu.be")) {
      const videoId = parsed.pathname.split("/").filter(Boolean)[0] || "";
      return videoId ? `youtube:${videoId}` : "";
    }
    if (host === "youtube.com" || host.endsWith(".youtube.com")) {
      const queryVideoId = parsed.searchParams.get("v") || "";
      if (queryVideoId) {
        return `youtube:${queryVideoId}`;
      }
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (["embed", "shorts", "live"].includes(parts[0]) && parts[1]) {
        return `youtube:${parts[1]}`;
      }
      return "";
    }
    if (host === "vimeo.com" || host.endsWith(".vimeo.com")) {
      const match = String(parsed.pathname || "").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);
      return match?.[1] ? `vimeo:${match[1]}` : "";
    }
  } catch (_err) {
    return "";
  }
  return "";
}

export function isSupportedVideoUrl(url) {
  return Boolean(supportedVideoIdentity(url));
}

export function classifyLinkImportKind(url) {
  if (!isHttpUrl(url)) {
    return "";
  }
  return isSupportedVideoUrl(url) ? "video" : "webpage";
}

export function resolveLinkedVideoCardId(currentUrl, linkedContext) {
  const cardId = Math.max(0, Math.floor(Number(linkedContext?.cardId) || 0));
  if (cardId <= 0) {
    return 0;
  }
  const currentIdentity = supportedVideoIdentity(currentUrl);
  const sourceIdentity = supportedVideoIdentity(linkedContext?.sourceUrl);
  return currentIdentity && currentIdentity === sourceIdentity ? cardId : 0;
}

export function isPdfUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return String(parsed.pathname || "").toLowerCase().endsWith(".pdf");
  } catch (_err) {
    return false;
  }
}
