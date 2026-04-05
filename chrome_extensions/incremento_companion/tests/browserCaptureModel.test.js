import test from "node:test";
import assert from "node:assert/strict";

import {
  buildBrowserCapturePayload,
  normalizeBrowserCaptureSettings,
  normalizeFieldMappings,
  parseTags,
  updateMappingsForNoteType,
} from "../src/shared/browserCaptureModel.js";

test("parseTags splits on whitespace and commas", () => {
  assert.deepEqual(parseTags(" alpha, beta  beta gamma "), ["alpha", "beta", "gamma"]);
});

test("normalizeFieldMappings keeps blank explicit mappings and defaults unknown values", () => {
  assert.deepEqual(
    normalizeFieldMappings(
      { titleField: "Missing", selectedTextField: "", urlField: "Missing", snapshotField: "Back" },
      ["Front", "Back"]
    ),
    { titleField: "Front", selectedTextField: "", urlField: "Front", snapshotField: "Back" }
  );
});

test("normalizeBrowserCaptureSettings selects saved note type and deck when present", () => {
  const meta = {
    noteTypes: [
      { name: "Basic", fields: ["Front", "Back"] },
      { name: "Cloze", fields: ["Text", "Extra"] },
    ],
    deckNames: ["Default", "Research"],
  };
  const settings = normalizeBrowserCaptureSettings(
    {
      noteTypeName: "Cloze",
      deckName: "Research",
      priority: 12.5,
      tagsText: "alpha beta",
      mappingsByNoteType: {
        Cloze: { titleField: "Text", selectedTextField: "Text", urlField: "Extra", snapshotField: "" },
      },
    },
    meta
  );
  assert.equal(settings.noteTypeName, "Cloze");
  assert.equal(settings.deckName, "Research");
  assert.equal(settings.priority, 12.5);
  assert.equal(settings.fieldMappings.titleField, "Text");
  assert.equal(settings.fieldMappings.urlField, "Extra");
  assert.equal(settings.fieldMappings.snapshotField, "");
});

test("updateMappingsForNoteType stores mappings by note type", () => {
  const updated = updateMappingsForNoteType(
    { mappingsByNoteType: {}, noteTypeName: "Basic", fieldMappings: {} },
    "Basic",
    { titleField: "Front", selectedTextField: "Front", urlField: "Back", snapshotField: "Back" }
  );
  assert.deepEqual(updated.mappingsByNoteType.Basic, {
    titleField: "Front",
    selectedTextField: "Front",
    urlField: "Back",
    snapshotField: "Back",
  });
});

test("buildBrowserCapturePayload serializes snapshots and form state", () => {
  const payload = buildBrowserCapturePayload(
    {
      url: "https://example.com/article",
      title: "Example",
      selectedText: "Selected text",
      snapshots: [{ filename: "snap-1.png", base64: "abcd" }],
    },
    {
      noteTypeName: "Basic",
      deckName: "Default",
      tagsText: "alpha beta",
      priority: 9.5,
      fieldMappings: {
        titleField: "Front",
        selectedTextField: "Front",
        urlField: "Back",
        snapshotField: "Back",
      },
    }
  );
  assert.equal(payload.noteTypeName, "Basic");
  assert.equal(payload.deckName, "Default");
  assert.deepEqual(payload.tags, ["alpha", "beta"]);
  assert.equal(payload.snapshots[0].filename, "snap-1.png");
  assert.equal(payload.fieldMappings.titleField, "Front");
  assert.equal(payload.fieldMappings.snapshotField, "Back");
});
