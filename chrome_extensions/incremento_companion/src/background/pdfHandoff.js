import { isFirefox } from "../shared/extensionApi.js";

const ARCHIVE_HOSTS = new Set(["archive.is", "archive.ph", "archive.today", "archive.md", "archive.li", "archive.fo", "archive.vn"]);
const KEY_PREFIX = "incremento_pdf_handoff_";

export function handoffSenderTab(msg, sender, api) {
  if (msg.type === "PDF_HANDOFF_READY") return sender?.frameId === 0 && Number.isInteger(sender?.tab?.id) ? sender.tab.id : null;
  if (String(sender?.url || "") !== api.runtime.getURL(`popup.html?pdfHandoff=${msg.ticket}`)) return null;
  const tabId = sender?.tab?.id ?? msg.tabId;
  return Number.isInteger(tabId) ? tabId : null;
}

export function handoffTicketFromUrl(value) {
  try {
    const url = new URL(value);
    if (url.origin !== "http://127.0.0.1:8766" || url.pathname !== "/incremento/webpage-pdf" || url.search || url.username || url.password) return "";
    return /^[a-f0-9]{64}$/.test(url.hash.slice(1)) ? url.hash.slice(1) : "";
  } catch { return ""; }
}

export function sameHandoffSite(original, current) {
  try {
    const first = new URL(original), second = new URL(current);
    if (![first, second].every(url => /^https?:$/.test(url.protocol) && !url.username && !url.password)) return false;
    return first.origin === second.origin || (first.protocol === "https:" && second.protocol === "https:" && first.port === second.port && ARCHIVE_HOSTS.has(first.hostname) && ARCHIVE_HOSTS.has(second.hostname));
  } catch { return false; }
}

function sameHandoffPage(original, current) {
  if (!sameHandoffSite(original, current)) return false;
  const first = new URL(original), second = new URL(current);
  return first.pathname.replace(/\/$/, "") === second.pathname.replace(/\/$/, "") && first.search === second.search;
}

function originPatterns(value, api) {
  const url = new URL(value);
  return url.protocol === "https:" && ARCHIVE_HOSTS.has(url.hostname)
    ? [...ARCHIVE_HOSTS].map(host => `https://${host}/*`) : [`${isFirefox(api) ? `${url.protocol}//${url.hostname}` : url.origin}/*`];
}

// Runs only in the handoff tab's isolated world. It observes verification;
// it never clicks a challenge, changes the page, or reads browser credentials.
export function watchVerifiedPage(ticket, expiresAt) {
  const previous = globalThis.__incrementoPdfHandoffWatch;
  if (previous?.ticket === ticket) return;
  if (previous) clearInterval(previous.timer);
  let previousText = "";
  const timer = setInterval(() => {
    if (Date.now() >= expiresAt) {clearInterval(timer); return;}
    if (document.readyState !== "complete") return;
    const text = String(document.body?.innerText || "").replace(/\s+/g, " ").trim().slice(0, 64000);
    const title = String(document.title || "").toLowerCase();
    const blockedTitle = /^(just a moment|attention required|security check|access denied|captcha\b|verify (you|that)|sign in\b|log in\b|login\b)/.test(title);
    const challenge = document.querySelector("#challenge-form, #captcha-form, #captcha, .sgcaptcha, .cf-challenge, input[type='password']");
    const blockedText = /(?:verify|confirm|checking).{0,50}(?:human|not a robot|your browser)|complete (?:the )?captcha|too many requests/i.test(text);
    if (blockedTitle || (text.length < 2000 && (challenge || blockedText)) || text.length < 100) {previousText = ""; return;}
    const sample = text.slice(0, 8000);
    if (sample !== previousText) {previousText = sample; return;}
    clearInterval(timer);
    void (globalThis.browser || globalThis.chrome).runtime.sendMessage({type: "PDF_HANDOFF_READY", ticket}).catch(() => {});
  }, 1000);
  globalThis.__incrementoPdfHandoffWatch = {ticket, timer};
}

export function createPdfHandoffController({api, rpc, readPage, now = Date.now}) {
  const launching = new Set(), submitting = new Set();
  const key = tabId => `${KEY_PREFIX}${tabId}`;
  const get = async tabId => (await api.storage.session.get(key(tabId)))[key(tabId)];
  const remove = tabId => api.storage.session.remove(key(tabId));
  const set = (tabId, value) => api.storage.session.set({[key(tabId)]: value});
  async function begin(tabId, ticket) {
    const job = await get(tabId);
    if (!job || job.ticket !== ticket || job.expiresAt <= now()) throw new Error("handoff_expired");
    await rpc({action: "describe", ticket});
    if (!await api.permissions.contains({origins: originPatterns(job.url, api)})) throw new Error("handoff_permission");
    await api.tabs.update(tabId, {url: job.url});
    return {ok: true};
  }
  async function navigate(tabId, url) {
    const ticket = handoffTicketFromUrl(url);
    if (!ticket || launching.has(tabId)) return;
    launching.add(tabId);
    try {
      const result = await rpc({action: "describe", ticket});
      // The backend supplies the destination; a webpage cannot choose it by
      // inserting a target URL into the handoff link.
      if (!sameHandoffSite(result.url, result.url)) throw new Error("handoff_expired");
      await set(tabId, {ticket, url: result.url, expiresAt: now() + Math.min(600, Number(result.remainingSeconds) || 0) * 1000});
      if (await api.permissions.contains({origins: originPatterns(result.url, api)})) {
        await begin(tabId, ticket);
      } else {
        await api.tabs.update(tabId, {url: api.runtime.getURL(`popup.html?pdfHandoff=${ticket}`)});
      }
    } finally {launching.delete(tabId);}
  }
  async function loaded(tabId, url) {
    const job = await get(tabId);
    if (!job) return;
    if (job.expiresAt <= now()) {await remove(tabId); return;}
    if (!sameHandoffPage(job.url, url)) return;
    if (!await api.permissions.contains({origins: originPatterns(url, api)})) return;
    await api.scripting.executeScript({target: {tabId, frameIds: [0]}, func: watchVerifiedPage, args: [job.ticket, job.expiresAt]});
  }
  async function ready(tabId, ticket, frameId) {
    if (frameId !== 0 || submitting.has(tabId)) return;
    submitting.add(tabId);
    try {
      const job = await get(tabId);
      if (!job || job.ticket !== ticket || job.expiresAt <= now()) return;
      const tab = await api.tabs.get(tabId);
      if (!sameHandoffPage(job.url, tab.url)) return;
      const context = await readPage(tabId, {includeHtml: true, htmlScope: "full", preserveStyles: true});
      if (!context?.html || !sameHandoffPage(job.url, context.url)) throw new Error("handoff_capture_failed");
      await rpc({action: "submit", ticket, url: context.url, html: context.html});
      await remove(tabId);
    } finally {submitting.delete(tabId);}
  }
  async function info(tabId, ticket) {
    const job = await get(tabId);
    if (!job || job.ticket !== ticket || job.expiresAt <= now()) throw new Error("handoff_expired");
    return {ok: true, url: job.url, origins: originPatterns(job.url, api)};
  }
  async function closed(tabId) {
    const job = await get(tabId);
    if (job) {
      await remove(tabId);
      await rpc({action: "fail", ticket: job.ticket});
    }
  }
  return {navigate, loaded, ready, info, begin, closed};
}
