"use strict";

(() => {
  if (window.__incrementoTimeHeartbeatLoaded) {
    return;
  }
  window.__incrementoTimeHeartbeatLoaded = true;

  function showToast(text) {
    const existing = document.getElementById("incremento-video-time-toast");
    if (existing) {
      existing.remove();
    }
    const toast = document.createElement("div");
    toast.id = "incremento-video-time-toast";
    toast.textContent = String(text || "");
    Object.assign(toast.style, {
      position: "fixed",
      zIndex: 2147483647,
      top: "10px",
      right: "10px",
      maxWidth: "320px",
      padding: "10px 14px",
      background: "rgba(0, 0, 0, 0.86)",
      color: "#fff",
      fontSize: "13px",
      fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      borderRadius: "6px",
      boxShadow: "0 2px 8px rgba(0, 0, 0, 0.4)",
      opacity: "0",
      transition: "opacity 0.2s ease",
    });
    document.documentElement.appendChild(toast);
    requestAnimationFrame(() => {
      toast.style.opacity = "1";
    });
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 220);
    }, 2400);
  }

  function getRuntime() {
    try {
      return chrome?.runtime || null;
    } catch (_err) {
      return null;
    }
  }

  try {
    const rt = getRuntime();
    rt?.onMessage?.addListener((msg, _sender, sendResponse) => {
      if (!msg || msg.type !== "SHOW_TOAST") {
        return;
      }
      showToast(msg.text || "");
      sendResponse?.({ ok: true });
    });
  } catch (_err) {
    // stale/invalidated context
  }

  function extractYouTubeId(url) {
    try {
      const u = new URL(url);
      const v = u.searchParams.get("v");
      if (v) return v;
      const parts = u.pathname.split("/").filter(Boolean);
      if (u.hostname === "youtu.be" && parts[0]) return parts[0];
      if ((parts[0] === "shorts" || parts[0] === "live" || parts[0] === "embed") && parts[1]) {
        return parts[1];
      }
    } catch (_err) {
      // noop
    }
    return "";
  }

  function extractVimeoId(url) {
    const m = String(url || "").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);
    return m ? m[1] : "";
  }

  function detectProviderAndId() {
    const href = window.location.href || "";
    const host = window.location.hostname || "";
    if (host.includes("youtube.com") || host === "youtu.be") {
      return { provider: "youtube", videoId: extractYouTubeId(href) };
    }
    if (host.includes("vimeo.com")) {
      return { provider: "vimeo", videoId: extractVimeoId(href) };
    }
    return { provider: "", videoId: "" };
  }

  function extractIncrementoCardId(url) {
    try {
      const u = new URL(url);
      const raw = u.searchParams.get("inc_card_id") || "";
      const cid = Number(raw);
      if (Number.isFinite(cid) && cid > 0) {
        return Math.floor(cid);
      }
    } catch (_err) {
      // noop
    }
    return 0;
  }

  function bestVideoElement() {
    const videos = Array.from(document.querySelectorAll("video"));
    if (videos.length === 0) return null;
    videos.sort((a, b) => {
      const as = (a.videoWidth || 0) * (a.videoHeight || 0);
      const bs = (b.videoWidth || 0) * (b.videoHeight || 0);
      return bs - as;
    });
    return videos[0];
  }

  function parseClockToSeconds(text) {
    const raw = String(text || "").trim();
    if (!raw) return -1;
    const parts = raw.split(":").map((p) => p.trim());
    if (!parts.every((p) => /^\d+$/.test(p))) {
      return -1;
    }
    if (parts.length === 2) {
      return Number(parts[0]) * 60 + Number(parts[1]);
    }
    if (parts.length === 3) {
      return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
    }
    return -1;
  }

  function readVimeoTimecodeSeconds() {
    const candidates = Array.from(
      document.querySelectorAll(
        '[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'
      )
    );
    for (const el of candidates) {
      const txt = String(el?.textContent || "").trim();
      const sec = parseClockToSeconds(txt);
      if (sec >= 0) {
        return sec;
      }
    }
    return -1;
  }

  function readYouTubeTimecodeSeconds() {
    const candidates = Array.from(
      document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']")
    );
    for (const el of candidates) {
      const txt = String(el?.textContent || "").trim();
      const sec = parseClockToSeconds(txt);
      if (sec >= 0) {
        return sec;
      }
    }
    return -1;
  }

  let lastSentSec = -1;
  let lastSentAt = 0;
  let extensionAlive = true;
  let periodic = null;

  function deactivateExtensionContext() {
    extensionAlive = false;
    if (periodic !== null) {
      clearInterval(periodic);
      periodic = null;
    }
  }

  function safeSendMessage(payload) {
    if (!extensionAlive) return false;
    try {
      const rt = getRuntime();
      if (!rt?.id) {
        deactivateExtensionContext();
        return false;
      }
      rt.sendMessage(payload, () => {
        try {
          const err = rt?.lastError;
          if (err && /context invalidated/i.test(String(err.message || ""))) {
            deactivateExtensionContext();
          }
        } catch (_err) {
          deactivateExtensionContext();
        }
      });
      return true;
    } catch (_err) {
      deactivateExtensionContext();
      return false;
    }
  }

  function sendHeartbeat(force = false, flush = false) {
    if (!extensionAlive) return;
    const { provider, videoId } = detectProviderAndId();
    if (!provider) return;

    const video = bestVideoElement();
    let sec = -1;
    if (video) {
      sec = Math.max(0, Math.floor(Number(video.currentTime) || 0));
    }
    if (provider === "youtube" && sec <= 0) {
      const ytSec = readYouTubeTimecodeSeconds();
      if (ytSec >= 0) {
        sec = ytSec;
      }
    }
    if (provider === "vimeo" && sec <= 0) {
      const vimeoSec = readVimeoTimecodeSeconds();
      if (vimeoSec >= 0) {
        sec = vimeoSec;
      }
    }
    if (sec < 0) return;
    const now = Date.now();
    if (!force && sec === lastSentSec && now - lastSentAt < 4000) {
      return;
    }
    lastSentSec = sec;
    lastSentAt = now;

    safeSendMessage({
      type: "heartbeat",
      provider,
      videoId,
      cardId: extractIncrementoCardId(window.location.href || ""),
      flush: !!flush,
      seconds: sec,
      url: window.location.href || "",
      title: document.title || "",
    });
  }

  periodic = window.setInterval(() => sendHeartbeat(false, false), 1000);
  window.addEventListener("pagehide", () => sendHeartbeat(true, true), { capture: true });
  window.addEventListener("beforeunload", () => sendHeartbeat(true, true), { capture: true });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      sendHeartbeat(true, true);
    }
  });
  document.addEventListener("timeupdate", () => sendHeartbeat(false, false), true);
  document.addEventListener("play", () => sendHeartbeat(true, false), true);
  document.addEventListener("pause", () => sendHeartbeat(true, true), true);
  document.addEventListener("ended", () => sendHeartbeat(true, true), true);

  window.setTimeout(() => sendHeartbeat(true, false), 1200);
  window.addEventListener("unload", () => {
    try {
      clearInterval(periodic);
    } catch (_err) {
      // noop
    }
  });
})();
