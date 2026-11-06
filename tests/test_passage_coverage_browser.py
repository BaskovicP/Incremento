"""Exercise the shipped viewer and generated EPUB script with synthetic documents."""
import json
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


def run_browser(script, *args):
    from webpage_browser import browser_runtime, _runtime_dir
    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional isolated browser runtime is not installed')
    result = subprocess.run([runtime[0], '-I', '-c', dedent(script), str(_runtime_dir() / 'packages'),
        runtime[1], *map(str, args)], cwd=Path(__file__).resolve().parents[1], env=dict(os.environ),
        capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('side', [False, True], ids=['main', 'reference'])
def test_pdf_selection_links_reveal_the_exact_repeated_phrase_and_report_only_displayed_pages(side):
    run_browser(r"""
        import json, sys
        from pathlib import Path
        from urllib.parse import urlsplit
        sys.path.insert(0, sys.argv[1])
        import pymupdf
        from playwright.sync_api import sync_playwright, expect
        with pymupdf.open() as pdf:
            page = pdf.new_page(width=600, height=1100)
            page.insert_text((40,100), 'First context. Same phrase. First ending.', fontsize=16)
            page.insert_text((40,900), 'Second context. Same phrase. Second ending.', fontsize=16)
            pdf.new_page().insert_text((40,100), 'Unvisited middle page')
            pdf.new_page().insert_text((40,100), 'Last page')
            document = pdf.tobytes()
        root = Path.cwd()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width':1000,'height':800})
            page.set_default_timeout(6000)
            assets = {f'/web/{name}':root/'web'/name for name in
                ('pdf_dock.html','dist/pdf_viewer.js','pdfjs/pdf.min.js','pdfjs/pdf.worker.min.js')}
            def respond(route):
                path = urlsplit(route.request.url).path
                if path == '/fixture.pdf': route.fulfill(body=document, content_type='application/pdf')
                elif path in assets: route.fulfill(body=assets[path].read_bytes(),
                    content_type='text/html' if path.endswith('.html') else 'text/javascript')
                else: route.abort()
            page.route('**/*',respond)
            side = sys.argv[3] == 'True'
            page.goto('http://incremento.test/web/pdf_dock.html' + ('?reference=reader' if side else ''))
            page.wait_for_function('() => typeof window.'+('incrementoReferenceStart' if side else 'incrementoPdfStart')+' === "function"')
            page.evaluate('''({side}) => {
                window.testCommands=[]; window.pycmd=message=>testCommands.push(message);
                const config={card_id:7,filename:'fixture.pdf',page:1,max_page:3,zoom:1,
                    worker:'/web/pdfjs/pdf.worker.min.js',url:'/fixture.pdf',locale:'en'};
                if (side) window.incrementoReferenceStart(config);
                else {window._pdfWorkerSrc=config.worker; window._pdfFileUrl=config.url;
                    window.incrementoPdfStart(7,'fixture.pdf',1,1);}
            }''',{'side':side})
            page.wait_for_function("() => document.querySelector('#pdf-text-layer')?.textContent.includes('Second context')")
            page.wait_for_function("() => testCommands.some(c=>c.startsWith('incremento_reader_coverage:'))")
            page.evaluate('incrementoReceiveCoverage({viewed_percent:66.7,marked_percent:33.3})')
            expect(page.get_by_text('Read to here 0%',exact=True)).to_be_visible()
            expect(page.locator('[data-reader-coverage]')).to_contain_text('Viewed 66.7% · Marked read 33.3%')
            page.evaluate('''() => {
                const walker=document.createTreeWalker(document.querySelector('#pdf-text-layer'),NodeFilter.SHOW_TEXT);
                const nodes=[];while(walker.nextNode()) nodes.push(walker.currentNode);
                const text=nodes.map(node=>node.textContent).join(''),start=text.lastIndexOf('Same phrase.');
                if(start<0) throw new Error('Synthetic passage missing: '+text);
                let offset=0,a=null,b=null;
                for(const node of nodes) {
                    const end=offset+node.textContent.length;
                    if(a===null && start>=offset && start<end) a=[node,start-offset];
                    if(start+12>offset && start+12<=end) b=[node,start+12-offset];
                    offset=end;
                }
                const range=document.createRange();range.setStart(...a);range.setEnd(...b);
                const selection=getSelection();selection.removeAllRanges();selection.addRange(range);
                a[0].parentElement.scrollIntoView({block:'center'});
            }''')
            assert page.evaluate('getSelection().toString()') == 'Same phrase.'
            page.get_by_role('button',name='Page links',exact=True).click()
            page.get_by_role('button',name='Link this page…',exact=True).click()
            message = page.evaluate("testCommands.filter(c=>c.startsWith('incremento_pdf_page_links:')).map(c=>JSON.parse(c.split(':').slice(1).join(':'))).find(c=>c.operation==='create')")
            assert message['passage']['quote'] == 'Same phrase.', message
            assert 'Second context.' in message['passage']['prefix'], message
            assert message['passage']['rects'][0][1] > .7
            page.evaluate('''passage=>{getSelection().removeAllRanges();scrollTo(0,0);
                incrementoRevealPdfExcerpt({cardId:7,page:1,passage});}''',message['passage'])
            cue=page.locator('[data-inc-excerpt-reveal]')
            expect(cue.first).to_be_visible()
            page.wait_for_function("() => Math.abs(document.querySelector('[data-inc-excerpt-reveal]').getBoundingClientRect().top-innerHeight/2)<250")
            assert page.evaluate("document.querySelector('[data-inc-excerpt-reveal]').offsetTop") > 600
            page.keyboard.press('Escape')
            expect(cue).to_have_count(0)
            page.evaluate('incrementoPdfNav(2)')
            page.wait_for_function("() => testCommands.some(c=>c.startsWith('incremento_reader_coverage:')&&JSON.parse(c.split(':').slice(1).join(':')).end===3)")
            viewed=page.evaluate("testCommands.filter(c=>c.startsWith('incremento_reader_coverage:')).map(c=>JSON.parse(c.split(':').slice(1).join(':')).end)")
            assert set(viewed) == {1,3}, viewed
            assert page.evaluate("document.querySelectorAll('[data-inc-excerpt-reveal]').length") == 0
            browser.close()
    """, side)


@pytest.mark.parametrize('track', [True, False], ids=['reader', 'destination-picker'])
def test_epub_reveal_preserves_text_and_coverage_survives_reflow_without_marking_a_whole_section(tmp_path, track):
    import ast
    source = Path('frontend/epub_dock.py')
    tree = ast.parse(source.read_text())
    constants = {'_PYCMD_BRIDGE', '_EPUB_HIGHLIGHT_COLORS', '_MAX_EPUB_SELECTION_CHARS'}
    namespace = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id in constants}
    messages = json.loads(Path('frontend/src/locales/en.json').read_text())
    namespace.update(json=json, _current_sections=lambda: [], normalize_highlight_color=lambda value: value,
        configured_highlight_when_extracting=lambda: False, get_locale=lambda: 'en',
        t=lambda key, **values: messages.get(key,key), __name__='frontend.epub_dock', __package__='frontend')
    builder = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_build_page_script')
    exec(compile(ast.Module(body=[builder],type_ignores=[]),str(source),'exec'),namespace)
    text = 'First paragraph. ' + 'Long text for viewport coverage. ' * 500 + ' Exact destination passage. Ending.'
    start = text.index('Exact destination passage.')
    passage = dict(quote='Exact destination passage.', start=start, end=start+26)
    script = namespace['_build_page_script'](card_id=7, section_index=0, scroll_ratio=0,
        text_scale=1, read_anchor=None, focus_offset=-1, search_query='', highlights=[], bridge_nonce='test',
        sections=[dict(text=text)], passage=passage, track_coverage=track)
    fixture = tmp_path / 'fixture.json'
    fixture.write_text(json.dumps(dict(script=script,text=text,passage=passage)))
    run_browser(r"""
        import json, sys
        from pathlib import Path
        sys.path.insert(0,sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        fixture=json.loads(Path(sys.argv[3]).read_text())
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=sys.argv[2],headless=True,chromium_sandbox=True)
            page=browser.new_page(viewport={'width':700,'height':600})
            page.set_default_timeout(6000)
            page.route('**/*',lambda route:route.fulfill(body='<html><body><p id="passage"></p></body></html>',content_type='text/html'))
            page.goto('http://incremento.test/chapter.html')
            page.evaluate('(text)=>document.querySelector("p").textContent=text',fixture['text'])
            messages=[]
            page.on('console',lambda message:messages.append(message.text))
            page.evaluate(fixture['script'])
            cue=page.locator('[data-inc-passage-reveal]')
            expect(cue.first).to_be_visible()
            assert page.locator('#passage').text_content() == fixture['text']
            assert page.locator('.incremento-epub-highlight').count() == 0
            location=page.evaluate('incrementoEpubCurrentLocation()')
            assert 0 < location['coverage']['end']-location['coverage']['start'] < len(fixture['text'])/2,location
            page.evaluate('''anchor=>{const node=document.querySelector('p').firstChild,range=document.createRange();
                range.setStart(node,anchor.start);range.setEnd(node,anchor.end);
                getSelection().removeAllRanges();getSelection().addRange(range);}''',fixture['passage'])
            before=page.evaluate('incrementoEpubCurrentLocation().passage')
            page.evaluate('incrementoSetEpubTextScale(1.7)')
            page.set_viewport_size({'width':450,'height':600})
            after=page.evaluate('incrementoEpubCurrentLocation().passage')
            assert before == after and before['quote'] == fixture['passage']['quote']
            # Deterministically request another report through a visibility event.
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            coverage=[message for message in messages if 'incremento_reader_coverage:' in message]
            assert bool(coverage) == (sys.argv[4]=='True'),coverage
            page.keyboard.press('Escape')
            expect(cue).to_have_count(0)
            assert page.locator('#passage').text_content() == fixture['text']
            browser.close()
    """, fixture, track)
