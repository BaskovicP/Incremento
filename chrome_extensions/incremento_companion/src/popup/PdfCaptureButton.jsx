import { t } from "../shared/i18n.js";

export function PdfCaptureButton({busy, hasSupportedPage, onAdd}) {
  return (
    <button
      className="kind-btn"
      data-kind="pdf-capture"
      disabled={busy || !hasSupportedPage}
      title={t("capture_opened_page_pdf_help")}
      onClick={() => void onAdd("pdf", {openedPage: true})}
    >
      {t("capture_opened_page_pdf")}
    </button>
  );
}
