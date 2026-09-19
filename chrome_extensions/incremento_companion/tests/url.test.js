import test from "node:test";
import assert from "node:assert/strict";

import {
  isHttpUrl,
  isPdfUrl,
  isSupportedVideoUrl,
  resolveLinkedVideoCardId,
} from "../src/shared/url.js";

test("isHttpUrl accepts http and https URLs", () => {
  assert.equal(isHttpUrl("https://example.com"), true);
  assert.equal(isHttpUrl("http://example.com"), true);
});

test("isHttpUrl rejects non-http URLs", () => {
  assert.equal(isHttpUrl("chrome://extensions"), false);
  assert.equal(isHttpUrl("ftp://example.com/file.pdf"), false);
  assert.equal(isHttpUrl(""), false);
});

test("isSupportedVideoUrl detects supported YouTube URLs", () => {
  assert.equal(isSupportedVideoUrl("https://www.youtube.com/watch?v=abc123"), true);
  assert.equal(isSupportedVideoUrl("https://youtu.be/abc123"), true);
  assert.equal(isSupportedVideoUrl("https://www.youtube.com/shorts/abc123"), true);
  assert.equal(isSupportedVideoUrl("https://www.youtube.com/live/abc123"), true);
  assert.equal(isSupportedVideoUrl("https://www.youtube.com/embed/abc123"), true);
});

test("isSupportedVideoUrl detects supported Vimeo URLs", () => {
  assert.equal(isSupportedVideoUrl("https://vimeo.com/123456789"), true);
  assert.equal(isSupportedVideoUrl("https://player.vimeo.com/video/123456789"), true);
});

test("isSupportedVideoUrl rejects unsupported or malformed video URLs", () => {
  assert.equal(isSupportedVideoUrl("https://www.youtube.com/watch"), false);
  assert.equal(isSupportedVideoUrl("https://example.com/watch?v=abc123"), false);
  assert.equal(isSupportedVideoUrl("not-a-url"), false);
});

test("resolveLinkedVideoCardId keeps the badge linked after the URL marker is removed", () => {
  assert.equal(
    resolveLinkedVideoCardId(
      "https://www.youtube.com/watch?v=abc123&t=42s",
      {
        cardId: 42,
        sourceUrl: "https://youtu.be/abc123?t=42s",
      },
    ),
    42,
  );
  assert.equal(
    resolveLinkedVideoCardId(
      "https://player.vimeo.com/video/123456789#t=42s",
      {
        cardId: 84,
        sourceUrl: "https://vimeo.com/123456789",
      },
    ),
    84,
  );
});

test("resolveLinkedVideoCardId rejects stale or non-video tab links", () => {
  const linked = {
    cardId: 42,
    sourceUrl: "https://www.youtube.com/watch?v=abc123",
  };
  assert.equal(
    resolveLinkedVideoCardId("https://www.youtube.com/watch?v=different", linked),
    0,
  );
  assert.equal(resolveLinkedVideoCardId("https://example.com/article", linked), 0);
  assert.equal(
    resolveLinkedVideoCardId("https://www.youtube.com/watch?v=abc123", {
      cardId: 0,
      sourceUrl: linked.sourceUrl,
    }),
    0,
  );
});

test("isPdfUrl detects PDF paths and ignores non-PDF paths", () => {
  assert.equal(isPdfUrl("https://example.com/files/paper.pdf"), true);
  assert.equal(isPdfUrl("https://example.com/files/PAPER.PDF"), true);
  assert.equal(isPdfUrl("https://example.com/files/paper.pdf?download=1"), true);
  assert.equal(isPdfUrl("https://example.com/files/paper"), false);
  assert.equal(isPdfUrl("bad-url"), false);
});
