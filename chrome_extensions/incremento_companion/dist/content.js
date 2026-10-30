import{t as i,ai as Yt,aj as Gt,s as Jt,aL as Qt,y as ce,Y as Se,k as Zt,W as Fe,aJ as en,aH as tn,aI as gt,aM as ht,aN as nn,aO as an,ap as We,aP as Te,h as rn,aB as bt,aQ as on,aR as ln,aS as sn,aT as cn,aU as he,aV as dn,aW as xt,aw as yt,aX as _t,aY as un,aE as wt,aG as pn,aZ as mn,a_ as Et,a$ as fn,b0 as gn,n as hn,g as bn,d as xn}from"./assets/extension-shared.js";const vt="incremento-video-time-toast";function St($=globalThis.document){var Q;(Q=$.getElementById(vt))==null||Q.remove()}function yn($,{action:Q="",request:de,document:F=globalThis.document,requestFrame:Z=globalThis.requestAnimationFrame,schedule:z=globalThis.setTimeout}={}){St(F);const q=Q==="open_shortcut_settings",C=F.createElement("div");if(C.id=vt,C.textContent=String($||""),C.setAttribute("role",q?"alert":"status"),Object.assign(C.style,{position:"fixed",zIndex:2147483647,top:"10px",right:"10px",maxWidth:q?"360px":"320px",padding:"10px 14px",background:"rgba(0, 0, 0, 0.86)",color:"#fff",fontSize:"13px",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"6px",boxShadow:"0 2px 8px rgba(0, 0, 0, 0.4)",opacity:"0",transition:"opacity 0.2s ease",lineHeight:"1.5"}),q){const ee=F.createElement("div");Object.assign(ee.style,{display:"flex",flexWrap:"wrap",gap:"8px",marginTop:"10px"});const R=E=>{const M=F.createElement("button");return M.type="button",M.textContent=E,Object.assign(M.style,{padding:"6px 10px",border:"1px solid #a7b1c2",borderRadius:"4px",background:"#fff",color:"#172033",font:"inherit",cursor:"pointer"}),ee.appendChild(M),M},I=R(i("open_shortcut_settings")),te=R(i("snapshot_warning_dismiss")),K=F.createElement("div");K.setAttribute("role","status"),K.hidden=!0,K.style.marginTop="8px",I.addEventListener("click",async E=>{if(E.stopPropagation(),!(!E.isTrusted||I.disabled)){I.disabled=!0,K.hidden=!0;try{const M=await de({type:"OPEN_SHORTCUT_SETTINGS"});if(M!=null&&M.ok){C.remove();return}}catch{}I.disabled=!1,K.textContent=i("open_shortcuts_failed"),K.hidden=!1}}),te.addEventListener("click",E=>{E.stopPropagation(),C.remove()}),C.appendChild(ee),C.appendChild(K)}return F.documentElement.appendChild(C),Z(()=>{C.style.opacity="1"}),q||z(()=>{C.style.opacity="0",z(()=>C.remove(),220)},2400),C}(()=>{var lt,st,ct,dt;const $="browser-capture-v14",Q="incremento-browser-capture-root",de=window.__incrementoContentScriptState&&typeof window.__incrementoContentScriptState=="object"?window.__incrementoContentScriptState:{};if(de.version===$&&de.ready)return;window.__incrementoContentScriptState={...de,version:$,ready:!1},window.__incrementoContentScriptVersion=$;const F="incremento_browser_capture_settings",Z=50;let z=Zt,q=null,C=null,ee="";const R=e=>{if(!(e!=null&&e.errorCode))return String((e==null?void 0:e.error)||"");const n={...e.errorParams};return n.count!=null&&(n.count=rn(n.count)),i(e.errorCode,n,e.error)};globalThis.__incrementoLastSelectedText=String(globalThis.__incrementoLastSelectedText||"").trim();function I(){var n;const e=String(((n=window.getSelection)==null?void 0:n.call(window).toString())||"").trim();return e?(globalThis.__incrementoLastSelectedText=e,e):String(globalThis.__incrementoLastSelectedText||"").trim()}function te(){var a;if(be())return;const e=(a=window.getSelection)==null?void 0:a.call(window),n=String((e==null?void 0:e.toString())||"").trim();if(n){globalThis.__incrementoLastSelectedText=n;try{const t=ln(e);globalThis.__incrementoLastSelection={...t,url:window.location.href},globalThis.__incrementoSelectionError=""}catch(t){globalThis.__incrementoLastSelection=null,globalThis.__incrementoSelectionError=t.message}}}function K(e){const n=globalThis.__incrementoLastSelection;if(globalThis.__incrementoSelectionError&&!n)throw new Error(i("selected_text_too_large",{count:gt}));return{originalSelectedText:e,selectedHtml:(n==null?void 0:n.selectedText)===e&&(n==null?void 0:n.url)===window.location.href?n.selectedHtml:""}}function E(e,n={}){return yn(e,{...n,request:j})}async function M(){try{const e=await ce.storage.local.get(Se);z=Fe(e==null?void 0:e[Se])}catch{z=Fe(null)}}function Ue(e){var r,o;const n=e instanceof Element?e:(e==null?void 0:e.parentElement)||null,a=(r=n==null?void 0:n.closest)==null?void 0:r.call(n,"a[href]");if(!a)return null;const t=String(a.href||((o=a.getAttribute)==null?void 0:o.call(a,"href"))||"").trim();return bt(t)?a:null}function Ce(e){var r,o,l,s,d,c,m,u,k,A,g,x;if(!e)return null;const n=String(e.href||((r=e.getAttribute)==null?void 0:r.call(e,"href"))||"").trim();if(!bt(n))return null;const t=[...Tt(e,n),(o=e.getAttribute)==null?void 0:o.call(e,"aria-label"),(l=e.getAttribute)==null?void 0:l.call(e,"title"),(c=(d=(s=e.querySelector)==null?void 0:s.call(e,"img[alt]"))==null?void 0:d.getAttribute)==null?void 0:c.call(d,"alt"),(k=(u=(m=e.querySelector)==null?void 0:m.call(e,"[aria-label]"))==null?void 0:u.getAttribute)==null?void 0:k.call(u,"aria-label"),(x=(g=(A=e.querySelector)==null?void 0:A.call(e,"[title]"))==null?void 0:g.getAttribute)==null?void 0:x.call(g,"title"),e.textContent];return{url:n,title:on(t,n)}}function ze(e,n){var a,t,r;n&&e.push((a=n.getAttribute)==null?void 0:a.call(n,"title"),(t=n.getAttribute)==null?void 0:t.call(n,"data-title-no-tooltip"),n.textContent,(r=n.getAttribute)==null?void 0:r.call(n,"aria-label"))}function Tt(e,n){var l,s,d,c;const a=Et(n);if(!a)return[];const t=[],r=((l=e.closest)==null?void 0:l.call(e,["ytd-rich-item-renderer","ytd-video-renderer","ytd-grid-video-renderer","ytd-compact-video-renderer","ytd-playlist-video-renderer","ytd-playlist-panel-video-renderer","ytd-reel-item-renderer","yt-lockup-view-model","ytm-shorts-lockup-view-model","[data-video-id]"].join(", ")))||null,o=r?[r,document]:[document];for(const m of o){const u=m===document?document.links||[]:((s=m.querySelectorAll)==null?void 0:s.call(m,"a[href]"))||[],k=Math.min(Number(u.length)||0,m===document?2e3:200);for(let A=0;A<k;A+=1){const g=u[A];if(g===e)continue;const x=String((g==null?void 0:g.href)||((d=g==null?void 0:g.getAttribute)==null?void 0:d.call(g,"href"))||"").trim();Et(x)===a&&(ze(t,g),ze(t,(c=g.querySelector)==null?void 0:c.call(g,"#video-title, #video-title-link, [data-title-no-tooltip]")))}}return t}function Ct(){let e=document.getElementById("incremento-tracking-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-tracking-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483646,top:"52px",right:"10px",display:"none",alignItems:"center",gap:"8px",padding:"8px 12px",background:"linear-gradient(135deg, rgba(10, 34, 64, 0.94), rgba(17, 83, 126, 0.94))",color:"#fff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",letterSpacing:"0.08em",textTransform:"uppercase",borderRadius:"999px",boxShadow:"0 4px 14px rgba(0, 0, 0, 0.28)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"none"});const n=document.createElement("span");n.textContent="●",Object.assign(n.style,{color:"#53f2a5",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(83, 242, 165, 0.85)"}),e.appendChild(n);const a=document.createElement("span");a.textContent="⚠",Object.assign(a.style,{color:"#ffd166",fontSize:"13px",lineHeight:"1",textShadow:"0 0 8px rgba(255, 209, 102, 0.55)"}),e.appendChild(a);const t=document.createElement("span");return t.id="incremento-tracking-badge-label",t.textContent=i("tracking"),e.appendChild(t),document.documentElement.appendChild(e),e}function X(e,n=""){ee=e?n:"";const a=Ct(),t=document.getElementById("incremento-tracking-badge-label");if(!(!a||!t)){if(!e){a.style.display="none";return}t.textContent=n==="web"?i("tracking_web_card"):i("tracking"),a.style.display="inline-flex"}}function Re(e){const n=Math.max(0,Math.floor(Number(e)||0)),a=Math.floor(n/3600),t=Math.floor(n%3600/60),r=n%60;return a>0?`${a}:${String(t).padStart(2,"0")}:${String(r).padStart(2,"0")}`:`${t}:${String(r).padStart(2,"0")}`}function kt(){let e=document.getElementById("incremento-browser-media-ref-badge");if(e)return e;e=document.createElement("div"),e.id="incremento-browser-media-ref-badge",Object.assign(e.style,{position:"fixed",zIndex:2147483645,top:"96px",right:"10px",display:"none",alignItems:"center",gap:"8px",maxWidth:"320px",padding:"9px 12px",background:"linear-gradient(135deg, rgba(28, 32, 48, 0.96), rgba(34, 62, 96, 0.96))",color:"#eef5ff",fontSize:"12px",fontWeight:"700",fontFamily:"system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",borderRadius:"14px",boxShadow:"0 5px 18px rgba(0, 0, 0, 0.30)",backdropFilter:"blur(6px)",WebkitBackdropFilter:"blur(6px)",pointerEvents:"auto"});const n=document.createElement("span");n.textContent="▶",Object.assign(n.style,{color:"#8fd3ff",fontSize:"11px",lineHeight:"1"}),e.appendChild(n);const a=document.createElement("span");a.id="incremento-browser-media-ref-badge-label",a.textContent="",Object.assign(a.style,{flex:"1 1 auto",minWidth:"0"}),e.appendChild(a);const t=document.createElement("button");return t.type="button",t.textContent="×",t.setAttribute("aria-label",i("saved_time_badge_dismiss")),Object.assign(t.style,{appearance:"none",border:"0",background:"transparent",color:"#a9bfdc",cursor:"pointer",fontSize:"16px",fontWeight:"700",lineHeight:"1",padding:"0 0 0 4px",margin:"0",pointerEvents:"auto"}),t.addEventListener("click",r=>{r.preventDefault(),r.stopPropagation(),_e=!0,e.style.display="none"}),e.appendChild(t),document.documentElement.appendChild(e),e}function ne(e){C=e;const n=kt(),a=document.getElementById("incremento-browser-media-ref-badge-label");if(!n||!a)return;if(!!!(e!=null&&e.hasReference)){n.style.display="none";return}if(_e)return;const r=String((e==null?void 0:e.timeText)||Re(e==null?void 0:e.seconds));a.textContent=r?i("last_saved_time",{time:r}):i("last_saved"),n.style.display="inline-flex"}function ue(){var e;try{return((e=ce)==null?void 0:e.runtime)||null}catch{return null}}Yt(),Gt(),Jt(()=>{var a;const e=document.getElementById("incremento-tracking-badge");Qt(e,()=>X(!0,ee)),C&&ne(C);const n=document.querySelector("#incremento-browser-media-ref-badge button");n==null||n.setAttribute("aria-label",i("saved_time_badge_dismiss")),(a=b==null?void 0:b.refreshLanguage)==null||a.call(b)}),M();try{(ct=(st=(lt=ce)==null?void 0:lt.storage)==null?void 0:st.onChanged)==null||ct.addListener((e,n)=>{var a;n!=="local"||!e||!Object.prototype.hasOwnProperty.call(e,Se)||(z=Fe((a=e[Se])==null?void 0:a.newValue))})}catch{}try{const e=ue();(dt=e==null?void 0:e.onMessage)==null||dt.addListener((n,a,t)=>{var r;if(!n||!n.type)return!1;if(n.type==="SHOW_TOAST")return E(n.text||"",{action:n.action}),t==null||t({ok:!0}),!1;if(n.type==="TRIGGER_BROWSER_CAPTURE"){if(String(n.mode||"").trim().toLowerCase()==="snapshot")return Ne(),t==null||t({ok:!0}),!1;const l=I();return l?(ye({mode:"selection",selectedText:l,snapshots:[]}).then(()=>t==null?void 0:t({ok:!0}),s=>{E((s==null?void 0:s.message)||i("open_capture_failed")),W(),t==null||t({ok:!1,error:String((s==null?void 0:s.message)||"")})}),!0):(E(i("select_page_text")),t==null||t({ok:!1}),!1)}if(n.type==="GET_PAGE_CONTEXT"){const o=en(tn,gt,{includeHtml:n.includeHtml!==!1,htmlScope:n.htmlScope,preserveStyles:n.preserveStyles===!0});return o.ok?(t==null||t(o),!1):(t==null||t({...o,error:R(o)}),!1)}if(n.type==="GET_CONTEXT_LINK_INFO"){const o=String(n.url||"").trim();let l=q;if(o&&String((l==null?void 0:l.url)||"")!==o){let s=null;const d=document.links||[],c=Math.min(Number(d.length)||0,2e3);for(let m=0;m<c;m+=1){const u=d[m];if(String((u==null?void 0:u.href)||((r=u==null?void 0:u.getAttribute)==null?void 0:r.call(u,"href"))||"").trim()===o){s=u;break}}l=Ce(s||null)}return t==null||t({ok:!0,url:String((l==null?void 0:l.url)||""),title:String((l==null?void 0:l.title)||"")}),!1}if(n.type==="GET_CURRENT_MEDIA_CONTEXT")return t==null||t(Xt()),!1;if(n.type==="APPLY_MEDIA_RESUME"){const o=Me(n.seconds);return t==null||t({ok:o}),!1}return n.type==="UPDATE_BROWSER_MEDIA_REF_BADGE"&&(_e=!1,ne(n.reference||null),t==null||t({ok:!0})),!1})}catch{}let b=null,h=null;function j(e){return gn(e,ue())}async function Ke(){const e=await j({type:"LOAD_BROWSER_CAPTURE_META"});if(!(e!=null&&e.ok))throw new Error(String((e==null?void 0:e.error)||i("load_capture_meta_failed")));return e}async function $e(e){const n=await j({type:"SUBMIT_BROWSER_CAPTURE",payload:e});if(!(n!=null&&n.ok))throw new Error(String((n==null?void 0:n.error)||i("failed_submit_capture")));return n}async function At(){const e=await j({type:"CAPTURE_VISIBLE_TAB"});if(!(e!=null&&e.ok)||!(e!=null&&e.dataUrl)){const n=new Error(String((e==null?void 0:e.error)||i("failed_capture_tab")));throw n.code=(e==null?void 0:e.errorCode)||"",n}return e.dataUrl}async function He(e){let n={};try{const a=await ce.storage.local.get(F);n=(a==null?void 0:a[F])||{}}catch{n={}}return sn(n,e)}async function Ve(e){try{await ce.storage.local.set({[F]:{noteTypeName:String((e==null?void 0:e.noteTypeName)||""),deckName:String((e==null?void 0:e.deckName)||""),priority:Number((e==null?void 0:e.priority)??Z),tagsText:String((e==null?void 0:e.tagsText)||""),mappingsByNoteType:(e==null?void 0:e.mappingsByNoteType)||{},linkToPassage:(e==null?void 0:e.linkToPassage)!==!1}})}catch{}}async function qe(e="",n=[]){const a=(h==null?void 0:h.meta)||await Ke();if(!Array.isArray(a==null?void 0:a.noteTypes)||a.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(a==null?void 0:a.deckNames)||a.deckNames.length===0)throw new Error(i("no_decks"));const t=(h==null?void 0:h.form)||await He(a);return h={mode:"snapshot",meta:a,form:t,context:{url:window.location.href||"",title:document.title||"",selectedText:ht("snapshot",e,I()),profileToken:a.profileToken||""},snapshots:Array.isArray(n)?n:[],statusKind:"",statusText:"",submitting:!1},h}async function Nt(e="",n=[]){const a=await qe(e,n),t=xt({...a.context,snapshots:a.snapshots.map(l=>({filename:l.filename,base64:l.base64}))},a.form),r=yt(t);if(!r.ok)throw new Error(i("continue_choose_fields",{error:R(r)}));const o=await $e(t);if(_t(o)==="duplicate")throw new Error(i("capture_duplicate_found"));return await Ve(a.form),o}function Xe(e){const n=e instanceof Element?e:(e==null?void 0:e.parentElement)||null;return n?n.closest("input, textarea, select")?!0:!!n.closest('[contenteditable=""], [contenteditable="true"]'):!1}function be(){return!!b}function Lt(e){return String((e==null?void 0:e.code)||"").toLowerCase()==="keyx"}function ke(e){var t;const n=b==null?void 0:b.shell,a=e==null?void 0:e.target;if(!(!n||!(a instanceof Node)||!n.contains(a))){if(e.type==="keydown"&&((t=b==null?void 0:b.handleTagAutocompleteKeyDown)!=null&&t.call(b,e))){e.stopPropagation();return}if(e.type==="keydown"&&e.key==="Escape"){e.preventDefault(),e.stopPropagation(),W();return}if(e.type==="keydown"&&fn(e,{form:b.form,submitting:h==null?void 0:h.submitting})){e.stopPropagation();return}e.stopPropagation()}}function xe(){if(b)return b;const e=document.createElement("div");e.id=Q,e.style.all="initial";const n=e.attachShadow({mode:"open"});document.documentElement.appendChild(e),n.addEventListener("keydown",ke,!0),n.addEventListener("keypress",ke,!0),n.addEventListener("keyup",ke,!0);const a=document.createElement("style");a.textContent=`
      :host { all: initial; }
      *, *::before, *::after { box-sizing: border-box; }
      .shell {
        position: fixed;
        inset: 0;
        z-index: 2147483645;
        font-family: "Avenir Next", "Segoe UI", sans-serif;
        color: #1f2328;
      }
      .backdrop {
        position: absolute;
        inset: 0;
        background: rgba(12, 18, 26, 0.42);
      }
      .panel {
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        width: min(760px, calc(100vw - 32px));
        max-height: calc(100vh - 32px);
        overflow: auto;
        border-radius: 24px;
        border: 1px solid rgba(90, 74, 47, 0.18);
        background:
          radial-gradient(circle at top left, rgba(255, 219, 161, 0.7), transparent 42%),
          linear-gradient(170deg, rgba(255, 251, 244, 0.98), rgba(245, 236, 223, 0.97));
        box-shadow: 0 28px 80px rgba(22, 23, 25, 0.32);
        padding: 22px;
      }
      .capture-shell {
        position: absolute;
        inset: 0;
        cursor: crosshair;
      }
      .capture-toolbar {
        position: absolute;
        top: 14px;
        left: 50%;
        transform: translateX(-50%);
        display: flex;
        align-items: center;
        gap: 10px;
        min-width: min(860px, calc(100vw - 24px));
        max-width: calc(100vw - 24px);
        padding: 12px 14px;
        border-radius: 18px;
        background: rgba(17, 25, 34, 0.92);
        color: #fff;
        box-shadow: 0 16px 34px rgba(0, 0, 0, 0.3);
      }
      .capture-toolbar strong {
        font-size: 13px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
      }
      .capture-toolbar span {
        font-size: 13px;
        opacity: 0.82;
      }
      .capture-toolbar .spacer {
        flex: 1;
      }
      .toolbar-btn,
      .primary-btn,
      .secondary-btn,
      .ghost-btn {
        border: 0;
        border-radius: 13px;
        padding: 10px 14px;
        font: inherit;
        cursor: pointer;
      }
      .toolbar-btn {
        background: rgba(255, 255, 255, 0.12);
        color: #fff;
      }
      .toolbar-btn.primary {
        background: linear-gradient(135deg, #b86a17, #e0932f);
      }
      .eyebrow {
        margin: 0 0 6px;
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #8f5a1e;
      }
      h2 {
        margin: 0 0 12px;
        font-size: 24px;
        line-height: 1.08;
      }
      .lead, .status, .field-note {
        margin: 0;
        font-size: 13px;
        line-height: 1.45;
        color: #5c5b57;
      }
      .status.error { color: #ab2f2f; }
      .status.success { color: #216c3f; }
      .grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin-top: 16px;
      }
      .field {
        display: flex;
        flex-direction: column;
        gap: 6px;
      }
      .field.full { grid-column: 1 / -1; }
      .field label {
        font-size: 12px;
        font-weight: 700;
        color: #433720;
      }
      .field input,
      .field textarea,
      .field select {
        width: 100%;
        border: 1px solid rgba(82, 68, 45, 0.18);
        border-radius: 13px;
        background: rgba(255, 255, 255, 0.9);
        padding: 11px 12px;
        font: inherit;
        color: inherit;
      }
      .field textarea {
        min-height: 110px;
        resize: vertical;
      }
      .field input[type="range"] {
        padding: 0;
      }
      .tag-autocomplete {
        position: relative;
      }
      .tag-suggestions {
        position: absolute;
        z-index: 10;
        top: calc(100% + 4px);
        right: 0;
        left: 0;
        max-height: 210px;
        overflow-y: auto;
        border: 1px solid rgba(82, 68, 45, 0.18);
        border-radius: 13px;
        background: #fffdf8;
        box-shadow: 0 14px 30px rgba(66, 48, 22, 0.2);
        padding: 4px;
      }
      .tag-suggestions[hidden] { display: none; }
      .tag-suggestions button {
        display: block;
        width: 100%;
        border: 0;
        border-radius: 9px;
        background: transparent;
        padding: 9px 10px;
        color: inherit;
        font: inherit;
        text-align: left;
        cursor: pointer;
      }
      .tag-suggestions button:hover,
      .tag-suggestions button.is-active {
        background: rgba(184, 106, 23, 0.13);
      }
      .field input:focus,
      .field textarea:focus,
      .field select:focus {
        outline: 2px solid rgba(184, 106, 23, 0.2);
        border-color: rgba(184, 106, 23, 0.38);
      }
      .snapshots {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px;
      }
      .snapshot-card {
        overflow: hidden;
        border: 1px solid rgba(82, 68, 45, 0.14);
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.72);
      }
      .snapshot-card img {
        display: block;
        width: 100%;
        height: 108px;
        object-fit: cover;
        background: #e8dfd2;
      }
      .snapshot-footer {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        padding: 8px 10px 10px;
      }
      .snapshot-footer span {
        font-size: 12px;
        color: #4d4b46;
      }
      .snapshot-footer button {
        border: 0;
        border-radius: 10px;
        padding: 6px 8px;
        background: rgba(171, 47, 47, 0.1);
        color: #8f2222;
        font: inherit;
        cursor: pointer;
      }
      .actions {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 10px;
        margin-top: 18px;
      }
      .primary-btn {
        background: linear-gradient(135deg, #9e5d12 0%, #d88219 100%);
        color: #fffdf8;
        font-weight: 700;
      }
      .secondary-btn {
        background: rgba(88, 73, 44, 0.09);
        color: #473a24;
        font-weight: 600;
      }
      .ghost-btn {
        background: rgba(88, 73, 44, 0.08);
        color: #473a24;
      }
      .selection-rect {
        position: absolute;
        border: 2px solid rgba(255, 171, 64, 0.96);
        background: rgba(255, 193, 101, 0.2);
        box-shadow: 0 0 0 1px rgba(20, 20, 20, 0.24), 0 12px 32px rgba(0, 0, 0, 0.16);
      }
      .selection-rect::after {
        content: attr(data-label);
        position: absolute;
        top: -26px;
        left: 0;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(17, 25, 34, 0.9);
        color: #fff;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }
      @media (max-width: 720px) {
        .grid {
          grid-template-columns: 1fr;
        }
        .panel {
          width: calc(100vw - 16px);
          padding: 18px;
        }
        .capture-toolbar {
          flex-wrap: wrap;
          justify-content: center;
        }
        .capture-toolbar .spacer {
          display: none;
        }
      }
    `,n.appendChild(a);const t=document.createElement("div");return t.className="shell",n.appendChild(t),b={host:e,shadow:n,shell:t},b}function W(){var e;(e=b==null?void 0:b.host)!=null&&e.isConnected&&b.host.remove(),b=null,h=null}function je(){const e=xe();e.handleTagAutocompleteKeyDown=null,e.form=null,e.shell.textContent=""}function Mt(e,n,a){const t=document.createElement("div");t.className="tag-autocomplete";const r=document.createElement("input");r.id="incremento-browser-capture-tags",r.type="text",r.value=String(e||""),r.placeholder="tag-one tag-two",r.autocomplete="off",r.spellcheck=!1,r.setAttribute("role","combobox"),r.setAttribute("aria-autocomplete","list");const o=document.createElement("div");o.id="incremento-browser-capture-tag-suggestions",o.className="tag-suggestions",o.setAttribute("role","listbox"),o.hidden=!0,r.setAttribute("aria-controls",o.id),r.setAttribute("aria-expanded","false");const l=hn(n);let s=!1,d=0,c=[];const m=()=>{var g;Array.from(o.children).forEach((x,v)=>{x.classList.toggle("is-active",v===d),x.setAttribute("aria-selected",v===d?"true":"false")}),!o.hidden&&c.length>0?(r.setAttribute("aria-activedescendant",`${o.id}-${d}`),(g=o.children[d])==null||g.scrollIntoView({block:"nearest"})):r.removeAttribute("aria-activedescendant")},u=()=>{const g=r.selectionStart??r.value.length;if(c=bn(l,r.value,g),d=c.length>0?Math.min(d,c.length-1):0,o.textContent="",o.hidden=!s||c.length===0,r.setAttribute("aria-expanded",o.hidden?"false":"true"),o.hidden){m();return}c.forEach((x,v)=>{const p=document.createElement("button");p.id=`${o.id}-${v}`,p.type="button",p.setAttribute("role","option"),p.setAttribute("aria-selected",v===d?"true":"false"),p.className=v===d?"is-active":"",p.textContent=x,p.addEventListener("mouseenter",()=>{d=v,m()}),p.addEventListener("mousedown",S=>{S.preventDefault(),k(x)}),o.appendChild(p)}),m()},k=g=>{const x=xn(r.value,g,r.selectionStart??r.value.length,r.selectionEnd??r.value.length);r.value=x.value,a(x.value),s=!1,d=0,r.focus(),r.setSelectionRange(x.cursor,x.cursor),u()},A=g=>{if(g.target!==r)return!1;if(g.key==="Escape"&&s)return g.preventDefault(),s=!1,u(),!0;if(!c.length)return!1;if(g.key==="ArrowDown"||g.key==="ArrowUp"){g.preventDefault();const x=g.key==="ArrowDown"?1:-1;if(!s)s=!0,d=x>0?0:c.length-1;else return d=(d+x+c.length)%c.length,m(),!0;return u(),!0}return s&&(g.key==="Enter"||g.key==="Tab")?(g.preventDefault(),k(c[d]),!0):!1};return r.addEventListener("input",()=>{a(r.value),d=0,s=!0,u()}),r.addEventListener("focus",()=>{s=!0,u()}),r.addEventListener("click",()=>{d=0,s=!0,u()}),r.addEventListener("select",u),r.addEventListener("blur",()=>{s=!1,u()}),t.appendChild(r),t.appendChild(o),{element:t,handleKeyDown:A}}function Bt(e,n){const a=document.createElement("div");a.className="snapshots";for(const t of n){const r=document.createElement("div");r.className="snapshot-card";const o=document.createElement("img");o.src=t.dataUrl,o.alt=t.filename,r.appendChild(o);const l=document.createElement("div");l.className="snapshot-footer";const s=document.createElement("span");s.textContent=t.filename,l.appendChild(s);const d=document.createElement("button");d.type="button",d.textContent=i("remove"),d.addEventListener("click",()=>{h.snapshots=h.snapshots.filter(c=>c.id!==t.id),H()}),l.appendChild(d),r.appendChild(l),a.appendChild(r)}return a}async function H(){var mt;const e=xe(),{shell:n,shadow:a}=e;e.refreshLanguage=()=>{H()};const t=h;je();const r=document.createElement("div");r.className="backdrop",r.addEventListener("click",()=>W()),n.appendChild(r);const o=document.createElement("section");o.className="panel",o.setAttribute("role","dialog"),o.setAttribute("aria-modal","true"),o.setAttribute("aria-labelledby","incremento-capture-title"),n.appendChild(o);const l=document.createElement("p");l.className="eyebrow",l.textContent=t.mode==="snapshot"?i("browser_snapshot"):i("browser_selection"),o.appendChild(l);const s=document.createElement("h2");s.id="incremento-capture-title",s.textContent=i("send_capture_anki"),o.appendChild(s);const d=document.createElement("p");d.className="lead",d.textContent=t.mode==="snapshot"?We("snapshots_ready",t.snapshots.length,{url:t.context.url}):i("selected_text_from",{url:t.context.url}),o.appendChild(d);const c=document.createElement("form");c.noValidate=!0,e.form=c;const m=document.createElement("div");m.className="grid",c.appendChild(m);const u=(f,y,w=!1,N="")=>{const _=document.createElement("div");_.className=`field${w?" full":""}`;const D=document.createElement("label");D.textContent=f;const se=y.matches("input,textarea,select,button")?y:y.querySelector("input,textarea,select,button")||y,ft=se.id||`incremento-capture-field-${m.children.length}`;if(se.id=ft,D.htmlFor=ft,_.appendChild(D),_.appendChild(y),N){const De=document.createElement("p");De.className="field-note",De.textContent=N,_.appendChild(De)}return _},k=document.createElement("select");for(const f of t.meta.noteTypes){const y=document.createElement("option");y.value=f.name,y.textContent=f.name,k.appendChild(y)}k.value=t.form.noteTypeName,k.addEventListener("change",()=>{var w;const f=t.meta.noteTypes.find(N=>N.name===k.value),y=cn((w=t.form.mappingsByNoteType)==null?void 0:w[k.value],(f==null?void 0:f.fields)||[]);t.form=he(t.form,k.value,y),H()}),m.appendChild(u(i("note_type"),k));const A=document.createElement("select");for(const f of t.meta.deckNames){const y=document.createElement("option");y.value=f,y.textContent=f,A.appendChild(y)}A.value=t.form.deckName,A.addEventListener("change",()=>{t.form.deckName=A.value}),m.appendChild(u(i("deck"),A));const g=Mt(t.form.tagsText,t.meta.tagNames,f=>{t.form.tagsText=f});b.handleTagAutocompleteKeyDown=g.handleKeyDown,m.appendChild(u(i("tags"),g.element,!0,i("tag_hint")));const x=document.createElement("div");x.style.display="grid",x.style.gridTemplateColumns="1fr auto",x.style.gap="10px",x.style.alignItems="center";const v=document.createElement("input");v.type="range",v.min="0",v.max="100",v.step="0.1",v.value=String(t.form.priority??Z);const p=document.createElement("input");p.type="number",p.setAttribute("aria-label",i("priority")),p.min="0",p.max="100",p.step="0.1",p.style.width="92px",p.value=String(t.form.priority??Z);const S=f=>{const y=Number(f),w=Number.isFinite(y)?Math.min(100,Math.max(0,y)):Z;t.form.priority=Number(w.toFixed(4)),v.value=String(t.form.priority),p.value=String(t.form.priority)};v.addEventListener("input",()=>S(v.value)),p.addEventListener("change",()=>S(p.value)),x.appendChild(v),x.appendChild(p),m.appendChild(u(i("priority"),x));const P=["",...((mt=t.meta.noteTypes.find(f=>f.name===t.form.noteTypeName))==null?void 0:mt.fields)||[]],O=(f,y)=>{const w=document.createElement("select");for(const N of P){const _=document.createElement("option");_.value=N,_.textContent=N||i("do_not_insert"),w.appendChild(_)}return w.value=P.includes(f)?f:"",w.addEventListener("change",()=>{y(w.value)}),w},Y=!!t.context.selectedText;m.appendChild(u(i("page_title_field"),O(t.form.fieldMappings.titleField,f=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,titleField:f})}),!1,i("page_title_field_note"))),m.appendChild(u(i("selected_text_field"),O(t.form.fieldMappings.selectedTextField,f=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,selectedTextField:f})}),!1,Y?i("chars_ready",{count:t.context.selectedText.length}):i("no_text_added"))),m.appendChild(u(i("source_url_field"),O(t.form.fieldMappings.urlField,f=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,urlField:f})}),!1,i("source_url_note"))),m.appendChild(u(i("snapshot_field"),O(t.form.fieldMappings.snapshotField,f=>{t.form=he(t.form,t.form.noteTypeName,{...t.form.fieldMappings,snapshotField:f})}),!0,t.snapshots.length>0?We("snapshots_selected",t.snapshots.length):i("no_snapshots")));const B=document.createElement("input");B.type="text",B.maxLength=1e3,B.value=t.context.title,B.addEventListener("input",()=>{t.context.title=B.value}),m.appendChild(u(i("capture_edit_title"),B,!0));const L=document.createElement("input");L.type="checkbox",L.checked=t.form.linkToPassage!==!1,L.style.width="auto",L.addEventListener("change",()=>{t.form.linkToPassage=L.checked}),m.appendChild(u(i("capture_link_passage"),L,!0,i("capture_passage_hint")));const me=document.createElement("textarea");if(me.value=t.context.selectedText,me.placeholder=t.mode==="snapshot"?i("add_text_snapshots"):i("selected_text_edit"),me.addEventListener("input",()=>{t.context.selectedText=me.value}),m.appendChild(u(t.mode==="snapshot"?i("text_to_add"):i("selected_text"),me,!0,i("inserted_text_note"))),t.snapshots.length>0){const f=document.createElement("div");f.className="field full";const y=document.createElement("label");y.textContent=i("snapshots"),f.appendChild(y),f.appendChild(Bt(a,t.snapshots)),m.appendChild(f)}const U=document.createElement("section");if(U.dataset.capturePreview="true",U.tabIndex=-1,U.setAttribute("aria-label",i("capture_field_preview")),U.hidden=!t.preview,t.preview){const f=document.createElement("h3");f.textContent=i("capture_field_preview"),U.appendChild(f);const y=document.createElement("p");y.className="field-note",y.textContent=i(t.preview.uniqueTitle?"capture_preview_unique_title":"capture_preview_hint"),U.appendChild(y);const w=document.createElement("iframe");w.title=i("capture_field_preview"),w.setAttribute("sandbox",""),w.setAttribute("referrerpolicy","no-referrer"),w.srcdoc=dn(t.preview.fields),w.style.cssText="width:100%;height:300px;border:1px solid #d6cbb9;border-radius:12px;background:white",U.appendChild(w);const N=document.createElement("a");try{const _=new URL(t.preview.sourceLink);if(!/^https?:$/.test(_.protocol)||_.username||_.password)throw new Error;N.href=_.href,N.target="_blank",N.rel="noopener noreferrer",N.textContent=i("capture_source_link",{title:t.preview.sourceTitle}),U.appendChild(N)}catch{}}c.appendChild(U);const G=document.createElement("div");G.hidden=!t.duplicate,G.setAttribute("role","status");const ut=document.createElement("p");ut.textContent=i("capture_duplicate_found"),G.appendChild(ut);const re=document.createElement("button");re.dataset.captureOpenExisting="true",re.type="button",re.className="secondary-btn",re.textContent=i("capture_open_existing"),re.addEventListener("click",()=>void ve("open_existing")),G.appendChild(re);const fe=document.createElement("button");fe.type="button",fe.className="secondary-btn",fe.textContent=i("capture_create_another"),fe.addEventListener("click",()=>void ve("create",!0)),G.appendChild(fe),c.appendChild(G);const pt=()=>{t.preview=null,t.duplicate=null,U.hidden=!0,G.hidden=!0};c.addEventListener("input",pt),c.addEventListener("change",pt);const ge=document.createElement("p");ge.setAttribute("role","status"),ge.setAttribute("aria-live","polite"),ge.className=`status${t.statusKind?` ${t.statusKind}`:""}`,ge.textContent=t.statusValidation?R(t.statusValidation):t.statusCode?i(t.statusCode):t.statusText,c.appendChild(ge);const oe=document.createElement("div");if(oe.className="actions",t.snapshots.length>0){const f=document.createElement("button");f.type="button",f.className="ghost-btn",f.textContent=i("capture_more"),f.addEventListener("click",()=>Ne(t.snapshots)),oe.appendChild(f)}const ie=document.createElement("button");ie.type="button",ie.className="secondary-btn",ie.textContent=i("capture_preview"),ie.disabled=!!t.submitting,ie.addEventListener("click",()=>void ve("preview")),oe.appendChild(ie);const le=document.createElement("button");le.type="button",le.className="secondary-btn",le.textContent=i("language_cancel"),le.addEventListener("click",()=>W()),oe.appendChild(le);const J=document.createElement("button");J.type="submit",J.setAttribute("aria-keyshortcuts","Enter"),J.className="primary-btn",J.textContent=t.submitting?i("saving"):i("create_note"),J.disabled=!!t.submitting,oe.appendChild(J),c.appendChild(oe);async function ve(f="create",y=!1){if(t.submitting)return;S(p.value);const w=xt({...t.context,snapshots:t.snapshots.map(_=>({filename:_.filename,base64:_.base64}))},t.form);w.action=f,w.allowDuplicate=y;const N=yt(w);if(!N.ok){t.statusKind="error",t.statusCode="",t.statusValidation=N,t.statusText=R(N),H();return}t.submitting=!0,t.statusKind="",t.statusValidation=null,t.statusCode=f==="preview"?"capture_preview_loading":f==="open_existing"?"capture_opening_existing":"creating_note",t.statusText=i(t.statusCode),H();try{const _=await $e(w);if(h!==t||!b)return;const D=_t(_);if(D==="preview"||D==="duplicate"){t.submitting=!1,t.statusCode="",t.statusText="",t.preview=D==="preview"?_:null,t.duplicate=D==="preview"?_.duplicate:_,await H();const se=b==null?void 0:b.shadow.querySelector(D==="preview"?"[data-capture-preview]":"[data-capture-open-existing]");se==null||se.focus();return}if(D==="error")throw new Error(i("create_note_failed"));if(await Ve(t.form),h!==t||!b)return;E(D==="opened"?i("capture_existing_opened"):i("created_note",{type:_.noteTypeName,deck:_.deckName})),W()}catch(_){if(h!==t||!b)return;t.submitting=!1,t.statusKind="error",t.statusValidation=null,t.statusCode="",t.statusText=(_==null?void 0:_.message)||i("create_note_failed"),H()}}if(c.addEventListener("submit",f=>{f.preventDefault(),ve()}),t.submitting){for(const f of c.querySelectorAll("input,select,textarea,button"))f.disabled=!0;le.disabled=!1}o.appendChild(c),un(e,J)}function It(e){return new Promise((n,a)=>{const t=new Image;t.onload=()=>n(t),t.onerror=()=>a(new Error(i("failed_decode_screenshot"))),t.src=e})}async function Pt(e,n){const a=await It(e),t=a.width/window.innerWidth,r=a.height/window.innerHeight,o=Math.max(0,Math.round(n.x*t)),l=Math.max(0,Math.round(n.y*r)),s=Math.max(1,Math.round(n.width*t)),d=Math.max(1,Math.round(n.height*r)),c=document.createElement("canvas");return c.width=s,c.height=d,c.getContext("2d").drawImage(a,o,l,s,d,0,0,s,d),c.toDataURL("image/png")}function Ot(e){const n=String(e||""),a=n.indexOf(",");return a>=0?n.slice(a+1):n}function Ae(e){const n=Math.abs(e.width),a=Math.abs(e.height);return{x:e.width>=0?e.x:e.x-n,y:e.height>=0?e.y:e.y-a,width:n,height:a}}function Ye(e=2){return new Promise(n=>{const a=Math.max(1,Number(e)||1);let t=0;const r=()=>{if(t+=1,t>=a){n();return}requestAnimationFrame(r)};requestAnimationFrame(r)})}function Dt(e,n){if(!(e instanceof Element))return!1;const a=window.getComputedStyle(e),t=n==="x"?a.overflowX:a.overflowY;return/(auto|scroll|overlay)/.test(String(t||""))?n==="x"?e.scrollWidth>e.clientWidth:e.scrollHeight>e.clientHeight:!1}function Ge(e,n){let a=e instanceof Element?e:null;for(;a;){if(Dt(a,n))return a;a=a.parentElement}const t=document.scrollingElement;return t instanceof Element?t:document.documentElement}function Ft(e,n){var c;if(!e)return;const a=((c=n==null?void 0:n.style)==null?void 0:c.pointerEvents)||"";n!=null&&n.style&&(n.style.pointerEvents="none");let t=null;try{t=document.elementFromPoint(e.clientX,e.clientY)}finally{n!=null&&n.style&&(n.style.pointerEvents=a)}const r=Number(e.deltaX)||0,o=Number(e.deltaY)||0,l=r?Ge(t,"x"):null,s=o?Ge(t,"y"):null,d=document.scrollingElement instanceof Element?document.scrollingElement:document.documentElement;r&&(l||d).scrollBy({left:r,top:0,behavior:"auto"}),o&&(s||d).scrollBy({left:0,top:o,behavior:"auto"})}async function Wt(e,n=[]){if(n.length>=Te)throw new Error(i("too_many_snapshots",{count:Te}));const a=xe();St(),a.shell.style.display="none";try{await Ye(2);const t=await At(),r=wt(t,{maxBytes:pn});if(!r.ok)throw new Error(R(r));const o=Ae(e),l=await Pt(t,o),s=wt(l,{maxBytes:mn});if(!s.ok)throw new Error(R(s));return{id:`${Date.now()}-${n.length}-${Math.random().toString(16).slice(2,8)}`,filename:`browser-capture-${n.length+1}.png`,dataUrl:l,base64:Ot(l)}}finally{b!=null&&b.shell&&(b.shell.style.display="",await Ye(1))}}function Ne(e=[]){var v;const n=xe();je();const a=e.length>0&&((v=h==null?void 0:h.context)==null?void 0:v.selectedText)||"";h={mode:"snapshot",meta:(h==null?void 0:h.meta)||null,form:(h==null?void 0:h.form)||null,context:{url:window.location.href||"",title:document.title||"",selectedText:a},snapshots:[...e],statusKind:"",statusText:"",submitting:!1};const t=n.shell,r=document.createElement("div");r.className="capture-shell",t.appendChild(r);const o=document.createElement("div");o.className="capture-toolbar";const l=p=>{o.replaceChildren();const S=document.createElement("strong");S.textContent=i("snapshot_mode"),o.appendChild(S);const T=document.createElement("span");T.textContent=i(p),o.appendChild(T);const P=document.createElement("span");P.className="spacer",o.appendChild(P)};l("snapshot_mode_intro"),t.appendChild(o);const s=[...e];let d=null,c=null,m=!1;const u=()=>{l("snapshot_mode_hint");const p=document.createElement("span");p.textContent=m?i("capturing"):We("snapshot_ready",s.length),o.appendChild(p);const S=document.createElement("button");S.type="button",S.className="toolbar-btn",S.textContent=i("undo"),S.disabled=m||s.length===0,S.addEventListener("click",()=>{s.pop(),u()}),o.appendChild(S);const T=document.createElement("button");T.type="button",T.className="toolbar-btn",T.textContent=i("clear"),T.disabled=m||s.length===0,T.addEventListener("click",()=>{s.splice(0,s.length),u()}),o.appendChild(T);const P=document.createElement("button");P.type="button",P.className="toolbar-btn",P.textContent=i("language_cancel"),P.addEventListener("click",()=>W()),o.appendChild(P);const O=document.createElement("button");O.type="button",O.className="toolbar-btn",O.textContent=i("extract_now"),O.disabled=m||s.length===0,O.addEventListener("click",async()=>{var B;if(!m){if(!s.length){E(i("draw_region_first"));return}m=!0,u();try{const L=await Nt(((B=h==null?void 0:h.context)==null?void 0:B.selectedText)||"",[...s]);E(i("created_note",{type:L.noteTypeName,deck:L.deckName})),W()}catch(L){m=!1,u(),E((L==null?void 0:L.message)||i("create_note_failed"))}}}),o.appendChild(O);const Y=document.createElement("button");Y.type="button",Y.className="toolbar-btn primary",Y.textContent=i("continue"),Y.addEventListener("click",()=>{var B;if(!m){if(!s.length){E(i("draw_region_first"));return}ye({mode:"snapshot",selectedText:((B=h==null?void 0:h.context)==null?void 0:B.selectedText)||"",snapshots:[...s]})}}),o.appendChild(Y)};n.refreshLanguage=u;const k=(p,S)=>{if(s.length>=Te){E(i("too_many_snapshots",{count:Te}));return}c={x:p,y:S,width:0,height:0},d=document.createElement("div"),d.className="selection-rect",d.dataset.label=i("capture_label",{count:s.length+1}),r.appendChild(d)},A=()=>{if(!d||!c)return;const p=Ae(c);Object.assign(d.style,{left:`${p.x}px`,top:`${p.y}px`,width:`${p.width}px`,height:`${p.height}px`})};r.addEventListener("pointerdown",p=>{m||p.button!==0||p.target!==r||(p.preventDefault(),k(p.clientX,p.clientY),A())}),r.addEventListener("pointermove",p=>{c&&(p.preventDefault(),c.width=p.clientX-c.x,c.height=p.clientY-c.y,A())});const g=p=>{c||m||(p.preventDefault(),Ft(p,n.host))};r.addEventListener("wheel",g,{passive:!1}),o.addEventListener("wheel",g,{passive:!1});const x=async()=>{if(!d||!c)return;const p=Ae(c),S=d;if(p.width>=24&&p.height>=24){m=!0,u();try{const T=await Wt(p,s);s.push(T)}catch(T){E((T==null?void 0:T.message)||i("failed_capture_tab"),{action:(T==null?void 0:T.code)==="snapshot_permission_required"?"open_shortcut_settings":""})}}else S.remove();S.remove(),d=null,c=null,m=!1,u()};r.addEventListener("pointerup",()=>{x()}),r.addEventListener("pointercancel",()=>{x()}),u()}async function ye({mode:e,selectedText:n="",snapshots:a=[]}){te();const t=e==="snapshot"?{}:K(n||I());if(e==="snapshot")await qe(n,a);else{const r=(h==null?void 0:h.meta)||await Ke();if(!Array.isArray(r==null?void 0:r.noteTypes)||r.noteTypes.length===0)throw new Error(i("no_note_types"));if(!Array.isArray(r==null?void 0:r.deckNames)||r.deckNames.length===0)throw new Error(i("no_decks"));const o=(h==null?void 0:h.form)||await He(r);h={mode:e,meta:r,form:o,context:{url:window.location.href||"",title:document.title||"",selectedText:ht(e,n,I()),...t,profileToken:r.profileToken||""},snapshots:Array.isArray(a)?a:[],statusKind:"",statusText:"",submitting:!1}}await H()}globalThis.__incrementoTriggerBrowserCapture=e=>{if(String(e||"").trim().toLowerCase()==="snapshot")return Ne(),{ok:!0};const a=I();return a?(ye({mode:"selection",selectedText:a,snapshots:[]}).catch(t=>{E((t==null?void 0:t.message)||i("open_capture_failed")),W()}),{ok:!0}):(E(i("select_page_text")),{ok:!1,error:i("select_page_text")})},document.addEventListener("keydown",e=>{if(!e.altKey||!Lt(e)||be()||Xe(e.target))return;if(e.metaKey){e.preventDefault(),e.stopPropagation(),nn(j,E).catch(()=>{E(i("snapshot_shortcut_unassigned"),{action:"open_shortcut_settings"})});return}if(e.ctrlKey||e.shiftKey)return;const n=I();n&&(e.preventDefault(),e.stopPropagation(),ye({mode:"selection",selectedText:n,snapshots:[]}).catch(a=>{E((a==null?void 0:a.message)||i("open_capture_failed")),W()}))},!0),document.addEventListener("contextmenu",e=>{const n=Ue(e.target);q=Ce(n)},!0),document.addEventListener("click",e=>{if(!z.modifierClickEnabled||e.defaultPrevented||Number(e.button)!==0||be()||Xe(e.target))return;const n=Ue(e.target);if(!n||!an(e,z))return;const a=Ce(n);if(!a)return;z.navigateAfterSave||e.preventDefault();const t=ue();t==null||t.sendMessage({type:"SAVE_CLICKED_LINK_AS_WEBPAGE",url:a.url,title:a.title,sourcePageUrl:window.location.href||"",sourcePageTitle:document.title||""},r=>{var o,l;(l=(o=ce)==null?void 0:o.runtime)==null||l.lastError})},!0),document.addEventListener("selectionchange",te,!0),document.addEventListener("mouseup",te,!0),document.addEventListener("keyup",te,!0),document.addEventListener("keydown",e=>{e.key==="Escape"&&be()&&(e.preventDefault(),e.stopPropagation(),W())},!0);function Ut(e){try{const n=new URL(e),a=n.searchParams.get("v");if(a)return a;const t=n.pathname.split("/").filter(Boolean);if(n.hostname==="youtu.be"&&t[0])return t[0];if((t[0]==="shorts"||t[0]==="live"||t[0]==="embed")&&t[1])return t[1]}catch{}return""}function zt(e){const n=String(e||"").match(/(?:\/video\/|\/)(\d{5,})(?:[/?#]|$)/);return n?n[1]:""}function Rt(){const e=window.location.href||"",n=window.location.hostname||"";return n.includes("youtube.com")||n==="youtu.be"?{provider:"youtube",videoId:Ut(e)}:n.includes("vimeo.com")?{provider:"vimeo",videoId:zt(e)}:{provider:"",videoId:""}}function Je(e){try{const a=new URL(e).searchParams.get("inc_card_id")||"",t=Number(a);if(Number.isFinite(t)&&t>0)return Math.floor(t)}catch{}return 0}function Kt(e){const n=String(e||"").replace(/^#/,"").trim();if(!n)return"";const t=n.indexOf("__incremento_resume__=1");return t<0?n:n.slice(0,t).replace(/[&?]+$/,"")}function $t(e){try{const n=new URL(e);n.searchParams.delete("inc_card_id"),n.searchParams.delete("inc_track_web"),n.searchParams.delete("inc_resume_sec"),n.searchParams.delete("inc_resume_media");const a=Kt(n.hash);return n.hash=a?`#${a}`:"",n.toString()}catch{return String(e||"")}}function Ht(e){try{const n=new URL(e),a=String(n.searchParams.get("inc_track_web")||"").trim().toLowerCase();return a==="1"||a==="true"||a==="yes"||a==="on"}catch{return!1}}function Vt(){if(window.top!==window)return;const e=window.location.href||"";if(!e||!/inc_(card_id|track_web|resume_sec|resume_media)|__incremento_resume__=1/.test(e))return;const n=$t(e);if(!(!n||n===e))try{history.replaceState(history.state,document.title||"",n),Pe=n}catch{}}let Le=null;function Qe(){let e=null,n=0;!Le&&typeof document.getElementsByTagName=="function"&&(Le=document.getElementsByTagName("video"));for(const a of Le||document.querySelectorAll("video")){const t=(a.videoWidth||0)*(a.videoHeight||0);(e===null||t>n)&&(e=a,n=t)}return e}function Me(e,n=12){const a=Math.max(0,Math.floor(Number(e)||0));if(a<=0)return!1;const t=Qe();if(!t)return n>0&&window.setTimeout(()=>Me(a,n-1),500),!1;try{return t.currentTime=a,E(i("resumed_to",{seconds:a})),!0}catch{return n>0&&window.setTimeout(()=>Me(a,n-1),500),!1}}function pe(){var l,s;const e=window.location.href||"",{provider:n,videoId:a}=Rt(),t=Qe(),r=n?e:String((t==null?void 0:t.currentSrc)||(t==null?void 0:t.src)||"").trim(),o=String(((l=t==null?void 0:t.getAttribute)==null?void 0:l.call(t,"title"))||((s=t==null?void 0:t.getAttribute)==null?void 0:s.call(t,"aria-label"))||document.title||"").trim();return{provider:n,videoId:a,video:t,mediaUrl:r,mediaTitle:o}}function qt(e=null){const{provider:n,video:a}=e||pe();let t=-1,r=!1;if(a&&(t=Math.max(0,Math.floor(Number(a.currentTime)||0)),r=!0),n==="youtube"&&t<=0){const o=Ie();o>=0&&(t=o,r=!0)}if(n==="vimeo"&&t<=0){const o=Be();o>=0&&(t=o,r=!0)}return{found:r,seconds:r?Math.max(0,t):0}}function Xt(){const e=window.location.href||"",n=pe(),{provider:a,videoId:t,mediaUrl:r,mediaTitle:o}=n,l=qt(n);return{ok:!0,pageUrl:e,pageTitle:document.title||"",provider:a,videoId:t,mediaUrl:r,mediaTitle:o,hasDetectedTime:!!l.found,seconds:Math.max(0,Math.floor(Number(l.seconds)||0)),timeText:l.found?Re(l.seconds):""}}function Ze(e){const n=String(e||"").trim();if(!n)return-1;const a=n.split(":").map(t=>t.trim());return a.every(t=>/^\d+$/.test(t))?a.length===2?Number(a[0])*60+Number(a[1]):a.length===3?Number(a[0])*3600+Number(a[1])*60+Number(a[2]):-1:-1}function Be(){const e=Array.from(document.querySelectorAll('[data-progress-bar-timecode="true"], [class*="Timecode_module_timecode__"]'));for(const n of e){const a=String((n==null?void 0:n.textContent)||"").trim(),t=Ze(a);if(t>=0)return t}return-1}function Ie(){const e=Array.from(document.querySelectorAll(".ytp-time-current, [class*='ytp-time-current']"));for(const n of e){const a=String((n==null?void 0:n.textContent)||"").trim(),t=Ze(a);if(t>=0)return t}return-1}async function et(){try{const e=await j({type:"GET_LINKED_CARD_CONTEXT",url:window.location.href||""});if(!(e!=null&&e.linked)||Number(e.cardId)<=0){ne(null);return}const n=await j({type:"LOAD_BROWSER_MEDIA_REF"});if(!(n!=null&&n.ok)||!(n!=null&&n.hasReference)){ne(null);return}ne(n)}catch{ne(null)}}let tt=-1,nt=0,at=-1,rt=0,_e=!1,ae=!0,we=null,Pe=window.location.href||"";function Ee(){ae=!1,we!==null&&(clearInterval(we),we=null)}function ot(e){if(!ae)return!1;try{const n=ue();return n!=null&&n.id?(n.sendMessage(e,()=>{try{const a=n==null?void 0:n.lastError;a&&/context invalidated/i.test(String(a.message||""))&&Ee()}catch{Ee()}}),!0):(Ee(),!1)}catch{return Ee(),!1}}function it(){if(!ae){X(!1);return}try{const e=ue();if(!(e!=null&&e.id)){X(!1);return}e.sendMessage({type:"GET_TRACKING_STATUS",url:window.location.href||""},n=>{try{if(e==null?void 0:e.lastError){X(!1);return}}catch{X(!1);return}X(!!(n!=null&&n.tracked),String((n==null?void 0:n.mode)||""))})}catch{X(!1)}}function Oe(e=!1,n=!1,a=null){if(!ae)return;const{provider:t,videoId:r,video:o}=a||pe();if(!t)return;let l=-1;if(o&&(l=Math.max(0,Math.floor(Number(o.currentTime)||0))),t==="youtube"&&l<=0){const d=Ie();d>=0&&(l=d)}if(t==="vimeo"&&l<=0){const d=Be();d>=0&&(l=d)}if(l<0)return;const s=Date.now();!e&&l===tt&&s-nt<4e3||(tt=l,nt=s,ot({type:"heartbeat",provider:t,videoId:r,cardId:Je(window.location.href||""),flush:!!n,seconds:l,url:window.location.href||"",title:document.title||""}))}function jt(e=!1,n=!1,a=null){if(!ae)return;const t=window.location.href||"",{provider:r,videoId:o,video:l,mediaUrl:s,mediaTitle:d}=a||pe();if(!l&&!r)return;let c=-1;if(l&&(c=Math.max(0,Math.floor(Number(l.currentTime)||0))),r==="youtube"&&c<=0){const u=Ie();u>=0&&(c=u)}if(r==="vimeo"&&c<=0){const u=Be();u>=0&&(c=u)}if(c<0)return;const m=Date.now();!e&&c===at&&m-rt<4e3||(at=c,rt=m,ot({type:"web_media_heartbeat",provider:r,videoId:o,cardId:Je(t),trackEnabled:Ht(t),flush:!!n,seconds:c,url:t,mediaUrl:s,mediaTitle:d,title:document.title||""}))}function V(e=!1,n=!1){if(!ae)return;const a=pe();Oe(e,n,a),jt(e,n,a)}we=window.setInterval(()=>{document.visibilityState!=="hidden"&&V(!1,!1)},1e3),window.setInterval(()=>{const e=window.location.href||"";e!==Pe&&(Pe=e,_e=!1,it(),et())},750),window.addEventListener("pagehide",()=>{V(!0,!0)},{capture:!0}),window.addEventListener("beforeunload",()=>{V(!0,!0)},{capture:!0}),document.addEventListener("visibilitychange",()=>{document.visibilityState==="hidden"?V(!0,!0):V(!0,!1)}),document.addEventListener("timeupdate",()=>{V(!1,!1)},!0),document.addEventListener("play",()=>{V(!0,!1)},!0),document.addEventListener("pause",()=>{V(!0,!0)},!0),document.addEventListener("ended",()=>Oe(!0,!0),!0),window.setTimeout(()=>Oe(!0,!1),1200),window.setTimeout(Vt,1200),window.setTimeout(it,300),window.setTimeout(()=>{et()},320),window.__incrementoContentScriptState={...window.__incrementoContentScriptState||{},version:$,ready:!0}})();
