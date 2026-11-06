"""Temporary element removal on an offline, script-disabled import preview."""

CLEANUP_SCRIPT = r"""(() => {
  if (globalThis.incrementoCleanup) return;
  const removed = [];
  let enabled = true, selected = null, hovered = null, observer = () => {};
  const overlay = document.createElement('div');
  overlay.dataset.incrementoZapOverlay = '';
  overlay.setAttribute('aria-hidden', 'true');
  overlay.style.cssText = 'all:initial!important;position:fixed!important;pointer-events:none!important;' +
    'z-index:2147483647!important;border:2px solid #e34b55!important;background:rgba(227,75,85,.12)!important;' +
    'box-sizing:border-box!important;display:none!important';
  const label = document.createElement('span');
  label.style.cssText = 'all:initial!important;pointer-events:none!important;position:absolute!important;left:0!important;top:0!important;' +
    'max-width:320px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;' +
    'font:12px/20px system-ui,sans-serif!important;background:#a71925!important;color:white!important;padding:0 6px!important';
  const cursor = document.createElement('style');
  cursor.textContent = 'html,html *{cursor:crosshair!important}';
  overlay.append(label, cursor);
  document.documentElement.appendChild(overlay);
  const state = () => ({enabled, count:removed.length});
  const report = () => observer(state());
  const eligible = element => element instanceof Element && element.isConnected &&
    document.body.contains(element) && element !== document.body &&
    !['SCRIPT','STYLE','LINK','META','TEMPLATE'].includes(element.tagName) &&
    element.getBoundingClientRect().width > 0 && element.getBoundingClientRect().height > 0;
  const target = event => {
    let element = event.target;
    if (event.shiftKey && element instanceof Element) element = element.parentElement;
    return eligible(element) ? element : null;
  };
  const hideOverlay = () => { overlay.style.setProperty('display', 'none', 'important'); };
  const select = element => {
    const changed = selected !== element;
    selected = eligible(element) ? element : null;
    if (!selected || !enabled) { hideOverlay(); return; }
    const rect = selected.getBoundingClientRect();
    for (const [key,value] of Object.entries({display:'block',left:rect.left+'px',top:rect.top+'px',
      width:rect.width+'px',height:rect.height+'px'})) overlay.style.setProperty(key,value,'important');
    if (changed) label.textContent = '× ' + (selected.getAttribute('aria-label') || selected.getAttribute('alt') ||
      selected.textContent || selected.tagName.toLowerCase()).slice(0,200).trim().replace(/\s+/g,' ').slice(0,80);
  };
  const hover = event => { if (enabled) { hovered = event.target; select(target(event)); } };
  const clearSelection = () => { selected = hovered = null; hideOverlay(); };
  const remove = element => {
    if (!eligible(element)) return;
    removed.push({element, parent:element.parentNode, next:element.nextSibling});
    element.remove(); clearSelection(); report();
  };
  const click = event => {
    if (!enabled) return;
    event.preventDefault(); event.stopImmediatePropagation();
    remove(target(event));
  };
  const undo = (notify = true) => {
    const entry = removed.pop();
    if (!entry) return;
    entry.parent.insertBefore(entry.element, entry.next && entry.next.parentNode === entry.parent ? entry.next : null);
    clearSelection(); if (notify) report();
  };
  const setEnabled = value => { enabled = Boolean(value); cursor.disabled = !enabled; clearSelection(); report(); };
  const shift = event => { if (enabled && event.key === 'Shift' && hovered) select(target({target:hovered,shiftKey:event.type === 'keydown'})); };
  const keydown = event => {
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'z' && removed.length) {
      event.preventDefault(); event.stopImmediatePropagation(); undo(); return;
    }
    if (!enabled) return;
    if (event.key === 'Shift') { shift(event); return; }
    if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); setEnabled(false); return; }
    if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault(); event.stopImmediatePropagation(); remove(selected); return;
    }
    const directions = {ArrowUp:'parentElement',ArrowDown:'firstElementChild',ArrowLeft:'previousElementSibling',ArrowRight:'nextElementSibling'};
    if (directions[event.key] && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault(); event.stopImmediatePropagation();
      const element = selected ? selected[directions[event.key]] : Array.from(document.body.children).find(eligible);
      if (eligible(element)) select(element);
    }
  };
  document.addEventListener('mousemove', hover, true);
  document.addEventListener('focusin', hover, true);
  document.addEventListener('click', click, true);
  document.addEventListener('keydown', keydown, true);
  document.addEventListener('keyup', shift, true);
  document.addEventListener('scroll', clearSelection, true);
  window.addEventListener('resize', clearSelection);
  window.addEventListener('blur', clearSelection);
  globalThis.incrementoCleanup = {
    state, undo, setEnabled, clearSelection,
    pointer(x,y,shiftKey,removeTarget) {
      if (!enabled) return;
      hovered = document.elementFromPoint(x,y);
      const element = target({target:hovered,shiftKey});
      if (removeTarget) remove(element); else select(element);
    },
    key(event) {
      const input = {...event,preventDefault(){},stopImmediatePropagation(){}};
      if (event.type === 'keyup') shift(input); else keydown(input);
    },
    observe(callback) { observer = callback; report(); },
    reset() { while (removed.length) undo(false); report(); },
    serialize() {
      const parent = overlay.parentNode;
      overlay.remove();
      try { return '<!DOCTYPE html>\n' + document.documentElement.outerHTML; }
      finally { if (parent) parent.appendChild(overlay); }
    },
    finish() {
      setEnabled(false);
      document.removeEventListener('mousemove', hover, true);
      document.removeEventListener('focusin', hover, true);
      document.removeEventListener('click', click, true);
      document.removeEventListener('keydown', keydown, true);
      document.removeEventListener('keyup', shift, true);
      document.removeEventListener('scroll', clearSelection, true);
      window.removeEventListener('resize', clearSelection);
      window.removeEventListener('blur', clearSelection);
      overlay.remove(); observer = () => {}; removed.length = 0;
    }
  };
})();"""

