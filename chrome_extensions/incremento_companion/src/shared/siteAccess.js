export const PERSISTENT_SITE_ACCESS_SCRIPT_ID = "incremento-persistent-http-content";
export const PERSISTENT_SITE_ORIGINS = Object.freeze([
  "http://*/*",
  "https://*/*",
]);

const PROVIDER_MATCHES = Object.freeze([
  "*://*.youtube.com/*",
  "*://*.youtu.be/*",
  "*://*.vimeo.com/*",
]);

function persistentContentScriptDefinition() {
  return {
    id: PERSISTENT_SITE_ACCESS_SCRIPT_ID,
    matches: [...PERSISTENT_SITE_ORIGINS],
    excludeMatches: [...PROVIDER_MATCHES],
    allFrames: true,
    js: ["content-loader.js"],
    runAt: "document_idle",
    persistAcrossSessions: true,
  };
}

export async function hasPersistentSiteAccess() {
  if (!chrome.permissions?.contains) {
    return false;
  }
  return Boolean(await chrome.permissions.contains({
    origins: [...PERSISTENT_SITE_ORIGINS],
  }));
}

export async function syncPersistentSiteContentScript() {
  if (
    !chrome.scripting?.getRegisteredContentScripts
    || !chrome.scripting?.registerContentScripts
  ) {
    return false;
  }

  const granted = await hasPersistentSiteAccess();
  const registered = await chrome.scripting.getRegisteredContentScripts({
    ids: [PERSISTENT_SITE_ACCESS_SCRIPT_ID],
  });
  const hasRegistration = Array.isArray(registered) && registered.length > 0;

  if (!granted) {
    if (hasRegistration && chrome.scripting?.unregisterContentScripts) {
      await chrome.scripting.unregisterContentScripts({
        ids: [PERSISTENT_SITE_ACCESS_SCRIPT_ID],
      });
    }
    return false;
  }

  const definition = persistentContentScriptDefinition();
  if (hasRegistration) {
    if (chrome.scripting?.updateContentScripts) {
      await chrome.scripting.updateContentScripts([definition]);
    } else if (chrome.scripting?.unregisterContentScripts) {
      await chrome.scripting.unregisterContentScripts({
        ids: [PERSISTENT_SITE_ACCESS_SCRIPT_ID],
      });
      await chrome.scripting.registerContentScripts([definition]);
    }
  } else {
    await chrome.scripting.registerContentScripts([definition]);
  }
  return true;
}

export async function requestPersistentSiteAccess() {
  if (!chrome.permissions?.request) {
    return false;
  }
  const granted = Boolean(await chrome.permissions.request({
    origins: [...PERSISTENT_SITE_ORIGINS],
  }));
  if (!granted) {
    return false;
  }
  await syncPersistentSiteContentScript();
  return true;
}

export async function removePersistentSiteAccess() {
  if (!chrome.permissions?.remove) {
    return false;
  }
  const removed = Boolean(await chrome.permissions.remove({
    origins: [...PERSISTENT_SITE_ORIGINS],
  }));
  await syncPersistentSiteContentScript();
  return removed;
}
