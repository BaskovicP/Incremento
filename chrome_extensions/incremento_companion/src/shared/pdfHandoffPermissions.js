import { extensionApi as chrome } from "./extensionApi.js";

export async function readPdfHandoffInfo(ticket, api = chrome) {
  const tab = await api.tabs.getCurrent();
  if (!Number.isInteger(tab?.id)) throw new Error("handoff_expired");
  const result = await api.runtime.sendMessage({type: "PDF_HANDOFF_INFO", ticket, tabId: tab.id});
  if (!result?.ok) throw new Error("handoff_expired");
  return {...result, tabId: tab.id};
}

export async function allowPdfHandoff(ticket, info, api = chrome) {
  // Called directly by the button: the browser requires a user gesture here.
  const permission = api.permissions.request({origins: info.origins});
  if (!await permission) throw new Error("handoff_capture_failed");
  const result = await api.runtime.sendMessage({type: "PDF_HANDOFF_BEGIN", ticket, tabId: info.tabId});
  if (!result?.ok) throw new Error("handoff_expired");
}
