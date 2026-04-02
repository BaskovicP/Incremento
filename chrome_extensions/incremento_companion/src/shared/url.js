export function isHttpUrl(url) {
  return /^https?:\/\//i.test(String(url || ""));
}

export function isSupportedVideoUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    const host = String(parsed.hostname || "").toLowerCase();
    if (host === "youtu.be" || host.endsWith(".youtu.be")) {
      return Boolean(parsed.pathname.split("/").filter(Boolean)[0]);
    }
    if (host === "youtube.com" || host.endsWith(".youtube.com")) {
      if (parsed.searchParams.get("v")) {
        return true;
      }
      const parts = parsed.pathname.split("/").filter(Boolean);
      return ["embed", "shorts", "live"].includes(parts[0]) && Boolean(parts[1]);
    }
    if (host === "vimeo.com" || host.endsWith(".vimeo.com")) {
      return /(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/.test(parsed.pathname);
    }
  } catch (_err) {
    return false;
  }
  return false;
}

export function isPdfUrl(url) {
  try {
    const parsed = new URL(String(url || ""));
    return String(parsed.pathname || "").toLowerCase().endsWith(".pdf");
  } catch (_err) {
    return false;
  }
}
