"""Clicking a saved parent shows context beside the unchanged live reviewer."""
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest

from tests.test_study_navigation_qt import run_scene


def test_parent_link_opens_a_read_only_sidebar_on_both_sides_and_reuses_it():
    run_scene('''
        from frontend import reviewer_parent_context as parent
        parent.get_active_profile=lambda:profile[0]
        snapshots=[]
        parent.load_parent_context=lambda *a: snapshots.append(a) or dict(
            card_id=10,title='Original <topic>',available=True,
            fields=[('Front','<b>The original topic</b>'),('Back','Full explanation')])
        parent.reviewer_shown();drain()
        assert 'Original <topic>' in scripts[-1]
        assert 'button.title' in scripts[-1]  # Source titles are hover text, not a banner.
        command=parent._command
        parent.on_js_message((False,None),command,mw.reviewer);drain();app.processEvents()
        dock=parent._dock
        assert dock.isVisible() and dock.window() is mw
        assert dock.widget().isReadOnly() and 'Full explanation' in dock.widget().toPlainText()
        assert web.isVisible() and web.isEnabled() and bottom.isVisible()
        assert mw.reviewer.card.id==41 and mw.reviewer.state=='question'
        assert mw.reviewer.auto_advance_enabled and web.toPlainText()=='Original question'
        mw.reviewer.state='answer';parent.reviewer_shown();drain()
        parent.on_js_message((False,None),parent._command,mw.reviewer);drain()
        assert parent._dock is dock and mw.reviewer.state=='answer'
        parent.reset();assert not dock.isVisible() and not dock.widget().toPlainText()
    ''')


def test_parent_commands_and_pending_results_cannot_cross_cards_profiles_or_closed_panes():
    run_scene('''
        from frontend import reviewer_parent_context as parent
        parent.get_active_profile=lambda:profile[0]
        parent.load_parent_context=lambda *a:dict(card_id=10,title='Original',available=True,fields=[('Front','Context')])
        parent.reviewer_shown();drain();command=parent._command
        parent.on_js_message((False,None),command,object())
        parent.on_js_message((False,None),command+'forged',mw.reviewer)
        assert parent._dock is None
        parent.on_js_message((False,None),command,mw.reviewer)
        op=pending.pop(0);result=op.op(mw.col)
        parent._dock.close();op.success(result)
        assert not parent._dock.isVisible() and not parent._dock.widget().toPlainText()
        parent.on_js_message((False,None),command,mw.reviewer)
        op=pending.pop(0);result=op.op(mw.col)
        profile[0]='Other';parent.reviewer_shown();op.success(result);drain()
        assert not parent._dock.isVisible() and not parent._dock.widget().toPlainText()
        parent.on_js_message((False,None),command,mw.reviewer)
        assert not parent._dock.isVisible()
        parent.reset()
    ''')


def test_parent_button_mutes_on_an_unlinked_card_and_deleted_sources_are_not_clickable():
    run_scene('''
        from frontend import reviewer_parent_context as parent
        parent.get_active_profile=lambda:profile[0]
        result=[dict(card_id=10,title='Deleted topic',available=False,fields=[])]
        parent.load_parent_context=lambda *a:result[0]
        parent.reviewer_shown();drain()
        assert 'Deleted topic' in scripts[-1] and '"available": false' in scripts[-1]
        parent.on_js_message((False,None),parent._command,mw.reviewer)
        assert parent._dock is None
        result[0]=None;mw.reviewer.card.id=42;parent.reviewer_shown();drain()
        assert '"parent": null' in scripts[-1]
        parent.reset()
    ''')


@pytest.mark.parametrize('side', ['question', 'answer'])
def test_hiding_parent_icon_closes_preview_cancels_pending_results_and_can_restore_it(side):
    run_scene(f'side={side!r}\n' + dedent('''
        from frontend import reviewer_parent_context as parent
        parent.get_active_profile=lambda:profile[0]
        config={'reviewer_parent_context_enabled':False}
        parent.load_addon_config=lambda *a:config
        parent.load_parent_context=lambda *a:dict(card_id=10,title='Original',available=True,fields=[('Front','Context')])
        mw.reviewer.state=side
        parent.reviewer_shown()
        assert not pending and not parent._command
        assert "document.getElementById('incremento-parent-context')?.remove()" in scripts[-1]
        config['reviewer_parent_context_enabled']=True
        parent.reviewer_shown();drain()
        command=parent._command
        parent.on_js_message((False,None),command,mw.reviewer);drain();app.processEvents()
        dock=parent._dock
        assert dock.isVisible() and dock.widget().toPlainText()
        parent.reviewer_shown()
        query=pending.pop(0);result=query.op(mw.col)
        config['reviewer_parent_context_enabled']=False
        parent.reviewer_shown()
        assert not dock.isVisible() and not dock.widget().toPlainText()
        assert not parent._command and parent._snapshot is None
        scripts_after_hide=list(scripts)
        query.success(result)
        parent.on_js_message((False,None),command,mw.reviewer)
        assert scripts==scripts_after_hide and not pending
        assert mw.reviewer.card.id==41 and mw.reviewer.state==side
        assert web.toPlainText()=='Original question' and mw.reviewer.auto_advance_enabled
        config['reviewer_parent_context_enabled']=True
        parent.reviewer_shown();drain()
        assert parent._command and '"available": true' in scripts[-1]
        assert mw.reviewer.card.id==41 and mw.reviewer.state==side
        parent.reset()
    '''))


