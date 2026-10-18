import { t } from "../shared/i18n.js";

const TOAST_ID = "incremento-video-time-toast";

export function dismissPageToast(doc = globalThis.document) {
  doc.getElementById(TOAST_ID)?.remove();
}

export function showPageToast(text, {
  action = "", request,
  document: doc = globalThis.document,
  requestFrame = globalThis.requestAnimationFrame,
  schedule = globalThis.setTimeout,
} = {}) {
  dismissPageToast(doc);
  const actionable = action === "open_shortcut_settings";
  const toast = doc.createElement("div");
  toast.id = TOAST_ID;
  toast.textContent = String(text || "");
  toast.setAttribute("role", actionable ? "alert" : "status");
  Object.assign(toast.style, {
    position: "fixed", zIndex: 2147483647, top: "10px", right: "10px",
    maxWidth: actionable ? "360px" : "320px", padding: "10px 14px",
    background: "rgba(0, 0, 0, 0.86)", color: "#fff", fontSize: "13px",
    fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    borderRadius: "6px", boxShadow: "0 2px 8px rgba(0, 0, 0, 0.4)",
    opacity: "0", transition: "opacity 0.2s ease", lineHeight: "1.5",
  });

  if (actionable) {
    const actions = doc.createElement("div");
    Object.assign(actions.style, {display: "flex", flexWrap: "wrap", gap: "8px", marginTop: "10px"});
    const button = label => {
      const element = doc.createElement("button");
      element.type = "button";
      element.textContent = label;
      Object.assign(element.style, {
        padding: "6px 10px", border: "1px solid #a7b1c2", borderRadius: "4px",
        background: "#fff", color: "#172033", font: "inherit", cursor: "pointer",
      });
      actions.appendChild(element);
      return element;
    };
    const open = button(t("open_shortcut_settings"));
    const dismiss = button(t("snapshot_warning_dismiss"));
    const error = doc.createElement("div");
    error.setAttribute("role", "status");
    error.hidden = true;
    error.style.marginTop = "8px";
    open.addEventListener("click", async event => {
      event.stopPropagation();
      if (!event.isTrusted || open.disabled) return;
      open.disabled = true;
      error.hidden = true;
      try {
        const response = await request({type: "OPEN_SHORTCUT_SETTINGS"});
        if (response?.ok) {
          toast.remove();
          return;
        }
      } catch (_error) { /* keep the warning and allow another attempt */ }
      open.disabled = false;
      error.textContent = t("open_shortcuts_failed");
      error.hidden = false;
    });
    dismiss.addEventListener("click", event => {
      event.stopPropagation();
      toast.remove();
    });
    toast.appendChild(actions);
    toast.appendChild(error);
  }

  doc.documentElement.appendChild(toast);
  requestFrame(() => {toast.style.opacity = "1";});
  // A warning with buttons must remain available for reading and keyboard use.
  if (!actionable) {
    schedule(() => {
      toast.style.opacity = "0";
      schedule(() => toast.remove(), 220);
    }, 2400);
  }
  return toast;
}
