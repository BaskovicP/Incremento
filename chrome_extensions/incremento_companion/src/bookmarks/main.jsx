import React from "react";
import { createRoot } from "react-dom/client";
import { BookmarksApp } from "./App.jsx";
import { initializeLanguage, localizeDocument, subscribeLanguage, watchLanguageStorage } from "../shared/i18n.js";

watchLanguageStorage();
subscribeLanguage(() => localizeDocument("bookmarks_title"));
void initializeLanguage().then(() => {
  localizeDocument("bookmarks_title");
  const rootElement = document.getElementById("root");
  createRoot(rootElement).render(
    <React.StrictMode>
      <BookmarksApp />
    </React.StrictMode>
  );
});
