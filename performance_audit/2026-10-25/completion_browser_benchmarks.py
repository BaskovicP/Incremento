"""Measure PDF Find observer work in an isolated, offline headless browser."""

import argparse
import json
import importlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "6a371c732fc6c7d65bb4468fdb5853a2926ec097"
sys.path.insert(0, str(ROOT))
_browser = importlib.import_module("backend.webpage_browser")
browser_runtime, _runtime_dir = _browser.browser_runtime, _browser._runtime_dir

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
runtime = browser_runtime()
if runtime is None:
    raise RuntimeError("This benchmark requires the explicitly installed optional browser runtime")
fixtures = []
for stage in ("before", "after"):
    source = (
        subprocess.check_output(["git", "show", f"{BASELINE}:frontend/src/PdfViewer.jsx"], cwd=ROOT, text=True)
        if stage == "before"
        else (ROOT / "frontend/src/PdfViewer.jsx").read_text()
    )
    styles = source[source.index("function clearSearchHitStyles(") : source.index("function findExcerptSpanMatch(")]
    if stage == "before":
        observe = """function observeSearchText(target, {render, clear}) {
          let frame=0;
          render();
          const observer=new MutationObserver(()=>{if(frame)cancelAnimationFrame(frame);frame=requestAnimationFrame(render);});
          observer.observe(target,{childList:true,subtree:true,characterData:true});
          return ()=>{if(frame)cancelAnimationFrame(frame);observer.disconnect();clear();};
        }"""
    else:
        observe = (ROOT / "frontend/src/pdfSearchObserver.mjs").read_text().replace("export function", "function")
    fixtures.append(
        {"stage": stage, "source": "function escapeHtml(text) {return String(text);}\n" + styles + "\n" + observe}
    )
script = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from playwright.sync_api import sync_playwright
fixtures=json.loads(sys.stdin.read())
results={}
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=sys.argv[2],headless=True,chromium_sandbox=True)
    for fixture in fixtures:
        page=browser.new_page()
        page.set_content('<div id="layer">'+'<span>alpha beta</span>'*1000+'</div>')
        page.add_script_tag(content=fixture['source'])
        results[fixture['stage']]=page.evaluate("""async ()=>{
          let renders=0, work=0;
          const target=document.getElementById('layer');
          const stop=observeSearchText(target,{render(){const start=performance.now();renders++;applySearchHitStyles(target,'alpha');work+=performance.now()-start;},clear(){clearSearchHitStyles(target);}});
          target.appendChild(Object.assign(document.createElement('span'),{textContent:'alpha external'}));
          for(let i=0;i<10;i++)await new Promise(requestAnimationFrame);
          const measured={render_callbacks:renders,highlight_work_ms:work,matched_fragments:target.querySelectorAll('[data-inc-search-fragment="1"]').length};
          stop(); return measured;
        }""")
        page.close()
    browser.close()
print(json.dumps(results))
'''
run = subprocess.run(
    [runtime[0], "-I", "-c", script, str(_runtime_dir() / "packages"), runtime[1]],
    input=json.dumps(fixtures),
    cwd=ROOT,
    capture_output=True,
    text=True,
    timeout=45,
)
if run.returncode:
    raise RuntimeError(run.stdout + run.stderr)
result = {
    "baseline_commit": BASELINE,
    "F16_find": json.loads(run.stdout.splitlines()[-1]),
    "scope": "1000 text spans plus one external update; 10 animation frames; actual production style functions and equivalent observer lifecycle; one browser sample",
}
assert result["F16_find"]["after"]["matched_fragments"] == 1001
assert result["F16_find"]["after"]["render_callbacks"] == 2
args.output.write_text(json.dumps(result, indent=2) + "\n")
