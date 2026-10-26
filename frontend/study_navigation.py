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
#incremento-study-card-resources h2 { margin: 0 0 3px; font-size: 14px; font-weight: 600; }
#incremento-study-card-resources p { margin: 0 0 16px; font-size: 12px; color: var(--study-card-muted); }
#incremento-study-card-resources .study-resource-tile {
  display: flex; align-items: center; gap: 14px; padding: 14px; margin-top: 10px;
  background: var(--study-workspace-canvas); border: 1px solid var(--study-card-border); border-radius: 8px;
}
#incremento-study-card-resources .study-resource-copy { flex: 1; min-width: 0; overflow-wrap: anywhere; }
#incremento-study-card-resources .study-resource-title { font-weight: 500; }
#incremento-study-card-resources .study-resource-detail { font-size: 12px; color: var(--study-card-muted); margin-top: 3px; }
#incremento-study-card-resources svg { width: 22px; height: 22px; flex: none; color: var(--study-card-accent); }
#incremento-study-card-resources button { flex: none; cursor: pointer; }
@media (max-width: 520px) {
  #qa[data-study-panel], #incremento-study-card-resources { width: 100% !important; padding: 20px !important; }
  #incremento-study-card-resources .study-resource-tile { flex-wrap: wrap; gap: 10px; }
  #incremento-study-card-resources .study-resource-copy { flex-basis: calc(100% - 40px); }
  #incremento-study-card-resources button { margin-inline-start: 32px; }
}
#incremento-study-navigation {
  display: flex; align-items: center; flex-wrap: wrap; gap: 12px 20px;
  box-sizing: border-box; margin: 0 0 24px; padding: 12px 0 16px;
  border-bottom: 1px solid var(--study-nav-border); text-align: start;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
#incremento-study-navigation .study-nav-label {
  color: var(--study-nav-foreground); font-size: 12px; font-weight: 500;
}
#incremento-study-navigation .study-nav-steps {
  display: inline-flex; align-items: center; gap: 4px; padding: 4px;
  max-width: 100%; box-sizing: border-box; border-radius: 12px;
  border: 1px solid var(--study-nav-border); background: var(--study-nav-surface);
}
#incremento-study-navigation button {
  gap: 7px; margin: 0 !important; background: transparent !important; border-color: transparent !important;
  color: var(--study-nav-foreground) !important; cursor: pointer;
}
#incremento-study-navigation button[aria-current="step"] {
  background: var(--study-nav-selected) !important; color: var(--study-nav-accent) !important;
  font-weight: 600 !important;
}
#incremento-study-navigation button:hover:not([aria-current="step"]) {
  background: var(--incremento-button-hover) !important;
}
#incremento-study-navigation svg { width: 16px; height: 16px; flex: none; }
#incremento-study-navigation.study-nav-entry .study-nav-label { display: none; }
@media (max-width: 520px) {
  #incremento-study-navigation { gap: 8px; }
  #incremento-study-navigation .study-nav-label { flex-basis: 100%; }
  #incremento-study-navigation .study-nav-steps { width: 100%; }
  #incremento-study-navigation button { flex: 1; min-width: 0 !important; padding: 0 9px !important; }
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
        QWidget#study-stage-bar {{ background: {colors['surface']}; border: 1px solid {colors['border']}; border-radius: 12px; }}
        QWidget#study-stage-bar QPushButton {{ background: transparent; color: {colors['foreground']};
            border: 1px solid transparent; border-radius: 8px; padding: 6px 12px; }}
        QWidget#study-stage-bar QPushButton:checked {{ background: {colors['selected']}; color: {colors['accent']}; font-weight: 600; }}
        QWidget#study-stage-bar QPushButton:hover {{ border-color: {colors['border']}; }}
        QWidget#study-stage-bar QPushButton:focus {{ border-color: {colors['accent']}; }}
        QWidget#study-stage-bar QPushButton:disabled {{ color: {container.palette().color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText).name()}; }}
    """)
    for stage, button in buttons.items():
        set_stage_icon(button, stage, colors)
    return colors


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
    button.textContent = route.label;
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
    const heading = document.createElement('h2'); heading.textContent = data.workspace.resources_label;
    const hint = document.createElement('p'); hint.textContent = data.workspace.hint;
    shelf.append(heading,hint);
    for (const resource of data.workspace.tiles) {
      const tile = document.createElement('div'); tile.className = 'study-resource-tile';
      const icon = steps.querySelector('[data-study-stage="' + resource.stage + '"] svg');
      if (icon) tile.appendChild(icon.cloneNode(true));
      const copy = document.createElement('div'); copy.className = 'study-resource-copy';
      const title = document.createElement('div'); title.className = 'study-resource-title'; title.textContent = resource.title;
      const detail = document.createElement('div'); detail.className = 'study-resource-detail'; detail.textContent = resource.detail;
      copy.append(title,detail);
      const action = document.createElement('button'); action.type = 'button'; action.textContent = resource.action;
      action.onclick = () => pycmd(resource.command);
      tile.append(copy,action); shelf.appendChild(tile);
    }
    card.after(shelf);
  } else if (card) {
    for (const name of ['data-study-panel','data-study-heading','data-study-state']) card.removeAttribute(name);
  }
})();
""" % payload
