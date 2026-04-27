(async () => {
  try {
    await import(chrome.runtime.getURL("dist/content.js"));
  } catch (error) {
    console.error("Incremento content loader failed.", error);
  }
})();
