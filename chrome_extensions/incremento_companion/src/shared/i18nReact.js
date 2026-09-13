import { useSyncExternalStore } from "react";
import { currentLanguageSnapshot, subscribeLanguage } from "./i18n.js";

export function useLanguage() {
  return useSyncExternalStore(subscribeLanguage, currentLanguageSnapshot, currentLanguageSnapshot);
}
