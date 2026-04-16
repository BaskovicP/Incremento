import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from PyQt6.QtPdf import QPdfDocument

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_STEM = 80


def _safe_pdf_stem(raw_name: str, fallback: str = "document") -> str:
    stem = _SAFE_FILENAME_RE.sub("_", str(raw_name or "").strip()).strip("._-")
    stem = stem[:_MAX_FILENAME_STEM].strip("._-")
    return stem or fallback

try:
    from .db import get_connection, replace_pdf_text_index
    from . import paths as _paths
    from .note_metadata import (
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )
except ImportError:
    from db import get_connection, replace_pdf_text_index  # test environment
    import paths as _paths
    from note_metadata import (  # type: ignore
        apply_incremento_metadata,
        build_incremento_metadata,
        ensure_incremento_metadata_fields,
    )


def get_pdf_dir() -> str:
    """Return (and create) the addon's user_files/<profile>/pdfs/ folder."""
    addon_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    )
    d = str(_paths.get_pdf_dir(addon_dir, _paths.get_active_profile()))
    os.makedirs(d, exist_ok=True)
    return d


def _copy_to_pdf_dir(pdf_path: str) -> str:
    """Copy *pdf_path* into the profile PDF dir; return the stored filename.

    Stored filenames always get a UUID suffix so repeated imports never reuse
    an older file just because the basename matches.
    """
    pdf_dir = get_pdf_dir()
    raw_name = os.path.basename(pdf_path)
    stem, ext = os.path.splitext(raw_name)
    stem = _safe_pdf_stem(stem, fallback="document")
    ext = ext if ext.lower() == ".pdf" else ".pdf"
    dest_name = f"{stem}-{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(pdf_dir, dest_name)

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


def _stored_pdf_title(title: str, attempt: int) -> str:
    base_title = str(title or "").strip() or "Untitled"
    if attempt <= 0:
        return base_title
    return f"{base_title} [{attempt + 1}]"


# ---------------------------------------------------------------------------
# Page progress I/O
# ---------------------------------------------------------------------------


def get_page(addon_dir: str, profile: str, card_id: int) -> int:
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT page FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 1


def get_zoom(addon_dir: str, profile: str, card_id: int) -> float:
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT zoom FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 1.0


def set_page(addon_dir: str, profile: str, card_id: int, page: int) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, ?, 1.0) "
        "ON CONFLICT(card_id) DO UPDATE SET page = excluded.page",
        (card_id, page),
    )
    conn.commit()


def set_zoom(addon_dir: str, profile: str, card_id: int, zoom: float) -> None:
    conn = get_connection(addon_dir, profile)
    conn.execute(
        "INSERT INTO pdf_progress (card_id, page, zoom) VALUES (?, 1, ?) "
        "ON CONFLICT(card_id) DO UPDATE SET zoom = excluded.zoom",
        (card_id, round(float(zoom), 2)),
    )
    conn.commit()


def get_read_page(addon_dir: str, profile: str, card_id: int) -> int:
    """Return the highest page marked as read (0 = nothing marked yet)."""
    row = (
        get_connection(addon_dir, profile)
        .execute("SELECT read_page FROM pdf_progress WHERE card_id = ?", (card_id,))
        .fetchone()
    )
    return row[0] if row else 0


