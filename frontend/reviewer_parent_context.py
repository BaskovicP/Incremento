"""Open an extract's parent beside the live reviewer without changing review state."""
from html import escape
import json
from pathlib import Path
import secrets

from aqt import mw
from aqt.operations import QueryOp
from aqt.qt import QDockWidget, QTextBrowser, Qt

try:
    from ..backend.card_context import load_parent_context
    from ..backend.config_service import load_addon_config, configured_reviewer_parent_context_enabled
    from ..backend.i18n import t
    from ..backend.paths import get_active_profile
except ImportError:
    from backend.card_context import load_parent_context
    from backend.config_service import load_addon_config, configured_reviewer_parent_context_enabled
    from backend.i18n import t
    from backend.paths import get_active_profile

_ADDON_DIR = str(Path(__file__).resolve().parent.parent)
_ADDON_PKG = __name__.split('.')[0]
_PREFIX = 'incremento_parent_context:'
_command = ''
_review_context = None
_snapshot = None
_dock = None
_open_request = 0


class ContextBrowser(QTextBrowser):
    def loadResource(self, _kind, _url):
        # Even sanitized parent content must never load a local/remote resource.
        return None


class ContextDock(QDockWidget):
    def closeEvent(self, event):
        global _open_request
        _open_request += 1
        self.widget().clear()
        super().closeEvent(event)


def _context():
    reviewer = getattr(mw, 'reviewer', None)
    card = getattr(reviewer, 'card', None)
    return (get_active_profile(), mw.col,
            int(card.id) if getattr(mw, 'state', '') == 'review' and card is not None else 0)


def _render_link(parent):
    data = json.dumps(dict(parent=parent, command=_command, label=t('study_parent'),
                           unavailable=t('study_unavailable')))
    mw.reviewer.web.eval("""(() => {
      const data = %s;
      document.getElementById('incremento-parent-context')?.remove();
      let style = document.getElementById('incremento-parent-context-style');
      if (!style) {
        style = document.createElement('style');
        style.id = 'incremento-parent-context-style';
        document.head.appendChild(style);
      }
      style.textContent = `
        button#incremento-parent-context[data-parent-state] {
          --parent-bg: #eef1f4; --parent-ink: #717b88; --parent-border: #d6dce4;
          appearance: none !important; box-sizing: border-box !important;
          display: inline-flex !important; flex: 0 0 32px !important;
          width: 32px !important; min-width: 32px !important; max-width: 32px !important;
          height: 32px !important; min-height: 32px !important; max-height: 32px !important;
          align-items: center !important; justify-content: center !important;
          margin: 0 0 8px !important; padding: 7px !important;
          border: 1px solid var(--parent-border) !important; border-radius: 8px !important;
          background: var(--parent-bg) !important; color: var(--parent-ink) !important;
          box-shadow: none !important; cursor: pointer; vertical-align: middle;
        }
        button#incremento-parent-context[data-parent-state="available"] {
          --parent-bg: #e6f5ed; --parent-ink: #176344; --parent-border: #9bceb4;
        }
        .night-mode button#incremento-parent-context[data-parent-state] {
          --parent-bg: #2d3137; --parent-ink: #929ba8; --parent-border: #464c55;
        }
        .night-mode button#incremento-parent-context[data-parent-state="available"] {
          --parent-bg: #193f31; --parent-ink: #9be4bc; --parent-border: #397e59;
        }
        button#incremento-parent-context[data-parent-state]:hover:not(:disabled) {
          background: var(--parent-bg) !important; filter: brightness(.94);
        }
        button#incremento-parent-context[data-parent-state]:focus-visible {
          outline: 2px solid var(--parent-ink) !important; outline-offset: 3px !important;
        }
        button#incremento-parent-context[data-parent-state]:disabled { cursor: default; opacity: .65 !important; }
        #incremento-study-navigation #incremento-parent-context { margin: 0 !important; }
        #incremento-parent-context svg { width: 16px; height: 16px; flex: none; }
      `;
      const button = document.createElement('button');
      button.id = 'incremento-parent-context'; button.type = 'button';
      button.dataset.parentState = data.parent?.available ? 'available' : 'unavailable';
      button.disabled = !data.parent?.available;
      button.title = data.label + (data.parent ? ': ' + data.parent.title : '')
        + (button.disabled ? ' · ' + data.unavailable : '');
      button.setAttribute('aria-label', data.label);
      button.setAttribute('aria-description', button.title);
      button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
        + 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
        + '<path d="M8 3h8v7H8z M12 10v4 M5 18v-4h14v4 M2 18h6v4H2z M16 18h6v4h-6z"/></svg>';
      button.onclick = () => pycmd(data.command);
      const steps = document.querySelector('#incremento-study-navigation .study-nav-steps');
      const card = document.getElementById('qa');
      if (steps) steps.appendChild(button);
      else if (card) card.before(button);
      else document.body.prepend(button);
    })();""" % data)


