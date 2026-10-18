const allowed = new Set("p div br strong b em i u s ul ol li blockquote pre code h1 h2 h3 h4 h5 h6 sub sup".split(" "));
const discard = new Set("script style template noscript iframe object embed svg math nav header footer aside form button select textarea input".split(" "));
const escape = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

export function readCaptureSelection(selection) {
  const selectedText = String(selection?.toString() || "").trim();
  if (selectedText.length > 200_000) throw new Error("Selected text is too large.");
  if (!selectedText || !selection?.rangeCount) return {selectedText, selectedHtml: ""};
  let nodes = 0;
  let size = 0;
  const serialize = (node, depth = 0) => {
    if (++nodes > 40_000 || depth > 64) throw new Error("Selected HTML is too large or deeply nested.");
    if (node.nodeType === 3) {
      const result = escape(node.textContent || "");
      size += result.length;
      if (size > 200_000) throw new Error("Selected HTML is too large.");
      return result;
    }
    const name = String(node.localName || "").toLowerCase();
    if (discard.has(name)) return "";
    const children = Array.from(node.childNodes || []).map(child => serialize(child, depth + 1)).join("");
    const result = allowed.has(name) ? (name === "br" ? "<br>" : `<${name}>${children}</${name}>`) : children;
    if (result.length > 200_000) throw new Error("Selected HTML is too large.");
    return result;
  };
  try {
    const selectedHtml = serialize(selection.getRangeAt(0).cloneContents());
    return {selectedText, selectedHtml};
  } catch (error) {
    if (error instanceof RangeError || /too large|deeply nested/.test(error.message)) throw error;
    return {selectedText, selectedHtml: ""};
  }
}
