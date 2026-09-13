import { displayMessage, formatNumber, t } from "../../shared/i18n.js";

export function ProgressPanel({ progress }) {
  const hidden = progress.total === 0;
  return (
    <section className={`progress-panel${hidden ? " is-hidden" : ""}`} aria-live="polite">
      <div className="progress-head">
        <strong id="progress-title">{t("progress_title")}</strong>
        <span>{`${formatNumber(progress.completed)} / ${formatNumber(progress.total)}`}</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={progress.percent}
        aria-labelledby="progress-title"
      >
        <div className="progress-fill" style={{ width: `${progress.percent}%` }}></div>
      </div>
      <p className="muted" id="progress-note">{displayMessage(progress.note)}</p>
    </section>
  );
}
