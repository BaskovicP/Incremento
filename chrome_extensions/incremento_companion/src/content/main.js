(() => {
  const CONTENT_SCRIPT_VERSION = "browser-capture-v2";
  if (window.__incrementoContentScriptVersion === CONTENT_SCRIPT_VERSION) {
    return;
  }
  window.__incrementoContentScriptVersion = CONTENT_SCRIPT_VERSION;

  const BROWSER_CAPTURE_SETTINGS_KEY = "incremento_browser_capture_settings";
  const DEFAULT_PRIORITY = 50;
  const PRIORITY_MIN = 0;
  const PRIORITY_MAX = 100;

  function clampPriority(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return DEFAULT_PRIORITY;
    }
    return Math.min(PRIORITY_MAX, Math.max(PRIORITY_MIN, Number(numeric.toFixed(4))));
  }

  function parseTags(rawValue) {
    return Array.from(
      new Set(
        String(rawValue || "")
          .replaceAll(",", " ")
          .split(/\s+/)
          .map((tag) => tag.trim())
          .filter(Boolean)
      )
    );
  }

  function normalizeFieldMappings(rawMappings, fields) {
    const fieldNames = Array.isArray(fields) ? fields.filter(Boolean) : [];
    const firstField = fieldNames[0] || "";
    const pick = (value) => {
      if (value === "") {
        return "";
      }
      if (fieldNames.includes(value)) {
        return value;
      }
      return firstField;
    };
    return {
      selectedTextField: pick(String(rawMappings?.selectedTextField || "")),
      urlField: pick(String(rawMappings?.urlField || "")),
      snapshotField: pick(String(rawMappings?.snapshotField || "")),
    };
  }

  function normalizeBrowserCaptureSettings(rawSettings, meta) {
    const noteTypes = Array.isArray(meta?.noteTypes) ? meta.noteTypes : [];
    const deckNames = Array.isArray(meta?.deckNames) ? meta.deckNames.filter(Boolean) : [];
    const preferredNoteType = String(rawSettings?.noteTypeName || "");
    const noteType = noteTypes.find((item) => item?.name === preferredNoteType) || noteTypes[0] || null;
    const noteTypeName = noteType?.name || "";
    const fields = Array.isArray(noteType?.fields) ? noteType.fields : [];
    const mappingsByNoteType = rawSettings?.mappingsByNoteType && typeof rawSettings.mappingsByNoteType === "object"
      ? rawSettings.mappingsByNoteType
      : {};
    const fieldMappings = normalizeFieldMappings(mappingsByNoteType[noteTypeName], fields);
    const preferredDeck = String(rawSettings?.deckName || "");
    const deckName = deckNames.includes(preferredDeck) ? preferredDeck : (deckNames[0] || "Default");
    return {
      noteTypeName,
      deckName,
      priority: clampPriority(rawSettings?.priority),
      tagsText: String(rawSettings?.tagsText || ""),
      fieldMappings,
      mappingsByNoteType,
    };
  }

  function updateMappingsForNoteType(settings, noteTypeName, fieldMappings) {
    return {
      ...settings,
      noteTypeName,
      fieldMappings: { ...fieldMappings },
      mappingsByNoteType: {
        ...(settings?.mappingsByNoteType || {}),
        [noteTypeName]: { ...fieldMappings },
      },
    };
  }

  function buildBrowserCapturePayload(context, formState) {
    return {
      url: String(context?.url || "").trim(),
      title: String(context?.title || "").trim() || String(context?.url || "").trim() || "Untitled",
      selectedText: String(context?.selectedText || "").trim(),
      noteTypeName: String(formState?.noteTypeName || "").trim(),
      deckName: String(formState?.deckName || "").trim(),
      tags: parseTags(formState?.tagsText),
      priority: clampPriority(formState?.priority),
      fieldMappings: {
        selectedTextField: String(formState?.fieldMappings?.selectedTextField || "").trim(),
        urlField: String(formState?.fieldMappings?.urlField || "").trim(),
        snapshotField: String(formState?.fieldMappings?.snapshotField || "").trim(),
      },
      snapshots: Array.isArray(context?.snapshots)
        ? context.snapshots.map((snapshot, index) => ({
          mimeType: "image/png",
          filename: String(snapshot?.filename || `browser-capture-${index + 1}.png`),
          base64: String(snapshot?.base64 || "").trim(),
        })).filter((snapshot) => snapshot.base64)
        : [],
    };
  }

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

  function ensureTrackingBadge() {
    let badge = document.getElementById("incremento-tracking-badge");
    if (badge) {
      return badge;
    }
    badge = document.createElement("div");
    badge.id = "incremento-tracking-badge";
    Object.assign(badge.style, {
      position: "fixed",
      zIndex: 2147483646,
      top: "52px",
      right: "10px",
      display: "none",
      alignItems: "center",
      gap: "8px",
      padding: "8px 12px",
      background: "linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",
      color: "#fff",
      fontSize: "12px",
      fontWeight: "700",
      fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      letterSpacing: "0.08em",
      textTransform: "uppercase",
      borderRadius: "999px",
      boxShadow: "0 4px 14px rgba(0, 0, 0, 0.28)",
      backdropFilter: "blur(6px)",
      WebkitBackdropFilter: "blur(6px)",
      pointerEvents: "none",
    });

    const dot = document.createElement("span");
    dot.textContent = "●";
    Object.assign(dot.style, {
      color: "#53f2a5",
      fontSize: "13px",
      lineHeight: "1",
      textShadow: "0 0 8px rgba(83, 242, 165, 0.85)",
    });
    badge.appendChild(dot);

    const warning = document.createElement("span");
    warning.textContent = "⚠";
    Object.assign(warning.style, {
      color: "#ffd166",
      fontSize: "13px",
      lineHeight: "1",
      textShadow: "0 0 8px rgba(255, 209, 102, 0.55)",
    });
    badge.appendChild(warning);

    const label = document.createElement("span");
    label.id = "incremento-tracking-badge-label";
    label.textContent = "Tracking";
    badge.appendChild(label);

    document.documentElement.appendChild(badge);
    return badge;
  }

  function setTrackingBadge(visible, mode = "") {
    const badge = ensureTrackingBadge();
    const label = document.getElementById("incremento-tracking-badge-label");
    if (!badge || !label) {
      return;
    }
    if (!visible) {
      badge.style.display = "none";
      return;
    }
    label.textContent = mode === "web" ? "Tracking Web Card" : "Tracking";
    badge.style.display = "inline-flex";
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
      if (!msg || !msg.type) {
        return false;
      }
      if (msg.type === "SHOW_TOAST") {
        showToast(msg.text || "");
        sendResponse?.({ ok: true });
        return false;
      }
      if (msg.type === "TRIGGER_BROWSER_CAPTURE") {
        const mode = String(msg.mode || "").trim().toLowerCase();
        if (mode === "snapshot") {
          void startSnapshotCapture();
          sendResponse?.({ ok: true });
          return false;
        }
        const selectedText = String(window.getSelection?.().toString() || "").trim();
        if (!selectedText) {
          showToast("Select text on the page first.");
          sendResponse?.({ ok: false });
          return false;
        }
        void openBrowserCaptureDialog({ mode: "selection", selectedText, snapshots: [] }).then(
          () => sendResponse?.({ ok: true }),
          (error) => {
            showToast(error?.message || "Failed to open browser capture.");
            closeBrowserCaptureUi();
            sendResponse?.({ ok: false, error: String(error?.message || "") });
          }
        );
        return true;
      }
      return false;
    });
  } catch (_err) {
    // stale/invalidated context
  }

  let browserCaptureUi = null;
  let browserCaptureState = null;

  function runtimeRequest(message) {
    return new Promise((resolve, reject) => {
      const rt = getRuntime();
      if (!rt?.sendMessage) {
        reject(new Error("Incremento extension runtime is unavailable."));
        return;
      }
      rt.sendMessage(message, (response) => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(error.message || "Extension request failed."));
          return;
        }
        resolve(response || null);
      });
    });
  }

  async function loadBrowserCaptureMeta() {
    const response = await runtimeRequest({ type: "LOAD_BROWSER_CAPTURE_META" });
    if (!response?.ok) {
      throw new Error(String(response?.error || "Failed to load browser capture metadata."));
    }
    return response;
  }

  async function submitBrowserCapture(payload) {
    const response = await runtimeRequest({ type: "SUBMIT_BROWSER_CAPTURE", payload });
    if (!response?.ok) {
      throw new Error(String(response?.error || "Failed to submit browser capture."));
    }
    return response;
  }

  async function captureVisibleTabPng() {
    const response = await runtimeRequest({ type: "CAPTURE_VISIBLE_TAB" });
    if (!response?.ok || !response?.dataUrl) {
      throw new Error(String(response?.error || "Failed to capture the current tab."));
    }
    return response.dataUrl;
  }

  async function loadBrowserCaptureSettings(meta) {
    let stored = {};
    try {
      const data = await chrome.storage.local.get(BROWSER_CAPTURE_SETTINGS_KEY);
      stored = data?.[BROWSER_CAPTURE_SETTINGS_KEY] || {};
    } catch (_err) {
      stored = {};
    }
    return normalizeBrowserCaptureSettings(stored, meta);
  }

  async function saveBrowserCaptureSettings(settings) {
    try {
      await chrome.storage.local.set({
        [BROWSER_CAPTURE_SETTINGS_KEY]: {
          noteTypeName: String(settings?.noteTypeName || ""),
          deckName: String(settings?.deckName || ""),
          priority: Number(settings?.priority ?? DEFAULT_PRIORITY),
          tagsText: String(settings?.tagsText || ""),
          mappingsByNoteType: settings?.mappingsByNoteType || {},
        },
      });
    } catch (_err) {
      // ignore storage write failures
    }
  }

  function isEditableTarget(target) {
    if (!target || !(target instanceof Element)) {
      return false;
    }
    if (target.closest("input, textarea, select")) {
      return true;
    }
    return !!target.closest('[contenteditable=""], [contenteditable="true"]');
  }

  function isBrowserCaptureOpen() {
    return !!browserCaptureUi;
  }

  function isBrowserCaptureKey(event) {
    return String(event?.code || "").toLowerCase() === "keyx";
  }

  function ensureBrowserCaptureUiRoot() {
    if (browserCaptureUi) {
      return browserCaptureUi;
    }
    const host = document.createElement("div");
    host.id = "incremento-browser-capture-root";
    host.style.all = "initial";
    const shadow = host.attachShadow({ mode: "open" });
    document.documentElement.appendChild(host);

    const style = document.createElement("style");
    style.textContent = `
      :host { all: initial; }
      *, *::before, *::after { box-sizing: border-box; }
      .shell {
        position: fixed;
        inset: 0;
        z-index: 2147483645;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        color: #1f2328;
      }
      .backdrop {
        position: absolute;
        inset: 0;
        background: rgba(12, 18, 26, 0.42);
      }
      .panel {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: min(760px, calc(100vw - 32px));
        max-height: calc(100vh - 32px);
        overflow: auto;
        border-radius: 24px;
        border: 1px solid rgba(90, 74, 47, 0.18);
        background:
          radial-gradient(circle at top left, rgba(255, 219, 161, 0.7), transparent 42%),
          linear-gradient(170deg, rgba(255, 251, 244, 0.98), rgba(245, 236, 223, 0.97));
        box-shadow: 0 28px 80px rgba(22, 23, 25, 0.32);
        padding: 22px;
      }
      .capture-shell {
        position: absolute;
        inset: 0;
        cursor: crosshair;
      }
      .capture-toolbar {
        position: absolute;
        top: 14px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: min(860px, calc(100vw - 24px));
        max-width: calc(100vw - 24px);
        padding: 12px 14px;
        border-radius: 18px;
        background: rgba(17, 25, 34, 0.92);
        color: #fff;
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.3);
      }
      .capture-toolbar strong {
        font-size: 13px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
      }
      .capture-toolbar span {
        font-size: 13px;
        opacity: 0.82;
      }
      .capture-toolbar .spacer {
        flex: 1;
      }
      .toolbar-btn,
      .primary-btn,
      .secondary-btn,
      .ghost-btn {
        border: 0;
        border-radius: 13px;
        padding: 10px 14px;
        font: inherit;
        cursor: pointer;
      }
      .toolbar-btn {
        background: rgba(255, 255, 255, 0.12);
        color: #fff;
      }
      .toolbar-btn.primary {
        background: linear-gradient(135deg, #b86a17, #e0932f);
      }
      .eyebrow {
        margin: 0 0 6px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #8f5a1e;
      }
      h2 {
        margin: 0 0 12px;
        font-size: 24px;
        line-height: 1.08;
      }
      .lead, .status, .field-note {
        margin: 0;
        font-size: 13px;
        line-height: 1.45;
        color: #5c5b57;
      }
      .status.error { color: #ab2f2f; }
      .status.success { color: #216c3f; }
      .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin-top: 16px;
      }
      .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .field.full { grid-column: 1 / -1; }
      .field label {
        font-size: 12px;
        font-weight: 700;
        color: #433720;
      }
      .field input,
      .field textarea,
      .field select {
        width: 100%;
        border: 1px solid rgba(82, 68, 45, 0.18);
        border-radius: 13px;
        background: rgba(255, 255, 255, 0.9);
        padding: 11px 12px;
        font: inherit;
        color: inherit;
      }
      .field textarea {
        min-height: 110px;
        resize: vertical;
      }
      .field input[type="range"] {
        padding: 0;
      }
      .field input:focus,
      .field textarea:focus,
      .field select:focus {
        outline: 2px solid rgba(184, 106, 23, 0.2);
        border-color: rgba(184, 106, 23, 0.38);
      }
      .snapshots {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px;
      }
      .snapshot-card {
        overflow: hidden;
        border: 1px solid rgba(82, 68, 45, 0.14);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
      }
      .snapshot-card img {
        display: block;
        width: 100%;
        height: 108px;
        object-fit: cover;
        background: #e8dfd2;
      }
      .snapshot-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding: 8px 10px 10px;
      }
      .snapshot-footer span {
        font-size: 12px;
        color: #4d4b46;
      }
      .snapshot-footer button {
        border: 0;
        border-radius: 10px;
        padding: 6px 8px;
        background: rgba(171, 47, 47, 0.1);
        color: #8f2222;
        font: inherit;
        cursor: pointer;
      }
      .actions {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 18px;
      }
      .primary-btn {
        background: linear-gradient(135deg, #9e5d12 0%, #d88219 100%);
        color: #fffdf8;
        font-weight: 700;
      }
      .secondary-btn {
        background: rgba(88, 73, 44, 0.09);
        color: #473a24;
        font-weight: 600;
      }
      .ghost-btn {
        background: rgba(88, 73, 44, 0.08);
        color: #473a24;
      }
      .selection-rect {
        position: absolute;
        border: 2px solid rgba(255, 171, 64, 0.96);
        background: rgba(255, 193, 101, 0.2);
        box-shadow: 0 0 0 1px rgba(20, 20, 20, 0.24), 0 12px 32px rgba(0, 0, 0, 0.16);
      }
      .selection-rect::after {
        content: attr(data-label);
        position: absolute;
        top: -26px;
        left: 0;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(17, 25, 34, 0.9);
        color: #fff;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      @media (max-width: 720px) {
        .grid {
          grid-template-columns: 1fr;
        }
        .panel {
          width: calc(100vw - 16px);
          padding: 18px;
        }
        .capture-toolbar {
          flex-wrap: wrap;
          justify-content: center;
        }
        .capture-toolbar .spacer {
          display: none;
        }
      }
    `;
    shadow.appendChild(style);

    const shell = document.createElement("div");
    shell.className = "shell";
    shadow.appendChild(shell);

    browserCaptureUi = { host, shadow, shell };
    return browserCaptureUi;
  }

  function closeBrowserCaptureUi() {
    if (browserCaptureUi?.host?.isConnected) {
      browserCaptureUi.host.remove();
    }
    browserCaptureUi = null;
    browserCaptureState = null;
  }

  function clearShell() {
    const ui = ensureBrowserCaptureUiRoot();
    ui.shell.textContent = "";
  }

  function renderSnapshotCards(shadow, snapshots) {
    const wrap = document.createElement("div");
    wrap.className = "snapshots";
    for (const snapshot of snapshots) {
      const card = document.createElement("div");
      card.className = "snapshot-card";

      const image = document.createElement("img");
      image.src = snapshot.dataUrl;
      image.alt = snapshot.filename;
      card.appendChild(image);

      const footer = document.createElement("div");
      footer.className = "snapshot-footer";

      const label = document.createElement("span");
      label.textContent = snapshot.filename;
      footer.appendChild(label);

      const removeButton = document.createElement("button");
      removeButton.type = "button";
      removeButton.textContent = "Remove";
      removeButton.addEventListener("click", () => {
        browserCaptureState.snapshots = browserCaptureState.snapshots.filter((item) => item.id !== snapshot.id);
        renderBrowserCaptureDialog();
      });
      footer.appendChild(removeButton);

      card.appendChild(footer);
      wrap.appendChild(card);
    }
    return wrap;
  }

  async function renderBrowserCaptureDialog() {
    const ui = ensureBrowserCaptureUiRoot();
    const { shell, shadow } = ui;
    const state = browserCaptureState;
    clearShell();

    const backdrop = document.createElement("div");
    backdrop.className = "backdrop";
    backdrop.addEventListener("click", () => closeBrowserCaptureUi());
    shell.appendChild(backdrop);

    const panel = document.createElement("section");
    panel.className = "panel";
    shell.appendChild(panel);

    const eyebrow = document.createElement("p");
    eyebrow.className = "eyebrow";
    eyebrow.textContent = state.mode === "snapshot" ? "Browser snapshot" : "Browser selection";
    panel.appendChild(eyebrow);

    const title = document.createElement("h2");
    title.textContent = "Send capture to Anki";
    panel.appendChild(title);

    const lead = document.createElement("p");
    lead.className = "lead";
    lead.textContent = state.mode === "snapshot"
      ? `${state.snapshots.length} snapshot${state.snapshots.length === 1 ? "" : "s"} ready from ${state.context.url}`
      : `Selected text from ${state.context.url}`;
    panel.appendChild(lead);

    const form = document.createElement("form");
    form.noValidate = true;
    const grid = document.createElement("div");
    grid.className = "grid";
    form.appendChild(grid);

    const createField = (labelText, control, full = false, noteText = "") => {
      const field = document.createElement("div");
      field.className = `field${full ? " full" : ""}`;
      const label = document.createElement("label");
      label.textContent = labelText;
      field.appendChild(label);
      field.appendChild(control);
      if (noteText) {
        const note = document.createElement("p");
        note.className = "field-note";
        note.textContent = noteText;
        field.appendChild(note);
      }
      return field;
    };

    const noteTypeSelect = document.createElement("select");
    for (const noteType of state.meta.noteTypes) {
      const option = document.createElement("option");
      option.value = noteType.name;
      option.textContent = noteType.name;
      noteTypeSelect.appendChild(option);
    }
    noteTypeSelect.value = state.form.noteTypeName;
    noteTypeSelect.addEventListener("change", () => {
      const nextNoteType = state.meta.noteTypes.find((item) => item.name === noteTypeSelect.value);
      const nextMappings = normalizeFieldMappings(
        state.form.mappingsByNoteType?.[noteTypeSelect.value],
        nextNoteType?.fields || []
      );
      state.form = updateMappingsForNoteType(state.form, noteTypeSelect.value, nextMappings);
      renderBrowserCaptureDialog();
    });
    grid.appendChild(createField("Note type", noteTypeSelect));

    const deckSelect = document.createElement("select");
    for (const deckName of state.meta.deckNames) {
      const option = document.createElement("option");
      option.value = deckName;
      option.textContent = deckName;
      deckSelect.appendChild(option);
    }
    deckSelect.value = state.form.deckName;
    deckSelect.addEventListener("change", () => {
      state.form.deckName = deckSelect.value;
    });
    grid.appendChild(createField("Deck", deckSelect));

    const tagsInput = document.createElement("input");
    tagsInput.type = "text";
    tagsInput.value = state.form.tagsText;
    tagsInput.placeholder = "tag-one tag-two";
    tagsInput.addEventListener("input", () => {
      state.form.tagsText = tagsInput.value;
    });
    grid.appendChild(createField("Tags", tagsInput, true));

    const priorityWrap = document.createElement("div");
    priorityWrap.style.display = "grid";
    priorityWrap.style.gridTemplateColumns = "1fr auto";
    priorityWrap.style.gap = "10px";
    priorityWrap.style.alignItems = "center";
    const prioritySlider = document.createElement("input");
    prioritySlider.type = "range";
    prioritySlider.min = "0";
    prioritySlider.max = "100";
    prioritySlider.step = "0.1";
    prioritySlider.value = String(state.form.priority ?? DEFAULT_PRIORITY);
    const priorityValue = document.createElement("input");
    priorityValue.type = "number";
    priorityValue.min = "0";
    priorityValue.max = "100";
    priorityValue.step = "0.1";
    priorityValue.style.width = "92px";
    priorityValue.value = String(state.form.priority ?? DEFAULT_PRIORITY);
    const syncPriority = (value) => {
      const numeric = Number(value);
      const safe = Number.isFinite(numeric) ? Math.min(100, Math.max(0, numeric)) : DEFAULT_PRIORITY;
      state.form.priority = Number(safe.toFixed(4));
      prioritySlider.value = String(state.form.priority);
      priorityValue.value = String(state.form.priority);
    };
    prioritySlider.addEventListener("input", () => syncPriority(prioritySlider.value));
    priorityValue.addEventListener("change", () => syncPriority(priorityValue.value));
    priorityWrap.appendChild(prioritySlider);
    priorityWrap.appendChild(priorityValue);
    grid.appendChild(createField("Priority", priorityWrap));

    const fields = state.meta.noteTypes.find((item) => item.name === state.form.noteTypeName)?.fields || [];
    const mappingOptions = ["", ...fields];
    const makeMappingSelect = (currentValue, onChange) => {
      const select = document.createElement("select");
      for (const fieldName of mappingOptions) {
        const option = document.createElement("option");
        option.value = fieldName;
        option.textContent = fieldName || "Do not insert";
        select.appendChild(option);
      }
      select.value = mappingOptions.includes(currentValue) ? currentValue : "";
      select.addEventListener("change", () => {
        onChange(select.value);
      });
      return select;
    };

    const hasTextContent = Boolean(state.context.selectedText);
    grid.appendChild(createField(
      "Selected text field",
      makeMappingSelect(state.form.fieldMappings.selectedTextField, (value) => {
        state.form = updateMappingsForNoteType(state.form, state.form.noteTypeName, {
          ...state.form.fieldMappings,
          selectedTextField: value,
        });
      }),
      false,
      hasTextContent
        ? `${state.context.selectedText.length} chars ready for insertion.`
        : "No text added yet."
    ));

    grid.appendChild(createField(
      "Source URL field",
      makeMappingSelect(state.form.fieldMappings.urlField, (value) => {
        state.form = updateMappingsForNoteType(state.form, state.form.noteTypeName, {
          ...state.form.fieldMappings,
          urlField: value,
        });
      }),
      false,
      "The current page URL is always available."
    ));

    grid.appendChild(createField(
      "Snapshot field",
      makeMappingSelect(state.form.fieldMappings.snapshotField, (value) => {
        state.form = updateMappingsForNoteType(state.form, state.form.noteTypeName, {
          ...state.form.fieldMappings,
          snapshotField: value,
        });
      }),
      true,
      state.snapshots.length > 0 ? `${state.snapshots.length} snapshot${state.snapshots.length === 1 ? "" : "s"} selected.` : "No snapshot images in this capture."
    ));

    const selectedTextInput = document.createElement("textarea");
    selectedTextInput.value = state.context.selectedText;
    selectedTextInput.placeholder = state.mode === "snapshot"
      ? "Add text to store with these snapshots..."
      : "Selected text will appear here. You can edit it before saving.";
    selectedTextInput.addEventListener("input", () => {
      state.context.selectedText = selectedTextInput.value;
    });
    grid.appendChild(createField(
      state.mode === "snapshot" ? "Text to add" : "Selected text",
      selectedTextInput,
      true,
      "This content is inserted into the selected text field if one is chosen."
    ));

    if (state.snapshots.length > 0) {
      const snapshotWrap = document.createElement("div");
      snapshotWrap.className = "field full";
      const label = document.createElement("label");
      label.textContent = "Snapshots";
      snapshotWrap.appendChild(label);
      snapshotWrap.appendChild(renderSnapshotCards(shadow, state.snapshots));
      grid.appendChild(snapshotWrap);
    }

    const status = document.createElement("p");
    status.className = `status${state.statusKind ? ` ${state.statusKind}` : ""}`;
    status.textContent = state.statusText;
    form.appendChild(status);

    const actions = document.createElement("div");
    actions.className = "actions";

    if (state.snapshots.length > 0) {
      const addMoreButton = document.createElement("button");
      addMoreButton.type = "button";
      addMoreButton.className = "ghost-btn";
      addMoreButton.textContent = "Capture more";
      addMoreButton.addEventListener("click", () => startSnapshotCapture(state.snapshots));
      actions.appendChild(addMoreButton);
    }

    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.className = "secondary-btn";
    cancelButton.textContent = "Cancel";
    cancelButton.addEventListener("click", () => closeBrowserCaptureUi());
    actions.appendChild(cancelButton);

    const submitButton = document.createElement("button");
    submitButton.type = "submit";
    submitButton.className = "primary-btn";
    submitButton.textContent = state.submitting ? "Saving..." : "Create note";
    submitButton.disabled = !!state.submitting;
    actions.appendChild(submitButton);

    form.appendChild(actions);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (state.submitting) {
        return;
      }
      const payload = buildBrowserCapturePayload(
        {
          ...state.context,
          snapshots: state.snapshots.map((snapshot) => ({
            filename: snapshot.filename,
            base64: snapshot.base64,
          })),
        },
        state.form
      );
      const hasMappedContent = Boolean(
        (payload.selectedText && payload.fieldMappings.selectedTextField)
        || payload.fieldMappings.urlField
        || (payload.snapshots.length > 0 && payload.fieldMappings.snapshotField)
      );
      if (!payload.noteTypeName || !payload.deckName) {
        state.statusKind = "error";
        state.statusText = "Choose a note type and deck.";
        renderBrowserCaptureDialog();
        return;
      }
      if (!hasMappedContent) {
        state.statusKind = "error";
        state.statusText = "Map at least one available capture part to a note field.";
        renderBrowserCaptureDialog();
        return;
      }

      state.submitting = true;
      state.statusKind = "";
      state.statusText = "Creating note in Anki...";
      renderBrowserCaptureDialog();
      try {
        const result = await submitBrowserCapture(payload);
        await saveBrowserCaptureSettings(state.form);
        showToast(`Created ${result.noteTypeName} note in ${result.deckName}.`);
        closeBrowserCaptureUi();
      } catch (error) {
        state.submitting = false;
        state.statusKind = "error";
        state.statusText = error?.message || "Failed to create note.";
        renderBrowserCaptureDialog();
      }
    });

    panel.appendChild(form);
  }

  function loadImage(dataUrl) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Failed to decode screenshot."));
      img.src = dataUrl;
    });
  }

  async function cropScreenshotDataUrl(dataUrl, region) {
    const image = await loadImage(dataUrl);
    const scaleX = image.width / window.innerWidth;
    const scaleY = image.height / window.innerHeight;
    const sx = Math.max(0, Math.round(region.x * scaleX));
    const sy = Math.max(0, Math.round(region.y * scaleY));
    const sw = Math.max(1, Math.round(region.width * scaleX));
    const sh = Math.max(1, Math.round(region.height * scaleY));
    const canvas = document.createElement("canvas");
    canvas.width = sw;
    canvas.height = sh;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(image, sx, sy, sw, sh, 0, 0, sw, sh);
    return canvas.toDataURL("image/png");
  }

  function dataUrlToBase64(dataUrl) {
    const raw = String(dataUrl || "");
    const index = raw.indexOf(",");
    return index >= 0 ? raw.slice(index + 1) : raw;
  }

  function normalizeSelectionRect(rect) {
    const width = Math.abs(rect.width);
    const height = Math.abs(rect.height);
    return {
      x: rect.width >= 0 ? rect.x : rect.x - width,
      y: rect.height >= 0 ? rect.y : rect.y - height,
      width,
      height,
    };
  }

  function waitForNextPaint(frames = 2) {
    return new Promise((resolve) => {
      const remaining = Math.max(1, Number(frames) || 1);
      let count = 0;
      const step = () => {
        count += 1;
        if (count >= remaining) {
          resolve();
          return;
        }
        requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }

  async function captureSnapshotRegion(region, existingSnapshots = []) {
    const ui = ensureBrowserCaptureUiRoot();
    ui.shell.style.display = "none";
    try {
      await waitForNextPaint(2);
      const dataUrl = await captureVisibleTabPng();
      const normalizedRegion = normalizeSelectionRect(region);
      const croppedDataUrl = await cropScreenshotDataUrl(dataUrl, normalizedRegion);
      return {
        id: `${Date.now()}-${existingSnapshots.length}-${Math.random().toString(16).slice(2, 8)}`,
        filename: `browser-capture-${existingSnapshots.length + 1}.png`,
        dataUrl: croppedDataUrl,
        base64: dataUrlToBase64(croppedDataUrl),
      };
    } catch (error) {
      throw new Error(error?.message || "Failed to capture the current tab.");
    } finally {
      if (browserCaptureUi?.shell) {
        browserCaptureUi.shell.style.display = "";
        await waitForNextPaint(1);
      }
    }
  }

  function startSnapshotCapture(existingSnapshots = []) {
    const ui = ensureBrowserCaptureUiRoot();
    clearShell();
    browserCaptureState = {
      mode: "snapshot",
      meta: browserCaptureState?.meta || null,
      form: browserCaptureState?.form || null,
      context: {
        url: window.location.href || "",
        title: document.title || "",
        selectedText: browserCaptureState?.context?.selectedText || "",
      },
      snapshots: [...existingSnapshots],
      statusKind: "",
      statusText: "",
      submitting: false,
    };

    const shell = ui.shell;
    const backdrop = document.createElement("div");
    backdrop.className = "backdrop";
    shell.appendChild(backdrop);

    const captureShell = document.createElement("div");
    captureShell.className = "capture-shell";
    shell.appendChild(captureShell);

    const toolbar = document.createElement("div");
    toolbar.className = "capture-toolbar";
    toolbar.innerHTML = `
      <strong>Snapshot Mode</strong>
      <span>Draw one or more rectangles on the page. The capture is limited to the current viewport.</span>
      <span class="spacer"></span>
    `;
    shell.appendChild(toolbar);

    const snapshots = [...existingSnapshots];
    let activeRect = null;
    let activeRegion = null;
    let captureInFlight = false;

    const updateToolbar = () => {
      toolbar.innerHTML = `
        <strong>Snapshot Mode</strong>
        <span>Draw a rectangle to capture it immediately, then scroll and capture another area if needed.</span>
        <span class="spacer"></span>
      `;
      const count = document.createElement("span");
      count.textContent = captureInFlight
        ? "Capturing..."
        : `${snapshots.length} snapshot${snapshots.length === 1 ? "" : "s"} ready`;
      toolbar.appendChild(count);

      const undoButton = document.createElement("button");
      undoButton.type = "button";
      undoButton.className = "toolbar-btn";
      undoButton.textContent = "Undo";
      undoButton.disabled = captureInFlight || snapshots.length === 0;
      undoButton.addEventListener("click", () => {
        snapshots.pop();
        updateToolbar();
      });
      toolbar.appendChild(undoButton);

      const clearButton = document.createElement("button");
      clearButton.type = "button";
      clearButton.className = "toolbar-btn";
      clearButton.textContent = "Clear";
      clearButton.disabled = captureInFlight || snapshots.length === 0;
      clearButton.addEventListener("click", () => {
        snapshots.splice(0, snapshots.length);
        updateToolbar();
      });
      toolbar.appendChild(clearButton);

      const cancelButton = document.createElement("button");
      cancelButton.type = "button";
      cancelButton.className = "toolbar-btn";
      cancelButton.textContent = "Cancel";
      cancelButton.addEventListener("click", () => closeBrowserCaptureUi());
      toolbar.appendChild(cancelButton);

      const doneButton = document.createElement("button");
      doneButton.type = "button";
      doneButton.className = "toolbar-btn primary";
      doneButton.textContent = "Continue";
      doneButton.addEventListener("click", () => {
        if (captureInFlight) {
          return;
        }
        if (!snapshots.length) {
          showToast("Draw at least one region first.");
          return;
        }
        void openBrowserCaptureDialog({
          mode: "snapshot",
          selectedText: browserCaptureState?.context?.selectedText || "",
          snapshots: [...snapshots],
        });
      });
      toolbar.appendChild(doneButton);
    };

    const beginRect = (x, y) => {
      activeRegion = { x, y, width: 0, height: 0 };
      activeRect = document.createElement("div");
      activeRect.className = "selection-rect";
      activeRect.dataset.label = `Capture ${snapshots.length + 1}`;
      captureShell.appendChild(activeRect);
    };

    const syncActiveRect = () => {
      if (!activeRect || !activeRegion) {
        return;
      }
      const normalized = normalizeSelectionRect(activeRegion);
      Object.assign(activeRect.style, {
        left: `${normalized.x}px`,
        top: `${normalized.y}px`,
        width: `${normalized.width}px`,
        height: `${normalized.height}px`,
      });
    };

    captureShell.addEventListener("pointerdown", (event) => {
      if (captureInFlight || event.button !== 0 || event.target !== captureShell) {
        return;
      }
      event.preventDefault();
      beginRect(event.clientX, event.clientY);
      syncActiveRect();
    });

    captureShell.addEventListener("pointermove", (event) => {
      if (!activeRegion) {
        return;
      }
      event.preventDefault();
      activeRegion.width = event.clientX - activeRegion.x;
      activeRegion.height = event.clientY - activeRegion.y;
      syncActiveRect();
    });

    const finishActiveRect = async () => {
      if (!activeRect || !activeRegion) {
        return;
      }
      const normalized = normalizeSelectionRect(activeRegion);
      const rectToRemove = activeRect;
      if (normalized.width >= 24 && normalized.height >= 24) {
        captureInFlight = true;
        updateToolbar();
        try {
          const snapshot = await captureSnapshotRegion(normalized, snapshots);
          snapshots.push(snapshot);
        } catch (error) {
          showToast(error?.message || "Failed to capture the current tab.");
        }
      } else {
        rectToRemove.remove();
      }
      rectToRemove.remove();
      activeRect = null;
      activeRegion = null;
      captureInFlight = false;
      updateToolbar();
    };

    captureShell.addEventListener("pointerup", () => {
      void finishActiveRect();
    });
    captureShell.addEventListener("pointercancel", () => {
      void finishActiveRect();
    });
    updateToolbar();
  }

  async function openBrowserCaptureDialog({ mode, selectedText = "", snapshots = [] }) {
    const meta = browserCaptureState?.meta || await loadBrowserCaptureMeta();
    if (!Array.isArray(meta?.noteTypes) || meta.noteTypes.length === 0) {
      throw new Error("No note types are available in Anki.");
    }
    if (!Array.isArray(meta?.deckNames) || meta.deckNames.length === 0) {
      throw new Error("No decks are available in Anki.");
    }
    const currentSettings = browserCaptureState?.form || await loadBrowserCaptureSettings(meta);
    browserCaptureState = {
      mode,
      meta,
      form: currentSettings,
      context: {
        url: window.location.href || "",
        title: document.title || "",
        selectedText: String(selectedText || "").trim(),
      },
      snapshots: Array.isArray(snapshots) ? snapshots : [],
      statusKind: "",
      statusText: "",
      submitting: false,
    };
    await renderBrowserCaptureDialog();
  }

  globalThis.__incrementoTriggerBrowserCapture = (mode) => {
    const captureMode = String(mode || "").trim().toLowerCase();
    if (captureMode === "snapshot") {
      void startSnapshotCapture();
      return { ok: true };
    }
    const selectedText = String(window.getSelection?.().toString() || "").trim();
    if (!selectedText) {
      showToast("Select text on the page first.");
      return { ok: false, error: "Select text on the page first." };
    }
    void openBrowserCaptureDialog({ mode: "selection", selectedText, snapshots: [] }).catch((error) => {
      showToast(error?.message || "Failed to open browser capture.");
      closeBrowserCaptureUi();
    });
    return { ok: true };
  };

  document.addEventListener("keydown", (event) => {
    if (!event.altKey || !isBrowserCaptureKey(event)) {
      return;
    }
    if (isBrowserCaptureOpen()) {
      return;
    }
    if (isEditableTarget(event.target)) {
      return;
    }

    if (event.metaKey) {
      event.preventDefault();
      event.stopPropagation();
      void startSnapshotCapture();
      return;
    }

    if (event.ctrlKey || event.shiftKey) {
      return;
    }

    const selectedText = String(window.getSelection?.().toString() || "").trim();
    if (!selectedText) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    void openBrowserCaptureDialog({ mode: "selection", selectedText, snapshots: [] }).catch((error) => {
      showToast(error?.message || "Failed to open browser capture.");
      closeBrowserCaptureUi();
    });
  }, true);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isBrowserCaptureOpen()) {
      event.preventDefault();
      event.stopPropagation();
      closeBrowserCaptureUi();
    }
  }, true);

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
  let badgePoll = null;
  let lastSeenHref = window.location.href || "";

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

  function fetchTrackingStatus() {
    if (!extensionAlive) {
      setTrackingBadge(false);
      return;
    }
    try {
      const rt = getRuntime();
      if (!rt?.id) {
        setTrackingBadge(false);
        return;
      }
      rt.sendMessage(
        {
          type: "GET_TRACKING_STATUS",
          url: window.location.href || "",
        },
        (response) => {
          try {
            const err = rt?.lastError;
            if (err) {
              setTrackingBadge(false);
              return;
            }
          } catch (_err) {
            setTrackingBadge(false);
            return;
          }
          setTrackingBadge(Boolean(response?.tracked), String(response?.mode || ""));
        }
      );
    } catch (_err) {
      setTrackingBadge(false);
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
  badgePoll = window.setInterval(() => {
    const nextHref = window.location.href || "";
    if (nextHref !== lastSeenHref) {
      lastSeenHref = nextHref;
      fetchTrackingStatus();
    }
  }, 750);
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
  window.setTimeout(fetchTrackingStatus, 300);
  window.addEventListener("unload", () => {
    try {
      clearInterval(periodic);
      clearInterval(badgePoll);
    } catch (_err) {
      // noop
    }
  });
})();
