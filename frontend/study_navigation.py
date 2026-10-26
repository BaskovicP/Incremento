"""Safe, keyboard-accessible navigation on the existing Anki review document."""
import json

try:
    from .reviewer_button_style import build_reviewer_button_style_js
except ImportError:
    from reviewer_button_style import build_reviewer_button_style_js


def reviewer_navigation_script(routes, label):
    payload = json.dumps(dict(routes=routes, label=label))
    return build_reviewer_button_style_js() + """
(() => {
  document.getElementById('incremento-study-resources')?.remove();
  document.getElementById('incremento-study-navigation')?.remove();
  const data = %s;
  const nav = document.createElement('nav');
  nav.id = 'incremento-study-navigation';
  nav.setAttribute('aria-label', data.label);
  nav.style.cssText = 'display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:18px auto';
  for (const route of data.routes) {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = route.label;
    button.dataset.studyStage = route.stage;
    if (route.current) {
      button.setAttribute('aria-current', 'step');
      button.style.setProperty('border-color', 'var(--incremento-button-focus)', 'important');
    }
    button.onclick = () => pycmd(route.command);
    nav.appendChild(button);
  }
  document.body.appendChild(nav);
})();
""" % payload
