"""The study bar stays separate from the live card and fits narrow viewports."""
import json
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


def test_study_bar_layout_themes_keyboard_and_card_preservation(tmp_path):
    from frontend.study_navigation import reviewer_navigation_script
    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    routes = [dict(stage=stage, label=label, current=stage == 'card', command='study:' + stage)
              for stage, label in [('card', 'Card'), ('book', 'Textbook'), ('video', 'Video')]]
    payload = tmp_path / 'navigation.json'
    payload.write_text(json.dumps(dict(script=reviewer_navigation_script(routes, 'Study resources'),
        entry=reviewer_navigation_script([dict(stage='resources', label='Study resources', command='open')],
                                        'Study resources'))))
    script = dedent('''
        import json, sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        payload=json.loads(Path(sys.argv[3]).read_text())
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page=browser.new_page(viewport={'width':1100,'height':650})
            page.route('**/*', lambda route: route.abort())
            page.set_content("""<!doctype html><html><head><style>
                body { margin:24px; font:18px/1.5 -apple-system,BlinkMacSystemFont,sans-serif; background:#fafafa; color:#30343a; }
                html.night-mode body { background:#2b2b2b; color:#eee; }
                #incremento-reviewer-priority-badge-spacer { height:70px; }
                #priority { position:fixed; top:18px;right:24px;font-size:12px;border:1px solid #52616d;padding:6px 12px;border-radius:8px; }
                #qa { text-align:left; }
            </style></head><body><div id="incremento-reviewer-priority-badge-spacer"></div>
            <div id="qa"><p>What is the core purpose of cluster analysis in descriptive analytics?</p>
            <button id="card-control">Card audio</button></div><aside id="priority">Priority 50</aside></body></html>""")
            page.evaluate("window.originalCard=document.getElementById('qa');window.commands=[];window.pycmd=c=>commands.push(c);window.cardClicks=0;document.getElementById('card-control').onclick=()=>cardClicks++")
            for dark in (False, True):
                page.evaluate('(dark)=>document.documentElement.classList.toggle("night-mode",dark)',dark)
                for width in (360,1100):
                    page.set_viewport_size({'width':width,'height':650})
                    page.evaluate(payload['script']); page.evaluate(payload['script'])
                    nav=page.get_by_role('navigation',name='Study resources')
                    assert nav.count()==1
                    box=nav.bounding_box(); card=page.locator('#qa').bounding_box()
                    assert box['y']+box['height'] < card['y']
                    assert box['y'] > page.locator('#priority').bounding_box()['y']+page.locator('#priority').bounding_box()['height']
                    for name in ('Card','Textbook','Video'):
                        button=nav.get_by_role('button',name=name,exact=True)
                        bounds=button.bounding_box()
                        assert 0 <= bounds['x'] < bounds['x']+bounds['width'] <= width
                        expect(button).to_be_visible()
                    selected=nav.get_by_role('button',name='Card',exact=True)
                    other=nav.get_by_role('button',name='Textbook',exact=True)
                    assert selected.evaluate('e=>getComputedStyle(e).backgroundColor') != other.evaluate('e=>getComputedStyle(e).backgroundColor')
                    other.focus(); page.keyboard.press('Enter')
                    assert page.evaluate('commands.at(-1)')=='study:book'
                    assert page.evaluate('originalCard===document.getElementById("qa")')
                    page.locator('#card-control').click()
                    assert page.evaluate('cardClicks')>0
                    page.screenshot(path=str(Path(sys.argv[4])/('study-'+('dark' if dark else 'light')+'-'+str(width)+'.png')))
            # Longer translated labels still fit, without truncating their names.
            page.locator('[data-study-stage=card]').evaluate('e=>e.lastChild.textContent="Kartica"')
            page.locator('[data-study-stage=book]').evaluate('e=>e.lastChild.textContent="Udžbenik"')
            page.set_viewport_size({'width':360,'height':650})
            assert page.evaluate('document.documentElement.scrollWidth')==360
            # The single entry action must not repeat its own label.
            page.evaluate(payload['entry'])
            assert page.get_by_role('button',name='Study resources',exact=True).count()==1
            expect(page.locator('.study-nav-label')).not_to_be_visible()
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1],
        str(payload), str(tmp_path)], cwd=Path(__file__).resolve().parents[1], env=dict(os.environ),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
