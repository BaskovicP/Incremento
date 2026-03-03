"""
This module defines the main functionality for the Incremental Learning Anki addon.
It includes the AddonManager class for managing addon-specific data and the learnFunction
for initiating the learning process.
"""

import json
import os
from aqt import mw
from aqt.utils import showInfo
from aqt.qt import *
from aqt import gui_hooks
from aqt.webview import WebContent
from aqt.reviewer import Reviewer
from aqt.browser.previewer import BrowserPreviewer
from aqt.clayout import CardLayout

from .utils.statistics import load_stats, save_stats
from .utils.cards import add_topic_type_to_custom_data


class AddonManager:
    def __init__(self):
        self.addon_dir = os.path.dirname(__file__)
        self.stats = None

    def get_stats(self):
        if self.stats is None:
            self.stats = load_stats(self.addon_dir)
        return self.stats


addon_manager = AddonManager()


def setup_web_exports():
    """Register PDF.js files as web exports so they can be loaded via /_addons/ URL."""
    addon_name = os.path.basename(os.path.dirname(__file__))
    mw.addonManager.setWebExports(__name__, r"user_files/pdfjs/.*(js)")


def inject_pdf_js(web_content: WebContent, context):
    """Inject PDF.js into card reviewer, browser previewer, and card layout."""
    if not isinstance(context, (Reviewer, BrowserPreviewer, CardLayout)):
        return

    addon_name = os.path.basename(os.path.dirname(__file__))
    # Use traditional script tag for UMD build of PDF.js
    # PDF.js 3.x exposes pdfjsLib as a global variable
    import_script = f"""
<script src="/_addons/{addon_name}/user_files/pdfjs/pdf.min.js"></script>
<script>
  console.log("[Incremento] PDF.js script loaded via traditional tag");
  if (typeof pdfjsLib !== 'undefined') {{
    console.log("[Incremento] pdfjsLib is available");
    pdfjsLib.GlobalWorkerOptions.workerSrc = '/_addons/{addon_name}/user_files/pdfjs/pdf.worker.min.js';
    console.log("[Incremento] Worker configured:", pdfjsLib.GlobalWorkerOptions.workerSrc);
  }} else {{
    console.error("[Incremento] pdfjsLib not available after script load!");
  }}
</script>
"""
    # Prepend the import script to the head
    web_content.head = import_script + web_content.head


PDF_MODEL_NAME = "PDF"
PDF_FIELDS = ["PdfFile", "PdfPage", "PdfZoom"]
PDF_MEDIA_FILES = {
    "pdf.min.js": "_incremento_pdf.min.js",
    "pdf.worker.min.js": "_incremento_pdf.worker.min.js",
}

