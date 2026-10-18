function captureError(code) {
  const error = new Error(code);
  error.code = code;
  return error;
}

export async function captureSnapshotForSender(api, sender) {
  const tabId = sender?.tab?.id;
  const windowId = sender?.tab?.windowId;
  if (!Number.isInteger(tabId) || tabId < 0 || !Number.isInteger(windowId) || windowId < 0) {
    throw captureError("snapshot_tab_changed");
  }
  const requireActiveSender = async () => {
    const tabs = await api.tabs.query({active: true, windowId});
    if (tabs.length !== 1 || tabs[0].id !== tabId) throw captureError("snapshot_tab_changed");
  };
  await requireActiveSender();
  let dataUrl;
  try {
    dataUrl = await api.tabs.captureVisibleTab(windowId, {format: "png"});
  } catch (error) {
    if (/activeTab|<all_urls>/i.test(String(error?.message || ""))) {
      throw captureError("snapshot_permission_required");
    }
    throw error;
  }
  await requireActiveSender();
  return dataUrl;
}

// A page keydown is not a Chrome extension invocation and cannot grant
// activeTab. Only the actual commands API handler may start keyboard capture.
export async function snapshotPageShortcutFallback(request, showHint) {
  const response = await request({type: "SNAPSHOT_SHORTCUT_HELP"});
  if (response?.message) showHint(response.message, {action: "open_shortcut_settings"});
}