def set_read_page(addon_dir: str, profile: str, card_id: int, read_page: int) -> None:
    conn = get_connection(addon_dir, profile)
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

    Extraction order:
      1. PyMuPDF (fitz) — handles Tesseract invisible-text layers (rendering
         mode 3) and is safe to call from background threads.
      2. Qt QPdfDocument — fast for regular PDFs; skips invisible text.
      3. pdftotext (poppler) — last resort external binary.
    """
    # 1. PyMuPDF — best at reading Tesseract OCR output
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages = [doc.load_page(i).get_text("text").strip() for i in range(len(doc))]
        doc.close()
        if any(pages):
            return pages
    except Exception:
        pass

    # 2. Qt QPdfDocument
    doc = QPdfDocument(None)
    try:
        doc.load(pdf_path)
        if doc.pageCount() > 0:
            pages = []
            for i in range(doc.pageCount()):
                sel = doc.getAllText(i)
                pages.append(sel.text().strip() if sel.isValid() else "")
            if any(pages):
                return pages
    except Exception:
        pass
    finally:
        doc.close()

    # 3. pdftotext (poppler)
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
                parts = [p.strip() for p in (proc.stdout or "").split("\f")]
                while parts and not parts[-1]:
                    parts.pop()
                if parts:
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
        ensure_incremento_metadata_fields(models, m)
        tmpl = models.new_template("Card 1")
        tmpl["qfmt"] = CARD_TEMPLATE_FRONT
        tmpl["afmt"] = CARD_TEMPLATE_BACK
        models.add_template(m, tmpl)
        models.add(m)
    else:
        changed = False
        if ensure_incremento_metadata_fields(models, m):
            changed = True
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


def ocr_pdf_in_place(pdf_path: str, progress_cb=None) -> bool:
    """OCR a scanned PDF and replace it with a searchable version.

    Pipeline:
      1. PyMuPDF renders all pages to PNG at 200 DPI (sequential — fitz is not thread-safe)
      2. Tesseract OCRs all pages in parallel (ThreadPoolExecutor, one thread per core)
      3. PyMuPDF merges the per-page PDFs (no pdfunite dependency)
      4. The merged file replaces the original

    Falls back to ocrmypdf if Tesseract is unavailable.
    Returns True on success, False if required tools are missing or OCR fails.
    """
    import tempfile
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # --- preferred pipeline: tesseract + PyMuPDF ---------------------------
    tesseract = _find_bin(
        shutil.which("tesseract"),
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    )

    if tesseract:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            pass
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Step 1: render all pages to PNG (sequential — fitz not thread-safe)
                img_paths: list[str] = []
                out_bases: list[str] = []
                total_pages = 0
                try:
                    doc = fitz.open(pdf_path)
                    total_pages = len(doc)
                    mat = fitz.Matrix(200 / 72, 200 / 72)  # 200 DPI
                    for i in range(total_pages):
                        pix = doc.load_page(i).get_pixmap(matrix=mat)
                        img_path = os.path.join(tmpdir, f"p{i:04d}.png")
                        pix.save(img_path)
                        img_paths.append(img_path)
                        out_bases.append(os.path.join(tmpdir, f"p{i:04d}"))
                    doc.close()
                except Exception:
                    total_pages = 0

                if total_pages == 0:
                    pass  # fall through to ocrmypdf
                else:
                    # Step 2: OCR all pages in parallel
                    page_pdfs: dict[int, str] = {}
                    workers = min(os.cpu_count() or 1, total_pages, 8)
                    done_count = 0
                    failed = False

                    def _ocr_page(i: int):
                        proc = subprocess.run(
                            [tesseract, img_paths[i], out_bases[i], "pdf"],
                            capture_output=True,
                            timeout=120,
                        )
                        return i, proc.returncode == 0

                    try:
                        with ThreadPoolExecutor(max_workers=workers) as pool:
                            futs = {pool.submit(_ocr_page, i): i for i in range(total_pages)}
                            for fut in as_completed(futs):
                                i, ok = fut.result()
                                if not ok:
                                    failed = True
                                    break
                                page_pdfs[i] = out_bases[i] + ".pdf"
                                done_count += 1
                                if progress_cb:
                                    progress_cb(done_count, total_pages)
                    except Exception:
                        failed = True

                    if not failed and len(page_pdfs) == total_pages:
                        # Step 3: merge with PyMuPDF (no pdfunite needed)
                        try:
                            merged_doc = fitz.open()
                            for i in range(total_pages):
                                with fitz.open(page_pdfs[i]) as part:
                                    merged_doc.insert_pdf(part)
                            merged_path = os.path.join(tmpdir, "merged.pdf")
                            merged_doc.save(merged_path)
                            merged_doc.close()
                            if os.path.getsize(merged_path) > 0:
                                shutil.move(merged_path, pdf_path)
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

    import tempfile as _tempfile
    fd, tmp_path = _tempfile.mkstemp(suffix=".pdf")
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
    metadata: dict[str, str] | None = None,
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

    page_texts = extract_pdf_pages_text(dest_path)

    def _build_note(stored_title: str):
        note = col.new_note(model)
        note["Title"] = stored_title
        note["PDF_Filename"] = media_filename
        apply_incremento_metadata(
            note,
            metadata
            or build_incremento_metadata(
                source_type="PDF",
                source_title=title,
                source_link=f"pdfs/{media_filename}",
            ),
        )
        for tag in ["Incremento"] + [t for t in (tags or []) if t != "Incremento"]:
            if not tag:
                continue
            if hasattr(note, "add_tag"):
                note.add_tag(tag)
            elif hasattr(note, "tags"):
                note.tags.append(tag)
        note.note_type()["did"] = deck_id
        return note

    cid = 0
    for attempt in range(25):
        stored_title = _stored_pdf_title(title, attempt)
        note = _build_note(stored_title)
        added = col.add_note(note, deck_id)
        if not added:
            continue
        cards = col.find_cards(f"nid:{note.id}")
        if cards:
            cid = cards[0]
            break
    if not cid:
        raise RuntimeError("Failed to add PDF card. Anki rejected the note.")

    try:
        replace_pdf_text_index(addon_dir, _paths.get_active_profile(), cid, page_texts)
    except Exception:
        pass
    return cid
