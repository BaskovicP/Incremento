export function pageWindow(length, offset = 0, size = 50) {
  const pageSize = Math.max(1, Math.floor(size));
  const count = Math.max(0, Math.floor(length));
  const last = Math.max(0, Math.floor((count - 1) / pageSize) * pageSize);
  const start = Math.min(last, Math.max(0, Math.floor(offset / pageSize) * pageSize));
  return {start, end: Math.min(count, start + pageSize), previous: Math.max(0, start - pageSize),
    next: Math.min(last, start + pageSize), count};
}
