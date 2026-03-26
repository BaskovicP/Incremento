import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from PyQt6.QtPdf import QPdfDocument

try:
    from .db import get_connection, replace_pdf_text_index
except ImportError:
    from db import get_connection, replace_pdf_text_index  # test environment


def get_pdf_dir() -> str:
    """Return (and create) the addon's user_files/pdfs/ folder.

    Stored inside the addon directory — outside Anki's media collection
    so PDFs are never uploaded to AnkiWeb.
    """
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    pdf_dir = os.path.join(addon_dir, "user_files", "pdfs")
    os.makedirs(pdf_dir, exist_ok=True)
    return pdf_dir


def _copy_to_pdf_dir(pdf_path: str) -> str:
    """Copy *pdf_path* into the profile PDF dir; return the stored filename.

    If a file with the same name already exists and has identical content the
    existing file is reused.  If the names collide but the content differs a
    numeric suffix is appended (e.g. ``report (1).pdf``).
    """
    pdf_dir = get_pdf_dir()
    dest_name = os.path.basename(pdf_path)
    dest_path = os.path.join(pdf_dir, dest_name)

    def _md5(path: str) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    if os.path.exists(dest_path):
        if _md5(pdf_path) == _md5(dest_path):
            return dest_name
        stem, ext = os.path.splitext(dest_name)
        n = 1
        while True:
            dest_name = f"{stem} ({n}){ext}"
            dest_path = os.path.join(pdf_dir, dest_name)
            if not os.path.exists(dest_path):
                break
            n += 1

    shutil.copy2(pdf_path, dest_path)
    return dest_name

PDF_NOTE_TYPE = "Incremento PDF"

CARD_TEMPLATE_FRONT = """
<div style="text-align:center; padding:60px 20px; font-family:sans-serif; color:#888;">
  <div style="font-size:1.3em; margin-bottom:10px; color:#ccc;">{{Title}}</div>
  <div style="font-size:0.85em;">PDF open in sidebar &nbsp;·&nbsp; select text → ⌘C → ⌘1–4 to fill fields</div>
</div>
{{PDF_Filename}}
""".strip()

CARD_TEMPLATE_BACK = "{{Title}}"


# ---------------------------------------------------------------------------
# Page progress I/O
# ---------------------------------------------------------------------------


