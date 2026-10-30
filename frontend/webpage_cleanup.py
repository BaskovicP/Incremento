"""Temporary element removal on an offline, script-disabled import preview."""

CLEANUP_SCRIPT = r"""(() => {
  if (globalThis.incrementoCleanup) return;
  const removed = [];
  let enabled = true;
  const overlay = document.createElement('div');
  overlay.dataset.incrementoZapOverlay = '';
  overlay.style.cssText = 'position:fixed;pointer-events:none;z-index:2147483647;' +
    'border:2px solid #e34b55;background:rgba(227,75,85,.12);box-sizing:border-box;display:none';
  document.documentElement.appendChild(overlay);
  const target = event => {
    let element = event.target;
    if (event.shiftKey && element.parentElement) element = element.parentElement;
    return element !== document.body && element !== document.documentElement &&
      element !== overlay && element instanceof Element ? element : null;
  };
  const hideOverlay = () => { overlay.style.display = 'none'; };
  const hover = event => {
    if (!enabled) return;
    const element = target(event);
    if (!element) { hideOverlay(); return; }
    const rect = element.getBoundingClientRect();
    Object.assign(overlay.style, {display:'block',left:rect.left+'px',top:rect.top+'px',
      width:rect.width+'px',height:rect.height+'px'});
  };
  const click = event => {
    if (!enabled) return;
    event.preventDefault(); event.stopImmediatePropagation();
    const element = target(event);
    if (!element) return;
    removed.push({element, style:element.getAttribute('style')});
    element.style.setProperty('display', 'none', 'important');
    hideOverlay();
  };
  const undo = () => {
    const entry = removed.pop();
    if (!entry) return;
    if (entry.style === null) entry.element.removeAttribute('style');
    else entry.element.setAttribute('style', entry.style);
    hideOverlay();
  };
  document.addEventListener('mousemove', hover, true);
  document.addEventListener('click', click, true);
  document.addEventListener('scroll', hideOverlay, true);
  globalThis.incrementoCleanup = {
    undo,
    reset() { while (removed.length) undo(); },
    setEnabled(value) { enabled = Boolean(value); hideOverlay(); },
    finish() {
      enabled = false;
      document.removeEventListener('mousemove', hover, true);
      document.removeEventListener('click', click, true);
      document.removeEventListener('scroll', hideOverlay, true);
      overlay.remove();
    }
  };
})();"""


def create_cleanup_preview(page, parent=None):
    """Host the existing isolated page; saving prints this exact edited DOM."""
    from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineScript
    try:
        from ..backend.i18n import t
    except ImportError:
        from backend.i18n import t

    dialog = QDialog(parent)
    dialog.setWindowTitle(t("imports_webpage_cleanup_title"))
    dialog.resize(1100, 800)
    layout = QVBoxLayout(dialog)
    help_label = QLabel(t("imports_webpage_cleanup_help"))
    help_label.setWordWrap(True)
    layout.addWidget(help_label)
    controls = QHBoxLayout()
    enabled = QCheckBox(t("imports_webpage_cleanup_zap"))
    enabled.setChecked(True)
    controls.addWidget(enabled)
    world = QWebEngineScript.ScriptWorldId.ApplicationWorld

    def command(code):
        page.runJavaScript("globalThis.incrementoCleanup && " + code, world)

    enabled.toggled.connect(lambda value: command("incrementoCleanup.setEnabled(" + ("true" if value else "false") + ")"))
    for key, method in (("imports_webpage_cleanup_undo", "undo"), ("imports_webpage_cleanup_reset", "reset")):
        button = QPushButton(t(key))
        button.clicked.connect(lambda _checked=False, action=method: command("incrementoCleanup." + action + "()"))
        controls.addWidget(button)
    controls.addStretch()
    save = QPushButton(t("imports_webpage_cleanup_save"))
    dialog.save_button = save
    controls.addWidget(save)
    cancel = QPushButton(t("imports_cancel"))
    cancel.clicked.connect(dialog.reject)
    controls.addWidget(cancel)
    layout.addLayout(controls)
    view = QWebEngineView(dialog)
    view.setPage(page)
    layout.addWidget(view)
    return dialog
