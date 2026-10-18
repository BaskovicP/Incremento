const escape = value => String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

// Fields come from the authenticated backend's allowlisted capture renderer.
// The caller also uses an empty iframe sandbox; this document cannot run scripts.
export function capturePreviewDocument(fields) {
  return '<!doctype html><html><head><meta charset="utf-8">'
    + '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
    + '<style>body{font:15px/1.5 system-ui,sans-serif;color:#29251f;background:#fffdf8;padding:12px;overflow-wrap:anywhere}h3{font-size:12px;color:#655744;border-bottom:1px solid #ddd;padding-bottom:6px}section{margin-bottom:24px}img{max-width:100%}pre{white-space:pre-wrap}a{color:#805010}</style></head><body>'
    + Object.entries(fields || {}).map(([name, html]) => `<section><h3>${escape(name)}</h3>${html}</section>`).join("")
    + '</body></html>';
}

export function captureResultKind(result) {
  if (!result?.ok) return "error";
  if (result.opened) return "opened";
  if (result.preview) return "preview";
  if (result.duplicate) return "duplicate";
  return result.type === "browser_capture" && result.noteId ? "created" : "error";
}