def get_page(addon_dir: str, card_id: int) -> int:
    row = (
        get_connection(addon_dir)
        .execute("SELECT page FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 1


def get_zoom(addon_dir: str, card_id: int) -> float:
    row = (
        get_connection(addon_dir)
        .execute("SELECT zoom FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 1.0


def set_page(addon_dir: str, card_id: int, page: int) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, ?, 1.0) "
        "ON CONFLICT(card_id) DO UPDATE SET page = excluded.page",
        (card_id, page),
    )
    conn.commit()


def set_zoom(addon_dir: str, card_id: int, zoom: float) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, 1, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET zoom = excluded.zoom",
        (card_id, round(float(zoom), 2)),
    )
    conn.commit()


def get_read_page(addon_dir: str, card_id: int) -> int:
    """Return the highest page marked as read (0 = nothing marked yet)."""
    row = (
        get_connection(addon_dir)
        .execute("SELECT read_page FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 0


def set_read_page(addon_dir: str, card_id: int, read_page: int) -> None:
    conn = get_connection(addon_dir)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom, read_page) VALUES (?, 1, 1.0, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET read_page = excluded.read_page",
        (card_id, read_page),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Note type management
# ---------------------------------------------------------------------------


def extract_pdf_pages_text(pdf_path: str) -> list[str]:
    """Extract per-page text from a PDF.

    Primary extractor: Qt QPdfDocument page text.
    Fallback extractor: pdftotext split by form-feed pages.
    """
    doc = QPdfDocument(None)
    try:
        doc.load(pdf_path)  # returns Error enum in Qt 6.4+; check pageCount instead
        if doc.pageCount() == 0:
            raise RuntimeError("QPdfDocument: no pages")
        pages = []
        for i in range(doc.pageCount()):
            sel = doc.getAllText(i)
            if sel.isValid():
                t = sel.text().strip()
                pages.append(t)
            else:
                pages.append("")
        if any(pages):
            return pages
    except Exception:
        pass
    finally:
        doc.close()

    # Fallback to poppler's pdftotext if installed.
    # Check common install locations in addition to PATH, since Anki's
    # subprocess environment may not include /opt/homebrew/bin.
    _candidates = [
        shutil.which("pdftotext"),
        "/opt/homebrew/bin/pdftotext",
        "/usr/local/bin/pdftotext",
        "/usr/bin/pdftotext",
    ]
    exe = next((c for c in _candidates if c and os.path.isfile(c)), None)
    if exe:
        try:
            proc = subprocess.run(
                [exe, "-layout", "-enc", "UTF-8", pdf_path, "-"],
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                text = proc.stdout or ""
                parts = [p.strip() for p in text.split("\f")]
                if parts:
                    while parts and not parts[-1]:
                        parts.pop()
                    return parts
        except Exception:
            pass

    return []


def extract_pdf_text(pdf_path: str) -> str:
    pages = extract_pdf_pages_text(pdf_path)
    return "\n\n".join([p for p in pages if p]).strip()

    return ""


def ensure_pdf_note_type(col) -> None:
    """Create the Incremento PDF note type, or update its template/fields if it already exists."""
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
        changed = False
        # Sync template
        tmpl = m["tmpls"][0]
        if tmpl["qfmt"] != CARD_TEMPLATE_FRONT or tmpl["afmt"] != CARD_TEMPLATE_BACK:
            tmpl["qfmt"] = CARD_TEMPLATE_FRONT
            tmpl["afmt"] = CARD_TEMPLATE_BACK
            changed = True
        if changed:
            models.update_dict(m)


# ---------------------------------------------------------------------------
# Card creation
# ---------------------------------------------------------------------------


def _find_bin(*candidates: str) -> str | None:
    """Return the first existing executable path from candidates."""
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def ocr_pdf_in_place(pdf_path: str) -> bool:
    """OCR a scanned PDF and replace it with a searchable version.

    Pipeline:
      1. PyMuPDF renders each page to a PNG at 200 DPI
      2. tesseract converts each PNG to a single-page searchable PDF
      3. pdfunite merges the pages into one file
      4. The merged file replaces the original

    Falls back to ocrmypdf if tesseract/pdfunite are unavailable.
    Returns True on success, False if required tools are missing or OCR fails.
    """
    import tempfile

    # --- preferred pipeline: tesseract + pdfunite --------------------------
    tesseract = _find_bin(
        shutil.which("tesseract"),
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
    )
    pdfunite = _find_bin(
        shutil.which("pdfunite"),
        "/opt/homebrew/bin/pdfunite",
        "/usr/local/bin/pdfunite",
        "/usr/bin/pdfunite",
    )

    if tesseract and pdfunite:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            pass
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                page_pdfs: list[str] = []
                try:
                    doc = fitz.open(pdf_path)
                    mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 DPI
                    for i in range(len(doc)):
                        pix = doc.load_page(i).get_pixmap(matrix=mat)
                        img_path = os.path.join(tmpdir, f"p{i:04d}.png")
                        pix.save(img_path)
                        out_base = os.path.join(tmpdir, f"p{i:04d}")
                        proc = subprocess.run(
                            [tesseract, img_path, out_base, "pdf"],
                            capture_output=True,
                            timeout=120,
                        )
                        if proc.returncode != 0:
                            break
                        page_pdfs.append(out_base + ".pdf")
                    doc.close()
                except Exception:
                    page_pdfs = []

                if len(page_pdfs) > 0:
                    merged = os.path.join(tmpdir, "merged.pdf")
                    try:
                        if len(page_pdfs) == 1:
                            shutil.copy2(page_pdfs[0], merged)
                        else:
                            subprocess.run(
                                [pdfunite] + page_pdfs + [merged],
                                capture_output=True,
                                timeout=120,
                                check=True,
                            )
                        if os.path.getsize(merged) > 0:
                            shutil.move(merged, pdf_path)
                            return True
                    except Exception:
                        pass

    # --- fallback: ocrmypdf ------------------------------------------------
    ocrmypdf = _find_bin(
        shutil.which("ocrmypdf"),
        "/opt/homebrew/bin/ocrmypdf",
        "/usr/local/bin/ocrmypdf",
        "/usr/bin/ocrmypdf",
    )
    if not ocrmypdf:
        return False

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        proc = subprocess.run(
            [ocrmypdf, "--skip-text", "--quiet", pdf_path, tmp_path],
            capture_output=True,
            timeout=300,
        )
        if proc.returncode == 0 and os.path.getsize(tmp_path) > 0:
            shutil.move(tmp_path, pdf_path)
            return True
    except Exception:
        pass
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return False


def add_pdf_card(
    addon_dir: str,
    col,
    pdf_path: str,
    title: str,
    deck_name: str = "Topics",
    tags: list[str] | None = None,
) -> int:
    """Copy PDF to media, create note, return card id."""
    ensure_pdf_note_type(col)

    # Copy file to profile-local PDF dir (not Anki media, so it won't sync)
    media_filename = _copy_to_pdf_dir(pdf_path)
    dest_path = os.path.join(get_pdf_dir(), media_filename)

    deck = col.decks.by_name(deck_name)
    if deck is None:
        deck_id = col.decks.add_normal_deck_with_name(deck_name).id
    else:
        deck_id = deck["id"]

    model = col.models.by_name(PDF_NOTE_TYPE)
    note = col.new_note(model)
    note["Title"] = title
    note["PDF_Filename"] = media_filename

    # Extract text from the stored copy; OCR in-place if no text found
    page_texts = extract_pdf_pages_text(dest_path)
    if not any(page_texts):
        ocr_pdf_in_place(dest_path)
        page_texts = extract_pdf_pages_text(dest_path)
    for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
        if not tag:
            continue
        if hasattr(note, "add_tag"):
            note.add_tag(tag)
        elif hasattr(note, "tags"):
            note.tags.append(tag)
    note.note_type()["did"] = deck_id
    col.add_note(note, deck_id)

    # Return the id of the first (and only) card created
    cid = col.find_cards(f"nid:{note.id}")[0]
    try:
        replace_pdf_text_index(addon_dir, cid, page_texts)
    except Exception:
        pass
    return cid
