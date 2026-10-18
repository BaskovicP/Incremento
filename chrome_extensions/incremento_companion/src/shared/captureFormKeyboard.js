export function focusCaptureSubmitButton(ui, button) {
  if (ui.initialFocusSet || button.disabled) return;
  ui.initialFocusSet = true;
  button.focus({preventScroll: true});
}

export function handleCaptureSubmitKey(event, {form, submitting = false}) {
  if (!form || event.key !== "Enter" || event.defaultPrevented
      || event.isComposing || event.keyCode === 229
      || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return false;

  const target = event.target;
  const tag = String(target?.tagName || "").toUpperCase();
  if (target?.isContentEditable || ["TEXTAREA", "SELECT", "A"].includes(tag)
      || (tag === "BUTTON" && target.type !== "submit")) return false;

  event.preventDefault();
  if (!event.repeat && !submitting) form.requestSubmit();
  return true;
}
