import { displayMessage, message } from "./i18n.js";

// Keep transport/storage enum values outside the displayed label. Descriptors
// let a running popup status change language without losing its import state.
export function cardKindMessage(kind) {
  switch (kind) {
    case "pdf": return message("pdf_kind");
    case "video": return message("video_kind");
    case "webpage": return message("webpage_kind");
    case "writing": return message("writing_kind");
    default: return message("content_kind");
  }
}

export function cardKindLabel(kind) {
  return displayMessage(cardKindMessage(kind));
}