def install_cleanup_input(page, view, is_enabled, exit_zap):
    """Forward native input without enabling execution of webpage scripts.

    Chromium suppresses DOM event listeners when JavascriptEnabled is false.
    Only trusted picker calls with primitive pointer/key data enter AppWorld.
    """
    import json
    from aqt.qt import QApplication, QEvent, QObject, Qt, QWebEngineScript

    class PickerInput(QObject):
        def __init__(self):
            super().__init__(view)
            self._pressed = None
            self._target = None
            self._cursor_set = False
            self._loaded = False
            view.installEventFilter(self)
            page.loadStarted.connect(lambda: setattr(self, '_loaded', False))
            page.loadFinished.connect(self.loaded)

        def loaded(self, ok):
            self._loaded = bool(ok)
            if ok and view.isVisible():
                self.attach()

        def attach(self, *_args):
            target = view.focusProxy() or view
            if target is not self._target:
                self._target = target
                target.setMouseTracking(True)
                target.installEventFilter(self)
            self.refresh()

        def refresh(self):
            if self._target is None:
                return
            if is_enabled():
                self._target.setCursor(Qt.CursorShape.CrossCursor)
                self._cursor_set = True
            elif self._cursor_set:
                self._target.unsetCursor()
                self._cursor_set = False

        def command(self, method, values):
            page.runJavaScript('globalThis.incrementoCleanup && incrementoCleanup.' + method + '(' +
                ','.join(json.dumps(value) for value in values) + ')', QWebEngineScript.ScriptWorldId.ApplicationWorld)

        def eventFilter(self, _object, event):
            kind = event.type()
            if kind == QEvent.Type.Show and self._loaded:
                self.attach()
                return False
            if kind not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.MouseMove,
                            QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick,
                            QEvent.Type.Wheel, QEvent.Type.Leave, QEvent.Type.FocusOut, QEvent.Type.Resize, QEvent.Type.Hide):
                return False
            try:
                active = bool(is_enabled())
            except RuntimeError:  # The owning toolbar can be destroyed before its view.
                return False
            if kind in (QEvent.Type.Wheel, QEvent.Type.Leave, QEvent.Type.FocusOut, QEvent.Type.Resize, QEvent.Type.Hide):
                if active:
                    self.command('clearSelection', [])
                return False
            if kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
                keys = {Qt.Key.Key_Left:'ArrowLeft', Qt.Key.Key_Right:'ArrowRight', Qt.Key.Key_Up:'ArrowUp',
                        Qt.Key.Key_Down:'ArrowDown', Qt.Key.Key_Delete:'Delete', Qt.Key.Key_Backspace:'Backspace',
                        Qt.Key.Key_Escape:'Escape', Qt.Key.Key_Shift:'Shift', Qt.Key.Key_Z:'z'}
                key = keys.get(event.key())
                modifiers = event.modifiers()
                control = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
                if active and key == 'Escape' and kind == QEvent.Type.KeyPress:
                    exit_zap()
                    return True
                if key and (active or key == 'z' and control) and (kind == QEvent.Type.KeyPress or key == 'Shift'):
                    self.command('key', [{'key':key, 'type':'keyup' if kind == QEvent.Type.KeyRelease else 'keydown',
                        'shiftKey':bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
                        'ctrlKey':control, 'metaKey':False, 'altKey':bool(modifiers & Qt.KeyboardModifier.AltModifier)}])
                    return True
            if not active:
                self._pressed = None
                return False
            if kind in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                point = view.mapFromGlobal(event.globalPosition().toPoint())
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if kind == QEvent.Type.MouseMove:
                    self.command('pointer', [point.x(),point.y(),shift,False])
                    return True
                if event.button() == Qt.MouseButton.LeftButton:
                    if kind == QEvent.Type.MouseButtonPress:
                        self._pressed = point
                    else:
                        if self._pressed is not None and (point-self._pressed).manhattanLength() < QApplication.startDragDistance():
                            self.command('pointer', [point.x(),point.y(),shift,True])
                        self._pressed = None
                    return True
            return active and kind == QEvent.Type.MouseButtonDblClick

    return PickerInput()


def create_cleanup_preview(page, parent=None):
    """Host the existing isolated page; saving prints this exact edited DOM."""
    from aqt.qt import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, Qt
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineScript
    try:
        from ..backend.i18n import t
    except ImportError:
        from backend.i18n import t

    dialog = QDialog(parent)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
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
    view._cleanup_input = install_cleanup_input(page, view, enabled.isChecked, lambda: enabled.setChecked(False))
    enabled.toggled.connect(lambda _enabled: view._cleanup_input.refresh())
    layout.addWidget(view)
    return dialog
