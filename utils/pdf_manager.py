import json
import os
from pathlib import Path

PDF_NOTE_TYPE = "Incremento PDF"

CARD_TEMPLATE_FRONT = r"""
<script src="/_addons/incremento/user_files/pdfjs/pdf.min.js"></script>
<div id="incremento-pdf-meta"
     data-filename="{{PDF_Filename}}"
     data-title="{{Title}}"
     style="display:none">{{PDF_Filename}}</div>
<div id="pdf-container" style="width:100%;text-align:center;">
  <canvas id="pdf-canvas" width="800"></canvas>
  <div id="pdf-error" style="color:red;display:none;"></div>
  <div id="pdf-controls" style="margin-top:8px;">
    <button onclick="incrementoPdfNav(-1)">&#8592; Prev</button>
    <span id="pdf-page-label" style="margin:0 12px;">Page — / —</span>
    <button onclick="incrementoPdfNav(1)">Next &#8594;</button>
  </div>
</div>

<script>
(function () {
  var _cardId    = null;
  var _filename  = null;
  var _page      = 1;
  var _totalPages= 0;
  var _pdfDoc    = null;
  var _busy      = false;

  function showError(msg) {
    var el = document.getElementById("pdf-error");
    if (el) { el.style.display = ""; el.textContent = msg; }
  }

  function renderPage(num) {
    if (_busy || !_pdfDoc) return;
    _busy = true;
    _pdfDoc.getPage(num).then(function(page) {
      var canvas  = document.getElementById("pdf-canvas");
      var ctx     = canvas.getContext("2d");
      var container = document.getElementById("pdf-container");
      var width   = container.offsetWidth || 800;
      var viewport= page.getViewport({ scale: 1 });
      var scale   = width / viewport.width;
      if (!scale || scale <= 0) scale = 1;
      var scaledVP= page.getViewport({ scale: scale });
      canvas.width = scaledVP.width;
      canvas.height= scaledVP.height;
      page.render({ canvasContext: ctx, viewport: scaledVP }).promise.then(function() {
        var lbl = document.getElementById("pdf-page-label");
        if (lbl) lbl.textContent = "Page " + num + " / " + _totalPages;
        _busy = false;
      }).catch(function(e) { showError("Render error: " + e); _busy = false; });
    }).catch(function(e) { showError("Page error: " + e); _busy = false; });
  }

  function _doStart() {
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      "/_addons/incremento/user_files/pdfjs/pdf.worker.min.js";
    var url = "/" + encodeURIComponent(_filename);
    pdfjsLib.getDocument(url).promise.then(function(doc) {
      _pdfDoc     = doc;
      _totalPages = doc.numPages;
      if (_page > _totalPages) _page = _totalPages;
      renderPage(_page);
    }).catch(function(e) { showError("Load error: " + e); });
  }

  window.incrementoPdfNav = function(delta) {
    if (!_pdfDoc) return;
    var next = _page + delta;
    if (next < 1 || next > _totalPages) return;
    _page = next;
    pycmd("incremento_pdf_nav:" + _cardId + ":" + _page);
    renderPage(_page);
  };

  window.incrementoPdfStart = function(cardId, filename, startPage) {
    _cardId   = cardId;
    _filename = filename;
    _page     = startPage || 1;
    window._incPdfPending = null;  // consumed

    if (typeof pdfjsLib === "undefined") {
      // PDF.js still loading — poll until ready (up to 2s)
      var _attempts = 0;
      var _poll = setInterval(function() {
        if (typeof pdfjsLib !== "undefined") {
          clearInterval(_poll);
          _doStart();
        } else if (++_attempts > 20) {
          clearInterval(_poll);
          showError("PDF.js failed to load.");
        }
      }, 100);
      return;
    }

    _doStart();
  };

  // If Python fired web.eval before this script ran, pick up the pending args now.
  if (window._incPdfPending) {
    var _p = window._incPdfPending;
    window._incPdfPending = null;
    incrementoPdfStart(_p.cardId, _p.filename, _p.page);
  }

})();
</script>
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


# ---------------------------------------------------------------------------
# Page progress I/O
# ---------------------------------------------------------------------------

def _progress_path(addon_dir: str) -> Path:
    path = Path(addon_dir) / "user_files" / "pdf_progress.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_pdf_progress(addon_dir: str) -> dict:
    path = _progress_path(addon_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_pdf_progress(addon_dir: str, data: dict) -> None:
    path = _progress_path(addon_dir)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
                   encoding="utf-8")
    os.replace(tmp, path)


def get_page(addon_dir: str, card_id: int) -> int:
    data = load_pdf_progress(addon_dir)
    return data.get(str(card_id), 1)


def set_page(addon_dir: str, card_id: int, page: int) -> None:
    data = load_pdf_progress(addon_dir)
    data[str(card_id)] = page
    save_pdf_progress(addon_dir, data)


# ---------------------------------------------------------------------------
# Note type management
# ---------------------------------------------------------------------------

def ensure_pdf_note_type(col) -> None:
    """Create the Incremento PDF note type, or update its template if it already exists."""
    models = col.models
    m = models.by_name(PDF_NOTE_TYPE)

    if m is None:
        m = models.new(PDF_NOTE_TYPE)
        for field_name in ("Title", "PDF_Filename"):
            fld = models.new_field(field_name)
            models.add_field(m, fld)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        # Always sync the template so code changes take effect without manual DB edits.
        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            models.update_dict(m)


# ---------------------------------------------------------------------------
# Card creation
# ---------------------------------------------------------------------------

def add_pdf_card(addon_dir: str, col, pdf_path: str, title: str,
                 deck_name: str = "Topics") -> int:
    """Copy PDF to media, create note, return card id."""
    ensure_pdf_note_type(col)

    # Copy file to Anki media folder; returns (possibly deduplicated) filename
    media_filename = col.media.add_file(pdf_path)

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(PDF_NOTE_TYPE)
    note = col.new_note(model)
    note["Title"] = title
    note["PDF_Filename"] = media_filename
    note.note_type()["did"] = deck_id
    col.add_note(note, deck_id)

    # Return the id of the first (and only) card created
    return col.find_cards(f"nid:{note.id}")[0]
