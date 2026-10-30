"""Safe, keyboard-accessible navigation on the existing Anki review document."""
import json

try:
    from .reviewer_button_style import build_reviewer_button_style_js
except ImportError:
    from reviewer_button_style import build_reviewer_button_style_js


NAVIGATION_COLORS = {
    'light': dict(surface='#f1f3f6', border='#dce1e8', foreground='#4b5563', selected='#e5effd', accent='#1e5ca8', paper='#ffffff', ink='#25272c'),
    'dark': dict(surface='#25272b', border='#464a51', foreground='#c0c5ce', selected='#2b405e', accent='#c4dbff', paper='#303236', ink='#f1f2f4'),
}
NAVIGATION_ICONS = {
    'card': 'M7 4h12v14H7z M4 7v14h12 M10 8h6 M10 12h4',
    'book': 'M12 5v15 M3 4h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v14h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3z',
    'video': 'M3 6h12v12H3z M15 10l6-3v10l-6-3z',
    'audio': 'M4 10v4 M8 6v12 M12 3v18 M16 7v10 M20 10v4',
    'resources': 'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
}

_NAVIGATION_CSS = ''.join(
    selector + ' {' + ''.join(f'--study-nav-{key}:{value};' for key, value in colors.items()) + '}\n'
    for selector, colors in (
        ('#incremento-study-navigation', NAVIGATION_COLORS['light']),
        ('.night-mode #incremento-study-navigation', NAVIGATION_COLORS['dark']),
    )
) + """
body[data-study-canvas] { background: var(--study-workspace-canvas) !important; }
#incremento-study-navigation[data-workspace] { max-width: 1200px; margin: 0 auto 28px; }
#qa[data-study-panel] {
  box-sizing: border-box; width: calc(100% - 32px) !important; max-width: 780px !important;
  margin: 0 auto !important; padding: 28px 32px !important; min-height: 190px;
  background: var(--study-card-paper); border: 1px solid var(--study-card-border);
  border-radius: 12px 12px 0 0; overflow-wrap: anywhere;
}
#qa[data-study-panel]::before {
  content: attr(data-study-heading) " · " attr(data-study-state); display: block;
  margin-bottom: 24px; font: 12px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  opacity: .7; text-align: start;
}
#qa[data-study-panel] :is(img, video, iframe, svg) { max-width: 100%; }
#incremento-study-card-resources {
  box-sizing: border-box; width: calc(100% - 32px); max-width: 780px; margin: 0 auto 32px;
  padding: 20px 32px 28px; background: var(--study-card-paper); color: var(--study-card-ink);
  border: 1px solid var(--study-card-border); border-top: 0; border-radius: 0 0 12px 12px;
  text-align: start; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
#incremento-study-card-resources { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
#incremento-study-card-resources .study-card-summary { font-size: 12px; color: var(--study-card-muted); }
#incremento-study-card-resources button { cursor: pointer; background: transparent !important; border-color: transparent !important; }
@media (max-width: 520px) {
  #qa[data-study-panel], #incremento-study-card-resources { width: 100% !important; padding: 16px !important; }
}
#incremento-study-navigation {
  display: flex; align-items: center; flex-wrap: wrap; gap: 12px 20px;
  box-sizing: border-box; margin: 0 0 24px; padding: 16px;
  border-bottom: 1px solid var(--study-nav-border); text-align: start;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
#incremento-study-navigation .study-nav-label { display: none; }
#incremento-study-navigation .study-nav-steps {
  display: inline-flex; align-items: center; gap: 5px; padding: 0;
  max-width: 100%; box-sizing: border-box; border-radius: 12px;
  border: 0; background: transparent;
}
#incremento-study-navigation button {
  gap: 7px; margin: 0 !important; background: transparent !important; border-color: transparent !important;
  color: var(--study-nav-foreground) !important; cursor: pointer;
}
#incremento-study-navigation button[data-availability] { height: auto !important; min-height: 36px !important; }
#incremento-study-navigation #incremento-study-link-resources { margin-inline-start: auto !important; }
#incremento-study-navigation .study-nav-copy { display: flex; align-items: center; gap: 8px; min-width: 0; white-space: normal; }
#incremento-study-navigation .study-nav-count { font-size: 12px; font-weight: 400; line-height: 1.4; padding: 1px 5px; border-radius: 3px; background: var(--study-nav-border); }
#incremento-study-navigation button:disabled { opacity: .7 !important; cursor: default; }
#incremento-study-card-resources button:disabled { cursor: default; }
#incremento-study-navigation button[aria-current="step"] {
  background: var(--study-nav-selected) !important; color: var(--study-nav-accent) !important;
  font-weight: 600 !important;
}
#incremento-study-navigation button:hover:not([aria-current="step"]):not(:disabled) {
  background: var(--incremento-button-hover) !important;
}
#incremento-study-navigation svg { width: 16px; height: 16px; flex: none; }
#incremento-study-navigation.study-nav-entry .study-nav-label { display: none; }
@media (max-width: 520px) {
  #incremento-study-navigation { gap: 8px; }
  #incremento-study-navigation .study-nav-label { flex-basis: 100%; }
  #incremento-study-navigation .study-nav-steps { width: 100%; flex-wrap: wrap; }
  #incremento-study-navigation button { flex: 1 0 auto; min-width: 0 !important; padding: 0 9px !important; }
  #incremento-study-navigation.study-nav-entry .study-nav-steps { width: auto; }
}
"""


