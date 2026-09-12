export const MAX_TAG_SUGGESTIONS = 8;

function tagKey(value) {
  return String(value || "").trim().toLowerCase();
}

function compareTags(left, right) {
  const leftKey = tagKey(left);
  const rightKey = tagKey(right);
  if (leftKey !== rightKey) {
    return leftKey < rightKey ? -1 : 1;
  }
  const leftValue = String(left);
  const rightValue = String(right);
  return leftValue === rightValue ? 0 : (leftValue < rightValue ? -1 : 1);
}

function tokenRange(rawValue, selectionStart, selectionEnd = selectionStart) {
  const value = String(rawValue || "");
  const lower = Math.max(0, Math.min(value.length, Number(selectionStart) || 0));
  const upper = Math.max(lower, Math.min(value.length, Number(selectionEnd) || lower));
  let start = lower;
  let end = upper;
  while (start > 0 && !/[\s,]/.test(value[start - 1])) {
    start -= 1;
  }
  while (end < value.length && !/[\s,]/.test(value[end])) {
    end += 1;
  }
  return { start, end };
}

export function normalizeAvailableTags(rawTags) {
  const byKey = new Map();
  for (const rawTag of Array.isArray(rawTags) ? rawTags : []) {
    const tag = String(rawTag || "").trim();
    const key = tagKey(tag);
    if (tag && key && !byKey.has(key)) {
      byKey.set(key, tag);
    }
  }
  return Array.from(byKey.values()).sort(compareTags);
}

export function getTagSuggestions(
  availableTags,
  rawValue,
  cursorPosition,
  limit = MAX_TAG_SUGGESTIONS
) {
  const value = String(rawValue || "");
  const cursor = Math.max(0, Math.min(value.length, Number(cursorPosition) || 0));
  const { start, end } = tokenRange(value, cursor, cursor);
  const query = tagKey(value.slice(start, end));
  const chosenKeys = new Set(
    `${value.slice(0, start)} ${value.slice(end)}`
      .replaceAll(",", " ")
      .split(/\s+/)
      .map(tagKey)
      .filter(Boolean)
  );
  const safeLimit = Math.max(0, Math.min(50, Number(limit) || 0));
  return normalizeAvailableTags(availableTags)
    .filter((tag) => {
      const key = tagKey(tag);
      return !chosenKeys.has(key) && (!query || key.includes(query));
    })
    .sort((left, right) => {
      const leftKey = tagKey(left);
      const rightKey = tagKey(right);
      const leftPrefix = query && leftKey.startsWith(query) ? 0 : 1;
      const rightPrefix = query && rightKey.startsWith(query) ? 0 : 1;
      return leftPrefix - rightPrefix
        || (query ? left.length - right.length : 0)
        || compareTags(left, right);
    })
    .slice(0, safeLimit);
}

export function applyTagSuggestion(rawValue, suggestion, selectionStart, selectionEnd) {
  const value = String(rawValue || "");
  const cleanSuggestion = String(suggestion || "").trim();
  const { start, end } = tokenRange(value, selectionStart, selectionEnd);
  const left = value.slice(0, start);
  const right = value.slice(end);
  const separator = right && /^[\s,]/.test(right) ? "" : " ";
  const nextValue = `${left}${cleanSuggestion}${separator}${right}`;
  return {
    value: nextValue,
    cursor: left.length + cleanSuggestion.length + separator.length,
  };
}
