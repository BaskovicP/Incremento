import test from "node:test";
import assert from "node:assert/strict";

import {
  PERSISTENT_SITE_ACCESS_SCRIPT_ID,
  PERSISTENT_SITE_ORIGINS,
  hasPersistentSiteAccess,
  removePersistentSiteAccess,
  requestPersistentSiteAccess,
  syncPersistentSiteContentScript,
} from "../src/shared/siteAccess.js";


function installChromeFake({ granted = false, registered = false } = {}) {
  const calls = {
    contains: [],
    request: [],
    remove: [],
    register: [],
    update: [],
    unregister: [],
  };
  let hasGrant = granted;
  let hasRegistration = registered;
  globalThis.chrome = {
    permissions: {
      async contains(value) {
        calls.contains.push(value);
        return hasGrant;
      },
      async request(value) {
        calls.request.push(value);
        hasGrant = true;
        return true;
      },
      async remove(value) {
        calls.remove.push(value);
        hasGrant = false;
        return true;
      },
    },
    scripting: {
      async getRegisteredContentScripts() {
        return hasRegistration ? [{ id: PERSISTENT_SITE_ACCESS_SCRIPT_ID }] : [];
      },
      async registerContentScripts(value) {
        calls.register.push(value);
        hasRegistration = true;
      },
      async updateContentScripts(value) {
        calls.update.push(value);
      },
      async unregisterContentScripts(value) {
        calls.unregister.push(value);
        hasRegistration = false;
      },
    },
  };
  return calls;
}


test("persistent access registers the HTTP(S) content loader without duplicating provider injection", async () => {
  const originalChrome = globalThis.chrome;
  const calls = installChromeFake({ granted: true });

  try {
    assert.equal(await hasPersistentSiteAccess(), true);
    assert.equal(await syncPersistentSiteContentScript(), true);
    assert.equal(calls.register.length, 1);
    assert.deepEqual(calls.register[0], [{
      id: PERSISTENT_SITE_ACCESS_SCRIPT_ID,
      matches: PERSISTENT_SITE_ORIGINS,
      excludeMatches: [
        "*://*.youtube.com/*",
        "*://*.youtu.be/*",
        "*://*.vimeo.com/*",
      ],
      allFrames: true,
      js: ["content-loader.js"],
      runAt: "document_idle",
      persistAcrossSessions: true,
    }]);
  } finally {
    globalThis.chrome = originalChrome;
  }
});


test("request and removal keep optional permission and dynamic registration aligned", async () => {
  const originalChrome = globalThis.chrome;
  const calls = installChromeFake();

  try {
    assert.equal(await requestPersistentSiteAccess(), true);
    assert.deepEqual(calls.request, [{ origins: PERSISTENT_SITE_ORIGINS }]);
    assert.equal(calls.register.length, 1);

    assert.equal(await removePersistentSiteAccess(), true);
    assert.deepEqual(calls.remove, [{ origins: PERSISTENT_SITE_ORIGINS }]);
    assert.deepEqual(calls.unregister, [{ ids: [PERSISTENT_SITE_ACCESS_SCRIPT_ID] }]);
  } finally {
    globalThis.chrome = originalChrome;
  }
});


test("revoked permission removes a stale dynamic content script", async () => {
  const originalChrome = globalThis.chrome;
  const calls = installChromeFake({ granted: false, registered: true });

  try {
    assert.equal(await syncPersistentSiteContentScript(), false);
    assert.deepEqual(calls.unregister, [{ ids: [PERSISTENT_SITE_ACCESS_SCRIPT_ID] }]);
    assert.equal(calls.register.length, 0);
  } finally {
    globalThis.chrome = originalChrome;
  }
});
