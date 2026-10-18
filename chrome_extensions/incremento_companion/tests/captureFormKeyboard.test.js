import test from "node:test";
import assert from "node:assert/strict";
import { focusCaptureSubmitButton, handleCaptureSubmitKey } from "../src/shared/captureFormKeyboard.js";

function key(overrides = {}) {
  return {key: "Enter", target: {tagName: "BUTTON", type: "submit"},
    defaultPrevented: false, preventDefault() {this.defaultPrevented = true;}, ...overrides};
}

test("opening capture focuses Create note once so Enter can immediately submit", () => {
  const ui = {};
  const focus = [];
  const button = {disabled: false, focus: options => focus.push(options)};
  focusCaptureSubmitButton(ui, button);
  assert.deepEqual(focus, [{preventScroll: true}]);
  focusCaptureSubmitButton(ui, button);
  assert.equal(focus.length, 1, "rerendering must not steal focus from an edited field");
});

test("plain Enter submits through the existing form submit path and prevents native double submission", () => {
  let submissions = 0;
  const event = key();
  assert.equal(handleCaptureSubmitKey(event, {form: {requestSubmit() {submissions += 1;}}}), true);
  assert.equal(submissions, 1);
  assert.equal(event.defaultPrevented, true);
});

test("text and priority inputs can submit with Enter", () => {
  for (const type of ["text", "number", "range"]) {
    let submissions = 0;
    handleCaptureSubmitKey(key({target: {tagName: "INPUT", type}}),
      {form: {requestSubmit() {submissions += 1;}}});
    assert.equal(submissions, 1, type);
  }
});

test("Enter preserves multiline editing, dropdowns, other buttons, composition, and tag completion", () => {
  const cases = [
    {target: {tagName: "TEXTAREA"}}, {target: {tagName: "SELECT"}},
    {target: {tagName: "BUTTON", type: "button"}}, {target: {tagName: "A"}},
    {target: {tagName: "SPAN", isContentEditable: true}},
    {isComposing: true}, {keyCode: 229}, {defaultPrevented: true},
    {altKey: true}, {ctrlKey: true}, {metaKey: true}, {shiftKey: true}, {key: "Escape"},
  ];
  for (const overrides of cases) {
    let submissions = 0;
    const event = key(overrides);
    const wasPrevented = event.defaultPrevented;
    assert.equal(handleCaptureSubmitKey(event, {form: {requestSubmit() {submissions += 1;}}}), false);
    assert.equal(submissions, 0);
    assert.equal(event.defaultPrevented, wasPrevented);
  }
});

test("held Enter and Enter during an in-flight add cannot create a second card", () => {
  let submissions = 0;
  let submitting = false;
  const form = {requestSubmit() {submissions += 1; submitting = true;}};
  handleCaptureSubmitKey(key(), {form, submitting});
  const second = key();
  handleCaptureSubmitKey(second, {form, submitting});
  const held = key({repeat: true});
  handleCaptureSubmitKey(held, {form, submitting: false});
  assert.equal(submissions, 1);
  assert.equal(second.defaultPrevented, true);
  assert.equal(held.defaultPrevented, true);
});

test("Enter is left alone when no capture form exists", () => {
  const event = key();
  assert.equal(handleCaptureSubmitKey(event, {form: null}), false);
  assert.equal(event.defaultPrevented, false);
});