PDF_FRONT_TEMPLATE = r"""
{{#PdfFile}}
<div id="pdf-wrapper">
  <div id="pdf-controls">
    <button class="pdf-btn" onclick="prevPage()">Prev</button>
    <button class="pdf-btn" onclick="nextPage()">Next</button>
    <button class="pdf-btn" onclick="zoomOut()">-</button>
    <button class="pdf-btn" onclick="zoomIn()">+</button>
    <span id="page-label"></span>
  </div>
  <div id="pdf-status"></div>
  <canvas id="pdf-canvas"></canvas>
</div>

<script>
  (function () {
    const statusEl = document.getElementById("pdf-status");
    const labelEl = document.getElementById("page-label");
    const canvas = document.getElementById("pdf-canvas");

    const pdfFile = "{{PdfFile}}";
    let pageNum = parseInt("{{PdfPage}}", 10);
    if (!pageNum || pageNum < 1) pageNum = 1;
    let zoom = parseFloat("{{PdfZoom}}");
    console.log("[Incremento] Initial zoom value from card:", "{{PdfZoom}}", "parsed as:", zoom);
    if (!zoom || zoom < 0.5) zoom = 1.0;
    console.log("[Incremento] Final initial zoom:", zoom);

    function setStatus(text) {
      statusEl.textContent = text || "";
    }

    function persistState() {
      if (typeof pycmd === "function") {
        pycmd(`incremento_pdf_state:${pageNum}:${zoom}`);
      }
    }

    function renderPage(num) {
      console.log("[Incremento] Rendering page", num, "with zoom:", zoom);
      window.pdfDoc.getPage(num).then(function (page) {
        console.log("[Incremento] Got page, applying zoom:", zoom);
        const viewport = page.getViewport({ scale: zoom });
        console.log("[Incremento] Viewport size:", viewport.width, "x", viewport.height);
        const ctx = canvas.getContext("2d");
        canvas.height = viewport.height;
        canvas.width = viewport.width;
        return page.render({ canvasContext: ctx, viewport: viewport }).promise;
      }).then(function () {
        labelEl.textContent = pageNum + "/" + window.pdfDoc.numPages;
        persistState();
      }).catch(function (err) {
        setStatus("Failed to render PDF page.");
        console.error(err);
      });
    }

    window.prevPage = function () {
      if (!window.pdfDoc || pageNum <= 1) return;
      pageNum -= 1;
      renderPage(pageNum);
    };

    window.nextPage = function () {
      if (!window.pdfDoc || pageNum >= window.pdfDoc.numPages) return;
      pageNum += 1;
      renderPage(pageNum);
    };

    window.zoomIn = function () {
      if (!window.pdfDoc) return;
      zoom = Math.min(zoom + 0.1, 4.0);
      console.log("[Incremento] Zooming in to:", zoom);
      renderPage(pageNum);
    };

    window.zoomOut = function () {
      if (!window.pdfDoc) return;
      zoom = Math.max(zoom - 0.1, 0.5);
      console.log("[Incremento] Zooming out to:", zoom);
      renderPage(pageNum);
    };

    // Wait for pdfjsLib to be available (injected by Anki)
    function waitForPdfJs(retryCount) {
      retryCount = retryCount || 0;
      if (retryCount > 50) {  // Wait up to 5 seconds
        setStatus("pdf.js not found after 5s. Check console for errors.");
        console.error("[Incremento] pdfjsLib not available after 50 retries");
        return;
      }
      
      console.log("[Incremento] Checking for pdfjsLib, attempt", retryCount);
      if (typeof pdfjsLib !== 'undefined') {
        console.log("[Incremento] pdfjsLib found, loading PDF from:", pdfFile);
        setStatus("Loading PDF...");
        
        // Build the correct URL for the PDF file
        // Anki serves media files at the root of the media server
        var pdfUrl;
        if (pdfFile.startsWith('http')) {
          pdfUrl = pdfFile;
        } else {
          // Get the base URL (origin + port, but remove any path like /_anki/)
          var baseUrl = window.location.protocol + '//' + window.location.host;
          pdfUrl = baseUrl + '/' + pdfFile;
        }
        console.log("[Incremento] Full PDF URL:", pdfUrl);
        
        // Worker is already configured by the injected script
        pdfjsLib.getDocument(pdfUrl).promise.then(function(doc) {
          console.log("[Incremento] PDF loaded successfully, pages:", doc.numPages);
          window.pdfDoc = doc;
          if (pageNum > doc.numPages) pageNum = doc.numPages;
          if (pageNum < 1) pageNum = 1;
          setStatus("");
          renderPage(pageNum);
        }).catch(function(err) {
          var errorMsg = err && err.message ? err.message : String(err);
          var errorName = err && err.name ? err.name : "Unknown";
          setStatus("Failed to load PDF: " + errorName + " - " + errorMsg);
          console.error("[Incremento] Failed to load PDF. Name:", errorName);
          console.error("[Incremento] Message:", errorMsg);
          console.error("[Incremento] Full error object:", err);
          if (err && typeof err === 'object') {
            Object.keys(err).forEach(function(key) {
              console.error("[Incremento] Error property " + key + ":", err[key]);
            });
          }
        });
      } else {
        // Retry after 100ms
        setTimeout(function() { waitForPdfJs(retryCount + 1); }, 100);
      }
    }

    // Wait for DOM and check if pdfjsLib is loaded
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() { waitForPdfJs(); });
    } else {
      waitForPdfJs();
    }
  })();
</script>
{{/PdfFile}}
{{^PdfFile}}
<div id="pdf-status">No PDF file set in PdfFile field.</div>
{{/PdfFile}}
"""

PDF_BACK_TEMPLATE = "congrats"

PDF_CSS = r"""
#pdf-wrapper { display: block; }
#pdf-controls { margin-bottom: 8px; }
.pdf-btn { margin-right: 6px; }
#page-label { margin-left: 8px; }
#pdf-status { margin: 6px 0; }
#pdf-canvas { max-width: 100%; height: auto; border: 1px solid #ccc; }
"""