def reset(*_):
    global _command, _review_context, _snapshot, _open_request
    _command, _review_context, _snapshot = '', None, None
    _open_request += 1
    if _dock is not None:
        _dock.close()


def reviewer_shown(*_):
    global _command, _review_context, _snapshot
    context = _context()
    if context != _review_context:
        reset()
    if not context[2]:
        return
    try:
        config = load_addon_config(getattr(mw, 'addonManager', None), _ADDON_PKG)
    except Exception:
        config = {}
    if not configured_reviewer_parent_context_enabled(config):
        reset()
        mw.reviewer.web.eval("document.getElementById('incremento-parent-context')?.remove();")
        return
    _review_context, _snapshot = context, None
    command = _command = _PREFIX + secrets.token_urlsafe(24)
    _render_link(None)
    profile, collection, card_id = context
    def work(col):
        if col is collection and _command == command:
            return load_parent_context(_ADDON_DIR, profile, col, card_id)
        return None
    def ready(result):
        global _snapshot
        if _command == command and _context() == context:
            _snapshot = result
            if result is not None:
                result = {key: result[key] for key in ('card_id', 'title', 'available')}
                result['title'] = result['title'] or t('reader_card_number', number=result['card_id'])
            _render_link(result)
    QueryOp(parent=mw, op=work, success=ready).failure(lambda _error: ready(None)).run_in_background()


def _open_parent():
    global _dock, _open_request
    context, parent_id = _review_context, _snapshot['card_id']
    if _dock is None:
        _dock = ContextDock(t('study_parent'), mw)
        _dock.setObjectName('incremento_parent_context_dock')
        browser = ContextBrowser(_dock)
        browser.setReadOnly(True)
        browser.setOpenLinks(False)
        browser.setOpenExternalLinks(False)
        browser.setAccessibleName(t('study_parent'))
        _dock.setWidget(browser)
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, _dock)
        mw.resizeDocks([_dock], [360], Qt.Orientation.Horizontal)
    _open_request += 1
    request = _open_request
    _dock.widget().setPlainText(t('study_loading'))
    _dock.show()
    profile, collection, card_id = context
    def work(col):
        if col is collection:
            return load_parent_context(_ADDON_DIR, profile, col, card_id)
        return None
    def ready(result):
        if request != _open_request or _context() != context or not _dock.isVisible():
            return
        if not result or not result['available'] or result['card_id'] != parent_id:
            _dock.widget().setPlainText(t('study_unavailable'))
            return
        parts = ['<h3>' + escape(result['title']) + '</h3>']
        parts.extend('<h4>' + escape(name) + '</h4>' + value for name, value in result['fields'])
        if not result['fields']:
            parts.append(escape(t('reader_note_no_visible_fields')))
        _dock.widget().setHtml(''.join(parts))
    QueryOp(parent=mw, op=work, success=ready).failure(lambda _error: ready(None)).run_in_background()


def on_js_message(handled, message, context):
    if not isinstance(message, str) or not message.startswith(_PREFIX):
        return handled
    if (context is getattr(mw, 'reviewer', None) and _command and message.isascii()
            and secrets.compare_digest(message, _command) and _context() == _review_context
            and _snapshot and _snapshot['available']):
        _open_parent()
    return True, None