def set_stage_icon(button, stage, colors):
    """Render the same small outline icon used by the reviewer navigation."""
    from aqt.qt import QByteArray, QIcon, QPainter, QPixmap, QSize, Qt
    from PyQt6.QtSvg import QSvgRenderer

    icon = QIcon()
    for state, color in ((QIcon.State.Off, colors['foreground']), (QIcon.State.On, colors['accent'])):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
               f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
               f'<path d="{NAVIGATION_ICONS[stage]}"/></svg>')
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        icon.addPixmap(pixmap, QIcon.Mode.Normal, state)
    button.setIcon(icon)
    button.setIconSize(QSize(16, 16))


def style_stage_bar(container, buttons):
    """Apply the grouped navigation treatment to the native resource window."""
    from aqt.qt import QPalette

    dark = container.palette().color(QPalette.ColorRole.Window).lightness() < 128
    colors = NAVIGATION_COLORS['dark' if dark else 'light']
    container.setObjectName('study-stage-bar')
    container.setStyleSheet(f"""
        QWidget#study-stage-bar {{ background: transparent; border: 0; }}
        QWidget#study-stage-bar QPushButton {{ background: transparent; color: {colors['foreground']};
            border: 1px solid transparent; border-radius: 8px; padding: 0; }}
        QWidget#study-stage-bar QPushButton:checked {{ background: {colors['selected']}; color: {colors['accent']}; font-weight: 600; }}
        QWidget#study-stage-bar QPushButton:hover {{ border-color: {colors['border']}; }}
        QWidget#study-stage-bar QPushButton:focus {{ border-color: {colors['accent']}; }}
        QWidget#study-stage-bar QPushButton:disabled {{ color: {container.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name()}; }}
        QWidget#study-stage-bar QLabel {{ color: {colors['foreground']}; }}
        QWidget#study-stage-bar QPushButton:checked QLabel#study-stage-title {{ color:{colors['accent']}; font-weight:500; }}
        QWidget#study-stage-bar QLabel#study-stage-count {{ background:{colors['border']}; color:{colors['ink']};
            padding:1px 5px; border-radius:3px; }}
    """)
    for stage, button in buttons.items():
        set_stage_icon(button, stage, colors)
    return colors


def reviewer_navigation_clear_script():
    """Remove our presentation without re-rendering Anki's live card document."""
    return """
(() => {
  for (const id of ['incremento-study-resources', 'incremento-study-navigation',
                    'incremento-study-card-resources', 'incremento-study-navigation-style']) {
    document.getElementById(id)?.remove();
  }
  const card = document.getElementById('qa');
  for (const name of ['data-study-panel', 'data-study-heading', 'data-study-state']) {
    card?.removeAttribute(name);
  }
  document.body.removeAttribute('data-study-canvas');
  for (const name of ['--study-workspace-canvas', '--study-card-border', '--study-card-paper',
                     '--study-card-muted', '--study-card-ink', '--study-card-accent']) {
    document.body.style.removeProperty(name);
  }
})();
"""


