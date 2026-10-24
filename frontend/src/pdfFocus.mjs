// Python owns the saved preference and native window layout. Only its replies
// change the pressed state; a failed save leaves the button and layout intact.
export function pdfFocusState(state, cardId) {
  if (!Number.isSafeInteger(cardId) || cardId <= 0 || state?.cardId !== cardId) {
    return {enabled: false, available: false};
  }
  return {enabled: state.enabled === true, available: state.available === true};
}

export function pdfFocusCommand(state, cardId) {
  const current = pdfFocusState(state, cardId);
  return current.available
    ? 'incremento_pdf_focus:' + JSON.stringify({cardId, enabled: !current.enabled})
    : null;
}
