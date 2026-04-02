import React from "react";
import { createRoot } from "react-dom/client";
import { BookmarksApp } from "./App.jsx";

const rootElement = document.getElementById("root");
createRoot(rootElement).render(
  <React.StrictMode>
    <BookmarksApp />
  </React.StrictMode>
);
