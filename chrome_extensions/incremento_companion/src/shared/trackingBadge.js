// A language change may relabel a badge only after tracking status displayed it.
export function refreshTrackingBadgeLanguage(badge, refresh) {
  if (!badge || badge.style?.display === "none") {
    return false;
  }
  refresh();
  return true;
}
