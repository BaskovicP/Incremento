"""Import dialogs render catalog text while retaining their stable choices."""

from pathlib import Path

from backend.i18n import Translator


ROOT = Path(__file__).resolve().parents[1]


def test_import_dialog_catalog_translates_labels_and_validation():
    tr = Translator("hr")
    assert tr.t("imports_add_local_file") == "Dodaj lokalnu datoteku"
    assert tr.t("imports_storage_managed") == "Kopiraj u Incremento"
    assert tr.t("imports_writing_source_required") == "Najprije unesite URL izvora."
    assert tr.t("imports_writing_fetch_failed", error="timeout") == "Dohvaćanje Markdowna mrežne stranice nije uspjelo:\ntimeout"
    assert Translator("zh-Hans").t("imports_add_web_page") == "添加网页"


def test_import_dialog_sources_use_localized_labels_without_translating_machine_values():
    local = (ROOT / "frontend/add_local_file_dialog.py").read_text(encoding="utf-8")
    writing = (ROOT / "frontend/add_writing_dialog.py").read_text(encoding="utf-8")
    assert 'setWindowTitle("Add Local File")' not in local
    assert 'addItem("Copy into Incremento", LOCAL_FILE_MODE_MANAGED_COPY)' not in local
    assert 'showInfo("Please enter a source URL first.")' not in writing
    assert 'showInfo(f"Failed to fetch webpage markdown:' not in writing
    assert '"webpage_markdown"' in writing


def test_video_and_webpage_dialog_statuses_are_localized():
    tr = Translator("hr")
    assert tr.t("imports_add_video") == "Dodaj videozapis"
    assert tr.t("imports_video_resolutions_failed", error="offline") == "Nije moguće učitati razlučivosti (offline). Upotrijebit će se najbolja dostupna."
    assert Translator("zh-Hans").t("imports_webpage_generating_pdf") == "正在生成 PDF…"
    video = (ROOT / "frontend/add_video_dialog.py").read_text(encoding="utf-8")
    assert 'setWindowTitle("Add Video")' not in video
    assert '"youtube"' in video


def test_pdf_and_epub_import_pickers_translate_selection_help():
    tr = Translator("hr")
    assert tr.t("imports_pdf_title") == "Dodaj PDF-ove"
    assert tr.t("imports_epub_title") == "Dodaj EPUB-ove"
    assert tr.t("imports_choose_checked_pdf") == "Označite barem jedan PDF za uvoz."
    assert tr.t("imports_pdf_progress", completed=2, total=4) == "Dodavanje PDF-ova… 2 / 4"
    assert Translator("zh-Hans").t("imports_choose_checked_epub") == "请勾选至少一个要导入的 EPUB。"
    pdf = (ROOT / "frontend/pdf_dialog.py").read_text(encoding="utf-8")
    epub = (ROOT / "frontend/epub_dialog.py").read_text(encoding="utf-8")
    assert 'setWindowTitle("Add PDFs")' not in pdf
    assert 'setWindowTitle("Add EPUBs")' not in epub


def test_djvu_import_pickers_describe_both_formats_in_all_languages():
    for locale in ("en", "hr", "zh-Hans"):
        tr = Translator(locale)
        assert "DjVu" in tr.t("imports_pdf_djvu_title")
        assert "*.djvu" in tr.t("imports_pdf_djvu_file_filter")
        assert "*.djv" in tr.t("imports_pdf_djvu_file_filter")
        assert "DjVu" in tr.t("imports_pdf_djvu_choose_file")
        assert "DjVu" in tr.t("root_menu_add_pdf")
        assert "DjVu" in tr.t("shortcut_add_pdf")
        assert "DjVu" in tr.t("onboarding_add_document_action")