def ensure_pdf_model() -> None:
    model_manager = mw.col.models

    def mm_call(snake_name, camel_name, *args):
        fn = getattr(model_manager, snake_name, None) or getattr(
            model_manager, camel_name, None
        )
        if fn is None:
            raise AttributeError(f"ModelManager missing {snake_name}/{camel_name}")
        return fn(*args)

    model = mm_call("by_name", "byName", PDF_MODEL_NAME)
    if model:
        # Update existing model template to latest version
        templates = model.get("tmpls", [])
        if templates:
            template = templates[0]
            template["qfmt"] = PDF_FRONT_TEMPLATE
            template["afmt"] = PDF_BACK_TEMPLATE
            model["css"] = PDF_CSS
            mm_call("save", "save", model)
        return

    model = mm_call("new", "new", PDF_MODEL_NAME)
    for field_name in PDF_FIELDS:
        field = mm_call("new_field", "newField", field_name)
        mm_call("add_field", "addField", model, field)

    template = mm_call("new_template", "newTemplate", "Card 1")
    template["qfmt"] = PDF_FRONT_TEMPLATE
    template["afmt"] = PDF_BACK_TEMPLATE
    model["css"] = PDF_CSS
    mm_call("add_template", "addTemplate", model, template)
    mm_call("add", "add", model)


def ensure_pdf_js_in_media() -> None:
    import shutil

    addon_dir = os.path.dirname(__file__)
    pdfjs_dir = os.path.join(addon_dir, "user_files", "pdfjs")
    for src_name, media_name in PDF_MEDIA_FILES.items():
        src_path = os.path.join(pdfjs_dir, src_name)
        if not os.path.exists(src_path):
            continue
        media_path = mw.col.media.dir()
        dst_media = os.path.join(media_path, media_name)
        if os.path.exists(dst_media):
            continue
        shutil.copy2(src_path, dst_media)


def on_js_message(handled, message, context):
    if not message.startswith("incremento_pdf_state:"):
        return handled
    try:
        _, page, zoom = message.split(":", 2)
        card = getattr(context, "card", None)
        if card is None and getattr(mw, "reviewer", None):
            card = mw.reviewer.card
        if not card:
            return (True, None)
        note = card.note()
        if "PdfPage" in note and "PdfZoom" in note:
            note["PdfPage"] = str(page)
            note["PdfZoom"] = str(zoom)
            mw.col.update_note(note)
        return (True, None)
    except Exception:
        return (True, None)


def init_pdf_note_type() -> None:
    try:
        ensure_pdf_model()
        gui_hooks.webview_did_receive_js_message.append(on_js_message)
    except Exception as exc:
        # Avoid breaking Anki load if model creation fails.
        print(f"[incremento] PDF note type init failed: {exc}")


def on_profile_open() -> None:
    init_pdf_note_type()


def init_addon() -> None:
    """Initialize the addon - call this when Anki starts (before profile open)."""
    try:
        setup_web_exports()
        gui_hooks.webview_will_set_content.append(inject_pdf_js)
        gui_hooks.profile_did_open.append(on_profile_open)
    except Exception as exc:
        print(f"[incremento] Addon init failed: {exc}")


init_addon()


def learnFunction() -> None:
    # cids = mw.col.find_cards("is:due")
    # cid = random.choice(cids)
    # card = mw.col.get_card(cid)

    add_topic_type_to_custom_data("topics")

    test_card = mw.col.get_card(mw.col.find_cards("deck:topics")[0])

    showInfo(json.loads(test_card.custom_data))

    config = mw.addonManager.getConfig(__name__)
    if config:
        showInfo(config["my_var"])
    else:
        showInfo("Learn button clicked! Replace this with your test code.")


learnAction = QAction("Start Incremental Learning", mw)
qconnect(learnAction.triggered, learnFunction)
mw.form.menuTools.addAction(learnAction)


def install_pdfjs_action() -> None:
    showInfo(
        "PDF.js is loaded automatically via web exports. No manual installation needed."
    )


installPdfJsAction = QAction("PDF.js Status", mw)
qconnect(installPdfJsAction.triggered, install_pdfjs_action)
mw.form.menuTools.addAction(installPdfJsAction)
