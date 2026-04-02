import React from "react";
import { createRoot } from "react-dom/client";
import { PopupApp } from "./App.jsx";

const rootElement = document.getElementById("root");
createRoot(rootElement).render(
  <React.StrictMode>
    <PopupApp />
  </React.StrictMode>
);
