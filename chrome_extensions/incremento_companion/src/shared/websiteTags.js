import { parseTags } from "../bookmarks/bookmarkModel.js";

export function websiteOrigin(value) {
  if (typeof value !== "string" || /[\s\x00-\x1f\x7f]/.test(value)) return "";
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.origin : "";
  } catch (_error) {
    return "";
  }
}

// Keep the latest edit while a request runs. Never let a late read/save replace
// typing or a newer website, and bind every write to its loaded Anki profile.
export function createWebsiteTagPreferences({load, save, onState, onTags}) {
  let disposed = false;
  let generation = 0;
  let origin = "";
  let profileToken = "";
  let text = "";
  let pending = null;
  let running = null;
  let state = {site: "", enabled: false, ready: false, loading: false, saving: false, error: null};
  const emit = patch => {
    state = {...state, ...patch};
    if (!disposed) onState({...state});
  };

  function queueSave() {
    if (disposed || !state.ready) return;
    pending = {generation, payload: {url: origin, enabled: state.enabled,
      tags: state.enabled ? parseTags(text) : [], profileToken}};
    emit({saving: true, error: null});
    if (running) return;
    running = (async () => {
      while (pending) {
        const current = pending;
        pending = null;
        try {
          await save(current.payload);
          if (current.generation === generation) emit({error: null});
        } catch (error) {
          if (current.generation === generation) emit({error});
        }
      }
    })().finally(() => {running = null; emit({saving: false});});
  }

  const model = {
    async load(url) {
      if (disposed) return;
      const current = ++generation;
      origin = websiteOrigin(url);
      profileToken = "";
      text = "";
      pending = null;
      onTags("");
      emit({site: "", enabled: false, ready: false, loading: Boolean(origin), saving: false, error: null});
      if (!origin) return;
      try {
        const result = await load(origin);
        if (disposed || current !== generation) return;
        profileToken = result.profileToken;
        text = result.enabled ? result.tags.join(" ") : "";
        onTags(text);
        emit({site: result.site, enabled: result.enabled === true, ready: true, loading: false});
      } catch (error) {
        if (!disposed && current === generation) emit({loading: false, error});
      }
    },
    changeTags(value) {
      text = value;
      if (!disposed) onTags(value);
      if (state.enabled) queueSave();
    },
    setEnabled(enabled) {
      if (disposed || !state.ready) return;
      emit({enabled});
      queueSave();
    },
    retry() {
      if (state.ready) queueSave();
      else void model.load(origin);
    },
    async flush() {
      while (running) await running;
      if (state.ready && state.error) throw state.error;
    },
    dispose() {disposed = true; ++generation;},
  };
  return model;
}