def reviewer_navigation_script(routes, label, *, workspace=None):
    payload = json.dumps(dict(routes=routes, label=label, icons=NAVIGATION_ICONS, css=_NAVIGATION_CSS,
                              workspace=workspace, colors=NAVIGATION_COLORS))
    return build_reviewer_button_style_js() + """
(() => {
  document.getElementById('incremento-study-resources')?.remove();
  document.getElementById('incremento-study-navigation')?.remove();
  const data = %s;
  const colors = data.colors[document.documentElement.classList.contains('night-mode') ? 'dark' : 'light'];
  let style = document.getElementById('incremento-study-navigation-style');
  if (!style) {
    style = document.createElement('style');
    style.id = 'incremento-study-navigation-style';
    document.head.appendChild(style);
  }
  style.textContent = data.css;
  const nav = document.createElement('nav');
  nav.id = 'incremento-study-navigation';
  nav.setAttribute('aria-label', data.label);
  nav.classList.toggle('study-nav-entry', data.routes.length === 1);
  if (data.workspace) nav.setAttribute('data-workspace', '');
  const label = document.createElement('span');
  label.className = 'study-nav-label';
  label.textContent = data.label;
  nav.appendChild(label);
  const steps = document.createElement('div');
  steps.className = 'study-nav-steps';
  nav.appendChild(steps);
  for (const route of data.routes) {
    const button = document.createElement('button');
    button.type = 'button';
    const copy = document.createElement('span'); copy.className = 'study-nav-copy';
    const title = document.createElement('span'); title.textContent = route.label;
    copy.appendChild(title);
    if (route.status) {
      button.title = route.status;
      button.setAttribute('aria-description', route.status);
      button.dataset.availability = route.availability;
    }
    if (route.stage !== 'card' && Number.isSafeInteger(route.count)) {
      const count = document.createElement('span');
      count.className = 'study-nav-count'; count.textContent = String(route.count);
      copy.appendChild(count);
    }
    button.appendChild(copy);
    button.disabled = Boolean(route.disabled);
    button.dataset.studyStage = route.stage;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.7');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', data.icons[route.icon || route.stage] || data.icons.resources);
    svg.appendChild(path);
    button.prepend(svg);
    if (route.current) {
      button.setAttribute('aria-current', 'step');
    }
    button.onclick = () => pycmd(route.command);
    steps.appendChild(button);
  }
  if (data.workspace?.link_action) {
    const action = document.createElement('button');
    action.id = 'incremento-study-link-resources';
    action.type = 'button';
    action.textContent = data.workspace.link_action.label;
    action.onclick = () => pycmd(data.workspace.link_action.command);
    nav.appendChild(action);
  }
  // Keep Anki's live #qa node and card templates intact, including listeners.
  const card = document.getElementById('qa');
  if (card) card.before(nav);
  else document.body.prepend(nav);
  document.getElementById('incremento-study-card-resources')?.remove();
  document.body.removeAttribute('data-study-canvas');
  if (card && data.workspace) {
    const paper = getComputedStyle(document.body).backgroundColor;
    const palette = {
      '--study-workspace-canvas': colors.surface, '--study-card-border': colors.border,
      '--study-card-paper': paper === 'rgba(0, 0, 0, 0)' ? colors.paper : paper,
      '--study-card-muted': colors.foreground, '--study-card-ink': colors.ink, '--study-card-accent': colors.accent
    };
    for (const [key,value] of Object.entries(palette)) document.body.style.setProperty(key,value);
    document.body.setAttribute('data-study-canvas','');
    card.setAttribute('data-study-panel','');
    card.setAttribute('data-study-heading',data.workspace.heading);
    card.setAttribute('data-study-state',data.workspace.state);
    const shelf = document.createElement('section');
    shelf.id = 'incremento-study-card-resources';
    shelf.setAttribute('aria-label', data.workspace.resources_label);
    const summary = document.createElement('span');
    summary.className = 'study-card-summary';
    summary.textContent = data.workspace.summary || '';
    shelf.appendChild(summary);
    if (data.workspace.manage_action) {
      const action = document.createElement('button');
      action.type = 'button'; action.textContent = data.workspace.manage_action.label;
      action.onclick = () => pycmd(data.workspace.manage_action.command);
      shelf.appendChild(action);
    }
    card.after(shelf);
  } else if (card) {
    for (const name of ['data-study-panel','data-study-heading','data-study-state']) card.removeAttribute(name);
  }
})();
""" % payload
