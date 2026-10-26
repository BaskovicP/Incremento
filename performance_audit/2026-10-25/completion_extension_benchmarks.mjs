// Synthetic models/SSR and actual committed bundle graphs; no user tabs or data.
import {readFileSync, writeFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
import {React, renderToString, loadJsx} from '../../chrome_extensions/incremento_companion/tests/reactHarness.js';
import * as model from '../../chrome_extensions/incremento_companion/src/bookmarks/bookmarkModel.js';

const root = fileURLToPath(new URL('../../', import.meta.url));
const baseline = '6a371c732fc6c7d65bb4468fdb5853a2926ec097';
const output = process.argv[2];
if (!output) throw new Error('Pass the output JSON path');
const prefix = 'chrome_extensions/incremento_companion/';
function source(file, stage) {
  return stage === 'before' ? execFileSync('git', ['show', `${baseline}:${path.relative(root, file)}`], {cwd: root, encoding:'utf8'}) : readFileSync(file, 'utf8');
}
function samples(work) {
  const values = [];
  for (let i=0;i<3;i++) { const start=performance.now(); work(); values.push(+(performance.now()-start).toFixed(3)); }
  return {median_ms: [...values].sort((a,b)=>a-b)[1], samples_ms: values};
}
const leaves=Array.from({length:10000}, (_,i)=>({id:`leaf-${i}`, title:`Bookmark ${i}`, url:'https://example.test/'}));
const tree=[{id:'root', title:'Folder', children:leaves}];
const items=model.buildBookmarkItems(tree);
for (const item of Object.values(items)) item.selected=true;
const index=model.buildBookmarkTreeIndex(tree), selectionPrefix=model.bookmarkSelectionPrefix(index, items);
const result={baseline_commit:baseline,node:process.version,scope:'Synthetic Node SSR, actual content module, static dependency bytes; no browser end-to-end latency claim.'};
result.F09_folder_counts={bookmarks:leaves.length, repeated_reads:1000,
  before:samples(()=>{for(let i=0;i<1000;i++) model.countSelected(model.collectBookmarkIds(tree[0], items),items);}),
  after_warm:samples(()=>{for(let i=0;i<1000;i++){const [a,b]=index.ranges.get('root'); if(selectionPrefix[b]-selectionPrefix[a]!==10000)throw Error('count');}}),
  after_cold_index:samples(()=>model.buildBookmarkTreeIndex(tree))};
result.F18_ssr={};
for (const stage of ['before','after']) {
  const load=file=>source(file,stage);
  const {BookmarkTree}=await loadJsx(path.join(root,prefix,'src/bookmarks/components/BookmarkTree.jsx'),load);
  const {ImportRows}=await loadJsx(path.join(root,prefix,'src/bookmarks/components/ImportRows.jsx'),load);
  let html='';
  const folder=()=>{html=renderToString(React.createElement(BookmarkTree,{nodes:tree,itemsById:items,treeIndex:index,selectionPrefix}));};
  const rows=()=>{html=renderToString(React.createElement(ImportRows,{items:Object.values(items)}));};
  result.F18_ssr[stage]={closed_folder:samples(folder)};
  folder(); result.F18_ssr[stage].closed_folder.checkboxes=(html.match(/type="checkbox"/g)||[]).length;
  result.F18_ssr[stage].import_rows=samples(rows);
  rows(); result.F18_ssr[stage].import_rows.mounted_rows=(html.match(/<article /g)||[]).length;
}
const staticImport=/\b(?:import|export)(?:\s*\{[^}]*\}\s*from\s*|\s*\*\s*as\s*\w+\s*from\s*|\s+[\w$]+\s*(?:,\s*\{[^}]*\}\s*)?from\s*|\s*)["'](\.[^"']+)["']/g;
result.F20_static_graph={};
for(const entry of ['background.js','content.js','offscreen.js']) {
  result.F20_static_graph[entry]={};
  for(const stage of ['before','after']) {
    const todo=[path.join(root,prefix,'dist',entry)], seen=new Set(); let bytes=0;
    while(todo.length){const file=todo.pop();if(seen.has(file))continue;seen.add(file);const code=source(file,stage);bytes+=Buffer.byteLength(code);todo.push(...[...code.matchAll(staticImport)].map(m=>path.resolve(path.dirname(file),m[1])));}
    result.F20_static_graph[entry][stage]={bytes,files:[...seen].map(file=>path.relative(root,file))};
  }
}

result.F21_media_sampling={};
for(const stage of ['before','after']) {
  const intervals=new Map(),events=new Map();let scans=0,messages=0;
  const videos=Array.from({length:50},(_,i)=>({videoWidth:640+i,videoHeight:360,currentTime:19,paused:false,getAttribute:()=> 'Synthetic'}));
  globalThis.document={title:'Synthetic',visibilityState:'visible',querySelector:()=>null,
    getElementsByTagName:()=>{scans++;return videos;},querySelectorAll:selector=>{if(selector==='video'){scans++;return [...videos];}return [];},
    addEventListener:(name,callback)=>events.set(name,callback),getElementById:()=>null,createElement:()=>({style:{},setAttribute(){},remove(){}}),documentElement:{appendChild(){}}};
  globalThis.window={location:new URL('https://www.youtube.com/watch?v=abc123DEF45'),getSelection:()=>({toString:()=>'',rangeCount:0}),addEventListener(){},setTimeout(){},setInterval:(fn,delay)=>intervals.set(delay,fn)};
  globalThis.requestAnimationFrame=fn=>fn();
  globalThis.chrome={i18n:{getUILanguage:()=> 'en'},storage:{local:{get:async()=>({ui_language:'en'})},onChanged:{addListener(){}}},runtime:{id:'synthetic',onMessage:{addListener(){}},sendMessage(message,callback){messages++;callback?.({ok:true});}}};
  const file=path.join(root,prefix,'src/content/main.js');
  const code=source(file,stage).replace(/from\s*["'](\.[^"']+)["']/g,(_,spec)=>`from ${JSON.stringify(pathToFileURL(path.resolve(path.dirname(file),spec)).href)}`);
  await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const tick=intervals.get(1000);
  const oneTick=()=>{videos.at(-1).currentTime++;tick();};
  const time=samples(()=>{for(let i=0;i<1000;i++)oneTick();});
  scans=messages=0;
  for(let i=0;i<1000;i++)oneTick();
  const visible={...time,video_dom_queries:scans,protocol_messages:messages};
  document.visibilityState='hidden'; events.get('visibilitychange')?.(); scans=messages=0;
  for(let i=0;i<1000;i++)oneTick();
  result.F21_media_sampling[stage]={videos:50,ticks:1000,visible,hidden:{video_dom_queries:scans,protocol_messages:messages}};
  delete globalThis.window;
}
writeFileSync(output,JSON.stringify(result,null,2)+'\n');
