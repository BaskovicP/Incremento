"""Exercise real reader palettes in a headless browser using synthetic content."""
import ast
import json
import os
from pathlib import Path
import subprocess
from textwrap import dedent

import pytest


def epub_script():
    source = Path(__file__).resolve().parents[1] / 'frontend/epub_dock.py'
    tree = ast.parse(source.read_text())
    constants = {'_PYCMD_BRIDGE', '_EPUB_HIGHLIGHT_COLORS', '_MAX_EPUB_SELECTION_CHARS'}
    namespace = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                 if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                 and node.targets[0].id in constants}
    messages = json.loads((source.parent / 'src/locales/en.json').read_text())
    namespace.update(json=json, _current_sections=lambda: [{'text': 'Synthetic passage'}],
                     normalize_highlight_color=lambda value: value,
                     configured_highlight_when_extracting=lambda: False,
                     get_locale=lambda: 'en', t=lambda key, **kwargs: messages.get(key, key))
    builder = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                   and node.name == '_build_page_script')
    exec(compile(ast.Module(body=[builder], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['_build_page_script'](card_id=42, section_index=0, scroll_ratio=0,
        text_scale=1, read_anchor=None, focus_offset=-1, search_query='', bridge_nonce='synthetic',
        highlights=[dict(id='saved', sectionIndex=0, color='blue', note='Keep note',
                         text='Synthetic passage', startOffset=0, endOffset=17)])


@pytest.mark.parametrize('reader', ['pdf', 'epub'])
def test_six_style_palette_marks_text_without_reflow_or_losing_note_and_range(tmp_path, reader):
    from webpage_browser import browser_runtime, _runtime_dir

    runtime = browser_runtime()
    if runtime is None:
        pytest.skip('Optional browser runtime is unavailable')
    fixture = tmp_path / 'epub-script.json'
    fixture.write_text(json.dumps(epub_script()))
    script = dedent(r'''
        import json, sys
        from pathlib import Path
        from urllib.parse import urlsplit
        sys.path.insert(0, sys.argv[1])
        from playwright.sync_api import sync_playwright, expect
        import pymupdf
        root = Path.cwd()
        reader = sys.argv[3]
        with pymupdf.open() as pdf:
            p = pdf.new_page(width=600, height=900)
            p.insert_text((40,100), 'Synthetic passage', fontsize=18)
            r = p.search_for('Synthetic passage')[0]
            data = pdf.tobytes()
            mark = dict(id='saved', page=1, color='blue', note='Keep note', text='Synthetic passage',
                rects=[dict(x=r.x0,y=r.y0,w=r.width,h=r.height)])
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=sys.argv[2], headless=True, chromium_sandbox=True)
            page = browser.new_page(viewport={'width': 350,'height': 700})
            page.set_default_timeout(5000)
            assets = {f'/web/{n}': root/'web'/n for n in ('pdf_dock.html','dist/pdf_viewer.js',
                'pdfjs/pdf.min.js','pdfjs/pdf.worker.min.js')}
            def route(request):
                path = urlsplit(request.request.url).path
                if path == '/fixture.pdf': request.fulfill(body=data,content_type='application/pdf')
                elif path in assets: request.fulfill(body=assets[path].read_bytes(),
                    content_type='text/html' if path.endswith('.html') else 'text/javascript')
                else: request.abort()
            page.route('**/*',route)
            if reader == 'pdf':
                page.goto('http://incremento.test/web/pdf_dock.html')
                page.wait_for_function('typeof window.incrementoPdfStart === "function"')
                page.evaluate("""mark => {
                    window.testCommands=[]; window.pycmd=c=>testCommands.push(c);
                    window._pdfWorkerSrc='http://incremento.test/web/pdfjs/pdf.worker.min.js';
                    window._pdfFileUrl='http://incremento.test/fixture.pdf'; window._incPdfHighlights=[mark];
                    window.incrementoPdfStart(42,'fixture.pdf',1,1);
                }""",mark)
                text=page.locator('#pdf-text-layer span').filter(has_text='Synthetic passage')
                expect(text).to_be_visible()
                box = text.bounding_box()
                page.mouse.click(box['x'] + 8, box['y'] + 8)
            else:
                page.set_content('<html><body><p id="passage">Synthetic passage with more words.</p></body></html>')
                page.evaluate("window.testCommands=[]; console.log=c=>{if(typeof c==='string')testCommands.push(c)}")
                page.evaluate(json.loads(Path(sys.argv[4]).read_text()))
                page.locator('.incremento-epub-highlight').click()
                page.get_by_role('button',name='Style',exact=True).click()
            popup=page.get_by_role('dialog',name='Annotation appearance',exact=True)
            expect(popup).to_be_visible()
            for label,style,kind in [('Underline','underline','Underline'),('Squiggly','squiggly','Squiggly'),
                ('Dashed','dashed','Underline'),('Dotted','dotted','Underline'),
                ('Strikethrough','strikeout','StrikeOut'),('Highlight','highlight','Highlight')]:
                popup.get_by_role('button',name=label,exact=True).click()
                expect(popup.get_by_role('button',name=label,exact=True)).to_have_attribute('aria-pressed','true')
                if reader=='pdf':
                    update=page.evaluate("testCommands.filter(c=>c.startsWith('incremento_pdf_hl_update:')).at(-1)")
                    saved=json.loads(update.split(':',1)[1])['highlight']
                    assert saved['pdf_annotation']['kind']==kind
                    assert saved['pdf_annotation']['incremento_style']==style
                    assert saved['note']=='Keep note' and saved['rects']==mark['rects'] and saved['color']=='blue'
                    rect=page.locator('[data-annotation-style]').first
                    assert rect.get_attribute('data-annotation-style')==style
                else:
                    nodes=page.locator('.incremento-epub-highlight')
                    expect(nodes.first).to_have_attribute('data-style',style)
                    assert page.locator('p').count()==1
                    assert nodes.first.get_attribute('data-note')=='Keep note'
                    css=nodes.first.evaluate('n=>({line:getComputedStyle(n).textDecorationLine,style:getComputedStyle(n).textDecorationStyle})')
                    if style!='highlight':
                        assert css['line']==('line-through' if style=='strikeout' else 'underline')
                        assert css['style']==('wavy' if style=='squiggly' else style if style in ['dashed','dotted'] else 'solid')
            box=popup.bounding_box()
            assert box['x']>=0 and box['x']+box['width']<=350
            assert box['y']>=0 and box['y']+box['height']<=700
            page.screenshot(path=str(Path(sys.argv[4]).parent/(reader+'-annotation-styles.png')))
            popup.screenshot(path=str(Path(sys.argv[4]).parent/(reader+'-annotation-palette.png')))
            page.keyboard.press('Escape')
            expect(popup).not_to_be_visible()
            if reader == 'pdf':
                page.get_by_role('button',name='Annotate',exact=True).click()
                page.get_by_role('combobox',name='Style',exact=True).select_option('squiggly')
                page.evaluate("""() => {
                    const n=document.querySelector('#pdf-text-layer span').firstChild;
                    const r=document.createRange(); r.selectNodeContents(n);
                    window.getSelection().removeAllRanges(); window.getSelection().addRange(r);
                }""")
                page.get_by_role('button',name='Mark selection',exact=True).click()
                command=page.evaluate("testCommands.filter(c=>c.startsWith('incremento_pdf_hl_add:')).at(-1)")
                created=json.loads(command.split(':',1)[1])['highlight']
                assert created['pdf_annotation']['kind']=='Squiggly'
                assert created['pdf_annotation']['incremento_style']=='squiggly'
                assert created['text']=='Synthetic passage'
            else:
                page.evaluate("""() => {
                    window.incrementoSetEpubAnnotationStyle('squiggly');
                    const walker=document.createTreeWalker(document.getElementById('passage'),NodeFilter.SHOW_TEXT);
                    const nodes=[]; while(walker.nextNode()) {
                        if (walker.currentNode.nodeValue.length) nodes.push(walker.currentNode);
                    }
                    const r=document.createRange(); r.setStart(nodes[0],0);
                    r.setEnd(nodes.at(-1),nodes.at(-1).length);
                    window.getSelection().removeAllRanges(); window.getSelection().addRange(r);
                }""")
                assert page.evaluate('window.incrementoAddEpubHighlight()') is True
                command=page.evaluate("testCommands.filter(c=>c.includes('incremento_epub_hl_add:')).at(-1)")
                created=json.loads(command.split('incremento_epub_hl_add:',1)[1])['highlight']
                assert created['style']=='squiggly'
                assert created['text']=='Synthetic passage with more words.'
            browser.close()
    ''')
    result = subprocess.run([runtime[0], '-I', '-c', script, str(_runtime_dir() / 'packages'),
                             runtime[1], reader, str(fixture)], cwd=Path(__file__).resolve().parents[1],
                            env=dict(os.environ), capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