def test_parent_icon_stays_compact_and_changes_color_with_parent_availability(tmp_path):
    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional webpage browser component has not been explicitly installed')
    payload = tmp_path / 'parent-button.json'
    run_scene(f'payload_path={str(payload)!r}\n' + dedent('''
        import json
        from pathlib import Path
        from frontend import reviewer_parent_context as parent
        from frontend.study_navigation import reviewer_navigation_script, reviewer_navigation_clear_script
        parent._command='incremento_parent_context:test-token'
        title='Original <img src=x onerror=alert(1)> ' + 'long source context '*30
        parent._render_link(dict(card_id=10,title=title,available=True))
        active=scripts[-1]
        parent._render_link(None);empty=scripts[-1]
        parent._render_link(dict(card_id=10,title='Deleted topic',available=False));missing=scripts[-1]
        parent.load_addon_config=lambda *a:{'reviewer_parent_context_enabled':False}
        parent.reviewer_shown();hidden=scripts[-1]
        routes=[dict(stage=stage,label=label,current=stage=='card',command='study:'+stage)
                for stage,label in [('card','Card'),('book','PDFs'),('video','Videos')]]
        Path(payload_path).write_text(json.dumps(dict(active=active,empty=empty,missing=missing,hidden=hidden,title=title,
            nav=reviewer_navigation_script(routes,'Study resources'),clear=reviewer_navigation_clear_script())))
    '''))
    script = dedent('''
        import json,sys
        from pathlib import Path
        sys.path.insert(0,sys.argv[1])
        from playwright.sync_api import sync_playwright,expect
        data=json.loads(Path(sys.argv[3]).read_text())
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=sys.argv[2],headless=True,chromium_sandbox=True)
            page=browser.new_page(viewport={'width':1100,'height':650})
            page.route('**/*',lambda route:route.abort())
            page.set_content(''' + repr('''<!doctype html><style>
                body { margin:16px; font:18px sans-serif; }
                button { width:100% !important; padding:30px !important; border-radius:30px !important; }
                html.night-mode body { background:#25272b; color:#eee; }
                </style><div id="qa"><p>Original question</p><input value="My answer"></div>''') + ''')
            page.evaluate('window.original=document.getElementById("qa");window.commands=[];window.pycmd=c=>commands.push(c)')
            for dark in (False,True):
                page.evaluate('(dark)=>document.documentElement.classList.toggle("night-mode",dark)',dark)
                for width in (360,1100):
                    page.set_viewport_size({'width':width,'height':650})
                    page.evaluate(data['nav']);page.evaluate(data['active']);page.evaluate(data['active'])
                    button=page.locator('#incremento-parent-context')
                    expect(button).to_have_count(1)
                    assert button.inner_text()==''
                    assert button.get_attribute('title').endswith(data['title'])
                    assert button.get_attribute('aria-label')=='Parent'
                    assert page.locator('#incremento-study-navigation #incremento-parent-context').count()==1
                    bounds=button.bounding_box()
                    assert bounds['width']==32 and bounds['height']==32
                    assert page.evaluate('document.documentElement.scrollWidth')==width
                    active=button.evaluate('e=>getComputedStyle(e).backgroundColor')
                    button.click();button.focus();page.keyboard.press('Enter')
                    assert page.evaluate('commands.slice(-2)')==['incremento_parent_context:test-token']*2
                    # Background toolbar refreshes must retain the source button and its action.
                    page.evaluate(data['nav'])
                    expect(button).to_be_enabled()
                    assert page.locator('#incremento-study-navigation #incremento-parent-context').count()==1
                    button.click()
                    assert page.evaluate('commands.at(-1)')=='incremento_parent_context:test-token'
                    page.screenshot(path=str(Path(sys.argv[4])/f'parent-toolbar-{dark}-{width}.png'))
                    page.evaluate(data['empty'])
                    expect(button).to_be_visible();expect(button).to_be_disabled()
                    muted=button.evaluate('e=>getComputedStyle(e).backgroundColor')
                    assert muted!=active
                    assert button.bounding_box()['width']==32
                    page.evaluate(data['missing'])
                    expect(button).to_be_disabled()
                    assert 'Deleted topic' in button.get_attribute('title')
                    page.evaluate(data['clear'])
                    expect(button).to_be_visible()
                    assert button.bounding_box()['width']==32
                    page.evaluate(data['active'])
                    expect(button).to_be_enabled()
                    assert page.evaluate('original===document.getElementById("qa")')
                    assert page.locator('input').input_value()=='My answer'
                    assert page.locator('img').count()==0
                    page.screenshot(path=str(Path(sys.argv[4])/f'parent-{dark}-{width}.png'))
                    page.evaluate(data['hidden'])
                    expect(button).to_have_count(0)
                    page.evaluate(data['nav'])
                    expect(button).to_have_count(0)
                    assert page.evaluate('original===document.getElementById("qa")')
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir()/'packages'), runtime[1],
        str(payload), str(tmp_path)], cwd=Path(__file__).resolve().parents[1], env=dict(os.environ),
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
