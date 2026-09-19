export function pageContextOptionsForImport(kind, options = {}) {
  const writingMode = String(options?.writingMode || "selection").toLowerCase();
  const needsPageMarkdown = kind === "writing" && writingMode === "webpage_markdown";
  return {
    includeHtml: kind === "pdf" || needsPageMarkdown,
    htmlScope: needsPageMarkdown && String(options?.pageContentScope || "main").toLowerCase() === "main"
      ? "main"
      : "full",
  };
}

// Chrome serializes this function into the page. Keep it free of imports and
// closure references; translate its stable error codes after it returns.
export function readPageContextFromTab(maxHtmlChars, maxSelectedTextChars, options = {}) {
  const includeHtml = options?.includeHtml !== false;
  const htmlScope = String(options?.htmlScope || "full").toLowerCase() === "main"
    ? "main"
    : "full";
  const selectionText = (
    (window.getSelection?.().toString() || "").trim()
    || String(globalThis.__incrementoLastSelectedText || "").trim()
  );

  let html = "";
  if (includeHtml) {
    let sourceRoot = document.documentElement || null;
    if (htmlScope === "main") {
      const candidates = Array.from(
        document.querySelectorAll?.("main, article, [role='main']") || []
      );
      sourceRoot = candidates.reduce((best, candidate) => {
        const bestLength = String(best?.textContent || "").trim().length;
        const candidateLength = String(candidate?.textContent || "").trim().length;
        return candidateLength > bestLength ? candidate : best;
      }, null) || document.body || sourceRoot;
    }

    const clonedRoot = sourceRoot?.cloneNode?.(true) || null;
    if (clonedRoot) {
      const ignoredSelectors = [
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
      ];
      if (htmlScope === "main") {
        ignoredSelectors.push("aside", "footer", "form", "header", "nav", "[hidden]", "[aria-hidden='true']");
      }
      for (const node of Array.from(clonedRoot.querySelectorAll?.(ignoredSelectors.join(", ")) || [])) {
        node.remove?.();
      }
      html = clonedRoot.outerHTML || "";
    } else {
      html = sourceRoot?.outerHTML || "";
    }
  }

  if (html.length > maxHtmlChars) {
    return {
      ok: false,
      errorCode: "page_html_too_large",
      errorParams: { count: maxHtmlChars, actual: html.length, scope: htmlScope },
    };
  }
  if (selectionText.length > maxSelectedTextChars) {
    return {
      ok: false,
      errorCode: "selected_text_too_large",
      errorParams: { count: maxSelectedTextChars, actual: selectionText.length },
    };
  }
  return {
    ok: true,
    html,
    selectionText,
    title: document.title || "",
    url: window.location.href || "",
  };
}
