import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAutomaticWritingTitle,
  buildPreferredWritingFilename,
  shouldAutoGenerateWritingTitle,
} from "../src/shared/writingTitle.js";

test("shouldAutoGenerateWritingTitle detects untouched default title", () => {
  assert.equal(
    shouldAutoGenerateWritingTitle("PySide6.QMenuBar - Qt for Python", "PySide6.QMenuBar - Qt for Python", "https://doc.qt.io"),
    true
  );
  assert.equal(
    shouldAutoGenerateWritingTitle("", "PySide6.QMenuBar - Qt for Python", "https://doc.qt.io"),
    true
  );
  assert.equal(
    shouldAutoGenerateWritingTitle("Custom capture title", "PySide6.QMenuBar - Qt for Python", "https://doc.qt.io"),
    false
  );
});

test("buildAutomaticWritingTitle adds selection context and timestamp", () => {
  const result = buildAutomaticWritingTitle(
    "PySide6.QMenuBar - Qt for Python",
    "https://doc.qt.io",
    "selection",
    "default Up property summary text",
    new Date("2026-04-05T14:30:15"),
    1_775_400_615_123_456
  );
  assert.equal(
    result,
    "PySide6.QMenuBar - Qt for Python - default Up property summary text [20260405-143015-123456]"
  );
});

test("buildAutomaticWritingTitle falls back to page title and timestamp for full-page markdown", () => {
  const result = buildAutomaticWritingTitle(
    "PySide6.QMenuBar - Qt for Python",
    "https://doc.qt.io",
    "webpage_markdown",
    "",
    new Date("2026-04-05T14:30:15"),
    1_775_400_615_654_321
  );
  assert.equal(result, "PySide6.QMenuBar - Qt for Python [20260405-143015-654321]");
});

test("buildAutomaticWritingTitle differs for repeated writes within the same second", () => {
  const left = buildAutomaticWritingTitle(
    "PySide6.QMenuBar - Qt for Python",
    "https://doc.qt.io",
    "webpage_markdown",
    "",
    new Date("2026-04-05T14:30:15"),
    1_775_400_615_100_001
  );
  const right = buildAutomaticWritingTitle(
    "PySide6.QMenuBar - Qt for Python",
    "https://doc.qt.io",
    "webpage_markdown",
    "",
    new Date("2026-04-05T14:30:15"),
    1_775_400_615_100_002
  );
  assert.notEqual(left, right);
});

test("buildPreferredWritingFilename keeps filenames short and excludes generated timestamp suffixes", () => {
  const result = buildPreferredWritingFilename(
    "PySide6.QWidgets.QMenuBar - Qt for Python Runs the QAction at pt. Returns None",
    "https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QMenuBar.html"
  );
  assert.equal(
    result,
    "pyside6.qwidgets.qmenubar-qt-for-python-runs-the-qaction-at-pt.-returns-none.md"
  );
});

test("buildPreferredWritingFilename falls back to a safe default", () => {
  assert.equal(buildPreferredWritingFilename("", ""), "writing-note.md");
});
