import React from "react";
import { createRoot } from "react-dom/client";
import { PopupApp } from "./App.jsx";
import { PdfHandoffPage } from "./PdfHandoffPage.jsx";
import { initializeLanguage, localizeDocument, subscribeLanguage, watchLanguageStorage } from "../shared/i18n.js";

watchLanguageStorage();
subscribeLanguage(() => localizeDocument("popup_title"));
void initializeLanguage().then(() => {
  localizeDocument("popup_title");
  const rootElement = document.getElementById("root");
  const handoffTicket = new URLSearchParams(window.location.search).get("pdfHandoff") || "";
  createRoot(rootElement).render(
    <React.StrictMode>
      {/^[a-f0-9]{64}$/.test(handoffTicket) ? <PdfHandoffPage ticket={handoffTicket} /> : <PopupApp />}
    </React.StrictMode>
  );
});
