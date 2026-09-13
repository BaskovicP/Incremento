import test from "node:test";
import assert from "node:assert/strict";
import { cardKindLabel, cardKindMessage } from "../src/shared/cardKind.js";
import { applyStoredLanguageChange, displayMessage, message } from "../src/shared/i18n.js";

test("known import kinds have translated labels and unknown kinds use a readable fallback", () => {
  const kinds = ["pdf", "video", "webpage", "writing", "unknown", "constructor"];
  const expected = {
    en: ["PDF", "YouTube/Video", "Webpage", "Writing", "Content", "Content"],
    hr: ["PDF", "YouTube/videozapis", "Mrežna stranica", "Pisanje", "Sadržaj", "Sadržaj"],
    "zh-Hans": ["PDF", "YouTube/视频", "网页", "写作", "内容", "内容"],
  };
  for (const [locale, labels] of Object.entries(expected)) {
    applyStoredLanguageChange(locale, {});
    assert.deepEqual(kinds.map(cardKindLabel), labels);
  }
  applyStoredLanguageChange("en", {});
});

test("an in-progress kind descriptor follows a language switch without changing its saved enum", () => {
  const result = { kind: "writing", title: "My writing" };
  const status = message("adding_card", { kind: cardKindMessage(result.kind) });
  applyStoredLanguageChange("hr", {});
  assert.equal(displayMessage(status), "Dodaje se kartica vrste Pisanje...");
  applyStoredLanguageChange("zh-Hans", {});
  assert.equal(displayMessage(status), "正在添加 写作 卡片…");
  assert.deepEqual(result, { kind: "writing", title: "My writing" });
  applyStoredLanguageChange("en", {});
});
