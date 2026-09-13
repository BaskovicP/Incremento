import React from "react";
import { createRoot } from "react-dom/client";
import { PopupApp } from "./App.jsx";
import { initializeLanguage, localizeDocument, subscribeLanguage, watchLanguageStorage } from "../shared/i18n.js";

watchLanguageStorage();
subscribeLanguage(() => localizeDocument("popup_title"));
void initializeLanguage().then(() => {
  localizeDocument("popup_title");
  const rootElement = document.getElementById("root");
  createRoot(rootElement).render(
    <React.StrictMode>
      <PopupApp />
    </React.StrictMode>
  );
});
