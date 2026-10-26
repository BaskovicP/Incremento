"""The centered study card preserves Anki's live DOM and authored controls."""
import json
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


def test_centered_card_panel_resources_and_answer_refresh_preserve_live_content(tmp_path):
    from frontend.study_navigation import reviewer_navigation_script
    from webpage_browser import browser_runtime, _runtime_dir
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    routes = [dict(stage=stage, label=label, current=stage == 'card', command='go:' + stage)
              for stage, label in [('card', 'Card'), ('book', 'Textbook'), ('video', 'Video')]]
    workspace = dict(heading='Review card', state='Question not answered', resources_label='Study resources',
        hint='Open a passage or recording without leaving this review.', tiles=[
            dict(stage='book', title='Geometry textbook', detail='Page 84 · Opposite angles', action='Read passage', command='go:book'),
            dict(stage='video', title='Why opposite angles are equal', detail='Episode 4 · 8:10–11:35', action='Open recording', command='go:video')])
    payload=tmp_path/'workspace.json'
    payload.write_text(json.dumps(dict(
        script=reviewer_navigation_script(routes,'Study resources',workspace=workspace),
        answer=reviewer_navigation_script(routes,'Study resources',workspace=dict(workspace,state='Answer revealed')),
        reset=reviewer_navigation_script(routes,'Study resources'))))
    script=dedent('''
        import json, sys
        from pathlib import Path
        sys.path.insert(0,sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        data=json.loads(Path(sys.argv[3]).read_text())
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=sys.argv[2],headless=True,chromium_sandbox=True)
            page=browser.new_page(viewport={'width':1200,'height':800})
            page.route('**/*',lambda route:route.abort())
            page.set_content('<html><head><style>body{margin:20px;font:20px/1.5 sans-serif;background:#fafafa;color:#25272c}.night-mode body{background:#2b2b2b;color:#eee}</style></head><body><div id="qa"><p id="question">Why are opposite angles in a parallelogram equal?</p><input id="typed" value="My answer"><button id="audio">Play audio</button><div style="height:30px"></div></div></body></html>')
            page.evaluate('window.card=document.getElementById("qa");window.cardParent=card.parentNode;window.commands=[];window.pycmd=c=>commands.push(c);window.plays=0;document.getElementById("audio").onclick=()=>plays++')
            for dark in (False,True):
                page.evaluate('(dark)=>document.documentElement.classList.toggle("night-mode",dark)',dark)
                for width in (360,1200):
                    page.set_viewport_size({'width':width,'height':800})
                    page.evaluate(data['script']); page.evaluate(data['script'])
                    card=page.locator('#qa'); bounds=card.bounding_box()
                    assert bounds['width']<=800
                    assert abs(bounds['x']+bounds['width']/2-width/2)<2
                    assert card.evaluate('e=>getComputedStyle(e).borderTopStyle')=='solid'
                    assert card.evaluate('e=>parseFloat(getComputedStyle(e).paddingLeft)')>=16
                    assert page.evaluate('card===document.getElementById("qa") && card.parentNode===window.cardParent')
                    assert page.locator('#typed').input_value()=='My answer'
                    page.locator('#audio').click(); assert page.evaluate('plays')>0
                    shelf=page.locator('#incremento-study-card-resources')
                    assert shelf.count()==1
                    shelf.get_by_role('button',name='Read passage').click()
                    assert page.evaluate('commands.at(-1)')=='go:book'
                    assert page.evaluate('document.documentElement.scrollWidth')==width
                    page.screenshot(path=str(Path(sys.argv[4])/('workspace-'+('dark' if dark else 'light')+'-'+str(width)+'.png')),full_page=True)
            # Native Anki answer rendering replaces content, not the #qa node.
            page.evaluate('card.innerHTML="<p>The parallel sides give equal alternate angles.</p>"')
            page.evaluate(data['answer'])
            assert page.locator('#qa').get_attribute('data-study-state')=='Answer revealed'
            assert page.locator('#incremento-study-card-resources').count()==1
            assert page.evaluate('card===document.getElementById("qa")')
            page.evaluate(data['reset'])
            assert page.locator('#incremento-study-card-resources').count()==0
            assert page.locator('#qa').get_attribute('data-study-panel') is None
            browser.close()
    ''')
    result=subprocess.run([runtime[0],'-I','-c',script,str(_runtime_dir()/'packages'),runtime[1],str(payload),str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],env=dict(os.environ),capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
