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

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (!msg || msg.type !== "SHOW_TOAST") {
      return;
    }
    showToast(msg.text || "");
    sendResponse?.({ ok: true });
  });

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

  let lastSentSec = -1;
  let lastSentAt = 0;

  function sendHeartbeat(force = false) {
    const { provider, videoId } = detectProviderAndId();
    if (!provider) return;

    const video = bestVideoElement();
    if (!video) return;

    const sec = Math.max(0, Math.floor(Number(video.currentTime) || 0));
    const now = Date.now();
    if (!force && sec === lastSentSec && now - lastSentAt < 4000) {
      return;
    }
    lastSentSec = sec;
    lastSentAt = now;

    chrome.runtime.sendMessage(
      {
        type: "heartbeat",
        provider,
        videoId,
        seconds: sec,
        url: window.location.href || "",
        title: document.title || "",
      },
      () => {
        void chrome.runtime?.lastError;
      }
    );
  }

  const periodic = window.setInterval(() => sendHeartbeat(false), 1000);
  window.addEventListener("pagehide", () => sendHeartbeat(true), { capture: true });
  window.addEventListener("beforeunload", () => sendHeartbeat(true), { capture: true });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      sendHeartbeat(true);
    }
  });
  document.addEventListener("timeupdate", () => sendHeartbeat(false), true);
  document.addEventListener("pause", () => sendHeartbeat(true), true);
  document.addEventListener("ended", () => sendHeartbeat(true), true);

  window.setTimeout(() => sendHeartbeat(true), 1200);
  window.addEventListener("unload", () => {
    try {
      clearInterval(periodic);
    } catch (_err) {
      // noop
    }
  });
})();
