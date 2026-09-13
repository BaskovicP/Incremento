// Chrome serializes this function into the page. Keep it free of imports and
// closure references; translate its stable error codes after it returns.
export function readPageContextFromTab(maxHtmlChars, maxSelectedTextChars) {
  const html = document.documentElement?.outerHTML || "";
  const selectionText = (
    (window.getSelection?.().toString() || "").trim()
    || String(globalThis.__incrementoLastSelectedText || "").trim()
  );
  if (html.length > maxHtmlChars) {
    return { ok: false, errorCode: "page_html_too_large", errorParams: { count: maxHtmlChars } };
  }
  if (selectionText.length > maxSelectedTextChars) {
    return { ok: false, errorCode: "selected_text_too_large", errorParams: { count: maxSelectedTextChars } };
  }
  return {
    ok: true,
    html,
    selectionText,
    title: document.title || "",
    url: window.location.href || "",
  };
}
