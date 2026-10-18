import { useEffect, useState } from "react";
import { t } from "../shared/i18n.js";
import { readPdfHandoffInfo, allowPdfHandoff } from "../shared/pdfHandoffPermissions.js";

export function PdfHandoffPage({ticket}) {
  const [info, setInfo] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let current = true;
    void readPdfHandoffInfo(ticket).then(result => {
      if (!current) return;
      if (result?.ok) setInfo(result);
      else setError("handoff_expired");
    }).catch(() => {if (current) setError("handoff_expired");});
    return () => {current = false;};
  }, [ticket]);
  async function allow() {
    if (!info || busy) return;
    // Keep this permission request directly in the user's click handler.
    const permission = allowPdfHandoff(ticket, info);
    setBusy(true);
    try {
      await permission;
    } catch {
      setError("handoff_capture_failed");
      setBusy(false);
    }
  }
  return <main className="app-shell"><section className="panel">
    <h1>{t("handoff_title")}</h1>
    <p>{t("handoff_waiting")}</p>
    {info ? <><p>{t("handoff_permission", {site: info.origins.map(origin => new URL(origin).hostname).join(", ")})}</p>
      <button className="primary-btn" disabled={busy} onClick={() => void allow()}>{t("handoff_allow")}</button></> : null}
    {error ? <p role="alert">{t(error)}</p> : null}
  </section></main>;
}
