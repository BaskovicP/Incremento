// Chrome keeps its existing API objects. Firefox uses browser.* for promises,
// while callback callers retain chrome.* and its callback-scoped lastError.
export function createExtensionApi(getChrome = () => globalThis.chrome, getBrowser = () => globalThis.browser) {
  const at = (root, path) => path.reduce((value, key) => value?.[key], root);
  const proxy = path => new Proxy({}, {
    get(_target, key) {
      const legacy = at(getChrome(), path);
      const browser = getBrowser();
      const modern = isFirefox(browser || null) ? at(browser, path) : undefined;
      if (!modern || key === "lastError") return legacy?.[key];
      const value = modern[key] ?? legacy?.[key];
      if (value && typeof value === "object") {
        // Events are synchronous; listener identity and response callbacks stay intact.
        if (typeof value.addListener === "function") return legacy?.[key] ?? value;
        return proxy([...path, key]);
      }
      if (typeof value !== "function") return value;
      return (...args) => {
        const owner = (typeof args.at(-1) === "function" && legacy?.[key]) || !modern[key] ? legacy : modern;
        return (owner?.[key] ?? legacy?.[key]).apply(owner, args);
      };
    },
  });
  return proxy([]);
}

export const extensionApi = createExtensionApi();

export function isFirefox(api = extensionApi) {
  return typeof api?.runtime?.getBrowserInfo === "function"
    || String(api?.runtime?.getURL?.("") || "").startsWith("moz-extension://");
}
