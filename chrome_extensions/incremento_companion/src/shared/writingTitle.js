function collapseWhitespace(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function resolveEpochMicros(now = new Date(), epochMicros = null) {
  const explicitMicros = Number(epochMicros);
  if (Number.isFinite(explicitMicros) && explicitMicros > 0) {
    return Math.floor(explicitMicros);
  }
  const perf = globalThis.performance;
  if (perf && Number.isFinite(perf.timeOrigin) && typeof perf.now === "function") {
    const highResMicros = Math.floor((perf.timeOrigin + perf.now()) * 1000);
    if (Number.isSafeInteger(highResMicros) && highResMicros > 0) {
      return highResMicros;
    }
  }
  return now.getTime() * 1000;
}

function formatTitleTimestamp(now = new Date(), epochMicros = null) {
  const year = String(now.getFullYear()).padStart(4, "0");
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  const seconds = String(now.getSeconds()).padStart(2, "0");
  const micros = String(resolveEpochMicros(now, epochMicros) % 1_000_000).padStart(6, "0");
  return `${year}${month}${day}-${hours}${minutes}${seconds}-${micros}`;
}

function truncateSegment(value, maxLength = 48) {
  const clean = collapseWhitespace(value);
  if (!clean || clean.length <= maxLength) {
    return clean;
  }
  return `${clean.slice(0, Math.max(1, maxLength - 1)).trimEnd()}…`;
}

function buildSlug(value, maxLength = 80) {
  const slug = collapseWhitespace(value)
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "");
  if (!slug) {
    return "writing-note";
  }
  const trimmed = slug.slice(0, maxLength).replace(/^[-._]+|[-._]+$/g, "");
  return trimmed || "writing-note";
}

export function shouldAutoGenerateWritingTitle(inputTitle, pageTitle, pageUrl) {
  const cleanInput = collapseWhitespace(inputTitle);
  const cleanPageTitle = collapseWhitespace(pageTitle);
  const cleanPageUrl = collapseWhitespace(pageUrl);
  if (!cleanInput) {
    return true;
  }
  return cleanInput === cleanPageTitle || cleanInput === cleanPageUrl;
}

export function buildAutomaticWritingTitle(
  pageTitle,
  pageUrl,
  writingMode,
  selectionText = "",
  now = new Date(),
  epochMicros = null
) {
  const baseTitle = collapseWhitespace(pageTitle) || collapseWhitespace(pageUrl) || "Untitled";
  const stamp = formatTitleTimestamp(now, epochMicros);
  if (String(writingMode || "selection") === "selection") {
    const excerpt = truncateSegment(selectionText, 40);
    if (excerpt) {
      return `${baseTitle} - ${excerpt} [${stamp}]`;
    }
  }
  return `${baseTitle} [${stamp}]`;
}


export function buildPreferredWritingFilename(title, url) {
  const base = buildSlug(title || url || "writing-note");
  return `${base}.md`;
}
